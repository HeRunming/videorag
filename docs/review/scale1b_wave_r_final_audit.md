# Task 105 — Final post-repair independent Wave-R audit

**Date:** 2026-09-14  
**Boundary:** `MACHINE_ADJUDICATED_PROVISIONAL_MVP`  
**Audit mode:** read-only verification of the Task-104 state, except for the
three Task-105 audit deliverables.

## Final decisions

```text
LEARNED_VISUAL_RETRIEVAL_READY
LEARNED_AUDIO_RETRIEVAL_READY
LEARNED_RETRIEVAL_READY
WAVE_R_DIAGNOSTIC_GO
FINAL_BENCHMARK_NOT_YET_VALIDATED
WAVE_R_MILESTONE_PROVEN
```

`WAVE_R_MILESTONE_PROVEN` means that the bounded Wave-R learned-retrieval
milestone is executable, reproducible, contract-compliant, and independently
audited after the Task-104 repairs. It does not promote the five retained
machine-adjudicated families to human gold, prove modality necessity, or
validate the final benchmark.

## Scope and method

This audit independently checked the current repository against the frozen
Task-101 contract and the Task-105 requirements. It did not rebuild the
full-timeline features and did not rerun all 3,433 SigLIP or 3,428 CLAP model
calls. It did:

- validate both exact local model snapshots and their full allowlists;
- inspect and hash all ten learned-feature checkpoints;
- run actual offline inference from original source media for both models;
- independently reconstruct all forty persisted fusion rankings;
- independently recompute all 64 metric rows and all 40 paired rows;
- inspect all 132 clean/intervention probe rows;
- run the strict verifier with actual-model spot recomputation;
- run focused tests and the full relevant regression.

## 1. Task-101 trust anchor

The trust anchor is self-consistent:

```text
decision: WAVE_R_CONTRACT_FROZEN
artifact inventory: 20/20 exact
anchor self-hash: valid
```

All 20 frozen files matched their recorded paths, sizes, and SHA-256 values.
The frozen evaluation set remains:

```text
retained:
  noaa01-r004-surf-av
  noaa01-r007-opening-plastic-waste
  noaa01-r011-bag-by-fence
  noaa01-r016-three-factors-vs
  noaa01-r017-north-atlantic-basin

excluded:
  noaa01-r014-aircraft-storm-view
  reason: VISION_SUPPORT_NOT_TOP20
```

The excluded family does not appear in any of the 64 metric rows.

## 2. Exact model snapshots

### SigLIP

```text
repo: google/siglip2-base-patch16-224
revision: 75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2
runtime model: SiglipModel
runtime processor: SiglipProcessor
config model_type: siglip
allowlisted payload: 8 files, 1,539,456,768 bytes
weight: model.safetensors
weight bytes: 1,500,800,904
weight SHA-256:
  612923381c76ec5a9bed335d1c48827e3f2e506ac31b044b63b2031fadee6a0b
technical gate: SIGLIP2_SNAPSHOT_READY
```

### CLAP

```text
repo: laion/clap-htsat-unfused
revision: 8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a
runtime model: ClapModel
runtime processor: ClapProcessor
config model_type: clap
allowlisted payload: 9 files, 617,900,277 bytes
weight: pytorch_model.bin
weight bytes: 614,525,833
weight SHA-256:
  1cd3c601bc4afe0fa87be3de4c13dd2cfadd249fac1e29acf74a9b296c3219bb
technical gate: CLAP_SNAPSHOT_READY
```

For both snapshots:

- the actual file set equals the manifest allowlist plus `SHA256SUMS`;
- every file size and SHA-256 matches;
- files are mode `0600` and snapshot directories are mode `0700`;
- one framework weight representation is present;
- response identities bind every file to the exact 40-character revision;
- offline smoke inference and deterministic replay are recorded as passed;
- no incomplete staging or partial-download residue was found.

The release boundary remains:

```text
technical_internal_use_authorized=true
redistribution_authorized=false
redistribution_decision=NOT_AUTHORIZED_PENDING_RELEASE_REVIEW
```

## 3. Learned checkpoints and full-timeline coverage

All ten checkpoint envelopes were independently verified:

```text
5 sources × 2 learned layers = 10 checkpoints
siglip2_visual checkpoints: 5
clap_audio checkpoints: 5
checkpoint file identity: 10/10
payload self-hash: 10/10
source SHA-256 binding: 10/10
model revision binding: 10/10
current configuration hash binding: 10/10
actual_learned_model=true: 10/10
```

