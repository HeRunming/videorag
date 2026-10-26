# AV-TRACE authoritative CVPR state

**As of:** 2026-10-23  
**Purpose:** single current-state index for migration and post-migration work  
**Authority:** this document does not authorize model, media, human-review, or
scientific execution

## 1. Current decision

AV-TRACE has a paper-worthy diagnostic thesis and mature audited engineering,
but it does not yet have the human-valid corpus or learned-agent evidence
required for a CVPR main submission.

```text
H1 families = 0
H2 families = 0
accepted SESs = 0
Gate A = REPAIR
Gate B = NOT_RUN
Gate C = NOT_READY
scientific episodes = 0
PAPER_CLAIM_READY = false
FINAL_BENCHMARK_VALIDATED = false
```

The canonical paper-facing H2 term is:

```text
H2_HUMAN_ADJUDICATED_SATURATION_AUDITED
```

Historical artifacts that say `H2_HUMAN_ADJUDICATED_GOLD` are not the current
paper-facing terminology and require contract alignment before new human
imports.

## 2. Scientific thesis

AV-TRACE evaluates whether a long-video audiovisual agent:

1. acquires a minimally sufficient multimodal evidence route;
2. uses and cites the evidence supporting each atomic claim;
3. recognizes insufficiency or access failure;
4. avoids premature stopping;
5. recovers after a registered route is restored; and
6. avoids false recovery in the matched `NO_TRIGGER` condition.

The primary diagnostic decomposition is:

```text
Acquire -> Ground -> Act
```

The matched states are:

```text
CLEAN / BLOCKED / RESTORED / NO_TRIGGER
```

Answer accuracy is currently a hypothesis-bearing motivation, not yet an
empirical learned-agent conclusion.

## 3. What is already proven

### 3.1 Engineering and protocol

- Real long audiovisual media can be acquired, hash-bound, indexed over the
  full timeline, replayed, and evaluated with action-level traces.
- Matched access states, common supported-answer endpoints, claim/citation
  scoring, final-point route certificates, typed failures, and no-trigger
  controls are implemented.
- Model-free construct-validation schemas, six-role packet construction,
  assignment/exposure ledgers, adjudication ordering, and post-adjudication
  saturation checks exist and have fail-closed tests.
- Learned visual/audio retrieval has been run on real but
  machine-provisional development families.
- Grounded-generator, learned-ReAct, and evidence-sufficiency adapters exist
  and have exercised real model paths.
- Public repository and small-file migration packages are content-ready,
  subject to the owner-selected code license and data-rights decisions.

### 3.2 Allowed empirical wording

The strongest current empirical statement is:

> On a small machine-provisional development set, pinned learned visual and
> audio encoders reproducibly change evidence rankings and do not
> automatically outperform task-shaped controls.

This is a development diagnostic. It is not a source-disjoint, H2, modality
necessity, end-to-end agent, or model-superiority result.

## 4. What is not proven

The repository does not currently support claims that:

- existing questions or evidence sets are human-valid benchmark gold;
- modality necessity or minimality has been established;
- all alternative sufficient evidence routes have been closed;
- any learned ReAct or sufficiency controller is competent;
- learned agents recover, stop correctly, or diagnose insufficiency;
- answer accuracy empirically hides support/citation failures;
- the sufficiency controller improves over ReAct;
- results generalize across source groups;
- the benchmark media or source-derived artifacts are publicly
  redistributable.

## 5. Data and source state

There are currently 15 exact local development source groups with complete
timeline indexes:

| Lineage | Source groups | Current use |
|---|---:|---|
| NOAA | 5 | development-touched |
| Oxford/MIT/Yale lecture sources | 4 | development/calibration |
| EPIC | 3 | development; P23 is future-test-ineligible |
| CaptainCook4D | 3 | development |

None is an admitted untouched scientific test source. Accepted families,
accepted SESs, H1, and H2 all remain zero.

Existing provisional registries overlap and must not be summed as independent
benchmark families. They are useful for engineering, failure discovery,
source prescreening, and labor estimation only.

Preferred final corpus:

```text
>= 60 H2 families
>= 30 source groups
>= 12 untouched test source groups
12/6/12 whole-source train/dev/test groups
approximately 24/12/24 H2 families
<= 3 H2 families per source
>= 4 capture formats
presentation-wrapped families <= 25%
```

Fallback:

```text
>= 60 H2 / >= 20 sources / >= 8 untouched test sources
```

The fallback supports only a narrow source-bounded descriptive diagnostic. It
does not authorize controller-superiority, population ranking, or broad
modality/mechanism generalization.

## 6. Learned-system state

| Component | Adapter | Real model path | Competence | Scientific evidence |
|---|---|---|---|---|
| Grounded generator | ready | exercised | partial finalizer signal; no integrated GO | none |
| Learned ReAct | ready | exercised, failed closed | NO-GO | none |
| Evidence-sufficiency agent | ready | exercised, failed at finalization | NO-GO | none |
| Native/direct A/V | implemented | exercised | NO-GO | none |

Tested Qwen, Granite, Qwen3, Qwen2.5-Omni, and external-gateway
configurations do not constitute approved paper systems. Previously consumed
holdouts cannot be prompt-tuned and rerun as unseen competence.

Gate C requires a new adapter/runtime version, a new independently frozen
source-free fictional suite, one-shot execution, raw-output sealing, and an
independent audit. Minimum current floors include:

- at least 48 cases;
- at least 90% valid structured calls;
- at least 85% first-action accuracy;
- at least 75% exact six-field state;
- at least 80% on each state component;
- at least 80% complete-evidence supported answers;
- at least 80% correct blocked/partial non-answer;
- at least 80% restoration reacquisition;
- zero unsupported required claims;
- zero evaluator-private exposure;
- zero deterministic answer/citation substitution.

