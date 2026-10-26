# Scale-1B Wave R learned-retrieval experiment contract

**Task:** 101  
**Frozen on:** 2026-09-12  
**Decision:** `WAVE_R_CONTRACT_FROZEN`

## 1. Purpose and scientific boundary

Wave R asks a narrow question:

> On the already frozen Scale-1A timeline, do pinned SigLIP2 and CLAP
> retrieval adapters exhibit different, reproducible evidence-ranking behavior
> from the current CLIP and AST controls?

This is a retrieval experiment. It is not a learned-agent, generation,
minimality, or modality-necessity experiment. The five retained families remain
machine-adjudicated provisional evaluation examples. They may be used only for
the predeclared measurements below, never for prompt selection,
hyperparameter selection, score calibration, fusion training, checkpoint
selection, query rewriting, or deciding which model output to report.

The following labels remain mandatory:

```text
MACHINE_ADJUDICATED_PROVISIONAL_MVP
human_reviewed=false
gold_annotation=false
modality_necessity_human_validated=false
LOW_N_DESCRIPTIVE_WAVE_R
```

Task 100 remains the authoritative Scale-1A audit:

```text
SCALE1A_ENGINEERING_GO
SCALE1A_DIAGNOSTIC_INCONCLUSIVE
FINAL_BENCHMARK_NOT_YET_VALIDATED
SCALE1A_MILESTONE_PROVEN
```

Wave R must not rewrite or regenerate any Scale-1A artifact. The exact
byte-level inventory and semantic hashes are frozen in
`data/rehearsal_plan/scale1b_wave_r_trust_anchor.json`.

## 2. Frozen data universe

### 2.1 Sources and lattice

The source universe is exactly the five already-audited NOAA assets:

```text
cand-045
cand-047
cand-049
cand-051
cand-052
```

The frozen lattice is:

| Unit | Count | Construction |
|---|---:|---|
| Four-second base cells | 3,433 | `start=4*i`; retain final short cell |
| Fine segments | 3,428 | nominal 8 s, stride 4 s |
| Context segments | 855 | nominal 32 s, stride 16 s |
| Fine + context segments | 4,283 | immutable candidate IDs and intervals |
| Speech chunks | 461 | non-overlapping, nominal 30 s |

Per-source fine+context candidate counts are:

```text
cand-045:  553
cand-047:  618
cand-049:  770
cand-051: 1161
cand-052: 1181
```

Per-source speech candidate counts are:

```text
cand-045:  60
cand-047:  67
cand-049:  83
cand-051: 124
cand-052: 127
```

No learned adapter may alter segment IDs, timestamps, source membership,
sampling timestamps, support IDs, family disposition, or the searchable
candidate universe.

### 2.2 Learned sidecars

SigLIP2 and CLAP are sidecar representations over the frozen lattice.

#### SigLIP2

- Encode exactly the 3,433 RGB frames sampled at the existing Scale-1A frame
  timestamps.
- Use the pinned model processor without an added prompt template.
- L2-normalize frame vectors.
- A fine/context segment vector is the L2-normalized arithmetic mean of its
  constituent frozen base-cell vectors.
- Serialize model outputs in a versioned restricted checkpoint; similarity is
  computed in float32.
- Produce exactly 4,283 visual candidate records with the existing segment IDs.

#### CLAP

- Decode exactly the 3,428 frozen fine intervals from the original source
  audio with PyAV.
- Resample according to the pinned CLAP processor configuration.
- Use the raw frozen query string without a prompt template.
- L2-normalize audio and text vectors.
- A context vector is the L2-normalized arithmetic mean of the frozen child
  fine-window vectors.
- Serialize model outputs in a versioned restricted checkpoint; similarity is
  computed in float32.
- Produce exactly 4,283 audio candidate records with the existing segment IDs.

No media derivative may persist. Temporary decoded frame/audio buffers must be
deleted before a model stage is declared complete.

### 2.3 Primary and stress-test scopes

`source_scoped` is the primary comparison. Its candidate universe contains
only records whose `source_ref` equals the family asset.

`cross_source` is a separately reported stress test over all five assets. It
must never be pooled with the primary result.

Every model/configuration must use the same scope filter and tie-break:

```text
descending score
ascending source_ref
ascending start_us
ascending end_us
ascending segment_id
ascending modality
```

## 3. Frozen evaluation families and queries

The retained evaluation-only families are:

| Family | Source | Evaluated routes | Frozen model queries |
|---|---|---|---|
| `noaa01-r004-surf-av` | `cand-049` | vision, ambient | V: `person water conditions near shore`; A: `environmental sounds same interval water` |
| `noaa01-r007-opening-plastic-waste` | `cand-051` | vision | V: `discarded material introductory montage` |
| `noaa01-r011-bag-by-fence` | `cand-051` | vision | V: `person carrying object beside fence` |
| `noaa01-r016-three-factors-vs` | `cand-052` | vision, speech | V/S: `how many hurricane formation factors stated` |
| `noaa01-r017-north-atlantic-basin` | `cand-052` | speech | S: `speaker main area hurricane activity basin` |

