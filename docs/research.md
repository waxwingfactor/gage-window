# Opportunity and positioning research

Research date: **2026-10-15**. This is desk research of public documentation, not customer interviews, adoption evidence, or a measured savings study. Product descriptions below are vendor or project statements; their operational claims were not independently tested.

## Decision: reject the broad idea; support a narrow companion workflow

A general tool that lists jobs or lots touched by an out-of-tolerance gauge would duplicate established capabilities. Offline operation, an open-source license, a date window, and an impact report are not sufficient differentiation.

Gage Window instead targets a quality coordinator at a small job shop investigating a specific incident from disconnected historical CSV inspection and tool-custody exports. The supported task is to map explicit equipment identities, apply human-chosen review windows, distinguish direct records from possible custody, preserve uncertain dates and unresolved rows, and record follow-up decisions in a worksheet that can be re-imported without losing its evidence identity. It does not determine part quality or choose a justified investigation window.

This is a **conditional opportunity judgment**, not a claim that the market is empty. Documented pain supports retrospective tracing and incomplete-record reconstruction. Demand for this exact bundle of CSV reconciliation, temporal uncertainty, complete row accounting, and decision roundtrip remains **inferred**. A shop with an integrated, complete inspection history should first use its existing recall workflow.

## Strong alternatives examined

