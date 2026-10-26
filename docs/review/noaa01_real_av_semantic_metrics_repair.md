# Task 90 — NOAA-01 real-A/V semantic metrics repair

**Date:** 2026-09-10  
**Stage:** `MACHINE_ADJUDICATED_PROVISIONAL_MVP`  
**Human reviewed:** `false`  
**Gold annotation:** `false`

## Decision

- **`ENGINEERING_GO`**
- **`PROVISIONAL_SCIENTIFIC_INCONCLUSIVE`**
- **`FINAL_BENCHMARK_NOT_YET_VALIDATED`**

Task 90 repairs all five semantic and policy-design defects identified by the
Task 89 independent red-team. The complete 72-trajectory real-A/V run was
regenerated twice, the second run reproduced all 13 selected artifact hashes,
and an independent implementation recomputed all 72 metric rows and all 40
aggregate rows without a mismatch.

This remains a bounded protocol MVP. It is not evidence that a learned agent
outperforms another system and it is not a publication-ready benchmark.

## 1. Explicit claim-level finalization

Every final output now contains:

- `asserted_claims`, each with a public `claim_handle`, assertion text, and
  claim-specific `citation_ids`;
- a redundant, validated `claim_to_citations` mapping;
- an optional free-text answer;
- an explicit `abstention` Boolean and sufficient/insufficient verdict.

Policies see neutral handles such as `slot.vision.1`; they never receive
evaluator claim IDs or evidence IDs. The evaluator first validates the output,
rejects unknown citations and private-ID leakage, and only then maps a public
slot to a registered provisional claim.

`Supported-Claim Rate` is now exactly:

```text
supported asserted claims / all asserted claims
```

An empty abstention is `null`. Unknown or malformed assertions remain in the
denominator and cannot be supported. Citation F1 is computed over valid
claim–evidence links rather than over an undifferentiated citation union.

## 2. Strict Success@Budget

`Success@Budget=1` now requires all of:

1. valid output/trajectory;
2. actual finalization within the step and cost budgets;
3. all required answer claims semantically correct;
4. acquisition of an accepted provisional support set;
5. valid supporting citations for every required claim;
6. no unknown, forbidden, or contradictory assertion.

The metric is explicitly marked `hypothesis_conditioned`.

## 3. Final-decision-point Premature Stop

The backend records an evaluator-private snapshot immediately before
`finalize`, including steps and cost already consumed, inaccessible channels,
blocked evidence routes, trigger state, and policy-visible pointers.

For every trajectory, the evaluator emits a route-feasibility certificate with:

- an executable tool/action suffix;
- exact remaining and required steps/cost;
- channel/route accessibility;
- whether the registered trigger could still fire;
- whether an accepted support set could still be acquired and cited.

A stop is premature only when the output is non-abstaining, evidence is
insufficient, and this exact-point continuation is certified feasible.
Abstention is not counted as premature. If eligibility cannot be proved, the
metric is `null`; if the route is proven closed, it is `0`.

All 72 regenerated trajectories have certificates. Independent checking found
zero certificate consistency errors.

## 4. Distinct evidence-sufficiency controller

The two agentic policies no longer share one implementation branch:

- `react-recovery` uses `reactive-query-reformulation/2.0`;
- `evidence-sufficiency` uses
  `explicit-evidence-sufficiency/2.0`.

The latter maintains a belief for each public claim slot, including modality,
hop index, support status, missing cause, and selected observation. It checks
channel status when visible evidence is missing or weak, avoids further search
once a slot is supported, and abstains if the visible coverage belief remains
incomplete.

Across the 18 family/state cases, the two controllers produce different tool
action sequences in **16 cases**. A focused test also verifies distinct code
paths and behavior.

This distinction was not tuned to manufacture aggregate superiority. Both
controllers still have the same All-Evidence Success, Answer Score,
Success@Budget, Premature Stop, and Recovery in this tiny pilot; their citation
and supported-claim behavior differs because the sufficiency controller
asserts only selected evidence-backed slots.

## 5. Low-N metadata

Every one of the 40 aggregate rows now contains:

```text
LOW_N_DESCRIPTIVE_PILOT
```

Metric-specific eligibility warnings remain separate, including
`NO_ELIGIBLE_ROWS`. This avoids interpreting the exact six-family/three-source
boundary as sufficient for inference.

## 6. Regenerated run

The run contains:

- 6 provisional families;
- 3 real long-video sources;
- 18 reviewed windows and 54 frozen-index records;
- 72 main trajectories;
- 12 no-trigger controls;
- 72/72 valid outputs;
- 6/6 intervention families passing;
- 12/12 no-trigger controls passing;
- maximum 9/10 tool calls;
- maximum 12.0/12.0 cost;
- unchanged source-media hashes;
- no persistent media derivative.

### Corrected aggregate results

| Policy | All-Evidence | Answer | Citation F1 | Supported Claims | Success@Budget | Premature Stop | Recovery |
|---|---:|---:|---:|---:|---:|---:|---:|
| Direct long context | N/A | 0.6667 | 0.7407 | 0.8235 | 0.6667 | 0.0000 | N/A |
| Single-shot RAG | 0.2222 | 0.2222 | 0.4444 | 0.6250 | 0.2222 | 0.3889 | N/A |
| ReAct recovery | 0.6667 | 0.6667 | 0.7407 | 0.8235 | 0.6667 | 0.0000 | 1.0000 |
| Evidence sufficiency | 0.6667 | 0.6667 | 0.6667 | 1.0000 | 0.6667 | 0.0000 | 1.0000 |

The Supported-Claim denominator differs across policies because empty
abstentions are correctly excluded (`null`). Modality Recall remains `null`
for every row because Task 85 established no human-validated modality
necessity.

## 7. Verification

Completed successfully:

```text
PYTHONPATH=src pytest -q tests_real_av
15 passed
```

```text
PYTHONPATH=src pytest -q \
  tests tests_mvp tests_media tests_agent_runtime \
  tests_validation tests_media_pipeline tests_real_av
441 collected and passed
```

Independent recomputation:

```text
72/72 metric rows, 0 mismatches
40/40 aggregate rows, 0 mismatches
72/72 route certificates, 0 consistency errors
11/11 run-manifest artifact hashes matched
```

Deterministic full replay:

```text
Second complete 72-trajectory run
13/13 selected regenerated artifact hashes unchanged
```

Restricted output permissions remain `0700` for the MVP data directory and
`0600` for restricted trajectories, runtime validation, the run manifest, and
this machine-readable audit.

## 8. Scientific interpretation

The corrected pipeline now demonstrates meaningful **descriptive** separation:

- single-shot RAG often stops with partial evidence while a continuation is
  still feasible;
- both agentic controllers recover under registered RESTORED interventions;
- the evidence-sufficiency controller abstains in all six BLOCKED cases and
  produces only supported assertions when it does answer;
- ReAct and evidence-sufficiency follow genuinely different trajectories.

The provisional scientific decision nevertheless remains
`PROVISIONAL_SCIENTIFIC_INCONCLUSIVE`, because the sample contains only six
machine-adjudicated families from three videos, retrieval is bounded to 18
windows, the controllers are deterministic protocol probes, and answers,
support sets, alternatives, minimality, and modality necessity have not been
human validated.

