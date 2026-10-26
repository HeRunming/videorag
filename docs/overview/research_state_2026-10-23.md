# AV-TRACE research state

**As of:** 2026-10-23  
**Audience:** project owner, maintainers, and research collaborators  
**Scope:** repository-public research summary; no private reserve identities,
credentials, authorization secrets, or restricted path details

> **Bottom line:** AV-TRACE has a mature diagnostic protocol and substantial
> real-media engineering evidence, but it does not yet have a scientific
> benchmark result. The current hard boundary is
> **H1 = 0, H2 = 0, Gate A = REPAIR, scientific episodes = 0**.

## 1. Executive status

| Layer | Current evidence | Honest status |
|---|---|---|
| Diagnostic idea | Fixed question/evidence graph with matched access blocking and restoration | Canonical thesis frozen |
| Engineering protocol | Episode schemas, tools, trajectories, replay, metrics, route certificates, leakage controls | Substantially proven |
| Real-media substrate | Multiple acquired long-video sources, stream checks, complete timeline indexes, machine mining | Development assets exist |
| Learned retrieval | Real visual/audio retrieval and fixed fusion comparisons on a small provisional set | Descriptive diagnostic only |
| Learned generation/agents | Adapters and competence suites exist; selected current rows failed competence/holdout gates | Not scientifically ready |
| Human construct validity | No human-accepted SES or H-tier family | **H1 = 0, H2 = 0** |
| Mini-pilot input gate | Prospective sources/slots and blank packets exist, but substantive requirements remain open | **Gate A = REPAIR** |
| Scientific evaluation | No authorized human-valid C/B/R/N run | **0 scientific episodes** |
| Untouched evaluation boundary | Sealed identity-free roster is conditionally audited | Locked; not construction-ready |
| Paper | Infrastructure and protocol story exists; empirical contribution does not | Claims blocked |

The project should currently be described as:

> **audited research infrastructure plus development-only diagnostics for a
> matched long-video evidence-access protocol.**

It should not be described as a validated benchmark, a public benchmark
release, or a completed learned-agent study.

## 2. How the research question changed

### 2.1 Original idea: a broad long audio-video agentic RAG benchmark

The initial concept covered a wide chain:

```text
long audio-video
  -> multimodal retrieval
  -> grounded generation
  -> agentic tool use and replanning
  -> answer with evidence
```

It sought to combine visual, speech, and ambient-audio retrieval; sparse and
multi-hop evidence; grounded answers and citations; evidence sufficiency;
abstention; stopping; tool or modality failure; recovery; and counterfactual
evidence use.

That direction produced useful infrastructure, but it was too broad to support
a crisp scientific claim. Nearly every individual component has close prior
art, and each intervention requires its own construct-validity proof.

### 2.2 Current idea: a diagnostic Acquire / Ground / Act thesis

The project now asks a narrower causal-behavioral question:

> Under a fixed question, claim-evidence graph, backend, and budget, what
> happens when a decisive evidence route is blocked and later restored?

The diagnostic decomposition is:

1. **Acquire:** did the system search, inspect, or read enough evidence?
2. **Ground:** did it use the acquired evidence to produce correct atomic
   claims and valid claim-level citations?
3. **Act:** did it recognize insufficiency or access failure, avoid premature
   stopping, adapt its search, and recover after restoration?

The core matched states are:

- `CLEAN`;
- `BLOCKED`;
- `RESTORED`;
- and, in the current causal protocol, `NO_TRIGGER`.

The critical conceptual move was from “retrieve a relevant clip” to “acquire a
minimal sufficient evidence set, after closing accepted alternative routes.”
This is why human review, alternative-SES search, necessity groups, and
intervention-isolation audits are not optional annotation polish; they are the
scientific foundation.

## 3. Canonical scientific proposition

The current thesis is falsifiable:

> Static clean-video answer accuracy is insufficient to establish long-video
> agent reliability. A reliable system must acquire sufficient evidence,
> attribute claims to that evidence, recognize when access or evidence is
> insufficient, change behavior when appropriate, and recover when a blocked
> route is restored.

Evidence that would support the thesis includes:

- systems with similar CLEAN answer accuracy but different false-sufficient,
  premature-stop, or restoration behavior;
