# Task 96 — Independent red-team of the Scale-1A full-timeline MVP

Date: 2026-09-11

## Final decision

```text
SCALE1A_NO_GO
SCALE1A_NO_GO
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

The first decision is the engineering gate and the second is the diagnostic
gate. This supersedes the Task-95 `SCALE1A_ENGINEERING_GO` claim for the
current artifacts. It does **not** invalidate the five source files, model
snapshots, segmentation, or checkpoint bytes. It means the current
intervention and evaluation layer does not satisfy the stated Task-91/95
protocol.

## What independently passed

- The Task-93 trust anchor verified all 94 frozen files.
- All five NOAA files retained their expected byte size, SHA-256, duration,
  video stream, and audio stream.
- Timeline arithmetic and complete base-cell coverage reproduce:

  | Layer | Count |
  |---|---:|
  | Four-second base cells | 3,433 |
  | Eight-second fine windows | 3,428 |
  | Thirty-two-second context windows | 855 |
  | Temporal windows | 4,283 |

- All 20 checkpoints pass key, count, size, SHA-256, payload-hash, symlink, and
  permission checks.
- Their frozen counts are 461 Whisper chunks, 3,428 AST fine-window records,
  3,433 OpenCV routing cells, and 3,433 CLIP cell vectors.
- The 3,433 CLIP vectors are all distinct, 512-dimensional, and approximately
  unit-normal after float16 round-trip (norm range
  `0.99981099–1.00020504`). Recomputing all 4,283 segment pools from their
  constituent cells produced zero float16 mismatches.
- A fresh local-only CLIP adapter test executed image and text inference and
  returned normalized 512-D outputs.
- Each modality contains 4,283 index records. No evaluator-private schema key
  was found in searchable records.
- Source-scoped and cross-source modes use distinct filtering paths. Identical
  top-20 results for some queries are an observed outcome, not shared-scope
  implementation.
- Independent query execution reproduced all recorded migration ranks:

  | Family | Recomputed support rank |
  |---|---|
  | r004 | ambient 10; visual 10 via temporal binding |
  | r007 | visual 7 |
  | r011 | visual 2 |
  | r014 | no visual support in top 20 |
  | r016 | speech 4; visual 4 via temporal binding |
  | r017 | speech 7 |

- The exclusion of r014 is supported, and the r007 masked Recall@5 criterion
  remains failed.
- The 120 ordinary rows and 20 displacement rows exist. Retrieval-rank fields
  were independently recalculated without mismatch. All 560 reported
  aggregate rows were also reproduced exactly.
- Restricted permissions and the specified public leakage scan passed.

## Critical defects

### D96-01 — BLOCKED speech evidence is still directly searchable

Speech is inferred in non-overlapping 30-second Whisper chunks, but
`_project_speech` copies each complete chunk transcript into every overlapping
8-second or 32-second segment. The intervention then suppresses only the
three nominal interval-overlap segment IDs.

For r016, the registered support records inherit three Whisper chunks. There
are **29 additional segment records** sharing those chunks that are not
suppressed. The top-ranked unsuppressed speech records still contain the
answer-bearing phrase “three factors.”

For r017, there are **18 additional segment records** sharing its two support
chunks that are not suppressed. Nine unsuppressed records in the source-scoped
top 20 contain `north`, `atlantic`, and `basin`, including ranks 1–6.

Consequently, the assertion

```text
BLOCKED suppresses every direct/derived/duplicate/alternative route
```

is false for both speech families.

### D96-02 — The 140 “trajectories” contain no action-level execution

`trajectories.json` contains metric-summary records produced by
`_simulate_episode`. It does not contain:

```text
actions
steps_used
cost_used
final_output
```

Therefore Task 96 cannot independently verify policy blindness, actual tool
order, trigger timing, budget use, reinspection/reacquisition, final
citations, or per-trajectory tool-time decode.

### D96-03 — Strict Task-90 Ground and Act metrics were not run

For all **140/140** records:

```text
Answer Score
Citation F1
Supported-Claim Rate
Success@Budget
```

are assigned directly from `All-Evidence Success`. No generated final answer,
asserted-claim list, claim-to-citation mapping, output validator, or actual
cost trace is persisted.

`Premature Stop` is likewise assigned by a policy-name condition rather than
the Task-90 final-point route-feasibility procedure. The stored
`strict_final_route_certificate` has four booleans but no route-feasibility
calculation.

The public and restricted arithmetic is internally reproducible, but these
columns are not executions of the metrics their names claim.

### D96-04 — Visual hard negatives are candidates, not validated negatives

Every retained family structurally has 12 rows. However:

- visual documents contain no searchable semantic text, so answer-alias and
  claim-token scans pass vacuously;
- `duplicate_cluster_split` is always written as `false`;
- the claimed two independent machine non-support checks are not persisted;
- “same-modality semantic” is assigned to a ranked, non-overlapping result
  without an independent content judgment.

The present rows may be retained as hard-negative **candidates**, but they
cannot support the intervention invariant “at least five admitted hard
negatives” yet.

### D96-05 — Speech localization has 30-second temporal leakage

The same whole-chunk transcript is copied into up to 10 overlapping windows
per source, and up to 13 in cand-052. An 8-second record may therefore expose
words spoken elsewhere in its 30-second parent chunk. This affects:

- exact-interval speech evidence;
- BM25 ranks;
- alternative-support scans;
- BLOCKED suppression;
- citation attribution.

Repair requires timestamp-token/segment decoding, or retaining chunk-level
speech retrieval with explicit localization uncertainty. It should not be
patched by merely extending the suppression list, because that would hide the
underlying temporal-attribution problem.

## Minimal repair applied

Only the fail-closed verifier was changed:

```text
src/av_trace_scale1a/core.py
```

It now requires:

1. `trajectories.json`;
2. action-level fields and final outputs;
3. final-point route-feasibility evidence;
4. suppression of all segment records sharing support Whisper chunks;
5. two persisted independent content checks for admitted visual negatives.

No checkpoint, index, trajectory, metric, Task-91/95 provenance file, source
video, or model snapshot was rewritten. The repaired verifier correctly
returns `SCALE1A_NO_GO` on the current artifacts.

## Validation actually executed

```text
PYTHONPATH=src python scripts/verify_scale1a.py \
  --repo-root . --trust-anchor-only