| Alternative and primary source | Documented workflow | Boundary of our comparison |
| --- | --- | --- |
| [GAGEtrak Getting Started Guide](https://gagetrak.com/wp-content/uploads/GAGEtrak_6.8_Getting_Started_Guide.pdf), issue/return chapter | Recording Part No. during issue/return enables a report of potentially affected parts when a gauge is found out of tolerance. | Direct counterexample to the broad idea. This guide does not establish how disconnected exports, ambiguous identities, or worksheet decision re-import are handled. |
| [1factory gage calibration](https://www.1factory.com/gage-calibration.html), features 3 and 13 | Issues gauges against a job and operation; traces jobs and features for a selected gauge and time period. | A strong integrated alternative. We do not claim that it lacks effective recall management. |
| [CalibraVault](https://clearstackapps.com/apps/calibravault/) | Offline, account-free Android register with a suspect-period jobs/lots report. It explicitly acknowledges unlogged usage, missing job references, and absent known-good baselines. | Directly defeats offline operation and honest missing-data warnings as standalone differentiators. Its documented workflow uses records maintained in its app. |
| [GaugeBase repository](https://github.com/ajayasai/gaugebase), README | Open-source local mode, register CSV import/export, downstream traceability risk views, and OOT/recall/CAPA case records. | Open-source local calibration and quality workflows already exist. Public documentation reviewed did not establish the proposed cross-export investigation roundtrip. |
| [Open Gauge repository](https://github.com/open-gauge/open-gauge), README | Self-hosted asset/calibration platform with coefficient history, certificates, traceability data, and API access. | Another credible open-source system alternative, particularly for ongoing calibration records. |
| [Overdue Calibration Finder](https://overdue-calibration-finder.theartofservice.com/) | Browser analysis of pasted instrument registers, date ambiguity, overdue status, and questions for OOT review. | Pasted spreadsheet analysis and date warnings are already available. The page explicitly bounds its input to the register. |

## Documented problem and evidence limits

A [September 2026 CyberMetrics forum discussion](https://forum.cybermetrics.com/t/weekly-poll-audit-readiness/323) contains a job shop's first-person report of difficulty associating many tools with many jobs for OOT analysis. The same thread explains existing GAGEtrak Crib/Where Used capabilities. This is direct evidence of an operational difficulty, not proof that a new product is needed or that native tools cannot solve it.

[Database Providers' calibration workflow](https://www.databaseproviders.com/calibration-management-software-iso9001-as9100/), particularly “Why Check-In and Check-Out History Is Not Enough,” explains that custody history usually cannot prove which instrument produced an inspection result. Without exact device IDs, an organization may need to reconstruct incomplete records, consider a broader product population, or rely on assumptions. Its review-period discussion also identifies calibration checks, known damage, use history, and technical assessment as relevant evidence. This is a vendor's explanation of a practical problem, not independent evidence of its prevalence.

Gage Window preserves that distinction: custody produces a possible overlap, never proof of measurement. Unknown identities and malformed relevant records remain visible. No matches mean no candidates were found in the supplied records; they do not establish that no unlogged use occurred. There is no claim of regulatory certification, safety assurance, technical correctness, or investigation closure.

## Search passes and challenge process

The lead and a separate AI research agent challenged the opportunity. The competition agent performed these search passes and inspected primary pages or guides, rather than relying on comparison-site rankings:

1. **Problem and broad competition:** searches such as `calibration out of tolerance impact analysis gage usage where used work orders software`, followed by native GAGEtrak and 1factory feature documentation. Result: reject generic where-used/recall reporting.
2. **Small-shop, offline, and worksheet alternatives:** searches combining `out of tolerance` with `offline`, `impact template`, `CSV`, and `suspect window`; inspection of CalibraVault and Overdue Calibration Finder. Result: reject offline-only and pasted-register-only differentiation.
3. **Open-source and exact workflow challenge:** searches combining calibration or gage management with `open source`, `traceability`, `usage log CSV impact`, `aliases`, and `retrospective reconciliation`; inspection of GaugeBase and Open Gauge. Result: the reviewed documentation did not describe the complete proposed cross-export, uncertainty-preserving, decision-roundtrip workflow.

These searches are bounded by the public material available on the research date. Unadvertised features, custom reports, integrations, spreadsheets, and other products may solve the same task. Failure to find an exact match is not proof of absence or universal uniqueness. The narrow companion scope is justified by its complete supported workflow, not by claiming better calibration management than the alternatives.

## Applying Crossing the Chasm selectively

The beachhead is deliberately narrower than “manufacturers”: quality coordinators at small job shops who already possess disconnected CSV usage/custody logs and need to investigate one gauge incident without first migrating historical records into a new operational system. The compelling reason to use it is to produce a reviewable candidate-work list with explicit uncertainties and carry human follow-up back into the same evidence package.

The **market alternative** is manual spreadsheet filtering, identity reconciliation, and follow-up notes. A clear **product alternative** is GAGEtrak's integrated issue/return and recall workflow; 1factory is another strong choice where inspection-level traceability is already captured. Gage Window complements existing records and is unsuitable as a replacement for an ongoing calibration or inspection system.

The whole supported product includes a strict input contract, explicit mappings and windows, a runnable constructed example, conservative classifications, row-level explanations, readable and machine-readable reports, a complete decision worksheet with validated re-import, integrity verification, installation, tests, and documented failure modes. These are necessary to finish the narrow task; they are not a claim of an enterprise quality-management offer.

### Original two-sentence positioning

For quality coordinators at small job shops who are dissatisfied with manually reconciling disconnected historical logs after a gauge incident, **Gage Window** is an offline investigation worksheet tool that reconstructs recorded candidate job and lot exposure while preserving identity and time uncertainty. Unlike GAGEtrak's integrated issue/return recall workflow, Gage Window works directly from explicitly mapped CSV exports and supplies conservative overlap explanations, complete row accounting, portable evidence reports, and a validated worksheet for recording and re-importing human follow-up decisions.

### Constructed usage scenarios

These scenarios are invented to explain intended use; they are not customer stories.

- An inspection export records `MIC-7`, while a crib export records its explicitly mapped alias `M7`. A date-only use falls across a timestamped review boundary. The investigator sees the possible overlap, its source row, and the precision limitation before assigning follow-up.
- A gauge checkout has no recorded return. The open custody interval overlaps a review window, so the report identifies a possible candidate job. A coordinator records an escalation and its evidence reference; the tool does not assert that the gauge measured that job or that any part failed.
- A work reference is missing or an instrument ID cannot be mapped. The record remains unresolved and gets a follow-up case rather than disappearing from a filtered spreadsheet. A short candidate list never conceals those gaps.

### Primary Moore and Chasm sources

- [Geoffrey Moore, Positioning](https://geoffreyamoore.com/positioning/): narrow beachhead, whole-product experience, and clear differentiation. Applied here to scope and alternatives, not to invented revenue or distribution plans.
- [Geoffrey Moore, “Positioning Your Product,” Stanford-hosted chapter](https://web.stanford.edu/group/e145/cgi-bin/winter/drupal/upload/handouts/MoorePositioning.pdf): source for the customer/need/category/benefit/alternative/differentiation positioning structure. The statement above is original.
- [Chasm Group, What We Do](https://chasmgroup.com/what-we-do/): whole-offer fit and positioning around delivered outcomes.
- [Chasm Group, Seven Deadly Sins](https://chasmgroup.com/7-deadly-sins-how-to-successfully-cross-the-chasm-with-cloud-based-solutions-by-avoiding-these-mistakes/): a whole product should fulfill the customer's compelling reason with the least complexity; installation and use are part of that task.

No reference customers, customer interviews, market leadership, production deployments, measured time savings, or adoption are claimed.