- correct answers that lack complete acquired support;
- successful retrieval followed by unsupported generation or citation;
- agents that diagnose insufficiency but fail to reacquire evidence;
- distinct recovery policies under the same backend and budget; and
- intervention effects that persist across source-disjoint human-valid
  families.

Evidence that would weaken or reject it includes:

- inability to obtain reproducible human-valid questions, SESs, necessity
  groups, or isolated interventions;
- all end-to-end differences being explained by retrieval recall alone;
- no behavioral separation among competent learned systems;
- effects driven by leakage, templates, one source, or evaluator-private data;
  or
- restoration mechanics that do not correspond to a defensible causal
  contrast.

## 4. Boundary with adjacent work

AV-TRACE's contribution cannot be any single item in the following list:
long-video retrieval, audiovisual retrieval, multi-hop evidence, VideoRAG,
agentic tool use, evidence sufficiency, stopping, or citation-aware video QA.

| Work | What it already occupies | Remaining AV-TRACE boundary |
|---|---|---|
| **LoVR** | Large-space long-video/clip text retrieval and localization | Not controlled access failure, insufficiency diagnosis, or restoration |
| **LongVidSearch** | Agentic multi-hop search with exact necessary evidence structure | Not matched runtime blocking/restoration with trace-level failure diagnosis |
| **FLARE** | Hard vision/audio/audiovisual retrieval, including bimodal necessity | Not an agent experiencing an outage, rerouting, and recovering |
| **V-RAGBench** | Decoupled retrieval/generation and dependence on retrieved video chunks | Not paired missing-evidence states or recovery/stopping calibration |

Other nearby work further occupies audiovisual multi-hop reasoning, general
video tool use, sufficiency verification, convergence/stopping, counterfactual
video evaluation, and evidence-backed QA.

The defensible white space is therefore the **combination** of:

1. one fixed latent evidence graph;
2. matched access interventions;
3. explicit insufficient and restored states;
4. action-level traces;
5. claim-level grounding;
6. final-point stopping analysis; and
7. recovery under a common supported-answer endpoint.

Even that boundary is only a candidate contribution until human construct
validation and learned-agent experiments succeed. No priority or “first”
claim is currently authorized.

## 5. Assets and experimental substrate

### 5.1 Real sources and acquisition

The repository contains evidence of exact acquisition and A/V validation for
multiple development sources:

- an early public-source long-video set used for the bounded MVP, full-timeline
  migration, and learned-retrieval wave;
- several lecture-style development sources used to exercise complete
  timelines, source mining, and governance;
- event-centric licensed-source development work, including a fully acquired
  and indexed long video used for the current authoring line; and
- additional source-route and technical preflight records that remain gated or
  conditional.

These sources have different rights, privacy, redistribution, and future-test
eligibility. “Acquired” or “indexed” does not mean “publicly releasable,”
“Gate-A eligible,” or “untouched.”

### 5.2 Full-timeline indexes

The engineering stack supports:

- deterministic temporal segmentation;
- visual, speech, and ambient-audio observations;
- source and segment hashes;
- lexical and learned retrieval surfaces;
- observation manifests separated from evaluator-private family semantics;
- complete timeline verification and replay; and
- candidate mining from frozen indexes.

The early real-media progression was:

1. bounded-window protocol MVP;
2. complete-timeline migration;
3. learned visual/audio retrieval over the frozen timeline.

The later event-centric development source also reached exact acquisition,
complete index status, repaired machine mining, and a frozen
machine-provisional family bundle.

### 5.3 Machine-provisional families

Machine mining has produced useful development leads, including near/local and
far/multi-hop visual-plus-audio hypotheses. These records are explicitly:

- not accepted families;
- not accepted SESs;
- not modality-necessity findings;
- not H1 or H2;
- not eligible for scientific interpretation; and
- subject to source-uniform human prescreen and full-source alternative-route
  review.

This boundary has held even when engineering artifacts were marked READY.

### 5.4 Learned retrieval

The completed learned-retrieval wave used pinned:

- learned visual-text retrieval;
- learned audio-text retrieval;
- lexical speech retrieval;
- legacy and fixed-fusion controls; and
- the same frozen full-timeline universe.

Its strongest conclusion is methodological, not model-ranking:

