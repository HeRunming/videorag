# Task 99 — Scale-1A diagnostic experiment contract repair

Date: 2026-09-11

## Decision

```text
SCALE1A_ENGINEERING_GO
SCALE1A_DIAGNOSTIC_INCONCLUSIVE
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

Task 99 changed only the derived experiment/evaluation layer. Five source
videos, pinned models, the Pilot-0 trust anchor and all 20 expensive media
inference checkpoints remain unchanged; checkpoint hashes match 20/20. The
frozen CLIP text-query ranker was executed, but no Whisper/AST inference or
CLIP frame-embedding checkpoint was recomputed.

## Contract repairs

### Query Reformulation Gain

The evaluator now derives search rounds from actual action/response logs. It
persists eligibility, search count, first-round end step, first-round support
coverage, final support coverage and gain. Results: **76/76**
eligible rows have a non-null value and **12** show positive gain.

### Modality switching

Switches are recomputed over the exact ordered sequence of content searches
and successful citable observations (`inspect_clip`/`read_transcript`). Status
and finalize actions are excluded. **36** trajectories contain at least one switch.

### RESTORED no-trigger controls

Exactly **10** matched controls were added: five retained families times two
agentic policies. They start from RESTORED's blocked pre-trigger state, use the
same budget and trigger-seeking action prefix, disable only restoration, fire
zero restoration events and fail complete support acquisition in 10/10 cases.

### True top-5 displacement

The intervention is fail-closed. Only r016 and r017 have at least five admitted
machine-validated negatives in a support-bearing modality. Visual-only
families remain ineligible; provisional visual candidates are not used.
Eight matched trajectories were run. All 8 prove accepted support moved outside
top-5: r016 `1 -> 20`; r017 `1/4 -> 19/20`. Recovery-enabled rows reacquire
evidence in 4/4 and recover fully supported answers in 2/4; disabled controls
reacquire evidence in 0/4.

## Regenerated outputs

- 120 ordinary C/B/R trajectories
- 10 RESTORED no-trigger controls
- 8 eligible displacement/control trajectories
- **138 trajectories, 654 actions**
- ordinary summaries exclude control/displacement rows
- control/displacement rows retain explicit eligibility and denominators

## Verification

```text
Focused tests: 36 passed
Full relevant regression: passed at 100%
Strict verifier: passed=true, failures=[]
Deterministic replay: all_match=true, checkpoint_count=20
```

The verifier now independently recomputes reformulation gain and modality
sequences, requires the exact RESTORED controls, proves top-K displacement,
and rejects provisional visual negatives in validated-negative metrics. Prior
Task-96/98 checks were retained.

## Why diagnostic status remains inconclusive

The contract is now executable and auditable, but scientific GO is not forced:
r007 still fails the frozen Recall@5 shortcut criterion; displacement is valid
for only two families; the sample is low-N and machine adjudicated; policies
are deterministic rather than learned; and no human gold or modality necessity
is available.

```text
MACHINE_ADJUDICATED_PROVISIONAL_MVP
human_reviewed=false
gold_annotation=false
learned_model_evaluation=false
Modality Recall=null
```
