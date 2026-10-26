# Post-preflight engineering and research backlog

**Status:** planning only. This document does not authorize media acquisition,
content annotation, or model runs.

## Definition of ready

Every item needs an owner, acceptance test, rights/data dependency, estimated
cost, and target date. Schema/tool changes require migration and versioning.

## P0 — before media acquisition

| ID | Work item | Acceptance |
|---|---|---|
| P0-01 | Institution/counsel rights interpretation | Approved note separates copyright basis, access, processing, and artifact-specific release authority. |
| P0-02 | Candidate asset manifests | Every proposed transfer has a valid 0.2.0 manifest, immutable evidence snapshot, reviewer, and no applicable `unknown_hold`. |
| P0-03 | Public-core reserve | Enough cleared candidates exist to select 20–30 videos while retaining a documented replacement reserve; no source/domain quota forces acquisition. |
| P0-04 | Acquisition controls | Only official direct download, official tooling under recorded terms, platform-authorized export/API, or rightsholder delivery are enabled. |

## P0 — before content annotation

| ID | Work item | Acceptance |
|---|---|---|
| P0-05 | Semantic validator implementation | Implements every rule in `semantic_validator_spec.md` with stable errors and positive/adversarial tests. |
| P0-06 | Synthetic end-to-end family | One `CLEAN`/`BLOCKED`/`RESTORED` family passes schema, semantic, trace, budget, forced-finalization, and replay tests. |
| P0-07 | Annotation qualification pack | Twelve-family rehearsal covers exhaustive alternatives, SES minimality, necessity groups, both mechanisms, and all anti-shortcut audits. |
| P0-08 | Annotation workspace | Supports source-time evidence, waveforms, graph/SES/group editing, family preview, pair diff, rights link, and quarantine. |
| P0-09 | Rights-aware preprocessing design | Deterministic transforms, lineage, hashes, time bases, and public/restricted storage separation are specified before implementation. |

## P1 — before Pilot-0 model runs

| ID | Work item | Acceptance |
|---|---|---|
| P1-01 | Freeze 60 valid families | 20–30 source-disjoint videos; exactly 180 episodes; all semantic, human, rights, and pair-isolation gates pass. |
| P1-02 | Four-system run manifest | Model/prompt/backend/index versions, decoding, seeds, retries, canaries, diagnostics, and invalid-run reserve are explicit. |
| P1-03 | Metric implementation | Unit tests cover the dashboard, state-independent denominators, video aggregation, and paired restoration gain. |
| P1-04 | Operating-characteristic simulation | Uses observed ICC, missingness, restoration usability, and plausible effects to inform Pilot-1—not to retrofit Pilot-0 significance. |
| P1-05 | Measured cost plan | Rehearsal-derived labor plus 720 core runs and every extra run block, storage layer, backup, and retention month are counted. |
| P1-06 | Frozen/open reproducibility anchor | One disclosed system replays end to end without institution-specific secrets on the public core. |

## P2 — after Pilot-0 construct validation

- controlled distractor insertion;
- ASR corruption;
- answer-flipping counterfactual replacement with separately licensed media;
- broad budget-cap curves;
- open-system track;
- larger compatibility suites;
- multilingual and active-perception extensions;
- confirmatory powered ranking study;
- public leaderboard infrastructure.

## Explicit non-goals now

- downloading media before Gate A;
- annotating content before Gate B;
- large-scale crawling;
- a 200-question production campaign;
- a confirmatory model ranking;
- a public leaderboard;
- training a foundation model.

