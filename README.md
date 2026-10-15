# gage-window

**Turn fragmented gauge-use exports into a reviewable incident worksheet, while keeping uncertainty visible.**

For small job shops with historical inspection and tool-custody CSVs, gage-window reconciles exact equipment aliases, conservative time intervals and human-selected review windows. It accounts for every row, groups candidate work into review cases, and validates completed worksheets against the original analysis.

This is a complete, narrowly scoped local CLI. It does not calibrate equipment, determine affected product, select a technically justified review window, certify compliance, or approve release. Custody is possible use, never proof of measurement. Missing history cannot be reconstructed from nothing.

## Install and try

Requires Python 3.10–3.13 on Windows, macOS or Linux. No runtime dependencies and no network calls. Download the wheel from [Releases](https://github.com/waxwingfactor/gage-window/releases), then install into your environment:

```sh
python -m pip install gage_window-1.0.0-py3-none-any.whl
gage-window example demo
gage-window analyze demo/project.json --out initial-review
```

The constructed example returns **exit 2**, intentionally: nine rows are accounted for, including three unresolved records and six review cases. Open `initial-review/report.html` in a browser and inspect `records.csv` for every original row. Copy `initial-review/cases.csv` to `decisions.csv`, edit only `status`, `owner`, `rationale` and `evidence`, then:

```sh
gage-window review initial-review --decisions decisions.csv --out follow-up
gage-window verify follow-up
```

Keep cases `open` while follow-up is pending. Use `reviewed` or `escalated` to record human follow-up; both require an owner, rationale and evidence reference. These statuses carry **no conformance or approval meaning**. Review returns exit 2 until no cases remain open. Neither analysis exit 0 nor review exit 0 establishes investigation closure.

## Bring your exports

Start from `demo/project.json`. List known canonical gauge IDs, explicit alias spellings, one or more human-chosen timestamped windows with reasons, and per-file column mappings. Source kinds are `direct` for records asserting inspection use and `custody` for checkouts. The tool never guesses IDs, columns, dates or measurement relationships.

- Offset-aware timestamps identify instants. Date-only cells represent the entire **UTC** day; normalize local calendar data before use.
- Direct blank end means point use. Custody blank end remains open indefinitely, so later matching windows are retained.
- A direct span entirely inside a window is `recorded_overlap`; partial/coarse boundary overlap and all custody overlap are `possible_overlap`.
- Unknown IDs, relevant missing/invalid dates, malformed row widths and missing candidate work IDs stay `unresolved`. Known unrelated gauges and records outside supplied windows remain in the row ledger.
- Duplicate source rows are retained and flagged. Work IDs compare exactly; separately numbered lots should have distinct work IDs before import.

See the [input and output contract](docs/contract.md) for exact schema, classifications, resource limits and error behavior. The [walkthrough](docs/walkthrough.md) explains preparing inputs and resolving evidence gaps. The [dated opportunity research and positioning](docs/research.md) compares strong native, commercial and open-source alternatives.

## Outputs and trust

A new output directory contains `analysis.json`, `records.csv`, `cases.csv`, readable `report.html`, exact CSV source snapshots and `manifest.json`. Review adds `decisions.csv`; the original cases remain available. Reports relocate and verify offline. Source paths are replaced by safe relative snapshot names. Original source cells remain in JSON and in the report. CSV formula-leading values are escaped for spreadsheet use.

`verify` checks file hashes and reproduces classifications and reports from bundled evidence. Hashes are **integrity checks, not authentication**. An editor who rewrites an entire bundle can replace its hashes. Keep protected originals separately when that matters. The report cannot prove external history is complete or that the mappings/evidence kinds supplied by a person are true.

Output directories must be new. Input/schema failures return exit 1 and do not publish a report; unresolved evidence returns exit 2 with a report. All data stays on the local machine; protect exports and reports according to your shop's access rules.

## Development and validation

```sh
python -m pip install build
python -m pip install -e .
python -m unittest discover -s tests -v
python -m build
```

The black-box acceptance suite was authored by a separate AI agent from the contract; independent AI-agent code review is recorded in PRs and [review notes](docs/review.md). This is not a human review or evidence of shop deployment. CI tests nine OS/Python combinations and installs both wheel and source distribution. Published release verification is recorded separately in [release verification](docs/release-verification.md).

MIT licensed. Report defects through [GitHub issues](https://github.com/waxwingfactor/gage-window/issues). No operational support SLA is promised.
