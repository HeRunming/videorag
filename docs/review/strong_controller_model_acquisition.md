# Strong controller model acquisition

**Finalized:** 2026-09-21 (Asia/Shanghai)  
**Decision:** `STRONG_CONTROLLER_MODEL_SNAPSHOT_READY`  
**Status:** `COMPLETE_VALIDATED_PROMOTED_SMOKE_PASSED`

## Frozen candidate and scope

- Repository: `Qwen/Qwen2.5-7B-Instruct`
- Exact revision: `a09a35458c702b33eeacc393d103063234e8bc28`
- Architecture: `Qwen2ForCausalLM`
- Exact-revision API/tree, README/model card, and license text remain archived under
  `data/restricted/scale1b/acquisition_records/strong_controller/qwen2.5-7b-a09a35458c70`.
- This task only resumed and validated the frozen snapshot and ran one synthetic
  controller smoke. It did not run `r017`, any scientific evaluation, or any
  evaluation family, and it did not modify Task-110/111 code or results.
- No redistribution authorization is claimed.

## Resume and byte accounting

Task 112 had already verified `config.json`, `generation_config.json`, the
safetensors index, and shard 1. Those `3,945,470,098` bytes were preserved and
re-verified; the complete shard was not downloaded again.

Task 113 downloaded the five missing allowlisted files sequentially with
resumable curl, ordinary bounded `--retry`, `--continue-at -`, and an explicit
output filename for each request. Final HTTP responses were successful, the
exact revision header was present, HTML/error payload signatures were rejected,
and each local file was required to have the archived expected byte size and
identity.

- Task-113 downloaded bytes: `11,292,869,398`
- Exact promoted payload: `15,238,339,496` bytes (14.192 GiB)
- Acquisition-record archive at final accounting: `174,031` bytes
- Total accounted acquisition: `15,238,513,527` bytes
- Selected-payload cap: `21,474,836,480` bytes (20 GiB) — pass
- Total-acquisition cap: `23,622,320,128` bytes (22 GiB) — pass

## Hash and structural validation

| File | Bytes | SHA-256 |
|---|---:|---|
| `config.json` | 663 | `7463bb0ea78315365e6c6b74de4e73bbcc8359dfb0c5a737584e077d42c0b03c` |
| `generation_config.json` | 243 | `3a8f9087e486054c8a4a08dae2e5a3ba62e23da212b5b8c08bc42cb983c3459f` |
| `model-00001-of-00004.safetensors` | 3,945,441,440 | `a1333e6293854747c481288ea83b348226af178dd565c49b6f9495ba1966aba7` |
| `model-00002-of-00004.safetensors` | 3,864,726,352 | `f5d25a2772cb825164a2a2c0fb6d51a87e282abf21e4dd75bc5cfb3cd0ea6185` |
| `model-00003-of-00004.safetensors` | 3,864,726,424 | `8efdec4c1bc12317ae1a38dc42b595ce777738a64deea3fcb8a0a91381bcdfd5` |
| `model-00004-of-00004.safetensors` | 3,556,377,672 | `1a72d403cdf0c1ec3cb7f289f17b394a01e64394c2e9b3c0f94dbce3faf879bd` |
| `model.safetensors.index.json` | 27,752 | `624bf7c47cd12468fdc16e38a47cf4f19e0415b859a223ba3c027eed2f0e1028` |
| `tokenizer.json` | 7,031,645 | `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539` |
| `tokenizer_config.json` | 7,305 | `5b5d4f65d0acd3b2d56a35b56d374a36cbc1c8fa5cf3b3febbbfabf22f359583` |

Validation passed:

- all four referenced safetensors shards exist and open with `safe_open`;
- the index contains 339 tensors and references exactly shards 1 through 4;
- the aggregate shard tensor-key set exactly matches the index;
- config and tokenizer load locally with `local_files_only=True` and
  `trust_remote_code=False`;
- the directory contains exactly the nine allowlisted regular files;
- no pickle weights, symlinks, executable-code files, or unexpected files exist.

The complete stage was atomically promoted by a same-parent rename to:

`data/restricted/scale1b/models/Qwen--Qwen2.5-7B-Instruct--a09a35458c70`

## Deterministic synthetic smoke

An initial process stopped before model loading because of the installed
SciPy/NumPy scalar-alias mismatch; no generation occurred. One actual CPU
`bfloat16` smoke then ran in a network namespace with proxy variables
removed, offline environment flags set, Python socket calls denied, and
`local_files_only=True`. The prompt was a synthetic multiplication tool call;
it contained no scientific/evaluation-family content.

- Result: pass
- Strict tool-schema JSON: valid
- Parsed call: `multiply({"a": 11, "b": 6})`
- Repair attempts: `0` (maximum permitted: 1)
- Prompt/completion/total tokens: `187 / 26 / 213`
- Tokenizer load: `0.484462` s
- Model load: `3.729040` s
- Generation: `19.527585` s
- In-process elapsed: `26.391916` s
- Peak RSS: `15,210,754,048` bytes (`14,854,252` KiB)
- Network attempts observed: `0`

The installed SciPy/NumPy combination required process-local NumPy scalar
aliases before importing the model class. This changed no repository,
environment, or model file.

Structured validation and smoke records are stored alongside the archived
acquisition metadata as `task113_snapshot_validation.json` and
`task113_smoke.json`.
