#!/usr/bin/env python3
"""Independent verification of actual, publicly published gage-window artifacts.

Run only after the release exists. No development checkout is imported. Public
requests are deliberately unauthenticated; runtime checks run in fresh venvs.
"""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import venv
import zipfile


REPOSITORY = "waxwingfactor/gage-window"
TAG = "v1.0.0"
VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent
CHECKOUT = HERE / "gage-window"
MAX_DOWNLOAD = 100 * 1024 * 1024
EXPECTED_COUNTS = {
    "other_gage": 1,
    "outside_window": 2,
    "possible_overlap": 2,
    "recorded_overlap": 1,
    "unresolved": 3,
}
OFFLINE_ENTRY = """import runpy, socket, sys
def blocked(*args, **kwargs):
    raise RuntimeError('Network is disabled by the independent verifier')
socket.socket = blocked
socket.create_connection = blocked
sys.argv = ['gage-window', *sys.argv[1:]]
runpy.run_module('gage_window', run_name='__main__')
"""


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def clean_environment():
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("PYTHON") or key in {"PIP_TARGET", "PIP_PREFIX", "PIP_USER"}:
            env.pop(key, None)
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PIP_CONFIG_FILE=os.devnull,
               PIP_NO_INPUT="1", GAGE_WINDOW_INSTALLED="1")
    return env


def public_request(url, *, json_response=False):
    parsed = urllib.parse.urlparse(url)
    require(parsed.scheme == "https", "Only public HTTPS downloads are supported")
    headers = {"User-Agent": "gage-window-independent-public-verifier/1.0"}
    if json_response:
        headers.update(Accept="application/vnd.github+json", **{"X-GitHub-Api-Version": "2022-11-28"})
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        chunks = []
        size = 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            require(size <= MAX_DOWNLOAD, "Public response exceeded verifier download budget")
            chunks.append(chunk)
    body = b"".join(chunks)
    return json.loads(body) if json_response else body


def api(path):
    return public_request("https://api.github.com/" + path, json_response=True)


def safe_tar_members(archive):
    members = archive.getmembers()
    require(len(members) <= 5000, "Unexpectedly large source archive")
    for member in members:
        path = PurePosixPath(member.name)
        require(not path.is_absolute() and ".." not in path.parts, "Unsafe sdist member path")
        require(member.isfile() or member.isdir(), "Unsupported symlink or special member in sdist")
        require(member.size <= MAX_DOWNLOAD, "Oversize sdist member")
    return members