`noaa01-r014-aircraft-storm-view` remains excluded with
`VISION_SUPPORT_NOT_TOP20`. It is a frozen exclusion/audit row and must not be
silently reintroduced, even if SigLIP2 retrieves it.

The second stored query-family string may be reported only in an explicitly
named, non-primary robustness appendix that runs every model with the same
string. It cannot replace the primary query or determine any configuration.

## 4. Exact comparison rows

All rows are evaluated at `K = {1, 5, 10, 20}` in both scopes.

### 4.1 Unimodal rows

| Row ID | Eligible families | Candidate universe | Ranker |
|---|---|---|---|
| `V-CLIP` | r004, r007, r011, r016 | frozen visual segments | frozen CLIP cosine |
| `V-SIGLIP2` | same four | identical visual segments | pinned SigLIP2 cosine |
| `A-AST` | r004 | frozen audio segments | frozen AST sparse cosine |
| `A-CLAP` | r004 | identical audio segments | pinned CLAP cosine |
| `S-BM25` | r016, r017 | 461 frozen speech chunks | frozen BM25 |

The visual pair is a **direct-retriever** comparison before temporal binding.
The audio pair is a direct-retriever comparison. `S-BM25` is unchanged and is
included as a fixed fusion input, not as a learned Wave-R pair.

### 4.2 Fusion rows

The only allowed fusion is deterministic equal-weight reciprocal-rank fusion:

```text
score(item) = sum_m 1 / (60 + rank_m(item))
rrf_k = 60
per-modality input depth = 20
weights: speech=1, ambient=1, vision=1
```

Deduplication and tie-break remain the Scale-1A rules. The existing
label-independent temporal-binding adapter, when applicable, is held fixed and
applied identically before every fusion variant. Direct unimodal rows remain
available so that temporal binding cannot hide a visual/audio model effect.

| Row ID | Vision input | Audio input | Speech input |
|---|---|---|---|
| `F-CTRL` | CLIP | AST | BM25 |
| `F-V` | SigLIP2 | AST | BM25 |
| `F-A` | CLIP | CLAP | BM25 |
| `F-VA` | SigLIP2 | CLAP | BM25 |

Inputs absent from a family are omitted rather than represented by an empty
learned score. A one-modality fusion row is retained for matrix completeness
but must be labeled equivalent to its unimodal input.

Logistic fusion and every other learned or calibrated fusion method are
disabled:

```text
LOGISTIC_FUSION_ENABLED=false
reason=NO_DISJOINT_TRAINING_SPLIT
```

## 5. Support matching

The authoritative support registry is the frozen
`migrated_families.json`.

1. Each evidence unit is identified by its evaluator-private evidence ID and
   modality.
2. A candidate supports an evidence unit only if:
   - its modality is the evidence modality; and
   - its frozen segment/chunk ID belongs to that unit's accepted route.
3. Fine/context representations of the same evidence are alternatives within
   that evidence unit, not multiple required pieces.
4. A fused temporal group supports an evidence unit only when the fused record
   records contribution from that modality and its segment ID matches an
   accepted route.
5. One candidate may satisfy two colocated evidence units only if both
   modality contributions are explicitly present. Timestamp overlap alone
   does not establish support.
6. No new alternative support discovered by a learned model is admitted
   automatically. It is logged as `UNADJUDICATED_ALTERNATIVE` and excluded
   from primary metrics until independently adjudicated.
7. The current support registry is provisional and must not be called gold,
   minimal, or modality-necessary.

## 6. Metrics and null rules

For each family, scope, and row:

- `Recall@K`: number of applicable evidence units with an accepted route in
  the first K results, divided by the number of applicable evidence units.
- `All-Evidence@K`: 1 only when every applicable evidence unit is retrieved by
  K; otherwise 0.
- `first_accepted_evidence_rank`: minimum accepted rank; `null` on no hit
  within depth 20.
- `MRR`: macro mean of reciprocal rank over applicable evidence units; a miss
  by depth 20 contributes zero.
- `nDCG@K`: binary evidence-unit gain, counting an evidence unit only at its
  first accepted occurrence. The ideal list contains
  `min(number_of_applicable_evidence_units, K)` unit gains.
- `paired_first_rank_delta = learned_rank - control_rank`; for paired
  arithmetic, a miss is represented as 21, while the displayed rank remains
  `null`.
- `paired_recall_delta@K = learned Recall@K - control Recall@K`.
- `paired_all_evidence_delta@K = learned All-Evidence@K - control
  All-Evidence@K`.
- `source_to_cross_degradation = cross_source_value - source_scoped_value`.
  Negative values indicate degradation.

No macro metric is emitted when its eligible denominator is zero. MRR/nDCG are
`null` for a row with no applicable registered evidence units. Modality Recall
remains `null`; these data do not establish modality necessity.

All per-family values and denominators must be emitted. Every aggregate must
carry:

```text
LOW_N_DESCRIPTIVE_WAVE_R
```

No confidence interval, significance claim, SOTA claim, or population
generalization is permitted at this sample size.

## 7. Resource measurements

Resource measurements are descriptive and do not alter model selection.

For each model:

- snapshot bytes and generated checkpoint/index bytes;
- number of encoded units and failures;
- offline index-build wall time and items/second;
- peak resident set size in an isolated child process;
- cold query latency and five warm repeats for every frozen query;
- per-row median and p95 warm latency;
- device, dtype, thread count, batch size, library versions, and seed.

Latency must separate embedding time from ranking time. Failed/OOM/timed-out
runs retain a typed failure row and must not be replaced with control outputs.

## 8. No-evaluation-tuning rule

The five retained families and the excluded family are evaluation-only.
Forbidden actions include:

- choosing prompts, pooling, batch size, dtype, score transform, RRF constant,
  modality weights, or checkpoint based on their ranks;
- manually rewriting a query after viewing output;
- selecting a model or reporting subset because it looks better;
- fitting calibration or logistic fusion to any of the six families;
- admitting learned-model discoveries as support without a separate
  adjudication artifact;
- dropping a failed family from a denominator.

Implementation debugging may use synthetic media or non-evaluation windows.
Any unavoidable post-freeze code repair must be documented, must not change
the contract, and requires a full matched replay.

## 9. Gates

### `SIGLIP2_SNAPSHOT_READY`

True only if the exact pinned
`google/siglip2-base-patch16-224@75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2`
allowlist is downloaded into restricted storage, every file has a verified
size and SHA-256, local-only load succeeds, image/text embeddings are finite
and normalized, deterministic replay passes, and the technical-use and
redistribution decisions are recorded separately.

### `CLAP_SNAPSHOT_READY`

The analogous gate for
`laion/clap-htsat-unfused@8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a`,
including offline audio/text embedding and deterministic replay.

### `LEARNED_VISUAL_RETRIEVAL_READY`

Requires `SIGLIP2_SNAPSHOT_READY`, exact 3,433-frame coverage, exact
4,283-segment sidecar coverage, finite normalized vectors, frozen query
encoding, deterministic rankings, no forbidden searchable fields, both
scopes, all four eligible families, resource accounting, and matched
`V-CLIP`/`V-SIGLIP2` rows.

### `LEARNED_AUDIO_RETRIEVAL_READY`

Requires `CLAP_SNAPSHOT_READY`, exact 3,428-fine-window coverage, exact
4,283-segment sidecar coverage, finite normalized vectors, frozen query
encoding, deterministic rankings, no forbidden searchable fields, both
scopes, r004 coverage, resource accounting, and matched `A-AST`/`A-CLAP`
rows.

### `LEARNED_RETRIEVAL_READY`

Requires both learned modality readiness gates, `S-BM25`, all four fusion
rows, exact source/lattice/support/query hashes, no evaluation tuning, fixed
RRF, complete null/failure rows, deterministic replay, and an independent
leakage/metric audit. It does **not** require a learned model to beat a
control.

### `WAVE_R_DIAGNOSTIC_GO`

Requires `LEARNED_RETRIEVAL_READY` and a reproducible, nontrivial diagnostic
separation: at least two retained families have a nonzero paired first-rank or
Recall@K delta in the source-scoped primary comparison, and at least one such
model-dependent change remains visible in the cross-source stress test or
changes an All-Evidence@K boundary in a fusion row. The interpretation remains
low-N and descriptive. Improvement is not required; reproducible degradation
is also a diagnostic result.

### `WAVE_R_DIAGNOSTIC_INCONCLUSIVE`

Used when engineering/readiness gates pass but the observed differences are
too sparse, tied, dominated by one family, unsupported by the provisional
routes, or otherwise insufficient for a scientific finding.

### `WAVE_R_NO_GO`

Used when snapshot integrity, lattice parity, candidate-universe parity,
support/query freeze, leakage safety, fixed-fusion policy, metric
recomputation, or deterministic replay fails. A model being worse than its
control is not a `NO_GO` reason.

The decision precedence is:

```text
contract/integrity failure -> WAVE_R_NO_GO
engineering ready but diagnostic criterion unmet -> WAVE_R_DIAGNOSTIC_INCONCLUSIVE
engineering ready and diagnostic criterion met -> WAVE_R_DIAGNOSTIC_GO
```

## 10. Required Wave-R outputs

A compliant implementation must persist:

1. exact model acquisition manifests;
2. sidecar checkpoint manifests and hashes;
3. per-query top-20 rankings with opaque candidate IDs;
4. per-family metric rows for all declared comparisons and both scopes;
5. paired deltas and resource measurements;
6. fixed-RRF rows;
7. typed failure/null records;
8. deterministic replay evidence;
9. leakage and independent metric audit;
10. the final readiness and diagnostic decisions.

The Wave-R result is an additive comparison. It must not mutate or replace the
Scale-1A baseline.