```

Passed before repair.

```text
PYTHONPATH=src python scripts/verify_scale1a.py \
  --repo-root . --strict
```

Passed under the original Task-95 verifier before repair, which motivated
strengthening that verifier.

The independent lightweight audit then read and recomputed:

- all segment coverage and counts;
- all 20 checkpoint hashes and payload hashes;
- every stored CLIP vector and all 4,283 pooled vectors;
- index counts and forbidden-key scans;
- all six family support ranks;
- speech-chunk lineage for both speech families;
- all 140 metric rows;
- all 560 aggregate rows;
- permissions and public leakage.

Focused tests after the repair:

```text
PYTHONPATH=src pytest -q \
  tests_scale1a tests/test_scale1a_model_acquisition.py

28 passed
```

Syntax validation:

```text
PYTHONPATH=src python -m py_compile src/av_trace_scale1a/core.py

PASS
```

Repaired verifier:

```text
PYTHONPATH=src python scripts/verify_scale1a.py \
  --repo-root . --no-strict

SCALE1A_NO_GO
```

It reports the missing action traces/certificates, speech-lineage leakage,
unvalidated visual negatives, and stale Task-95 engineering claim.

## Work deliberately not executed

Per the stop instruction, Task 96 did **not**:

- rerun the 461 Whisper calls;
- rerun the 3,428 AST calls;
- rerun the 3,433 source-frame CLIP calls;
- rerun the former 470-test regression;
- rebuild all downstream artifacts;
- alter media or model files.

The frozen inference checkpoints remain reusable after the speech
localization contract is redesigned. New model inference is not necessarily
required for the fix: the safest low-cost option is initially to index speech
at its honest 30-second chunk granularity, rebuild the derived index and
interventions, and then execute real action-level deterministic policies
through the existing Task-90 validation machinery.

## Final assessment

Scale-1A has successfully demonstrated a complete **multimodal timeline
feature/index construction pipeline**. It has not yet demonstrated a valid
full-timeline Agentic RAG evaluation:

```text
SCALE1A_NO_GO
SCALE1A_NO_GO
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

This is repairable without discarding the expensive model checkpoints, but
the C/B/R interventions, hard-negative admission, action trajectories, and
strict Ground/Act scoring must be regenerated before reconsidering an
engineering GO.
