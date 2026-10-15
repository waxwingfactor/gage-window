"""Regression tests for boundaries found by the independent code review.

Inputs are constructed. Most checks exercise the CLI; the resource test also
patches the rendering entry point to prove rejection occurs before rendering.
"""

import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gage_window import core


class ReviewBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gage-window-review-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def cli(self, *args):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        return subprocess.run(
            [sys.executable, "-m", "gage_window", *map(str, args)],
            cwd=self.base, env=env, text=True, encoding="utf-8",
            capture_output=True, timeout=30,
        )

    def assert_exit(self, result, expected):
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def project(self, rows, headers=None, windows=None):
        headers = headers or ["gage", "work", "when"]
        with (self.base / "uses.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(rows)
        project = {
            "schema_version": 1,
            "gages": ["G-1"], "aliases": {},
            "windows": windows or [{
                "id": "review-window", "gage_id": "G-1",
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-02-01T00:00:00Z",
                "reason": "Constructed boundary test",
            }],
            "sources": [{
                "name": "constructed export", "path": "uses.csv", "kind": "direct",
                "columns": {"gage_id": "gage", "work_id": "work", "start": "when"},
            }],
        }
        path = self.base / "project.json"
        path.write_text(json.dumps(project), encoding="utf-8")
        return path

    def analyze(self, config, name="report", expected=0):
        out = self.base / name
        self.assert_exit(self.cli("analyze", config, "--out", out), expected)
        return out

    @staticmethod
    def read_worksheet(path):
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            return reader.fieldnames, list(reader)

    @staticmethod
    def write_worksheet(path, headers, rows):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

    def test_one_case_with_61_records_accepts_untouched_generated_worksheet(self):
        config = self.project([["G-1", "WORK-A", "2026-01-11"]] * 61)
        report = self.analyze(config)
        _, rows = self.read_worksheet(report / "cases.csv")
        self.assertEqual(len(rows), 1)
        self.assertGreater(len(rows[0]["record_ids"]), 4096)
        self.assertEqual(len(json.loads(rows[0]["record_ids"])), 61)
        reviewed = self.base / "reviewed"
        self.assert_exit(self.cli("review", report, "--decisions", report / "cases.csv", "--out", reviewed), 2)
        self.assert_exit(self.cli("verify", reviewed), 0)

    def test_aggregate_identity_larger_than_default_csv_field_limit_roundtrips(self):
        config = self.project([["G-1", "WORK-A", "2026-01-11"]] * 2000)
        report = self.analyze(config)
        analysis = json.loads((report / "analysis.json").read_text(encoding="utf-8"))
        self.assertEqual(len(analysis["cases"][0]["record_ids"]), 2000)
        self.assertGreater(len(json.dumps(analysis["cases"][0]["record_ids"])), 128 * 1024)
        reviewed = self.base / "reviewed"
        self.assert_exit(self.cli("review", report, "--decisions", report / "cases.csv", "--out", reviewed), 2)
        self.assert_exit(self.cli("verify", reviewed), 0)

    def test_maximum_escaped_work_ids_roundtrip_without_truncation(self):
        work_ids = ["=" + "x" * 4095, "'" + "y" * 4095]
        config = self.project([["G-1", work, "2026-01-11"] for work in work_ids])
        report = self.analyze(config)
        analysis = json.loads((report / "analysis.json").read_text(encoding="utf-8"))
        self.assertEqual({case["work_id"] for case in analysis["cases"]}, set(work_ids))
        _, rows = self.read_worksheet(report / "cases.csv")
        self.assertEqual({len(row["work_id"]) for row in rows}, {4097})
        reviewed = self.base / "reviewed"
        self.assert_exit(self.cli("review", report, "--decisions", report / "cases.csv", "--out", reviewed), 2)
        self.assert_exit(self.cli("verify", reviewed), 0)

    def test_aggregate_window_identity_can_exceed_source_cell_limit(self):
        windows = [{
            "id": str(index) + "w" * 4095, "gage_id": "G-1",
            "start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z",
            "reason": "Constructed overlapping review window",
        } for index in range(2)]
        config = self.project([["G-1", "A", "2026-01-11"]], windows=windows)
        report = self.analyze(config)
        _, rows = self.read_worksheet(report / "cases.csv")
        self.assertGreater(len(rows[0]["window_ids"]), 4096)
        reviewed = self.base / "reviewed"
        self.assert_exit(self.cli("review", report, "--decisions", report / "cases.csv", "--out", reviewed), 2)
        self.assert_exit(self.cli("verify", reviewed), 0)

    def test_editable_length_limit_applies_after_csv_safety_decoding(self):
        report = self.analyze(self.project([["G-1", "A", "2026-01-11"]]))
        headers, rows = self.read_worksheet(report / "cases.csv")
        owner = "=" + "x" * 4095
        rows[0].update(status="reviewed", owner="'" + owner,
                       rationale="Human-reviewed constructed record", evidence="TEST-1")
        decisions = self.base / "edited.csv"
        self.write_worksheet(decisions, headers, rows)
        reviewed = self.base / "reviewed"
        self.assert_exit(self.cli("review", report, "--decisions", decisions, "--out", reviewed), 0)
        self.assert_exit(self.cli("verify", reviewed), 0)
        _, output_rows = self.read_worksheet(reviewed / "decisions.csv")
        self.assertEqual(output_rows[0]["owner"], "'" + owner)
        rows[0]["owner"] = "x" * 4097
        self.write_worksheet(decisions, headers, rows)
        rejected = self.base / "too-long"
        self.assert_exit(self.cli("review", report, "--decisions", decisions, "--out", rejected), 1)
        self.assertFalse(rejected.exists())

    def test_surplus_cells_do_not_replace_an_original_reserved_looking_header(self):
        config = self.project(
            [["G-1", "A", "2026-01-11", "original value", "surplus one", "surplus two"]],
            headers=["gage", "work", "when", "__extra_cells__"],
        )
        report = self.analyze(config, expected=2)
        analysis = json.loads((report / "analysis.json").read_text(encoding="utf-8"))
        record = analysis["records"][0]
        self.assertEqual(record["classification"], "unresolved")
        self.assertEqual(record["raw"]["__extra_cells__"], "original value")
        self.assertEqual(record["extra_cells"], ["surplus one", "surplus two"])
        with (report / "records.csv").open(encoding="utf-8", newline="") as stream:
            flat = next(csv.DictReader(stream))
        self.assertEqual(json.loads(flat["raw"])["__extra_cells__"], "original value")
        self.assertEqual(json.loads(flat["extra_cells"]), ["surplus one", "surplus two"])
        self.assertIn("original value", (report / "report.html").read_text(encoding="utf-8"))
        self.assert_exit(self.cli("verify", report), 0)

    def test_header_expansion_rejected_before_render_or_publication(self):
        headers = ["gage", "work", "when"] + [f"{index:03}" + "h" * 1021 for index in range(125)]
        config = self.project([["G-1", "A", "2026-01-11"] + [""] * 125] * 100, headers=headers)
        self.assertLess((self.base / "uses.csv").stat().st_size, 20 * 1024 * 1024)
        output = self.base / "rejected"
        with mock.patch.object(core, "make_files", side_effect=AssertionError("rendering must not start")) as build:
            with self.assertRaisesRegex(core.InputError, "Expanded row evidence exceeds 8 MiB"):
                core.analyze(config, output)
            build.assert_not_called()
        self.assertFalse(output.exists())
        self.assert_exit(self.cli("analyze", config, "--out", output), 1)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.base.glob(".gage-window-*")))


if __name__ == "__main__":
    unittest.main()
