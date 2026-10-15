# Independent AI-agent review record

Date: 2026-10-15. These are reviews by separate AI agents in the same authorized development session, not human reviews, customer validation, or approval from a second GitHub account.

## Independence and scope

- One research agent independently discovered documented tool/job traceability pain and challenged native, commercial and open-source alternatives.
- Another research agent performed adversarial feature-level competition research and authored the dated research/positioning document. Both rejected a generic OOT recall product and supported only the narrow export-reconciliation companion.
- The discovery agent then independently authored 24 black-box CLI acceptance tests from the supported contract, without editing implementation files.
- A third AI agent reviewed the implementation and added boundary regressions without editing it. The lead implemented the fixes and the reviewer rechecked them.

## Findings and fixes

| Finding | Severity | Resolution and verification |
| --- | --- | --- |
| A case with 61 records generated an aggregate identity cell larger than the importer's input-cell limit; escaping a maximum-length work ID also exceeded that limit. | P1 | Separate bounded generated identity fields from source/editable fields; raise the CSV parser's bounded aggregate field limit. Regression tests cover large cases, maximum escaped work IDs, aggregate windows and editable lengths. |
| Long repeated CSV headers could amplify allowed inputs into excessive report memory/output. | P1 | Count expanded canonical record bytes while classifying; stop at 8 MiB before rendering. Also enforce output file/total budgets. Regression verifies failure before rendering/publication. |
| Surplus cells on a malformed row could replace a legitimate original header named `__extra_cells__`. | P2 | Store surplus cells separately from the original header/value map; preserve both in JSON, records CSV, HTML and source snapshot. Regression verifies all representations and report reproduction. |

The reviewer found no material classification error in inclusive boundaries, offsets, conservative date spans, direct/custody distinction, open custody intervals or partial overlaps. Re-review confirmed the three original findings were resolved. No unresolved material findings were reported at that review point.

## Other validation

The lead exercised wheel and source-distribution installation in separate fresh virtual environments outside the checkout, with PYTHONPATH removed, verifying installed module locations, exact constructed example counts, review re-import, relocation and existing-output refusal. CI repeats acceptance and installation checks on Windows/macOS/Linux with Python 3.10/3.12/3.13.

The generated static report was actually rendered in the in-app browser at desktop and 390px mobile width. DOM measurements showed page scroll width equal to viewport width (390px); tables scroll within focusable regions. Tab focused the evidence table, and Right moved its horizontal scroll by 40px. Heading/table semantics and visible keyboard focus were inspected. This is a static local report, not a hosted interactive application. No claim of a complete accessibility audit is made.

A separate AI agent subsequently verified the actual published wheel and sdist; see release-verification.md for exact revisions, hashes, environments and observed results.
