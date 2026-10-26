# P23_102 diagnostic experiment and finding table template

**Frozen:** 2026-10-14  
**Status:** `PREREGISTERED_TEMPLATE__NOT_EXECUTED`  
**Registry:** `data/rehearsal_plan/p23_102_diagnostic_finding_registry_v1.json`  
**Scope:** future machine-provisional P23_102 development rehearsal only  
**Results:** none; every result cell below is intentionally blank

**No fabricated results:** this artifact contains schemas and decision rules,
not observations.

## 1. Paper boundary

This template preregisters how a future P23_102 development rehearsal would be
tabulated. It does not authorize media access, model execution, family
construction, intervention execution, or scientific interpretation.

P23_102 is one development source group (`P23`). Every P23_102 family, clip,
index, annotation, encode, transcript, and derivative therefore belongs to the
same source cluster. Results produced from this source:

- must carry `LOW_N_MACHINE_PROVISIONAL_P23_102_DEVELOPMENT_REHEARSAL`;
- are descriptive engineering diagnostics, not human-valid benchmark results;
- cannot establish source-disjoint generalization, population ranking,
  controller superiority, modality generalization, or a causal paper claim;
- cannot be pooled with H2 evaluation results; and
- must use “machine-provisional complete evidence” rather than “gold” unless a
  later, separate artifact establishes
  `H2_HUMAN_ADJUDICATED_SATURATION_AUDITED`.

The frozen paper position remains a benchmark-and-diagnostic-protocol paper,
not a controller-method paper. Null, adverse, unavailable, invalid, and
structurally ineligible outcomes remain visible.

## 2. Exact experimental rows

The primary table has exactly these four system rows, in this order:

| Row ID | Paper label | Role | Acquire | Ground | Act / staged R–N |
|---|---|---|---|---|---|
| `direct_long_context` | Direct LC | Non-agent endpoint baseline | No search; deterministic chronological modality-round-robin packing | One shared grounded-finalizer call | Act metrics null; exogenous R–N structurally ineligible before assignment |
| `single_shot_rag` | Single-shot RAG | Nonadaptive learned retrieval baseline | One frozen query per visual, speech, and ambient channel; frozen fusion | Shared grounded finalizer over acquired observations | Staged but no post-checkpoint search or reformulation |
| `learned_react` | Learned ReAct | Adaptive tool-using baseline | Model-authored bounded search, inspection, status, and reformulation | Shared grounded finalizer and citation validator | May continue or recover after the neutral checkpoint |
| `learned_evidence_sufficiency` | Sufficiency agent | Adaptive explicit-sufficiency baseline | Same public backend, tools, observations, and budget as ReAct | Same finalizer and validator as ReAct | Public claim coverage, missing modality/hop, sufficiency, and recovery state |

No deterministic controller, oracle/complete-evidence diagnostic, or
partial-evidence diagnostic may be relabeled as one of these four learned
rows. Complete-versus-partial evidence is an auxiliary generator diagnostic,
not a fifth primary system.

## 3. Arms and intervention mechanisms

Every applicable `family × mechanism × system` block uses:

| Arm | State | Access/event definition | Intended endpoint |
|---|---|---|---|
| `C` | `CLEAN` | At least one machine-provisional accepted SES is reachable; no scheduled event | Supported answer |
| `B` | `BLOCKED` | Registered route is inaccessible; no scheduled event | Calibrated insufficiency or access-failure diagnosis |
| `R` | `RESTORED` | Same blocked prefix as N; byte-identical neutral checkpoint; evaluator-private route restored | Supported answer |
| `N` | `NO_TRIGGER` | Same blocked prefix and byte-identical checkpoint as R; route remains blocked | Blocked continuation, without false recovery |

The mechanisms are separate:

1. `SILENT_ROUTE_WITHHOLDING`: a registered necessity group and deterministic
   leaks are withheld without an explicit outage marker.
2. `EXPLICIT_CHANNEL_OUTAGE`: one registered channel returns the frozen typed
   unavailable response.

The two mechanisms have separate denominators, tables, intervals, and finding
decisions. A pooled primary restoration effect is prohibited.

The exogenous event is fixed at zero-based action index 4, after four completed
action/response cycles and before the fifth model decision. `R` and `N` use a
single blocked prefix followed by fresh isolated continuations. The public
prefix and checkpoint bytes must match. Restoration is independent of action
identity, system identity, output, correctness, and `get_channel_status`.

## 4. Metric families

### 4.1 Acquire

Primary:

- `evidence_recall`;
- `all_evidence_success`.

Secondary:

- `retrieval_recall_at_5`;
- `retrieval_recall_at_20`;
- `all_ses_coverage`;
- `necessity_route_coverage`;
- `complete_ses_reacquired`;
- `candidate_modality_routing_coverage`;
- first accepted evidence rank, MRR, and retrieval burden.

Direct LC Acquire values are null because exposure is not policy-selected
retrieval.

### 4.2 Ground

Primary:

- `answer_score`;
- `citation_f1`;
- `supported_claim_rate`;
- `supported_answer_endpoint`.

Secondary:

