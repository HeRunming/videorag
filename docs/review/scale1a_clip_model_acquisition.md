# Task 94 — Scale-1A CLIP snapshot acquisition

## Decision

```text
CONDITIONAL_GO
```

The exact bounded snapshot is acquired, verified, promoted, and usable for
local-only CLIP image/text embedding inference. The decision remains
conditional because the exact-revision Hugging Face model metadata and model
card do not declare a license. The snapshot stays restricted and
redistribution is not authorized.

The machine-readable gates are intentionally separate:

```text
technical_inference_decision: CLIP_SNAPSHOT_READY
redistribution_decision: NOT_AUTHORIZED
overall/release decision: CONDITIONAL_GO
```

`CLIP_SNAPSHOT_READY` permits Scale-1A to load this exact snapshot for
restricted internal inference only. It does not weaken or override the
redistribution decision.

## Exact identity and bound

- Repository: `openai/clip-vit-base-patch32`
- Revision: `3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268`
- Restricted snapshot:
  `data/restricted/noaa01/models/clip-vit-base-patch32-3d74acf/`
- Hard cap: `1,073,741,824` bytes
- Verified payload: `608,871,522` bytes in 9 allowlisted files
- Cap headroom: `464,870,302` bytes
- Selected framework weight: `pytorch_model.bin` (`605,247,071` bytes)
- Excluded duplicate/foreign framework weights: `flax_model.msgpack`,
  `tf_model.h5`

The allowlist contains the exact model card, model configuration, image
preprocessor configuration, tokenizer assets, and one PyTorch weight. No
safetensors weight exists at the pinned revision, and no second framework
weight was acquired.

## Official metadata and model-card evidence

The official exact-revision model API reported the requested repository and
40-character commit. The official exact-revision tree supplied each file's
byte size and Git object ID, plus the LFS SHA-256 for the PyTorch weight.
Downloaded response headers reported the same `X-Repo-Commit`; response ETags
matched the expected Git/LFS object identity; the LFS response also reported
its expected byte size.

The exact `README.md` is present at Git object
`8522e1fe72cb2372ff825dad901ccd718ce45d6b`, local SHA-256
`8f0e8c678e0afe5f384f3bf8a6694c1cb53c41e52f86277967b6c5354cb0f9f4`.
Neither `cardData.license`, a `license:` model tag, nor README front matter
provides a license. This absence is not interpreted as permission: the
restricted-storage technical gate passes, while the release/redistribution
gate remains closed.

## Acquisition and integrity controls

The downloader enforced the cap before payload transfer, used exact revision
URLs and resumable `curl` transfers through the authorized primary proxy, and
removed all proxy headers/temporary metadata before promotion. No credential
was printed or persisted.

Files were downloaded into a fixed restricted staging directory (`0700`),
then checked for:

- exact complete allowlist and no extra files;
- expected byte size for every file;
- local Git blob identity (or reconstructed Git LFS pointer identity);
- local SHA-256 for every file and the upstream LFS SHA-256 for the weight;
- exact response commit/object identity;
- no symlinks or subdirectories; and
- restricted file modes (`0600`).

`SHA256SUMS` was written and verified before the staging directory was
atomically renamed to the final snapshot. The final directory is `0700` and no
staging directory remains.

## Offline inference verification

The promoted snapshot was independently loaded with network access disabled
and `local_files_only=True`:

- Python `3.13.11`
- Linux `5.4.241-1-tlinux4-0017.7`, x86_64, glibc `2.28`
- PyTorch `2.10.0`, CPU, float32, one thread
- Transformers `5.2.0`
- NumPy `1.26.4`
- Pillow `12.1.0`
- deterministic algorithms enabled, seed `0`
- `CLIPProcessor(..., use_fast=False)`

A synthetic in-memory `224 x 224` RGB gradient and the text
`a synthetic red and green gradient` produced:

- image embedding shape: `[1, 512]`
- text embedding shape: `[1, 512]`
- normalized cosine similarity: `0.2803524136543274`
- exact deterministic replay: passed

The synthetic image was never written to disk, and no media derivative was
retained.

## Verification commands and tests

Focused acquisition tests:

```text
pytest -q tests/test_scale1a_model_acquisition.py
12 passed
```

Independent offline verifier:

```text
python tools/scale1a_model_preflight.py --validate-existing --offline-smoke --repo-root .
status: VALID
files: 9
payload_bytes: 608871522
```

Task 94b repaired the shared-model-root compatibility check. NOAA adjudication
continues to verify exactly its own two pinned `model.safetensors` weights and
the exact file sets within those owned snapshots. The separately registered
CLIP `pytorch_model.bin` is accepted only when its Task-94 manifest identity,
technical-use gate, fail-closed redistribution gate, byte count, and SHA-256
all match. Unregistered or conflicting PyTorch weights remain rejected.

The authoritative machine-readable record is
`data/restricted/noaa01/models/scale1a_clip_acquisition_manifest.json`.