## 7. Construct-validity contract repair required before humans

Do not distribute the current blank Pilot-v4 packets. Before any human review,
complete the following P0 contract alignment:

1. add explicit `source_group_id` and lineage/participant grouping rather
   than treating `source_id` as the group;
2. align schemas/importers with
   `H2_HUMAN_ADJUDICATED_SATURATION_AUDITED`;
3. implement a latest Gate A/B evaluator containing every post-pivot
   condition;
4. add a completed-authoring to construct-registry bridge;
5. add a completed Task194/audio-prescreen import path;
6. freeze reviewer calibration and qualification thresholds prospectively.

Existing importer output alone must not be treated as final Gate B authority
until these changes are complete.

## 8. Gate A and Gate B targets

### Gate A input

```text
6 frozen source groups
12 substantive candidate families
2 families per source group
2 excluded calibration families
>= 8 unique trained reviewers
72 real role assignments
```

All exact media, lineage, processing/annotation authority, privacy/component,
prescreen, authoring, exposure, and intervention-feasibility records must be
complete before packet distribution.

### Gate B GO

```text
12/12 complete
H1 >= 9/12
H2 >= 8/12
pair-isolation failures <= 1/12
systematic minimality/modality failures <= 3/12
critical governance holds = 0
```

Additional conditions:

- at least two accepted non-NOAA source groups;
- at least three accepted event-centric source groups, or prospectively
  remove the broad claim;
- ambient and `V+S+A` H2 coverage, or prospectively remove those strata;
- every saturation discovery reopened, repaired, readjudicated, and
  re-audited;
- measured yield and labor support scaling without weakening the construct.

The 12-family output remains:

```text
LOW_N_MINI_PILOT_DESCRIPTIVE_ONLY
```

## 9. End-to-end mini diagnostic

Only after Gates B and C and the causal-interlock audit are GO, run:

### Required learned systems

1. direct long-context A/V;
2. single-shot learned RAG;
3. learned ReAct;
4. learned evidence-sufficiency agent.

### Required diagnostics

- oracle-H2 evidence generator;
- partial-evidence generator;
- deterministic ReAct and sufficiency controls;
- `F-CTRL` and `F-VA` retrieval sensitivity.

### Required states and mechanisms

```text
CLEAN / BLOCKED / RESTORED / NO_TRIGGER
SILENT_ROUTE_WITHHOLDING / EXPLICIT_CHANNEL_OUTAGE
```

Gate D should require at least:

- intervention-aware separation across at least three source groups;
- nonzero answer-versus-support or citation divergence;
- at least two non-retrieval failure classes, each across at least two
  sources;
- complete invalid/missing-run accounting;
- no finding driven by one family or source;
- independent replay, metric, leakage, and route-certificate audit.

If comparing sufficiency with ReAct, a directional improvement claim requires:

```text
CLEAN supported-answer loss <= 0.10 absolute
and >= 0.15 absolute improvement on a preregistered intervention metric
and no single-source explanation
```

## 10. Post-migration execution order

```text
P0  Restore and verify code, protected manifests, and authorized assets
P1  Align construct and paper contracts
P2  Freeze analysis/table schemas before outcomes
P3  Run local-source human prescreen; selectively acquire only if needed
P4  Freeze the exact Gate-A 6-source/12-family input
P5  Run the Gate-B human construct pilot
P6  In parallel, build and run a new Gate-C competence suite
P7  Run the low-N H2 end-to-end diagnostic only after B/C/interlock GO
P8  Scale only if Gate D shows cross-source diagnostic value
P9  Freeze >=60-H2 source-disjoint corpus and main evaluation
P10 Independent result, claim, statistics, rights, and release audit
P11 Write final Results, Abstract, and Conclusion last
```

The immediate critical path is `P1 -> P4/P5` and `P6` in parallel. Continuing
single-source P23 authoring/retrieval work is lower priority because it cannot
produce source-disjoint H2 evidence.

## 11. Paper-material status

Ready as foundations:

- thesis and problem definition;
- Acquire/Ground/Act protocol;
- C/B/R/N intervention semantics;
- metric definitions and prospective statistical plan;
- engineering/reproducibility narrative;
- audit, limitations, and rights boundaries.

Still empty or result-gated:

- corpus and construct statistics;
- construction funnel and human agreement;
- competent system contract;
- main Acquire/Ground/Act dashboard;
- matched intervention effects;
- answer/support divergence and failure-stage findings;
- ablations and source-level uncertainty;
- result figures;
- final abstract and conclusion.

Before viewing scientific test outcomes, freeze table/figure schemas,
denominators, qualitative-example selection, statistical code, and
claim-to-cell mappings.

## 12. Authoritative and historical documents

Current controlling documents:

- `docs/overview/research_state_2026-10-23.md`
- this state index;
- `docs/paper/cvpr_pivot_v2_addendum.md`
- `docs/paper/av_trace_cvpr_main_blueprint_v2.md`
- `docs/paper/source_disjoint_scaleup_wave_v1.md`
- `docs/overview/next_steps_after_migration.md`
- `data/rehearsal_plan/post_migration_cvpr_work_queue.json`

Historical registries and reports remain immutable evidence. When their
terminology or status conflicts with this index, do not rewrite the historical
artifact; use a superseding versioned contract or ledger.

R22 remains permanently:

```text
R22_SCIENTIFIC_NO_GO_PERMANENT_R23_REQUIRED
```

It must not be rerun, redrawn, or semantically installed as success.