- answer-correct but unsupported;
- correct-answer/wrong-citation;
- unsupported-claim rate;
- partial-evidence unsupported completion;
- calibrated non-answer/abstention;
- oracle/complete-evidence grounding ceiling.

Search pointers are not citations. Only acquired citable observation IDs count.

### 4.3 Act

Primary:

- `success_at_budget`;
- `premature_stop`;
- `recovery`.

Secondary:

- false sufficient;
- calibrated refusal;
- access-failure diagnosis;
- modality-switch opportunity and switch completion;
- restored-route inspection;
- trigger-to-reacquisition actions/cost;
- post-event cost;
- no-trigger false recovery.

Act values are null for a row that has no legal staged action trajectory.

## 5. Estimands and uncertainty

The common positive endpoint is one only when the assigned run is valid and
in budget, emits `sufficient`, answers all required claims correctly, asserts
no forbidden/contradictory/unknown claim, and supports every required claim
with acquired citations instantiating a registered machine-provisional support
derivation.

For P23_102, point estimates are:

1. episode outcomes;
2. required within-family arm, system, or diagnostic-condition contrasts;
3. equal-weight averages over eligible P23_102 families.

The source-group aggregation step is displayed but cannot estimate
between-source uncertainty because there is only one source group.

The development interval is a paired family-cluster percentile bootstrap:

- at least 10,000 resamples;
- seed `2310220261014`;
- resample families with replacement;
- carry every paired system, arm, mechanism, and diagnostic condition for a
  selected family together;
- report 95% percentile intervals;
- never resample individual episodes or actions independently.

With fewer than five eligible paired families, report the point estimate,
numerator, denominator, and `CI_NOT_REPORTED__N_LT_5`. With five or more
families the interval is still descriptive. A source-cluster paper interval
requires a future source-disjoint corpus and is not approximated here.

## 6. Missing, invalid, and ITT policy

- All preregistered assigned runs remain in intention-to-evaluate/ITT.
- Every assigned invalid run contributes zero to positive success endpoints.
- For lower-is-better adverse endpoints, report the semantic rate, the invalid
  count, `event_or_invalid`, and a valid-run-only sensitivity.
- An R/N prefix that terminates before the event remains in both assigned arms;
  its paired R–N difference is zero.
- Event not reached, route not inspected, and evidence not reacquired remain
  in the R/N ITT denominator.
- Structural ineligibility frozen before assignment is null with a reason code,
  receives no synthetic outcome, and is not missing data.
- A missing or invalid feasible-route certificate makes premature stop null.
  If certificate coverage is not 100% for the preregistered eligible
  denominator, the finding is descriptive/inconclusive only.
- Evaluator or evidence-registry defects quarantine the affected family across
  all systems, arms, and mechanisms. Original-assignment and corrected
  denominators are both reported.
- No outcome-based replacement, silent retry selection, available-case pair
  dropping, or post-outcome redefinition is allowed.

## 7. Main paper-facing table schemas

All cells use `—` until an authorized future rehearsal writes a versioned
result artifact.

### Table P23-A — Frozen matrix and validity accounting

One row per `system × mechanism × arm`.

| system_id | mechanism | arm | assigned_n | structurally_ineligible_n | valid_n | invalid_n | early_terminal_n | event_reached_n | prefix_integrity_n | status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| — | — | — | — | — | — | — | — | — | — | — |

### Table P23-B — Acquire / Ground / Act dashboard

One row per `system × mechanism × arm × metric_id`.

| stage | metric_id | system_id | mechanism | arm | eligible_n | numerator_or_mean | estimate | ci95_low | ci95_high | invalid_n | null_reason | warning |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| — | — | — | — | — | — | — | — | — | — | — | — | — |

### Table P23-C — Mechanism-specific exogenous restoration ITT

Only staged systems are assigned to the primary R/N estimand. Direct LC is
shown as structurally ineligible, not as zero.

| estimand_id | mechanism | system_id | assigned_pairs_n | early_terminal_pairs_n | invalid_pairs_n | R_supported_rate | N_supported_rate | R_minus_N_ITT | ci95_low | ci95_high | interpretation |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `P1_RN_SILENT_ROUTE_WITHHOLDING_ITT` | silent | — | — | — | — | — | — | — | — | — | descriptive only |
| `P2_RN_EXPLICIT_CHANNEL_OUTAGE_ITT` | explicit | — | — | — | — | — | — | — | — | — | descriptive only |

### Table P23-D — Preregistered diagnostic findings

| finding_id | criterion_status | effect_or_rate | ci95 | eligible_families_n | source_groups_n | invalid_n | objective decision | permitted wording |
|---|---|---:|---|---:|---:|---:|---|---|
| `P23F-01-RANKING-INVERSION` | — | — | — | — | 1 | — | — | — |
| `P23F-02-RK-GAIN-GROUND-LOSS` | — | — | — | — | 1 | — | — | — |
| `P23F-03-PREMATURE-STOP-PARTIAL` | — | — | — | — | 1 | — | — | — |
| `P23F-04-MODALITY-SWITCH-FAILURE` | — | — | — | — | 1 | — | — | — |
| `P23F-05-RN-RESTORATION-ITT` | — | — | — | — | 1 | — | — | — |
| `P23F-06-COMPLETE-VS-PARTIAL` | — | — | — | — | 1 | — | — | — |
| `P23F-07-COST-BENEFIT-HOP-MODALITY` | — | — | — | — | 1 | — | — | — |

