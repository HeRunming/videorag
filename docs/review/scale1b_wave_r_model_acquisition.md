# Scale-1B Wave R model acquisition review

**Task:** 102  
**Date:** 2026-09-12  
**Scope:** exact acquisition and offline validation tooling for SigLIP2 and
CLAP; no Scale-1A production or result artifact was changed.

## Final decision

```text
SIGLIP2_SNAPSHOT_READY
CLAP_SNAPSHOT_READY
WAVE_R_MODELS_READY
```

Both exact snapshots are now installed for restricted internal inference.
Redistribution remains independently closed pending a release review.

## Exact frozen targets

| Model | Exact revision | Allowlisted payload | Cap | Weight representation |
|---|---|---:|---:|---|
| `google/siglip2-base-patch16-224` | `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2` | 1,539,456,768 B | 2 GiB | `model.safetensors` only |
| `laion/clap-htsat-unfused` | `8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a` | 617,900,277 B | 1 GiB | `pytorch_model.bin` only |

Total frozen transfer payload:

```text
2,157,357,045 bytes < 3 GiB
```

The allowlists contain only the exact Transformers-compatible model,
processor, tokenizer and model-card files from the exact-revision trees.
`.gitattributes` and all alternative framework weights are excluded.

## Metadata and license evidence

Task 92 had already retrieved official Hugging Face API and recursive-tree
responses for both exact commits on 2026-09-11. Task 102 copied those records
into restricted provenance storage and independently validated:

- exact repository ID and 40-hex revision;
- `private=false`, `gated=false`;
- exact file size, Git object ID and LFS SHA-256 for every allowlisted file;
- one and only one selected framework weight;
- consistent `apache-2.0` metadata in `cardData` and official tags.

The downloader re-fetched current exact-revision API, tree and README evidence,
validated the README Git identity and archived the responses under restricted
storage. The SigLIP metadata archive was reused only after exact local
revalidation when its already-complete staging directory was resumed.

Even after successful technical validation, redistribution remains:

```text
NOT_AUTHORIZED_PENDING_RELEASE_REVIEW
```

An Apache-2.0 metadata declaration is evidence for a later release review; it
is not converted automatically into benchmark redistribution authorization.

## Implemented fail-closed acquisition

The downloader implements:

- exact `resolve/<40-hex-revision>/<filename>` URLs;
- pre-network per-model and total cap enforcement;
- restricted `0700` staging and `0600` files;
- resumable `curl --continue-at -` transfers;
- bounded connect and transfer timeouts;
- response `x-repo-commit` and ETag/object-identity checks;
- exact local size, Git object/LFS identity and SHA-256 checks;
- SigLIP2 safetensors structure validation;
- complete allowlist enforcement, no symlinks or extra files;
- canonical `SHA256SUMS` generation and verification;
- atomic snapshot promotion only after validation;
- preservation of a restricted partial staging directory on transfer failure;
- no token or credential persistence.

## Offline smoke contract

After each complete snapshot is verified, the downloader sets the Hugging Face
and Transformers offline flags, removes token environment variables and runs
on CPU with `local_files_only=True`.

### SigLIP2

- `Siglip2Processor` and `Siglip2Model`;
- deterministic in-memory 224×224 RGB gradient;
- one text query;
- normalized image and text vectors;
- cosine similarity;
- second inference with maximum absolute-difference tolerance `1e-6`.

### CLAP

- `ClapProcessor` and `ClapModel`;
- deterministic in-memory 440 Hz waveform at the processor sample rate;
- one text query;
- normalized audio and text vectors;
- cosine similarity and the same replay tolerance.

The manifest records class names, embedding dimension, dtype, similarity,
load/inference latency, peak RSS and runtime versions. No image or waveform is
written to disk.

## Runtime-class correction

The repository name contains `siglip2`, but this exact snapshot declares:

```json
{"model_type": "siglip"}
```

The original smoke implementation incorrectly selected `Siglip2Model`.
Runtime class selection is now driven by the pinned local `config.json`:

```text
model_type=siglip  → SiglipModel + SiglipProcessor
model_type=siglip2 → Siglip2Model + Siglip2Processor
```

Unknown model types fail closed. For the acquired snapshot the recorded
classes are `SiglipModel` and `SiglipProcessor`.

## Completed offline inference

| Model | Embedding dim | dtype | Similarity | Replay max delta | Load | First inference | Replay inference | Peak RSS |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| SigLIP | 768 | float32 | 0.1564454 | 0.0 | 4.52 s | 1.36 s | 0.52 s | 2,014,160 KiB |
| CLAP | 512 | float32 | 0.4327447 | 0.0 | 4.65 s | 0.50 s | 0.21 s | 1,402,184 KiB |

The values above are the acquisition-run measurements stored in the
restricted manifest; timing is descriptive and host-dependent.

## Revalidation command

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
python tools/scale1b_wave_r_model_preflight.py \
  --validate-existing --offline-smoke
```

## Validation performed now

```text
python -m py_compile:
PASS

focused Task-102 tests:
17 passed

default tests/:
PASS, exit code 0
```

The strict offline validator reports:

```text
WAVE_R_MODELS_VALID
```
