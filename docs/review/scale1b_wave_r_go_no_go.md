# Scale-1B Wave-R learned retrieval: Go/No-Go

**Task:** 103  
**Date:** 2026-09-12  
**Boundary:** `MACHINE_ADJUDICATED_PROVISIONAL_MVP`

## Decision

```text
LEARNED_VISUAL_RETRIEVAL_READY
LEARNED_AUDIO_RETRIEVAL_READY
LEARNED_RETRIEVAL_READY
WAVE_R_DIAGNOSTIC_GO
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

The readiness decisions mean the pinned models, frozen timeline, learned
vectors, retrieval indices, comparison matrix and replay checks are executable.
They do not mean that the learned systems outperform the controls.

## Executed configuration

- SigLIP checkpoint:
  `google/siglip2-base-patch16-224@75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2`.
  The pinned configuration resolves to `SiglipModel`; output dimension is 768.
- CLAP checkpoint:
  `laion/clap-htsat-unfused@8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a`.
  Output dimension is 512.
- Both snapshots are local-only, hash-verified and restricted. Redistribution
  remains unauthorized.
- The exact Scale-1A lattice is retained:
  3,433 base cells, 3,428 fine windows, 855 context windows and 4,283 total
  timeline segments across five videos.
- SigLIP encodes one source frame for every base cell. CLAP encodes every
  exact fine audio interval. Fine/context vectors use normalized mean pooling.
- Persisted vectors are float16; ranking arithmetic is float32.
- Ten source/layer checkpoints were generated and are resumable.
- No decoded source frame or waveform was persisted.

## Evaluation

All nine Task-101 rows were run in source-scoped and cross-source settings:

```text
V-CLIP, V-SIGLIP2
A-AST, A-CLAP
S-BM25
F-CTRL, F-V, F-A, F-VA
```

The fixed fusion remains non-learned equal-weight RRF with `k=60`. No
evaluation-family tuning, calibration or logistic fusion was used.

The primary result contains 64 per-family metric rows, 40 paired-comparison
rows, and 132 retrieval/probe records. Five retained families enter primary
aggregates; `noaa01-r014-aircraft-storm-view` remains an explicit excluded
audit record and was not silently reintroduced.

### Selected source-scoped aggregates

| Ranker | n | Recall@5 | Recall@20 | All-Evidence@20 | MRR |
|---|---:|---:|---:|---:|---:|
| V-CLIP | 4 | 0.25 | 0.50 | 0.50 | 0.1607 |
| V-SIGLIP2 | 4 | 0.25 | 0.25 | 0.25 | 0.0833 |
| A-AST | 1 | 0.00 | 1.00 | 1.00 | 0.1000 |
| A-CLAP | 1 | 0.00 | 0.00 | 0.00 | 0.0000 |
| S-BM25 | 2 | 1.00 | 1.00 | 1.00 | 1.0000 |
| F-CTRL | 5 | 0.50 | 0.90 | 0.80 | 0.3886 |
| F-V | 5 | 0.50 | 0.70 | 0.60 | 0.3367 |
| F-A | 5 | 0.50 | 0.70 | 0.60 | 0.3786 |
| F-VA | 5 | 0.50 | 0.50 | 0.40 | 0.3167 |

These are descriptive low-N results, not population estimates. In this pilot,
the new encoders are often worse than the frozen controls on the exact
machine-provisional support routes. That does not invalidate technical
readiness. It is a useful diagnostic warning that stronger generic encoders
do not automatically improve domain-specific evidence localization.

The frozen diagnostic criterion passes because multiple retained families
show reproducible paired differences in source-scoped retrieval, differences
also occur cross-source, and fusion crosses an All-Evidence boundary. The
result is therefore `WAVE_R_DIAGNOSTIC_GO`, even though the direction is
mostly degradation.

## Intervention boundary

The task runs retrieval-level CLEAN/BLOCKED/RESTORED route suppression probes.
Where Scale-1A has validated negative candidates, top-five displacement and
reranking rows are also persisted. These tests demonstrate retrieval
suppression/restoration only. They do not establish learned agent recovery.

## Verification

- Task-101 frozen inventory: 20/20 verified before inference.
- Task-102 exact model gates: SigLIP and CLAP ready.
- Full learned coverage:
  - SigLIP base cells: 3,433/3,433
  - SigLIP segment vectors: 4,283/4,283
  - CLAP fine vectors: 3,428/3,428
  - CLAP context vectors: 855/855
  - invalid CLAP segments: 0
- Isolated one-item actual-model probes:
  - SigLIP: 768-D, norm approximately 1, peak RSS 1,697,360 KiB
  - CLAP: 512-D, norm approximately 1, peak RSS 1,694,296 KiB
- Actual output spot recomputation:
  - SigLIP max absolute float16 difference: `0.0001082420`
  - CLAP max absolute float16 difference: `0.0000303984`
- Checkpoint resume replay: **10/10 checkpoint hashes unchanged**.
- Derived ranking/metric replay: all four semantic hashes unchanged.
- Task-101 direct-control rows: **24/24 reproduced with zero metric mismatch**.
- Independent artifact/metric audit: **82 checks passed, 0 failures**.
- Strict verifier: `passed=true`, `failures=[]`.
- Actual-model spot recomputation passed for both SigLIP and CLAP.
- Focused Task-102/103 tests: **48 passed**.
- Full related regression: **498 tests collected, exit code 0**.

## Scientific interpretation

Wave R validates the central engineering claim that two pinned learned
retrievers can be evaluated over the same complete long-video timeline without
substituting Scale-1A features or changing candidate identities.

The present data also reveal meaningful model-dependent ranking differences.
However, these six families are not a representative benchmark sample. The
ambient comparison has only one eligible family, evidence is machine
adjudicated, and modality necessity remains unvalidated and therefore `null`.
The final benchmark remains unvalidated pending dataset expansion and later
stratified human review.