> replacing a task-shaped control with a general learned encoder can materially
> change evidence localization, and “newer learned retriever” does not imply
> better retrieval for the current provisional tasks.

The result remains low-N, source-limited, and machine-provisional. It contains
no learned generator or learned agent end-to-end evaluation and cannot support
a general superiority or inferiority claim.

### 5.5 Learned baseline implementations

The repository contains:

- a direct audiovisual baseline adapter;
- a shared learned generator/finalizer path;
- learned ReAct and explicit evidence-sufficiency controllers;
- strict structured actions and claim/citation finalization;
- observed-evidence locks;
- exogenous restoration support;
- invalid-run typing and provenance logging; and
- fictional competence and unseen-holdout suites.

Several model snapshots reached acquisition or technical-load readiness.
However, the current selected strong learned rows did not pass the frozen
competence/holdout gates required for scientific execution. Adapter readiness
must not be confused with model competence.

### 5.6 Quantitative inventory

The most useful public, non-sensitive inventory is:

| Asset line | Verified repository state | Scientific boundary |
|---|---|---|
| Early real-A/V development set | 5 acquired long videos; bounded protocol on 6 provisional families; 72 main deterministic trajectories and 12 no-trigger controls | Engineering/protocol evidence only |
| Early full-timeline index | 4,283 temporal segments across the 5 videos; 5 retained provisional evaluation families after migration | No human-valid family |
| Learned-retrieval wave | 3,433 visual source-frame vectors, 4,283 pooled visual records, 3,428 fine audio vectors, 855 context audio vectors; 64 metric rows, 40 paired rows, 132 retrieval/probe rows | Low-N, retrieval-only, machine-provisional |
| Event-centric development source | Exact source acquired; full-timeline pipeline complete; repaired miner produced 20 V+A machine leads, including 8 structurally far/multi-hop leads | All 20 remain `REPAIR`; accepted family count 0 |
| Machine-provisional rehearsal bundle | 20 frozen development families and 56 evidence handles over 28 unique target intervals | Accepted SES count 0; H-tier count 0 |
| Learned controller/finalizer stack | Direct-A/V, RAG, ReAct, sufficiency, structured finalization, observed-evidence lock, and restoration adapters exist | No authorized scientific-family run |

Current strong-baseline gate outcomes should be read separately from model
acquisition:

| Baseline line | Technical state | Competence state |
|---|---|---|
| Learned visual/audio retrieval | Pinned snapshots and real retrieval wave complete | Retrieval readiness only; no end-to-end competence claim |
| Granite controller/finalizer line | Snapshot acquisition and adapter development completed | Frozen competence and unseen holdout: NO-GO |
| Qwen3 controller fallback line | Adapter/holdout machinery completed | Unseen holdout: NO-GO |
| Qwen2.5-Omni direct-A/V line | Acquisition and technical runtime readiness completed | Frozen direct-A/V competence: NO-GO |

These NO-GO results are retained evidence. They cannot be replaced by claiming
that a technically loadable model is scientifically competent.

## 6. What the completed engineering experiments established

### 6.1 Bounded real-A/V MVP

The first real-media milestone established that the protocol can be executed
on actual long A/V:

- exact media binding and decoding;
- CLEAN/BLOCKED/RESTORED state construction;
- fixed-budget deterministic policy probes;
- action-level trajectories;
- claim/citation validation;
- no-trigger controls; and
- deterministic replay and independent metric recomputation.

Its scientific decision remained provisional and inconclusive because the
families were machine-adjudicated, few, and not evaluated with learned agents.

### 6.2 Full-timeline migration

Moving from selected windows to complete timelines showed why bounded retrieval
can overstate task ease. It also exposed important engineering defects that
were caught through independent NO-GO and repair cycles, including index
semantics, metric scope, and artifact binding.

This stage strengthened the repository's audit discipline but did not produce
human-valid benchmark families.

### 6.3 Learned-retrieval wave

The retrieval wave showed real, reproducible ranking differences between
learned encoders and controls. Most observed directions on the tiny provisional
set were not improvements. The correct interpretation is a source-scoped
diagnostic about retrieval behavior, not a headline that one family of models
is universally better or worse.

## 7. R21, R22, and the R23 split

