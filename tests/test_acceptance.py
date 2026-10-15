"""Independent, black-box acceptance tests for the published v1 contract.

These tests deliberately use only the command line and its machine-readable
artifacts.  They do not import the implementation or duplicate its interval
algorithm.  All examples are constructed; none represent a shop investigation.
"""

import copy
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CLIAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gage-window-acceptance-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.counter = 0

    def cli(self, *args):
        env = dict(os.environ)
        if env.get("GAGE_WINDOW_INSTALLED") == "1":
            env.pop("PYTHONPATH", None)
            env.pop("PYTHONHOME", None)
        else:
            env["PYTHONPATH"] = str(ROOT / "src")
        return subprocess.run(
            [sys.executable, "-m", "gage_window", *map(str, args)],
            cwd=self.base,
            env=env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=30,
        )

    def assert_exit(self, result, expected):
        self.assertEqual(
            result.returncode,
            expected,
            f"stdout={result.stdout}\nstderr={result.stderr}",
        )

    def project(self, rows, *, kind="direct", windows=None, extra=None):
        self.counter += 1
        directory = self.base / f"project-{self.counter}"
        directory.mkdir()
        source = directory / "uses.csv"
        with source.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["tool", "job", "began", "ended", "reference", "note"])
            writer.writerows(rows)
        project = {
            "schema_version": 1,
            "gages": ["G-1", "G-2"],
            "aliases": {"serial-1": "G-1"},
            "windows": windows if windows is not None else [{
                "id": "event-1",
                "gage_id": "G-1",
                "start": "2026-01-10T12:00:00Z",
                "end": "2026-01-12T12:00:00Z",
                "reason": "Constructed review window chosen by a person",
            }],
            "sources": [{
                "name": "inspection export",
                "path": "uses.csv",
                "kind": kind,
                "columns": {
                    "gage_id": "tool", "work_id": "job", "start": "began",
                    "end": "ended", "reference": "reference",
                },
            }],
        }
        if extra:
            project.update(extra)
        config = directory / "project.json"
        config.write_text(json.dumps(project), encoding="utf-8")
        return config, project

    def analyze(self, config, *, expected=0, name=None):
        self.counter += 1
        out = self.base / (name or f"report-{self.counter}")
        result = self.cli("analyze", config, "--out", out)
        self.assert_exit(result, expected)
        if expected != 1:
            self.assertTrue(out.is_dir())
            analysis = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
            return out, analysis
        self.assertFalse(out.exists(), "Invalid operation published an output directory")
        return out, None

    @staticmethod
    def csv_rows(path):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            return list(reader.fieldnames), list(reader)

    @staticmethod
    def write_csv(path, headers, rows):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

    def reviewed_decisions(self, report):
        headers, rows = self.csv_rows(report / "cases.csv")
        for row in rows:
            row.update(status="reviewed", owner="Quality reviewer", rationale="Recorded human review", evidence="QA-123")
        path = report.parent / f"{report.name}-decisions.csv"
        self.write_csv(path, headers, rows)
        return path, headers, rows

    def test_direct_points_offsets_and_inclusive_boundaries(self):
        config, _ = self.project([
            ["G-1", "JOB-A", "2026-01-10T07:00:00-05:00", "", "start", ""],
            ["G-1", "JOB-B", "2026-01-12T17:00:00+05:00", "", "end", ""],
            ["G-1", "JOB-C", "2026-01-12T12:00:00.000001Z", "", "after", ""],
        ])
        report, data = self.analyze(config)
        self.assertEqual([r["classification"] for r in data["records"]],
                         ["recorded_overlap", "recorded_overlap", "outside_window"])
        self.assertEqual(data["records"][0]["start"], data["records"][0]["end"])
        self.assert_exit(self.cli("verify", report), 0)

    def test_conservative_day_precision_and_partial_intervals(self):
        config, _ = self.project([
            ["G-1", "A", "2026-01-10", "", "coarse-start", ""],
            ["G-1", "B", "2026-01-11", "", "coarse-inside", ""],
            ["G-1", "C", "2026-01-12", "", "coarse-end", ""],
            ["G-1", "D", "2026-01-10T11:59:59Z", "2026-01-10T12:00:00Z", "partial", ""],
        ])
        _, data = self.analyze(config)
        self.assertEqual([r["classification"] for r in data["records"]],
                         ["possible_overlap", "recorded_overlap", "possible_overlap", "possible_overlap"])

    def test_all_matching_windows_retained_even_with_containment(self):
        windows = [
            {"id": "wide", "gage_id": "G-1", "start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z", "reason": "wide test"},
            {"id": "narrow", "gage_id": "G-1", "start": "2026-01-11T12:00:00Z", "end": "2026-01-11T13:00:00Z", "reason": "narrow test"},
        ]
        config, _ = self.project([["G-1", "A", "2026-01-11T11:00:00Z", "2026-01-11T12:00:00Z", "", ""]], windows=windows)
        _, data = self.analyze(config)
        record = data["records"][0]
        self.assertEqual(record["classification"], "recorded_overlap")
        self.assertEqual(set(record["window_ids"]), {"wide", "narrow"})

    def test_custody_never_claims_recorded_measurement(self):
        config, _ = self.project([
            ["G-1", "A", "2026-01-11T00:00:00Z", "2026-01-11T01:00:00Z", "closed", ""],
            ["G-1", "B", "2025-01-01", "", "open", ""],
        ], kind="custody")
        _, data = self.analyze(config)
        self.assertEqual([r["classification"] for r in data["records"]], ["possible_overlap", "possible_overlap"])
        self.assertIsNone(data["records"][1]["end"])

    def test_unknown_identity_bad_dates_missing_work_are_retained(self):
        config, _ = self.project([
            ["UNKNOWN", "A", "2000-01-01", "", "unknown-outside", ""],
            ["", "B", "2026-01-11", "", "blank-tool", ""],
            ["G-1", "C", "2026-01-11T00:00:00", "", "naive-time", ""],
            ["G-1", "D", "", "", "missing-date", ""],
            ["G-1", "", "2026-01-11", "", "missing-work", ""],
            ["G-2", "E", "garbage", "", "other-with-issue", ""],
        ])
        _, data = self.analyze(config, expected=2)
        self.assertEqual(len(data["records"]), 6)
        self.assertEqual([r["classification"] for r in data["records"]], ["unresolved"] * 5 + ["other_gage"])
        self.assertTrue(data["records"][-1]["reasons"], "Invalid date issue was discarded for other gage")
        self.assertEqual(sum(data["counts"].values()), 6)

    def test_invalid_interval_and_ambiguous_dates_unresolved(self):
        config, _ = self.project([
            ["G-1", "A", "2026-01-11T02:00:00Z", "2026-01-11T01:00:00Z", "reverse", ""],
            ["G-1", "B", "01/11/2026", "", "ambiguous", ""],
            ["G-1", "C", "2026-02-30", "", "impossible", ""],
        ])
        _, data = self.analyze(config, expected=2)
        self.assertEqual([r["classification"] for r in data["records"]], ["unresolved"] * 3)

    def test_aliases_are_exact_and_never_fuzzy(self):
        config, _ = self.project([
            ["serial-1", "A", "2026-01-11", "", "exact", ""],
            ["SERIAL-1", "B", "2026-01-11", "", "case-differs", ""],
            [" G-1", "C", "2026-01-11", "", "space-differs", ""],
        ])
        _, data = self.analyze(config, expected=2)
        self.assertEqual([r["classification"] for r in data["records"]], ["recorded_overlap", "unresolved", "unresolved"])
        self.assertEqual(data["records"][0]["gage_id"], "G-1")

    def test_duplicate_records_remain_distinct_and_flagged(self):
        row = ["G-1", "A", "2026-01-11", "", "identical", "preserved extra"]
        config, _ = self.project([row, row])
        _, data = self.analyze(config)
        records = data["records"]
        self.assertEqual(len(records), 2)
        self.assertEqual(len({r["record_id"] for r in records}), 2)
        self.assertEqual([r["row"] for r in records], [2, 3])
        self.assertTrue(any("duplicate" in " ".join(r["reasons"]).lower() for r in records))
        self.assertEqual(len(data["cases"]), 1)
        self.assertEqual(len(data["cases"][0]["record_ids"]), 2)
        self.assertEqual(records[0]["raw"]["note"], "preserved extra")

    def test_blank_csv_record_is_retained_and_numbered(self):
        config, _ = self.project([[], ["G-1", "A", "2026-01-11", "", "", ""]])
        _, data = self.analyze(config, expected=2)
        self.assertEqual(len(data["records"]), 2)
        self.assertEqual([r["row"] for r in data["records"]], [2, 3])
        self.assertEqual(data["records"][0]["classification"], "unresolved")

    def test_multiline_cell_uses_logical_record_numbers(self):
        config, _ = self.project([
            ["G-1", "A", "2026-01-11", "", "first", "line one\nline two"],
            ["G-1", "B", "2026-01-11", "", "second", ""],
        ])
        _, data = self.analyze(config)
        self.assertEqual([r["row"] for r in data["records"]], [2, 3])
        self.assertEqual(data["records"][0]["raw"]["note"], "line one\nline two")

    def test_missing_work_gets_separate_case_per_record(self):
        config, _ = self.project([
            ["G-1", "", "2026-01-11", "", "one", ""],
            ["G-1", "", "2026-01-11", "", "two", ""],
        ])
        _, data = self.analyze(config, expected=2)
        self.assertEqual(len(data["cases"]), 2)
        self.assertTrue(all(len(case["record_ids"]) == 1 for case in data["cases"]))

    def test_sources_have_independent_explicit_column_maps(self):
        config, project = self.project([["G-1", "A", "2026-01-11", "", "", ""]])
        other = config.parent / "other.csv"
        other.write_text("Work,Gage,When,Extra\nA,G-1,2026-01-11,kept\n", encoding="utf-8-sig")
        project["sources"].append({"name": "second export", "path": "other.csv", "kind": "custody", "columns": {"gage_id": "Gage", "work_id": "Work", "start": "When"}})
        config.write_text(json.dumps(project), encoding="utf-8")
        _, data = self.analyze(config)
        self.assertEqual(len(data["records"]), 2)
        self.assertEqual(set(r["classification"] for r in data["records"]), {"recorded_overlap", "possible_overlap"})
        self.assertEqual(len(data["cases"]), 1)
        self.assertEqual(len(data["source_hashes"]), 2)
        self.assertEqual(data["records"][1]["raw"]["Extra"], "kept")

    def test_invalid_project_contracts_publish_nothing(self):
        config, project = self.project([["G-1", "A", "2026-01-11", "", "", ""]])
        mutations = {
            "alias chain": lambda p: p["aliases"].update({"a": "b", "b": "G-1"}),
            "canonical remap": lambda p: p["aliases"].update({"G-1": "G-2"}),
            "unknown window gage": lambda p: p["windows"][0].update(gage_id="UNKNOWN"),
            "date only window": lambda p: p["windows"][0].update(start="2026-01-10"),
            "naive window": lambda p: p["windows"][0].update(start="2026-01-10T00:00:00"),
            "reversed window": lambda p: p["windows"][0].update(start="2026-02-10T00:00:00Z"),
            "unknown key": lambda p: p.update(guess_columns=True),
            "duplicate mapped header": lambda p: p["sources"][0]["columns"].update(work_id="tool"),
            "remote source": lambda p: p["sources"][0].update(path="https://example.invalid/uses.csv"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(project)
                mutate(changed)
                config.write_text(json.dumps(changed), encoding="utf-8")
                self.analyze(config, expected=1)

    def test_duplicate_or_empty_headers_are_rejected(self):
        config, _ = self.project([])
        for header in ["tool,job,began,ended,reference,tool\n", "tool,job,began,ended,reference,\n"]:
            with self.subTest(header=header):
                (config.parent / "uses.csv").write_text(header, encoding="utf-8")
                self.analyze(config, expected=1)

    def test_oversize_cell_is_rejected_without_report(self):
        config, _ = self.project([["G-1", "A", "2026-01-11", "", "", "x" * 4097]])
        self.analyze(config, expected=1)

    def test_existing_output_directory_is_not_modified(self):
        config, _ = self.project([["G-1", "A", "2026-01-11", "", "", ""]])
        out = self.base / "already-there"
        out.mkdir()
        marker = out / "do-not-touch"
        marker.write_text("existing content", encoding="utf-8")
        self.assert_exit(self.cli("analyze", config, "--out", out), 1)
        self.assertEqual(list(out.iterdir()), [marker])
        self.assertEqual(marker.read_text(), "existing content")

    def test_review_records_all_cases_and_preserves_original(self):
        config, _ = self.project([["G-1", "A", "2026-01-11", "", "", ""]])
        report, analysis = self.analyze(config)
        before = {p.name: p.read_bytes() for p in report.iterdir() if p.is_file()}
        decisions, _, _ = self.reviewed_decisions(report)
        reviewed = self.base / "reviewed"
        self.assert_exit(self.cli("review", report, "--decisions", decisions, "--out", reviewed), 0)
        self.assertEqual(json.loads((reviewed / "analysis.json").read_text())["analysis_id"], analysis["analysis_id"])
        self.assertTrue((reviewed / "decisions.csv").is_file())
        self.assert_exit(self.cli("verify", reviewed), 0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in report.iterdir() if p.is_file()})

    def test_open_review_returns_attention_exit_code(self):
        config, _ = self.project([["G-1", "A", "2026-01-11", "", "", ""]])
        report, _ = self.analyze(config)
        reviewed = self.base / "still-open"
        self.assert_exit(self.cli("review", report, "--decisions", report / "cases.csv", "--out", reviewed), 2)
        self.assert_exit(self.cli("verify", reviewed), 0)

    def test_review_rejects_identity_changes_missing_extra_and_duplicate(self):
        config, _ = self.project([["G-1", "A", "2026-01-11", "", "", ""]])
        report, _ = self.analyze(config)
        decisions, headers, rows = self.reviewed_decisions(report)
        variants = []
        for field in ["analysis_id", "case_id", "work_id", "record_ids", "window_ids"]:
            changed = copy.deepcopy(rows)
            changed[0][field] += "edited"
            variants.append((f"edited-{field}", changed))
        variants.extend([("missing", []), ("duplicate", rows + rows)])
        extra = copy.deepcopy(rows)
        extra[0]["case_id"] = "0" * 64
        variants.append(("extra", rows + extra))
        for name, altered in variants:
            with self.subTest(name=name):
                self.write_csv(decisions, headers, altered)
                out = self.base / name
                self.assert_exit(self.cli("review", report, "--decisions", decisions, "--out", out), 1)
                self.assertFalse(out.exists())

    def test_review_requires_status_and_complete_human_rationale(self):
        config, _ = self.project([["G-1", "A", "2026-01-11", "", "", ""]])
        report, _ = self.analyze(config)
        decisions, headers, rows = self.reviewed_decisions(report)
        for field in ["owner", "rationale", "evidence", "status"]:
            with self.subTest(field=field):
                changed = copy.deepcopy(rows)
                changed[0][field] = "" if field != "status" else "closed"
                self.write_csv(decisions, headers, changed)
                out = self.base / f"invalid-{field}"
                self.assert_exit(self.cli("review", report, "--decisions", decisions, "--out", out), 1)
                self.assertFalse(out.exists())

    def test_decisions_from_a_different_analysis_are_rejected(self):
        config, project = self.project([["G-1", "A", "2026-01-11", "", "", ""]])
        report, original = self.analyze(config)
        decisions, _, _ = self.reviewed_decisions(report)
        project["windows"][0]["reason"] = "Changed review-window rationale"
        config.write_text(json.dumps(project), encoding="utf-8")
        changed_report, changed = self.analyze(config)
        self.assertNotEqual(original["analysis_id"], changed["analysis_id"])
        out = self.base / "stale-review"
        self.assert_exit(self.cli("review", changed_report, "--decisions", decisions, "--out", out), 1)
        self.assertFalse(out.exists())

    def test_verify_detects_changed_bundled_source_and_record_artifacts(self):
        config, _ = self.project([["G-1", "A", "2026-01-11", "", "", ""]])
        report, data = self.analyze(config)
        source = report / data["source_hashes"][0]["file"]
        original = source.read_bytes()
        source.write_bytes(original + b"\n")
        self.assert_exit(self.cli("verify", report), 1)
        source.write_bytes(original)
        self.assert_exit(self.cli("verify", report), 0)
        with (report / "records.csv").open("a", encoding="utf-8") as stream:
            stream.write("tampered\n")
        self.assert_exit(self.cli("verify", report), 1)

    def test_unsafe_csv_values_and_html_are_escaped_and_roundtrip(self):
        payload = '<script>alert("x")</script><img src="https://example.invalid/x">'
        config, _ = self.project([
            ["G-1", "=1+1", "2026-01-11", "", payload, "@SUM(A1:A2)"],
            ["G-1", payload, "2026-01-11", "", "", ""],
        ])
        report, data = self.analyze(config)
        self.assertEqual(data["records"][0]["raw"]["job"], "=1+1")
        html = (report / "report.html").read_text(encoding="utf-8")
        self.assertNotIn("<script", html.lower())
        self.assertNotIn('<img src="https://example.invalid', html)
        self.assertIn("&lt;script&gt;", html)
        _, cases = self.csv_rows(report / "cases.csv")
        self.assertIn("'=1+1", [case["work_id"] for case in cases])
        decisions, headers, rows = self.reviewed_decisions(report)
        for row in rows:
            row.update(owner="=owner", rationale="+review rationale", evidence="@evidence")
        self.write_csv(decisions, headers, rows)
        out = self.base / "safe-reviewed"
        self.assert_exit(self.cli("review", report, "--decisions", decisions, "--out", out), 0)
        _, final_decisions = self.csv_rows(out / "decisions.csv")
        self.assertTrue(all(row["owner"] == "'=owner" for row in final_decisions))
        self.assertTrue(all(row["rationale"] == "'+review rationale" for row in final_decisions))
        self.assertTrue(all(row["evidence"] == "'@evidence" for row in final_decisions))
        self.assert_exit(self.cli("verify", out), 0)

    def test_example_runs_outside_checkout_and_verifies(self):
        example = self.base / "constructed-example"
        self.assert_exit(self.cli("example", example), 0)
        configs = list(example.glob("*.json"))
        self.assertTrue(configs)
        project = next(p for p in configs if json.loads(p.read_text()).get("schema_version") == 1 and "sources" in json.loads(p.read_text()))
        report = self.base / "example-analysis"
        result = self.cli("analyze", project, "--out", report)
        self.assertIn(result.returncode, (0, 2), result.stdout + result.stderr)
        self.assert_exit(self.cli("verify", report), 0)


if __name__ == "__main__":
    unittest.main()
