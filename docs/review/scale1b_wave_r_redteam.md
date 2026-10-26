# Task 104 — Independent red-team of Scale-1B Wave-R

**Date:** 2026-09-14  
**Boundary:** `MACHINE_ADJUDICATED_PROVISIONAL_MVP`

## Decisions

```text
LEARNED_VISUAL_RETRIEVAL_READY
LEARNED_AUDIO_RETRIEVAL_READY
LEARNED_RETRIEVAL_READY
WAVE_R_DIAGNOSTIC_GO
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

The three readiness decisions are engineering decisions. They mean that the
pinned models, learned vectors, frozen candidate lattice, nine-system
comparison and replay path are executable and auditable. They do not mean that
the learned retrievers outperform the controls.

## Independent findings

### Models

The exact restricted snapshots were independently checked:

- `google/siglip2-base-patch16-224` at
  `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2`;
- `laion/clap-htsat-unfused` at
  `8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a`.

The snapshots contain their exact allowlists, one framework weight
representation each, matching sizes and SHA-256 values, restricted
permissions, and no staging residue. The local SigLIP configuration declares
`model_type=siglip`, so `SiglipModel`/`SiglipProcessor` is the correct runtime
despite the repository name containing “siglip2”. CLAP resolves to
`ClapModel`/`ClapProcessor`.

Offline image/text and audio/text smoke inference passed. Technical internal
use is authorized; redistribution remains
`NOT_AUTHORIZED_PENDING_RELEASE_REVIEW`.

### Sources and learned vectors

All five NOAA source files match the acquisition-manifest size and SHA-256.
The frozen lattice remains:

```text
3,433 base cells
3,428 fine windows
855 context windows
4,283 total timeline segments
```

The learned sidecars contain:

```text
3,433 SigLIP source-frame vectors
4,283 SigLIP segment vectors, 768-D
3,428 CLAP fine-window vectors
855 CLAP context vectors, 512-D
```

All stored vectors are finite, float16-serialized, approximately unit
normalized, and scored in float32. Pooling was independently checked at the
beginning, middle and end of three sources. Maximum absolute differences after
float16 round-trip were approximately `1.92e-4` for SigLIP and `5.84e-5` for
CLAP.

Actual source inference was repeated on middle positions from `cand-045`,
`cand-049`, and `cand-052` for both models. SigLIP differences from persisted
float16 values were at most `1.83e-4`. CLAP differences were at most
`3.91e-5` when using the exact build path—decode the source once, then slice
the frozen interval. No Wave-R frame, waveform, or media clip is persisted.

### Frozen experiment

All nine Task-101 systems are present in both declared scopes:

```text
V-CLIP, V-SIGLIP2, A-AST, A-CLAP, S-BM25,
F-CTRL, F-V, F-A, F-VA
```

Fusion is fixed equal-weight RRF with `k=60`, input depth 20, and unit
vision/ambient/speech weights. Logistic fusion and evaluation-family fitting
remain disabled. The five retained families are unchanged, and `r014` remains
excluded.

After repair, there are exactly:

```text
64 metric rows
40 paired-comparison rows
132 retrieval/probe rows
```

Every primary metric was independently recomputed from the persisted ranking,
support groups, and modality-contribution map with zero mismatches. Paired
deltas also had zero mismatches.

## Defects found and repaired

### T104-01 — stale model-manifest binding

The learned checkpoints were bound to an earlier byte version of the model
acquisition manifest. A later successful offline validation had rewritten the
manifest, but the Wave-R verifier did not compare the current gate hashes
against the observation configuration.

Repair:

- added fail-closed `STALE_GATE_HASH_BINDING` verification;
- added `tools/scale1b_wave_r_rebind_gate_hashes.py`;
- rebound only the ten checkpoint envelopes after verifying their payload
  hashes, source hashes, exact model revisions, and
  `actual_learned_model=true`;
- rebuilt derived manifests with all ten checkpoints reused.

No learned feature inference was rerun.

### T104-02 — fusion contract and metric/ranking disagreement

Task 101 requires the existing label-independent temporal-binding adapter to be
applied identically before every fusion variant. Task 103 did not apply it.
Additionally, one `r004 / source_scoped / F-CTRL` metric row was taken from
frozen route-rank numbers that disagreed with its persisted ranking and
modality contributions.

Repair:

- applied temporal binding symmetrically to control and learned visual inputs
  before `F-CTRL`, `F-V`, `F-A`, and `F-VA`;
- required metrics to be calculated from the exact persisted ranking and
  contribution evidence;
- retained Task-101 direct rows only as parity references, not as an override;
- regenerated rankings, metric rows, paired rows, summaries and manifests.

### T104-03 — intervention scope was overstated

The route-suppression probe removes support IDs from an already produced clean
top-20 list; it does not rerank the entire candidate universe after
suppression.

Repair:

```text
probe_scope=clean_top20_suppression_projection
fresh_full_universe_rerank=false
retrieval_recovery_only=true
```

These rows are retained as bounded retrieval diagnostics. They are not
presented as learned-agent recovery or full-universe counterfactual reranking.

### T104-04 — CLAP spot-check decode-path discrepancy

An interval-only decoder differed substantially from the persisted `cand-045`
vector. Repeating the check with the exact build procedure—full-source decode
followed by exact interval slicing—reduced the difference to `3.91e-5`.
Therefore the checkpoint is valid; the interval-only helper is not equivalent
to the build path for that asset.

## Repaired results

Selected source-scoped aggregates remain:

| System | n | Recall@5 | Recall@20 | All-Evidence@20 | MRR |
|---|---:|---:|---:|---:|---:|
| V-CLIP | 4 | 0.25 | 0.50 | 0.50 | 0.1607 |
| V-SIGLIP2 | 4 | 0.25 | 0.25 | 0.25 | 0.0833 |
| A-AST | 1 | 0.00 | 1.00 | 1.00 | 0.1000 |
| A-CLAP | 1 | 0.00 | 0.00 | 0.00 | 0.0000 |
| F-CTRL | 5 | 0.50 | 0.90 | 0.80 | 0.3986 |
| F-VA | 5 | 0.50 | 0.50 | 0.40 | 0.3167 |

The negative-performance conclusion is real under the frozen provisional
routes: SigLIP2, CLAP, and the fully substituted fusion do not improve the
corresponding controls. This does not invalidate readiness.

`WAVE_R_DIAGNOSTIC_GO` remains justified by the preregistered Task-101 rule:
nonzero source-scoped paired changes occur on at least two retained families,
corresponding changes remain visible cross-source, and a fusion
All-Evidence boundary changes. The conclusion is only a low-N descriptive
finding that general-purpose learned encoders can alter—and here often
degrade—domain-specific evidence ranking.

## Verification actually executed

- exact snapshot/allowlist/hash/permission validation;
- offline SigLIP and CLAP image/audio/text smoke inference;
- actual-source inference at three positions per model;
- source file identity checks for all five videos;
- full vector count, dimension, finiteness, norm, pooling, silence and timeline
  checks;
- independent recomputation of all 64 metric rows and 40 paired rows;
- Task-103 independent artifact audit: 82 checks, zero failures;
- strict Wave-R verifier: `passed=true`, `failures=[]`;
- focused Task-102/104 tests: **49 passed**;
- full relevant regression: reached 100% and exited zero;
- all ten checkpoints were reused after the provenance-envelope repair;
- derived ranking/metric hashes and all 22 run-manifest artifacts match.

## Remaining limitations

- Five retained machine-adjudicated families over only three source videos.
- The audio comparison has one eligible family.
- Evidence routes are provisional, not human gold or minimal evidence.
- Modality necessity remains unvalidated and its metric remains null.
- Route-suppression probes are top-20 projections, not full-universe reranks.
- This is learned retrieval evaluation, not learned generation or agent
  evaluation.

This Task-104 report and `redteam.json` are the authoritative post-repair
interpretation. The Task-103 report is retained unchanged as historical
provenance and should not be used for exact post-repair metric values or probe
semantics.
