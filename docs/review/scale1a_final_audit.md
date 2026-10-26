# Task 100 — Final lightweight independent Scale-1A audit

Date: 2026-09-11

## Final decision

```text
SCALE1A_ENGINEERING_GO
SCALE1A_DIAGNOSTIC_INCONCLUSIVE
FINAL_BENCHMARK_NOT_YET_VALIDATED
SCALE1A_MILESTONE_PROVEN
```

`SCALE1A_MILESTONE_PROVEN` means that the bounded Scale-1A engineering and
diagnostic protocol milestone has an executable, internally consistent and
honestly inconclusive result. It does **not** promote the current data to
human-validated gold, establish modality necessity, evaluate learned agents,
or validate the final benchmark.

This audit was read-only with respect to production and generated Scale-1A
artifacts. It did not rerun Whisper, AST, CLIP frame inference, or a fresh
model build. Only the three Task-100 audit deliverables were created.

## Independent execution

The Task-93 trust anchor passed:

```text
verified=true
inventory_count=94
source_bindings=5
```

The current strict verifier passed:

```text
decision=SCALE1A_ENGINEERING_GO
diagnostic_decision=SCALE1A_DIAGNOSTIC_INCONCLUSIVE
failures=[]
passed=true
```

Focused tests were independently rerun:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
pytest -q tests_scale1a tests/test_scale1a_model_acquisition.py

36 passed
```

The full relevant regression was also independently rerun:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
pytest -q -p no:cacheprovider \
  tests tests_mvp tests_media tests_agent_runtime \
  tests_validation tests_media_pipeline tests_real_av tests_scale1a

100% passed; exit code 0
```

Pytest did not print a numeric total in this environment, so this audit does
not invent one.

## Trajectory inventory

Independent parsing of the current restricted trajectory file found:

| Item | Result |
|---|---:|
| Total trajectories | 138 |
| Total ordered actions | 654 |
| Ordinary full-timeline CLEAN/BLOCKED/RESTORED trajectories | 120 |
| RESTORED no-trigger controls | 10 |
| Validated-negative displacement/control trajectories | 8 |

Every trajectory has ordered action/response records, actual step and cost
accounting, a final output, and a final-point route-feasibility certificate.
Action indices, cumulative cost, finalization, and budget constraints all
recomputed without mismatch.

The 120 ordinary trajectories are exactly:

```text
5 retained families ×
2 scopes ×
3 states ×
4 policies
```

The ten no-trigger and eight displacement rows are explicitly labeled and are
not included in ordinary CLEAN/BLOCKED/RESTORED aggregates.

## Task-98 blocker closure

### T98-01 — Query Reformulation Gain

Query gain was independently recomputed directly from action logs:

```text
eligible trajectories: 76
eligible with non-null value: 76/76
positive gain: 12
mismatches: 0
```

The computation identifies the first and second content searches, measures
accepted-support coverage after the first observation round, and subtracts it
from final accepted-support coverage.

### T98-02 — Modality switching

The ordered diagnostic sequence was independently reconstructed from:

```text
content searches +
successful citable inspect_clip/read_transcript observations
```

Status and finalize actions were excluded. Results:

```text
trajectories with a modality-bearing sequence: 118
trajectories with at least one switch: 36
mismatches: 0
```

### T98-03 — No-trigger controls and true top-5 displacement

All ten controls satisfy the frozen matched-control contract:

- state is `RESTORED`;
- scope is source-scoped;
- restoration alone is disabled;
- budget matches the ordinary RESTORED trajectory;
- the trigger-seeking action prefix matches;
- no restoration event fires;
- complete support is not acquired in 10/10.

Displacement is restricted to the two families with admitted
machine-validated negatives:

```text
noaa01-r016-three-factors-vs
noaa01-r017-north-atlantic-basin
```

All 8/8 rows contain a valid top-5 displacement proof:

```text
r016: 1 -> 20
r017: 1/4 -> 19/20
```

Independent outcome counts:

```text
recovery enabled, evidence reacquired: 4/4
recovery enabled, supported answer recovered: 2/4
recovery disabled, evidence reacquired: 0/4
```

The three visual-first families remain ineligible for validated-negative
displacement. Their 36 visual candidates remain explicitly
`machine_provisional_hard_negative_candidate`, with `admitted=false` and
metric eligibility disabled.

## Strict metric audit

For all 138 rows, this audit recomputed the following from the persisted final
output, claim-level validation, citations, acquired support, actual budget,
and final route certificate:

- Answer Score;
- Citation F1;
- Supported-Claim Rate;
- Success@Budget;
- Premature Stop.

There were zero mismatches. In particular:

- Supported-Claim Rate uses supported asserted claims divided by all asserted
  claims and remains null for an empty abstention;
- Success@Budget jointly requires a valid output, budget compliance, correct
  required claims, complete accepted support, valid required-claim citations,
  and no forbidden or contradictory assertion;
- Premature Stop is evaluated against route feasibility at the actual
  finalization point.

All 560 aggregate rows were also independently reconstructed. The
reconstructed rows exactly match `report.json`; ordinary aggregates use only
the 120 ordinary trajectories, while displacement outcomes occupy separate
aggregate rows.

## Speech lineage and checkpoint replay

The repaired speech index remains chunk-unique:

```text
Whisper chunks: 461
speech search records: 461
unique chunk IDs: 461
maximum records per chunk: 1
```

For every retained speech-bearing family, all records derived from a support
chunk are included in the BLOCKED suppression closure. The former
fine/context transcript projection leak is not present.

All 20 checkpoint files independently match the current observation manifest
and Task-99 recorded SHA-256 values, sizes, and `0600` permissions.

Checkpoint-derived deterministic replay was executed in read-only mode by
disabling only the post-replay build-manifest status writer. No model
checkpoint was recomputed. The following eight semantic artifacts matched
their current originals:

```text
segment
index
migration
negatives
interventions
rankings
trajectories
summary
```

Result:

```text
all_match=true
checkpoint_count=20
```

## Provenance, permissions and leakage

- Task-99 run-manifest hashes match current files.
- The restricted Scale-1A directory is `0700`.
- Restricted files are `0600`; no restricted symlink was found.
- The current public result/report surface contains none of the configured
  restricted paths, media filenames, private answer/evidence fields, raw
  vectors, observed segment IDs, or route certificates.
- Current reports consistently record the same three-layer decision.

## Scale-1B boundary

The existing Scale-1B audit status remains:

```text
COMPLETE_FOR_BOUNDED_DOWNLOADS_AND_SMOKE_TESTS
```

The plan's execution decision remains `READY_FOR_BOUNDED_DOWNLOADS`, while all
readiness gates correctly remain false:

```text
LEARNED_RETRIEVAL_READY=false
LEARNED_GENERATION_READY=false
LEARNED_AGENT_READY=false
SCALE1B_READY=false
```

This wording distinguishes planning completeness from learned-system
readiness.

## Why the diagnostic decision remains inconclusive

Engineering correctness does not justify a scientific GO. The current result
still has the following limitations:

1. five retained machine-adjudicated families over three family-bearing
   videos;
2. deterministic protocol policies rather than learned-system evaluation;
3. no human-validated answer, evidence minimality, or modality necessity;
4. only r016 and r017 qualify for validated-negative displacement;
5. r007 remains below the frozen Recall@5 shortcut criterion.

Therefore the honest milestone result is:

```text
SCALE1A_ENGINEERING_GO
SCALE1A_DIAGNOSTIC_INCONCLUSIVE
FINAL_BENCHMARK_NOT_YET_VALIDATED
SCALE1A_MILESTONE_PROVEN
```