def inspect_distributions(artifacts, root):
    wheel = next(path for path in artifacts if path.suffix == ".whl")
    sdist = next(path for path in artifacts if path.name.endswith(".tar.gz"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        require(any(name.endswith(".dist-info/METADATA") for name in names), "Wheel lacks package metadata")
        require(any(name.endswith("gage_window/example/project.json") for name in names), "Wheel lacks runnable example")
        metadata = archive.read(next(name for name in names if name.endswith(".dist-info/METADATA"))).decode()
        require(f"Version: {VERSION}\n" in metadata, "Wheel metadata version differs from release")
        require("Requires-Dist:" not in metadata, "Unexpected runtime dependency in wheel")
    test_directory = root / "published-tests"
    test_directory.mkdir()
    with tarfile.open(sdist, "r:gz") as archive:
        members = safe_tar_members(archive)
        names = [member.name for member in members if member.isfile()]
        required = [
            "/README.md", "/LICENSE", "/pyproject.toml", "/docs/contract.md",
            "/docs/research.md", "/docs/walkthrough.md", "/docs/review.md",
            "/examples/project.json", "/examples/inspections.csv", "/examples/checkouts.csv",
            "/src/gage_window/example/project.json", "/tests/test_acceptance.py",
            "/tests/test_review_boundaries.py", "/scripts/check_distribution.py",
        ]
        for suffix in required:
            require(any(name.endswith(suffix) for name in names), f"Sdist lacks {suffix}")
        for member in members:
            parts = PurePosixPath(member.name).parts
            if member.isfile() and len(parts) == 3 and parts[1] == "tests" and parts[2].endswith(".py"):
                stream = archive.extractfile(member)
                require(stream is not None, "Unreadable published test")
                (test_directory / parts[2]).write_bytes(stream.read())
    return test_directory, {"wheel_example_present": True, "runtime_dependencies": [],
                            "sdist_required_docs_examples_tests_scripts_present": True,
                            "published_test_files": sorted(p.name for p in test_directory.iterdir())}


def snapshot_hashes(directory):
    return {str(path.relative_to(directory)): digest(path.read_bytes())
            for path in directory.rglob("*") if path.is_file()}


def run_installed(artifact, workspace, published_tests):
    workspace.mkdir()
    venv_directory = workspace / "venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(venv_directory)
    python = venv_directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    console = venv_directory / ("Scripts/gage-window.exe" if os.name == "nt" else "bin/gage-window")
    env = clean_environment()
    observations = []

    def run(args, *, expected=0, label, timeout=180):
        result = subprocess.run([str(python), "-I", *map(str, args)], cwd=workspace,
                                env=env, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        require(result.returncode == expected,
                f"{label}: expected {expected}, received {result.returncode}: {result.stdout}\n{result.stderr}")
        observations.append({"check": label, "exit_code": result.returncode})
        return result.stdout + result.stderr

    def cli(*args, expected=0, label, offline=False):
        prefix = ["-c", OFFLINE_ENTRY] if offline else ["-m", "gage_window"]
        return run([*prefix, *args], expected=expected, label=label)

    run(["-m", "pip", "install", "--no-deps", "--no-cache-dir", str(artifact)], label="fresh noneditable artifact installation", timeout=300)
    identity = json.loads(run(["-c", "import gage_window, importlib.metadata, json, sys; print(json.dumps({'file': gage_window.__file__, 'version': gage_window.__version__, 'venv': sys.prefix != sys.base_prefix, 'dependencies': importlib.metadata.requires('gage-window')}))"], label="installed module identity"))
    location = Path(identity["file"]).resolve()
    require(location.is_relative_to(venv_directory.resolve()), "Installed import escaped fresh venv")
    require(not location.is_relative_to(CHECKOUT.resolve()), "Development checkout leaked into import")
    require(identity["version"] == VERSION and identity["venv"], "Wrong installed version or nonisolated interpreter")
    require(identity["dependencies"] is None, "Unexpected installed runtime dependency")
    console_result = subprocess.run([str(console), "--version"], cwd=workspace, env=env,
                                    capture_output=True, text=True, encoding="utf-8", timeout=30)
    require(console_result.returncode == 0 and console_result.stdout.strip() == VERSION, "Installed console command failed")
    observations.append({"check": "installed console entry point", "exit_code": 0})

    cli("example", "original-inputs", label="installed constructed example creation", offline=True)
    cli("analyze", "original-inputs/project.json", "--out", "original-report", expected=2,
        label="exact constructed example analysis", offline=True)
    initial = workspace / "original-report"
    analysis = json.loads((initial / "analysis.json").read_text(encoding="utf-8"))
    require(len(analysis["records"]) == 9 and len(analysis["cases"]) == 6, "Wrong example record/case counts")
    require(analysis["counts"] == EXPECTED_COUNTS, "Wrong example classification counts")
    require(len({row["record_id"] for row in analysis["records"]}) == 9, "Example row identity collision")
    cli("verify", initial, label="initial report reproduction", offline=True)

    with (initial / "cases.csv").open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        headers, decisions = reader.fieldnames, list(reader)
    require(len(decisions) == 6, "Missing generated review case")
    for index, decision in enumerate(decisions):
        decision.update(status="reviewed" if index % 2 else "escalated", owner="Independent constructed reviewer",
                        rationale="Constructed review recorded for artifact verification", evidence="PUBLIC-VERIFY-1")
    decision_path = workspace / "completed-decisions.csv"
    with decision_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(decisions)
    cli("review", initial, "--decisions", decision_path, "--out", "completed-review",
        label="complete six-case human-status roundtrip", offline=True)
    reviewed = workspace / "completed-review"
    cli("verify", reviewed, label="completed review reproduction", offline=True)
    with (reviewed / "decisions.csv").open(encoding="utf-8", newline="") as stream:
        final = list(csv.DictReader(stream))
    require(len(final) == 6 and all(row["status"] in {"reviewed", "escalated"} for row in final), "Completed decisions were not retained")

    before = snapshot_hashes(initial)
    cli("analyze", "original-inputs/project.json", "--out", initial, expected=1,
        label="existing output refusal", offline=True)
    require(snapshot_hashes(initial) == before, "Output refusal modified existing report")
    project_path = workspace / "original-inputs/project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["windows"][0]["reason"] += " Changed by independent verifier."
    project_path.write_text(json.dumps(project), encoding="utf-8")
    cli("analyze", project_path, "--out", "changed-analysis", expected=2,
        label="new analysis after changed review window", offline=True)
    changed = json.loads((workspace / "changed-analysis/analysis.json").read_text(encoding="utf-8"))
    require(changed["analysis_id"] != analysis["analysis_id"], "Changed project retained old analysis identity")
    cli("review", "changed-analysis", "--decisions", decision_path, "--out", "stale-review", expected=1,
        label="stale decision rejection", offline=True)
    require(not (workspace / "stale-review").exists(), "Stale decisions published a report")
    project["windows"][0]["start"] = "2026-09-05T12:00:00"
    project_path.write_text(json.dumps(project), encoding="utf-8")
    cli("analyze", project_path, "--out", "malformed-report", expected=1,
        label="unsupported naive-window rejection", offline=True)
    require(not (workspace / "malformed-report").exists(), "Malformed project published a report")

    relocated = workspace / "relocated-evidence" / "report"
    relocated.parent.mkdir()
    initial.rename(relocated)
    shutil.rmtree(workspace / "original-inputs")
    shutil.rmtree(workspace / "changed-analysis")
    decision_path.unlink()
    require(not initial.exists() and not (workspace / "original-inputs").exists(), "Original paths were not removed")
    cli("verify", relocated, label="relocated report with original input paths removed and sockets disabled", offline=True)
    cli("verify", reviewed, label="review with original reports and inputs removed and sockets disabled", offline=True)
    tampered = workspace / "tampered-report"
    shutil.copytree(relocated, tampered)
    with (tampered / "records.csv").open("ab") as stream:
        stream.write(b"tampered\n")
    cli("verify", tampered, expected=1, label="tampered public-artifact report rejection", offline=True)

    test_copy = workspace / "installed-tests"
    shutil.copytree(published_tests, test_copy)
    test_output = run(["-m", "unittest", "discover", "-s", test_copy, "-v"],
                      label="published acceptance and boundary tests against installed package", timeout=300)
    count = re.search(r"Ran (\d+) tests", test_output)
    require(count is not None and int(count.group(1)) >= 31, "Expected published acceptance/boundary suite did not run")
    require("\nOK\n" in test_output, "Installed published test suite did not report success")
    return {
        "artifact": artifact.name,
        "installation": "fresh venv; noneditable; no PYTHONPATH or PYTHONHOME; isolated Python invocation",
        "module_location_relative_to_venv": str(location.relative_to(venv_directory.resolve())),
        "module_outside_development_checkout": True,
        "version": identity["version"],
        "example_records": 9,
        "example_cases": 6,
        "example_counts": analysis["counts"],
        "completed_case_decisions": len(final),
        "runtime_offline_guard": "Python socket constructors and create_connection disabled for principal and failure flows",
        "original_inputs_and_initial_report_paths_removed": True,
        "published_tests_passed": int(count.group(1)),
        "observations": observations,
    }


def sanitize(value, runtime):
    if isinstance(value, dict):
        return {key: sanitize(item, runtime) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item, runtime) for item in value]
    if isinstance(value, str):
        for path, replacement in [(str(runtime), "<verification-workspace>"), (str(HERE), "<work>"),
                                  (str(Path.home()), "<user-home>")]:
            value = value.replace(path, replacement)
        return value
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-commit", help="Optional exact reviewed revision supplied by release lead")
    parser.add_argument("--report", type=Path, default=HERE / "public-verification.json")
    args = parser.parse_args()
    require(sys.version_info >= (3, 10), "Verifier needs supported Python 3.10+")
    runtime = Path(tempfile.mkdtemp(prefix="public-gage-window-", dir=HERE))
    report = {"schema_version": 1, "repository": f"https://github.com/{REPOSITORY}", "tag": TAG,
              "started_at_utc": now(), "status": "running", "requests_authenticated": False,
              "environment": {"system": platform.system(), "release": platform.release(),
                              "machine": platform.machine(), "python": platform.python_version()},
              "verifier_sha256": digest(Path(__file__).read_bytes()), "installations": []}
    try:
        release = api(f"repos/{REPOSITORY}/releases/tags/{TAG}")
        require(not release.get("draft"), "Release is still a draft")
        require(release.get("tag_name") == TAG and release.get("published_at"), "Actual published release not found")
        assets = release["assets"]
        names = [asset["name"] for asset in assets]
        require(len(set(names)) == len(names), "Duplicate public release asset names")
        wheel_names = [name for name in names if name.endswith(".whl")]
        sdist_names = [name for name in names if name.endswith(".tar.gz")]
        require(len(wheel_names) == len(sdist_names) == 1, "Expected exactly one public wheel and sdist")
        expected_names = set(wheel_names + sdist_names + ["SHA256SUMS", "PROVENANCE.json"])
        require(expected_names <= set(names), "Public release lacks integrity/provenance files")
        downloads = runtime / "downloads"
        downloads.mkdir()
        asset_results = []
        for asset in assets:
            if asset["name"] not in expected_names:
                continue
            require(Path(asset["name"]).name == asset["name"], "Unsafe public asset name")
            data = public_request(asset["browser_download_url"])
            sha = digest(data)
            require(asset.get("digest") == "sha256:" + sha, f"GitHub API asset digest mismatch or unavailable: {asset['name']}")
            require(asset["size"] == len(data), "Public asset size differs from GitHub API")
            (downloads / asset["name"]).write_bytes(data)
            asset_results.append({"name": asset["name"], "sha256": sha, "size_bytes": len(data),
                                  "public_url": asset["browser_download_url"], "github_api_digest_matched": True})
        sums = {}
        for line in (downloads / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?([^/\\]+)", line)
            require(match is not None, "Malformed public SHA256SUMS line")
            sha, name = match.groups()
            require(name not in sums, "Duplicate checksum entry")
            sums[name] = sha.lower()
        require(set(sums) == expected_names - {"SHA256SUMS"}, "Checksum set does not exactly cover distributions and provenance")
        for name, sha in sums.items():
            require(digest((downloads / name).read_bytes()) == sha, f"Published checksum mismatch: {name}")
        provenance = json.loads((downloads / "PROVENANCE.json").read_text(encoding="utf-8"))
        require(provenance["repository"] == REPOSITORY and provenance["tag"] == TAG, "Provenance repository or tag mismatch")
        commit = provenance["commit"]
        require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Provenance lacks full Git commit")
        require(args.expected_commit is None or commit == args.expected_commit, "Release differs from expected reviewed revision")
        require(provenance["artifacts"] == {name: sums[name] for name in wheel_names + sdist_names}, "Artifact provenance hashes differ from public bytes")
        tag_object = api(f"repos/{REPOSITORY}/git/ref/tags/{TAG}")["object"]
        for _ in range(3):
            if tag_object["type"] != "tag":
                break
            tag_object = api(f"repos/{REPOSITORY}/git/tags/{tag_object['sha']}")["object"]
        require(tag_object["type"] == "commit" and tag_object["sha"] == commit, "Public tag differs from provenance commit")
        ci_match = re.fullmatch(r"https://github\.com/" + re.escape(REPOSITORY) + r"/actions/runs/(\d+)", provenance["ci_run_url"])
        require(ci_match is not None, "Provenance CI link is not a repository Actions run")
        ci = api(f"repos/{REPOSITORY}/actions/runs/{ci_match.group(1)}")
        require(ci["head_sha"] == commit and ci["status"] == "completed" and ci["conclusion"] == "success", "Provenance CI did not pass on release commit")
        checks = api(f"repos/{REPOSITORY}/commits/{commit}/check-runs?per_page=100")
        required = [check for check in checks["check_runs"] if check["name"] == "required-ci"]
        require(any(check["status"] == "completed" and check["conclusion"] == "success" for check in required), "No passing required-ci on exact release revision")
        report.update(public_release_url=release["html_url"], release_published_at=release["published_at"],
                      commit=commit, public_assets=asset_results, published_sums_matched=True,
                      provenance_matched=True, public_tag_matched=True, ci_run_url=ci["html_url"],
                      exact_revision_required_ci_passed=True)
        distributions = [downloads / name for name in wheel_names + sdist_names]
        test_directory, contents = inspect_distributions(distributions, runtime)
        report["distribution_contents"] = contents
        for index, artifact in enumerate(distributions):
            report["installations"].append(run_installed(artifact, runtime / f"installation-{index + 1}", test_directory))
        report["status"] = "verified"
        report["finished_at_utc"] = now()
        report["limitations"] = ["One local macOS/Python environment independently exercised published artifacts; CI supplies other OS/Python coverage.",
                                 "Hashes and provenance match public GitHub records; they are not independent cryptographic publisher authentication.",
                                 "Examples are constructed and no shop deployment or engineering decision was tested."]
    except Exception as exc:
        report.update(status="failed", finished_at_utc=now(), error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        sanitized = sanitize(report, runtime)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.report.with_suffix(args.report.suffix + ".tmp")
        temporary.write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(args.report)
    print(f"VERIFIED: {REPOSITORY} {TAG}: actual public wheel and sdist; report={args.report.name}")


if __name__ == "__main__":
    main()