### 7.1 R21: real authoring attempt, fail closed

R21 was a real authoring attempt in the development lineage. Its retained
audit recorded independent failures in:

- duplicate or lexical collision;
- embedding collision; and
- far-family semantic contract.

R21 is historical evidence, not a successful authoring result. Later repairs
do not overwrite its outcome.

### 7.2 R22: real one-shot attempt, permanently closed

R22 consumed its one authorized attempt. The top-level runtime exception was
traced to an overly strict local-pronoun validator, but deterministic
reconstruction also found independent scientific blockers:

- three exact duplicate query pairs;
- their corresponding same-kind near collisions;
- two cross-family compositional similarity exceedances; and
- one cross-family ambient semantic-tuple duplicate.

The binding decision is:

```text
R22_SCIENTIFIC_NO_GO_PERMANENT_R23_REQUIRED
```

Consequences:

- R22 must not be rerun;
- its authorization receipt must not be reused;
- no reserve may be substituted or redrawn as an R22 fallback;
- retained outputs may not be replayed into a success; and
- future work must be a separately preregistered and authorized R23
  experiment.

This is a permanent scientific NO-GO, independent of the validator defect.

### 7.3 R23-A: implementation repair plus deterministic replay

R23-A repaired the local binding and semantic-gate implementation and added a
model-free replay of the retained R22 evidence. The replay:

- reconstructed the accepted factors and final rows;
- confirmed exact binding and provenance;
- accepted the sentence-local pronoun case; and
- reproduced the independent collision blockers.

Therefore:

```text
R23_A_IMPLEMENTATION_READY
R22 replay decision = NO-GO
```

R23-A is not a model run, a new scientific attempt, or a Canary GO.

### 7.4 R23-B v9: design GO only

R23-B v9 closes a set of fail-closed protocol details for a future fresh
global-distinctiveness experiment, including canonical surrogate handling,
dependency binding, and a principal-registry trust boundary.

Its decision is:

```text
R23_B_V9_DESIGN_READY
```

This means the design artifacts and model-free preflight surface are ready.
It does **not** mean authorization, execution, external signature, human
identity proof, or scientific GO.

### 7.5 R23-C: implementation ready, not run

R23-C is a deliberately exposed development-calibration canary built on
already exposed R21/R22 identities. It is designed to measure query
identifiability before learned retrieval and can never become a fresh
untouched evaluation.

Its status is:

```text
R23_C_EXPOSED_CALIBRATION_IMPLEMENTATION_READY
```

No real R23-C model run has occurred. A future run would still need separate
one-shot authorization and could produce only a machine-calibration result,
not scientific GO.

## 8. Human-validity and Gate A state

The current source and packet work has produced prospective matrices, blank
human forms, role separation, exposure ledgers, and fail-closed importers.
None of that is a completed human result.

Current counts:

```text
human observations: 0
human decisions:    0
accepted SESs:      0
H1 families:        0
H2 families:        0
scientific episodes: 0
```

Gate A remains:

```text
MINI_PILOT_INPUT_READY = REPAIR
```

The primary blockers include source-specific authority, completed semantic
prescreens, completed audio review where applicable, fresh human authoring,
alternative-route closure, missing modality/profile strata, calibrations,
reviewer readiness, and leakage/causal interlocks.

The repository contains several artifacts named READY. In this area, READY
usually means a builder, packet set, schema, or governance surface is complete.
It does not imply Gate A GO.

## 9. Untouched-test ledger boundary

The current untouched-test work has a valid public commitment and an
independently audited sealed private roster spanning three dataset lineages.
This is a governance achievement, but the exact boundary is strict:

- identities remain private;
- selection was commitment-only and content-blind;
- all groups remain conditional;
- construction is locked;
- distribution is locked;
- unlock is not authorized;
- rights, exact source access, selected-object A/V access, and technical
  preflight remain incomplete for at least part of the roster; and
- no test annotation, evaluation, release, or scientific claim is authorized.

The ledger protects a possible future evaluation set. It is not evidence that
such a set currently exists in usable form.

## 10. What is known, unknown, and prohibited

### Established

