# Scale-1A full-timeline multimodal MVP — post-Task-99 decision

Date: 2026-09-11

## Final decision

```text
SCALE1A_ENGINEERING_GO
SCALE1A_DIAGNOSTIC_INCONCLUSIVE
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

Task 99 repairs the three derived-layer contract defects identified by the
Task-98 independent audit. Source media, model snapshots, the Pilot-0 trust
anchor, and all 20 expensive Whisper/AST/CLIP checkpoints were left unchanged.
Task-96 and Task-98 remain historical red-team records.

## Repaired diagnostic contracts

- Query Reformulation Gain is recomputed from actual search/observation action
  logs. Each row records first-round coverage, final coverage, eligibility and
  gain. There are 76 eligible trajectories and 76 non-null values; 12 gains
  are positive.
- Modality switching uses the ordered modality-bearing sequence of content
  searches plus successful citable `inspect_clip`/`read_transcript` actions.
  Status and finalize actions are excluded. Thirty-six trajectories contain at
  least one switch.
- Ten matched RESTORED controls were executed: 5 retained families x 2 agentic
  policies with `restoration_enabled=false`. All execute the same pre-trigger
  action prefix, fire no restoration event, and fail to acquire a complete
  support set.
- True top-5 displacement is restricted to the two families with admitted,
  machine-validated speech negatives (`r016`, `r017`). Eight matched rows were
  run. Every first relevant ranking moves all accepted support below top-5:
  r016 rank 1 -> 20 and r017 ranks 1/4 -> 19/20. Recovery-enabled rows reacquire
  evidence in 4/4 cases and recover a supported answer in 2/4; disabled controls
  reacquire evidence in 0/4. Visual-only families remain ineligible rather than
  using provisional visual candidates.

## Regenerated scale

- 120 ordinary C/B/R trajectories
- 10 RESTORED no-trigger controls
- 8 eligible hard-negative displacement/control trajectories
- 138 total trajectories and 654 recorded actions
- 5 retained families; r014 remains excluded
- 20/20 checkpoint hashes unchanged

Control and displacement rows are separately labeled and excluded from ordinary
C/B/R aggregates. `Modality Recall` remains null because modality necessity is
not human validated.

## Verification

```text
Focused tests: 36 passed
Full relevant regression: passed (100%)
Strict verifier: passed=true, failures=[]
Checkpoint-derived replay: all_match=true, checkpoint_count=20
```

The diagnostic result remains inconclusive rather than forced to GO. Although
displacement recovery/control, action-level reformulation metrics and matched
RESTORED controls now work, `r007` still fails the frozen Recall@5 shortcut
criterion, only two families are eligible for validated-negative displacement,
and the evaluation remains low-N, deterministic, machine-adjudicated and not
human-gold.

```text
MACHINE_ADJUDICATED_PROVISIONAL_MVP
human_reviewed=false
gold_annotation=false
learned_model_evaluation=false
```