The repaired gate hashes in the observation configuration exactly match the
current Task-101 contract, Task-102 model manifest, and Scale-1A final audit.
This closes the stale-binding defect found in Task 104.

Coverage is exact:

| Representation | Count |
|---|---:|
| SigLIP source-frame vectors | 3,433 |
| SigLIP pooled segment vectors | 4,283 |
| CLAP fine-window vectors | 3,428 |
| CLAP pooled context vectors | 855 |
| Learned visual index records | 4,283 |
| Learned audio index records | 4,283 |

All inspected vectors were finite and approximately unit normalized after
float16 serialization. Dimensions are 768 for SigLIP and 512 for CLAP.

### Actual-source inference

The strict verifier independently decoded the first frozen source intervals
from `cand-045` and reran both actual models:

```text
SigLIP max absolute difference: 0.00010824203491210938
CLAP max absolute difference:   0.00003039836883544922
tolerance:                      0.002
```

An additional Task-105 check used middle intervals from `cand-049`, including
the production CLAP path of full-source audio decode followed by exact frozen
interval slicing:

```text
SigLIP max absolute difference: 0.00008571147918701172
CLAP max absolute difference:   0.00003042072057723999
tolerance:                      0.002
```

Both passed. In addition, beginning/middle/end pooled segment vectors were
reconstructed for both layers on `cand-045`, `cand-049`, and `cand-052`.
Across 18 pooling checks:

```text
SigLIP maximum pooling difference: 0.00019150972366333008
CLAP maximum pooling difference:   0.00005838274955749512
```

These are consistent with the documented float16 round-trip tolerance.

## 4. Task-101 experiment contract

All nine systems are present with the exact expected row counts:

| System | Metric rows |
|---|---:|
| V-CLIP | 8 |
| V-SIGLIP2 | 8 |
| A-AST | 2 |
| A-CLAP | 2 |
| S-BM25 | 4 |
| F-CTRL | 10 |
| F-V | 10 |
| F-A | 10 |
| F-VA | 10 |

The complete experiment contains:

```text
metric rows: 64
paired rows: 40
retrieval/probe rows: 132
  clean: 64
  route suppression: 60
  validated-negative displacement: 8
```

All 64 clean rows use the exact Task-101 primary query for their family and
modality. The primary and stress-test scopes remain distinct:

```text
primary: source_scoped
stress:  cross_source
```

Fusion parameters match the frozen contract:

```text
type: equal-weight RRF
rrf_k: 60
input depth: 20
vision / ambient / speech weights: 1 / 1 / 1
logistic fusion: disabled
reason: NO_DISJOINT_TRAINING_SPLIT
evaluation-family tuning: disabled
```

### Temporal binding

Task 105 reconstructed all 40 fusion rows from the persisted direct rankings,
the frozen candidate records, the label-independent temporal-binding function,
and fixed RRF. Results:

```text
fusion rankings reconstructed: 40/40
ranking mismatches: 0
modality-contribution mismatches: 0
multimodal fusion rows with binding applied: 16/16
bound visual records per applicable row: 19–20
```

Single-modality fusion rows correctly reduce to their sole available input and
do not require temporal binding.

The Task-101 preflight contains pre-repair F-CTRL values for the two `r004`
scopes. Those two fusion rows differ after the required temporal-binding
repair. This is an expected, documented Task-104 correction rather than hidden
drift: all 14 direct unimodal control rows retain parity, while current fusion
metrics are derived from the current persisted bound rankings.

## 5. Metrics and paired findings

All 64 metric rows were independently recomputed from:

- evaluator-private persisted top-20 rankings;
- registered support groups;
- explicit modality contributions for fused results.

The recomputation covered:

```text
first accepted evidence rank
Recall@1/5/10/20
All-Evidence@1/5/10/20
MRR
nDCG@1/5/10/20
```

Result:

```text
64/64 rows recomputed
metric mismatches: 0
```

All 40 paired rows were independently recomputed, including first-rank
sentinel arithmetic and every Recall, All-Evidence, MRR, and nDCG delta:

```text
40/40 rows recomputed
paired-delta mismatches: 0
```

Selected source-scoped results are:

| System | n | Recall@5 | Recall@20 | All-Evidence@20 | MRR |
|---|---:|---:|---:|---:|---:|
| V-CLIP | 4 | 0.25 | 0.50 | 0.50 | 0.1607 |
| V-SIGLIP2 | 4 | 0.25 | 0.25 | 0.25 | 0.0833 |
| A-AST | 1 | 0.00 | 1.00 | 1.00 | 0.1000 |
| A-CLAP | 1 | 0.00 | 0.00 | 0.00 | 0.0000 |
| S-BM25 | 2 | 1.00 | 1.00 | 1.00 | 1.0000 |
| F-CTRL | 5 | 0.50 | 0.90 | 0.80 | 0.3986 |
| F-V | 5 | 0.50 | 0.70 | 0.60 | 0.3367 |
| F-A | 5 | 0.50 | 0.70 | 0.60 | 0.3786 |
| F-VA | 5 | 0.50 | 0.50 | 0.40 | 0.3167 |

The negative direction of several learned-model deltas is genuine under the
frozen provisional support routes. Technical readiness does not require the
new model to outperform its control.

## 6. Probe scope

All 60 route-suppression rows explicitly state:

```text
probe_scope=clean_top20_suppression_projection
fresh_full_universe_rerank=false
retrieval_recovery_only=true
```

All eight validated-negative displacement rows are also marked
`retrieval_recovery_only=true`.

Therefore the evidence supports bounded retrieval-level suppression and
restoration diagnostics only. It does not support a claim of learned-agent
recovery or fresh full-universe counterfactual reranking.

## 7. Integrity and disclosure checks

```text
run-manifest artifacts: 22/22 exact
restricted directory/file permissions: passed
restricted symlinks: none
persistent frame/audio/video derivatives: none
public absolute-path/proxy/vector/transcript leakage: none
```

The public result files remain summaries; evaluator-private rankings and
learned vectors stay under the restricted tree.

## 8. Executed verification

### Model acquisition validation

```text
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
python tools/scale1b_wave_r_model_preflight.py \
  --repo-root . --validate-existing

WAVE_R_MODELS_VALID
```

### Strict Wave-R verifier with actual-model spot inference

```text
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
PYTHONPATH=src python scripts/verify_scale1b_wave_r.py \
  --repo-root . --spot-recompute

passed=true
failures=[]
siglip2_max_abs=0.00010824203491210938
clap_max_abs=0.00003039836883544922
```

### Independent artifact audit

```text
PYTHONPATH=src python scripts/audit_scale1b_wave_r.py --repo-root .

82 checks passed
0 failures
```

The script rewrote its legacy Task-103 `final_audit.json` deterministically;
that file is not a Task-105 deliverable and is not included in the Wave-R
22-artifact run manifest. Its resulting content remains a passing Task-103
audit record.

### Focused tests

```text
PYTHONPATH=src pytest -q \
  tests/test_scale1b_wave_r_model_acquisition.py tests_scale1b

49 passed
```

### Full relevant regression

```text
PYTHONPATH=src pytest -q \
  tests tests_mvp tests_media tests_agent_runtime \
  tests_validation tests_media_pipeline tests_real_av \
  tests_scale1a tests_scale1b

530 passed
exit code 0
```

Warnings were limited to the unavailable CUDA runtime, dependency-version
warnings, and SWIG deprecation warnings; no test failed.

## 9. Diagnostic decision

The Task-101 preregistered condition is satisfied without changing thresholds:

- source-scoped paired changes occur on three retained families:
  `r004`, `r007`, and `r011`;
- corresponding paired changes persist in cross-source evaluation;
- fused All-Evidence boundaries change.

The principal observed direction is degradation:

- SigLIP has lower Recall@20 than CLIP over the four provisional visual
  families;
- CLAP misses the sole provisional ambient family by depth 20 while AST
  retrieves it;
- F-VA has lower All-Evidence@20 than F-CTRL.

This is a useful diagnostic result: replacing a domain-aligned or task-aligned
control with a generic learned encoder can materially alter and degrade
full-timeline evidence localization. It is not evidence that one architecture
is generally superior.

## 10. Remaining scientific limitations

- Only five retained families are scored.
- Only one family is eligible for the audio comparison.
- The retained routes are machine adjudicated and provisional.
- No answer/evidence set is human gold.
- Minimality and modality necessity remain unvalidated.
- No learned generator or learned agent is evaluated in Wave R.
- Probe interventions are top-20 projections rather than full-universe
  reranks.
- Results carry `LOW_N_DESCRIPTIVE_WAVE_R`; no significance, SOTA, or
  population-level claim is justified.

Subject to those explicit boundaries, the current repository proves the
bounded Wave-R learned-retrieval milestone.