- The matched protocol is technically implementable.
- Full-timeline A/V indexing and retrieval can be audited and replayed.
- Claim-level grounding and final-point stopping semantics can be represented.
- Learned retrievers can produce materially different evidence rankings.
- Fail-closed governance can preserve negative authoring results and untouched
  identities.

### Still unknown

- Whether enough source-diverse H2 families can be created under unchanged
  criteria.
- Whether strong learned systems show meaningful Acquire/Ground/Act separation.
- Whether intervention effects persist beyond development sources.
- Whether non-retrieval failures remain after conditioning on acquisition.
- Whether the required source, rights, reviewer, and compute path is practical
  at CVPR scale.

### Prohibited claims

- human gold or benchmark-valid families;
- proven modality necessity;
- learned-agent recovery success;
- controller superiority;
- broad source or domain generalization;
- public benchmark availability;
- first, unique, or SOTA positioning; and
- converting R21/R22 failures into success through repair or replay.

## 11. CVPR path

The CVPR route is dependency-driven:

1. **Gate A:** produce an authorized, source-valid 12-family input and trained
   human workflow.
2. **Gate B:** run construct validation and obtain sufficient H1/H2 yield
   without weakening criteria.
3. **Gate C:** pass strong learned-baseline competence and unseen holdout.
4. **Causal interlock:** freeze state surfaces, restoration/no-trigger
   mechanics, assignments, sessions/caches, and leakage tests.
5. **Gate D:** run the first authorized H2 learned-agent mini diagnostic.
6. **Scale decision:** proceed only if the mini diagnostic shows
   paper-relevant failure separation across sources.
7. **Corpus and test freeze:** reach the source-disjoint H2 target while
   preserving the untouched ledger.
8. **Main evaluation and paper claim audit.**

The preferred paper-scale target remains at least 60 H2 families across at
least 30 source groups with 12 untouched test groups. A smaller fallback is
descriptive and cannot support controller-superiority claims.

The next migration owner should not start with bulk model runs or paper prose.
The critical path is human construct validity and baseline competence.

## 12. Quick navigation

### Thesis and governance

- [`docs/project_charter.md`](../project_charter.md)
- [`docs/paper/cvpr_thesis_and_evidence_gates.md`](../paper/cvpr_thesis_and_evidence_gates.md)
- [`docs/paper/cvpr_pivot_v2_addendum.md`](../paper/cvpr_pivot_v2_addendum.md)

### Related work and positioning

- [`docs/research/novelty_boundary.md`](../research/novelty_boundary.md)
- [`docs/research/related_work_matrix.md`](../research/related_work_matrix.md)

### Real-media and learned-retrieval milestones

- [`docs/review/core_milestone_completion_audit.md`](../review/core_milestone_completion_audit.md)
- [`docs/review/scale1a_final_audit.md`](../review/scale1a_final_audit.md)
- [`docs/review/scale1b_wave_r_final_audit.md`](../review/scale1b_wave_r_final_audit.md)

### Human validity and Gate A

- [`docs/review/mini_pilot_family_candidates_scientific_audit.md`](../review/mini_pilot_family_candidates_scientific_audit.md)
- [`docs/review/pilot_v4_candidate_integration_audit.md`](../review/pilot_v4_candidate_integration_audit.md)
- [`docs/review/pilot_v4_human_packets_audit.md`](../review/pilot_v4_human_packets_audit.md)

### R21/R22/R23

- [`docs/review/p23_102_canary2_r22_terminal_audit.md`](../review/p23_102_canary2_r22_terminal_audit.md)
- [`docs/design/p23_102_query_authoring_v2.md`](../design/p23_102_query_authoring_v2.md)
- [`docs/design/p23_102_global_distinctiveness_v9.md`](../design/p23_102_global_distinctiveness_v9.md)
- [`docs/design/p23_102_r23c_exposed_calibration_canary.md`](../design/p23_102_r23c_exposed_calibration_canary.md)

### Untouched-test governance

- [`docs/review/untouched_test_group_ledger_v3_1.md`](../review/untouched_test_group_ledger_v3_1.md)
- [`docs/review/untouched_test_group_ledger_v3_1_audit_addendum.md`](../review/untouched_test_group_ledger_v3_1_audit_addendum.md)

### Handoff

- [`docs/overview/next_steps_after_migration.md`](next_steps_after_migration.md)