### Table P23-E — Complete-evidence versus partial-evidence generator diagnostic

“Gold” is not a permitted P23_102 label. The complete condition is
machine-provisional unless later H2 adjudication exists.

| generator_id | evidence_condition | eligible_n | answer_accuracy | supported_answer_rate | unsupported_completion_rate | abstention_rate | invalid_n | ci_status |
|---|---|---:|---:|---:|---:|---:|---:|---|
| — | `COMPLETE_MACHINE_PROVISIONAL_SES` | — | — | — | — | — | — | — |
| — | `PROPER_PARTIAL_BREAKS_REQUIRED_CLAIM` | — | — | — | — | — | — | — |

### Table P23-F — Cost/benefit by hop count and required modality set

Rows with fewer than five eligible paired families are
`SPARSE_STRATUM_DESCRIPTIVE_ONLY`. Empty strata are retained as unavailable.

| stratum_axis | stratum_value | system_id | comparator_id | eligible_pairs_n | delta_supported_answer | delta_tool_cost | incremental_cost_per_supported_answer | dominance_class | ci_status |
|---|---|---|---|---:|---:|---:|---:|---|---|
| `hop_count` | `ONE_HOP` | — | — | — | — | — | — | — | — |
| `hop_count` | `MULTI_HOP` | — | — | — | — | — | — | — | — |
| `required_modality_set` | — | — | — | — | — | — | — | — | — |

### Table P23-G — Failure and missingness ledger

| failure_or_exclusion_code | system_id | mechanism | arm | count | ITT treatment | affected metrics | notes |
|---|---|---|---|---:|---|---|---|
| — | — | — | — | — | — | — | — |

## 8. Objective finding rules

The JSON registry is normative. The short paper rules are:

1. **Ranking inversion:** on the same eligible families, one system has higher
   answer accuracy and lower evidence completeness than another, with both
   paired differences nonzero. Opposite-sign 95% intervals may be labeled
   “interval-stable descriptive”; otherwise label “observed descriptive.”
2. **R@K gain with Ground loss:** a frozen retrieval configuration improves
   paired recall@K but lowers the paired supported-answer endpoint under the
   same generator/finalizer and eligible records.
3. **Premature stop after partial evidence:** the system has acquired some but
   not a complete accepted SES, a valid feasible continuation exists, and it
   finalizes `sufficient` or an answer before acquiring a complete SES.
4. **Modality-switch failure:** a certified alternate required modality is
   reachable within remaining budget after failure/partial evidence in the
   current modality, but the policy never issues a valid acquisition action in
   that alternate modality before terminal output.
5. **Restoration effect:** report mechanism-specific assigned
   `RESTORED - NO_TRIGGER` differences on the common supported-answer endpoint.
   No trigger-conditioned or pooled primary replacement is allowed.
6. **Complete versus partial evidence:** compare unsupported completion and
   calibrated abstention for the same generator under deterministic complete
   and claim-breaking partial bundles. P23_102 must not call these bundles
   human gold.
7. **Cost/benefit:** within each preregistered hop and required-modality
   stratum, classify paired system differences as dominance, beneficial
   tradeoff, harmful tradeoff, or no directional difference. Infinite or
   undefined cost-per-success values remain explicit.

Any criterion may resolve to `NOT_OBSERVED`, `INCONCLUSIVE`, `UNAVAILABLE`, or
`STRUCTURALLY_INELIGIBLE`. The registry never requires a favorable result.

## 9. Exact result-artifact dependencies

Before any cell is populated, all applicable dependencies in the JSON
registry must pass. The future result package is expected at:

```text
data/restricted/p23_102_acquire_ground_act_rehearsal_v1/runs/{run_id}/
```

Required result members include:

```text
run_manifest.json
assignments.jsonl
raw_trajectories.jsonl
raw_model_calls.jsonl
citation_outputs.jsonl
r_n_prefix_pairs.jsonl
episode_metrics.jsonl
failure_ledger.jsonl
aggregate_metrics.json
replay_manifest.json
file_inventory.json
```

The complete/partial diagnostic additionally requires a frozen diagnostic
assignment manifest and per-condition outputs. No table is populated from
hand-entered numbers; each displayed value must resolve to a field and hash in
the result inventory.

## 10. Caption and wording template

> **P23_102 machine-provisional development diagnostic.** Values summarize one
> development source group and are descriptive only. Intervals, where shown,
> are paired family-cluster bootstrap intervals and do not represent
> between-source uncertainty. Invalid assigned runs remain fail-closed in
> intention-to-evaluate/ITT denominators. Silent withholding and explicit
> outage mechanisms are not pooled. No human-valid benchmark, controller
> superiority, source-generalization, or causal paper claim is made.

`P23_102_DIAGNOSTIC_FINDING_REGISTRY_READY`
