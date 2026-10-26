# AV-TRACE

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**Matched diagnostics for long-video agent reliability**

**Status badges (text):** `research-prototype` · `gate-a--repair` ·
`h1--0` · `h2--0` · `scientific-episodes--0` ·
`public-benchmark--not-available`

AV-TRACE studies a question that endpoint video-QA accuracy cannot answer:

> When decisive evidence is unavailable and later restored, can a long-video
> agent recognize that its evidence is insufficient, change how it searches,
> ground each claim in observations it actually acquired, and recover without
> guessing?

The project began as a broad benchmark for long audio-video agentic RAG. It has
since narrowed to a diagnostic **Acquire / Ground / Act** thesis built around
matched evidence-access interventions.

## Current research thesis

One evaluation family fixes the source, question, claim-evidence graph, tools,
and budget. Only access to a predeclared evidence route changes:

- **CLEAN:** sufficient evidence is reachable.
- **BLOCKED:** a validated necessary route is unavailable.
- **RESTORED:** the run begins like BLOCKED, then a policy-blind trigger
  restores the route.
- **NO_TRIGGER:** a matched control in which the route is not restored.

The intended analysis separates:

1. **Acquire** — did the system locate and inspect sufficient evidence?
2. **Ground** — are its answer claims supported by observations it acquired,
   with valid claim-level citations?
3. **Act** — did it diagnose insufficiency or access failure, continue or
   abstain appropriately, and recover after restoration?

This is a diagnostic protocol, not currently a validated public benchmark or
leaderboard.

## Status snapshot — 2026-10-23

| Area | Current status |
|---|---|
| Protocol and replay infrastructure | Substantially implemented and audited |
| Real media acquisition and full-timeline indexing | Demonstrated on multiple development sources |
| Learned retrieval | Executed on a small machine-provisional development set; descriptive only |
| Learned generator/controller adapters | Implemented and tested in fictional competence suites; current selected strong rows have not passed the scientific readiness gate |
| Human construct validation | **H1 = 0, H2 = 0** |
| Gate A — mini-pilot input | **REPAIR** |
| Scientific C/B/R/N episodes | **0 executed** |
| R21 / R22 authoring experiments | Real attempts retained as fail-closed results; **R22 permanently NO-GO** |
| R23-A | Deterministic repair and R22 replay implemented; replay remains NO-GO |
| R23-B v9 | Protocol/design ready only; not authorized or executed |
| R23-C | Implementation ready for exposed development calibration; not actually run |
| Untouched test roster | Commitment-only private roster conditionally audited; construction and distribution remain locked |
| Paper claim readiness | **Not ready** |

The most important limitation is not missing code. It is missing construct
validity: there are no human-adjudicated, saturation-audited evidence families,
no accepted minimal sufficient evidence sets, and no authorized scientific
episode.

## What already exists

- schemas and tooling for matched evidence-access episodes;
- action-level trajectories, deterministic replay, leakage checks, route
  certificates, and claim/citation evaluation;
- real long-video acquisition, stream verification, and full-timeline
  multimodal indexing;
- machine-provisional candidate mining and development-only family bundles;
- learned visual and audio retrieval experiments with fixed controls;
- learned direct-A/V and controller adapter implementations plus fictional
  competence/holdout evaluations;
- source-exposure governance and a sealed untouched-test commitment boundary;
- detailed positive, negative, and fail-closed audit records.

These assets establish engineering readiness and expose failure modes. They do
not establish benchmark validity, model superiority, modality necessity, or
broad generalization.

## Boundary with related work

AV-TRACE does **not** claim to be the first long-video retrieval, audiovisual,
VideoRAG, multi-hop evidence, or agentic video benchmark.

- **LoVR** already studies retrieval from long videos.
- **LongVidSearch** already makes necessary multi-hop evidence central.
- **FLARE** already provides hard audio/visual retrieval cases.
- **V-RAGBench** already decouples retrieval and generation and tests
  dependence on retrieved chunks.
- Other recent systems and benchmarks study tool use, evidence sufficiency,
  stopping, audiovisual reasoning, and evidence attribution.

The intended contribution is narrower: **matched intervention on the same
evidence graph, combined with trace-level diagnosis of acquisition, grounding,
stopping, and recovery**. Whether that contribution survives human validation
and learned-agent experiments remains an open empirical question.

See [`docs/research/novelty_boundary.md`](docs/research/novelty_boundary.md) and
[`docs/research/related_work_matrix.md`](docs/research/related_work_matrix.md)
for the dated literature audit.

## Read this first

- **Current research state:**  
  [`docs/overview/research_state_2026-10-23.md`](docs/overview/research_state_2026-10-23.md)
- **Migration handoff and next steps:**  
  [`docs/overview/next_steps_after_migration.md`](docs/overview/next_steps_after_migration.md)
- **Single authoritative CVPR state after migration preparation:**  
  [`docs/overview/authoritative_cvpr_state_2026-10-23.md`](docs/overview/authoritative_cvpr_state_2026-10-23.md)
- **Machine-readable post-migration work queue:**  
  [`data/rehearsal_plan/post_migration_cvpr_work_queue.json`](data/rehearsal_plan/post_migration_cvpr_work_queue.json)
- **Canonical project charter:**  
  [`docs/project_charter.md`](docs/project_charter.md)
- **CVPR thesis and evidence gates:**  
  [`docs/paper/cvpr_thesis_and_evidence_gates.md`](docs/paper/cvpr_thesis_and_evidence_gates.md)
- **Current CVPR pivot:**  
  [`docs/paper/cvpr_pivot_v2_addendum.md`](docs/paper/cvpr_pivot_v2_addendum.md)
- **R22 terminal decision:**  
  [`docs/review/p23_102_canary2_r22_terminal_audit.md`](docs/review/p23_102_canary2_r22_terminal_audit.md)
- **R23 design surfaces:**  
  [`R23-A`](docs/design/p23_102_query_authoring_v2.md) ·
  [`R23-B v9`](docs/design/p23_102_global_distinctiveness_v9.md) ·
  [`R23-C`](docs/design/p23_102_r23c_exposed_calibration_canary.md)

## Repository map

| Path | Purpose |
|---|---|
| `docs/spec/` | episode, action, output, trajectory, and metric contracts |
| `docs/design/` | prospective protocol and implementation designs |
| `docs/review/` | audits, decisions, negative results, and readiness boundaries |
| `docs/paper/` | thesis, preregistration, CVPR gates, and scale-up plans |
| `docs/research/` | related-work and novelty analysis |
| `src/` | reusable benchmark, media, controller, and validation components |
| `tools/`, `scripts/` | acquisition, indexing, authoring, replay, and audit tools |
| `tests*/`, `tooling/tests/` | unit, integration, and governance regression tests |

Restricted media, private identity mappings, credentials, authorization
receipts, and untouched-test identities are intentionally outside the public
documentation surface.

## Claim discipline

Until later gates pass, please use the following language:

- **Allowed:** engineering-ready, machine-provisional, development-only,
  descriptive diagnostic, design-ready, implementation-ready, fail-closed.
- **Not allowed:** human gold, benchmark-validated, modality necessary,
  controller superiority, scientific GO, public benchmark core, first, unique,
  or state of the art.

Negative results are first-class project outputs. In particular, R21 and R22
must not be rewritten as successful runs, and R22 must never be rerun or
retrofitted into a success.

## Immediate priority

The shortest credible path is:

1. preserve the current frozen and fail-closed boundaries;
2. complete source authority and human workflow prerequisites;
3. repair Gate A and run a small human construct-validation pilot;
4. obtain H1/H2 families without weakening the criteria;
5. pass strong-baseline competence and causal/leakage gates;
6. only then run matched learned-agent scientific episodes and decide whether
   a CVPR-scale study is justified.

The detailed dependency order and stop rules are in
[`docs/overview/next_steps_after_migration.md`](docs/overview/next_steps_after_migration.md).

## License and data

Project-authored code and documentation are released under the
[Apache License 2.0](LICENSE). Third-party datasets, media, model weights,
metadata snapshots, and derived artifacts retain their own licenses, privacy
conditions, and redistribution restrictions. See
[`docs/migration/THIRD_PARTY_DATA_NOTICE.md`](docs/migration/THIRD_PARTY_DATA_NOTICE.md).
