# AV-TRACE migration and recovery runbook

**As of:** 2026-10-23  
**Decision output:** `READY` or `BLOCKED`  
**Verifier:** `scripts/verify_migration_readiness.py`  
**Execution boundary:** model-free verification; no upload and no token read.

This runbook restores a new machine from reviewed code plus independently
authorized upstream sources. It is not a procedure for copying the current
working tree wholesale.

## Recovery order

Follow this order:

1. clone GitHub code with LFS smudging disabled;
2. create and inventory the Python/system environment;
3. obtain fresh GitHub/HF credentials and authenticate on the new machine;
4. restore only approved project assets, preferably by pinned upstream
   re-download;
5. verify file identities, revisions, permissions, and path rebinding;
6. run model-free smoke/tests;
7. rebuild derived caches and generated outputs from code;
8. regenerate machine-local plans and confirm that plans/authorizations are
   current;
9. only then seek approval for a separate model or acquisition execution.

Do not skip directly from copied files to execution.

## Phase 0: establish the recovery boundary

Read:

- `docs/migration/new_machine_bootstrap.md`;
- `docs/migration/github_release_boundary.md`;
- `docs/migration/huggingface_assets.md`;
- `data/migration/hf_asset_manifest.json`;
- `data/migration/path_rebinding_manifest.json`.

Record the new:

- repository root;
- machine/host identity;
- Python environment;
- CUDA driver/GPU identity, if applicable;
- authorized operators and data sources;
- GitHub commit/tag or reviewed source archive identity;
- date of each newly issued authorization.

The absence of a repository-level code license remains a public-release
blocker; it does not prevent an authorized internal recovery, but it prevents
assuming public redistribution rights.

## Phase 1: clone and environment

Use the commands in `new_machine_bootstrap.md`. Required minimums:

- Python satisfying `pyproject.toml` (`>=3.11`);
- Git;
- Git LFS, even when payload download remains disabled;
- PyAV and the four core pyproject dependencies;
- external `ffmpeg` and `ffprobe`;
- `huggingface-hub`/`hf` for pinned upstream restoration;
- a working NVIDIA driver only if the planned post-readiness workload requires
  a GPU.

Torch, Transformers, Safetensors, OpenCV, PyArrow, and XGrammar are optional
for base readiness but may be required by a selected restoration plan. Install
them from reviewed sources and record versions. Do not treat the source
machine's Python 3.13/Torch build as portable.

## Phase 2: fresh credentials and reauthorization

### GitHub

For private code, authenticate interactively with `gh auth login`, or inject a
short-lived `GH_TOKEN` from a secret manager. Never put a real token in this
repository, a migration JSON, a command transcript, or an issue.

### Hugging Face

Issue a new least-privilege token, then:

```bash
hf auth login
hf auth whoami
```

For automation, inject `HUGGINGFACE_HUB_TOKEN` or the site-standard equivalent
at runtime. The readiness verifier accepts `--hf-authenticated` as an operator
attestation; it deliberately does not inspect token stores or environment
values.

### Source-specific access

EPIC, CaptainCook4D, LongVideoBench, gated HF datasets/models, private derived
repositories, and any source-specific portals require current access on the
new machine/operator. Old cookies, headers, authorization JSON, approval
receipts, attempts, nonces, and governance ledgers do not transfer authority.

Generate a new authorization artifact only through the current approved
process. Its subject, machine, plan hash, expiry, and requested operation must
match the new recovery action.

## Phase 3: decide what migrates

Use each `upload_policy` in `data/migration/hf_asset_manifest.json`.

| Policy | New-machine action |
|---|---|
| `redownload_upstream` | Restore from the exact upstream repository/object and pinned revision. Do not copy local weights as the default. |
| `rebuild_from_code` | Restore code/input identities, then rebuild. Do not copy generated cache/output bytes. |
| `private_derived_index` | Restore only after owner review, private-repository authorization, and dependency/hash checks. |
| `public_metadata_only` | Restore only reviewed, redacted, non-substitutive metadata. |
| `never_upload` | Do not use HF/project rehosting as a migration route. Reacquire from the authorized source or leave absent. |
| `delete_after_verified_migration` | Do not migrate staging chunks. They are disposable only after the final source asset and independent backup have verified. |

### Not portable as execution state

The following may not be reused to start work:

- old attempt markers, `.exit_code`, stdout/stderr, raw attempts, or failure
  capsules;
- authorization or approval records from the old machine;
- `.authorization_nonces`;
- cookies, browser state, request headers, tokens, credential caches, private
  keys, or proxy credentials;
- temporary range/chunk staging;
- generated Python/test/lint caches, wheels, build directories, or HF cache
  locks;
- old plans that embed the old root, machine identity, stale source route, or
  expired authorization.

### Audit-only material

R22 capsules, terminal markers, ledgers, status snapshots, and historical
reviews may be retained only when needed for audit. Recommended destination:

```text
data/migration/audit_archive/r22/
```

Requirements:

- copy only reviewed files;
- record and verify their source SHA-256 values;
- retain exact bytes, including the old absolute path;
- make the archive read-only;
- keep it outside every runtime authorization search path;
- never interpret its marker/decision as permission for a new run.

The readiness verifier fails if owner-write permission remains on an R22 audit
archive.

## Phase 4: path rebinding

The old root is:

```text
/path/to/av-trace
```

Run:

```bash
python scripts/bootstrap_new_machine.py --mode check --repo-root "$AV_TRACE_ROOT"
```

Classifications:

1. **public code blocker** — executable code/current public config must be
   changed to use `--repo-root`, `AV_TRACE_ROOT`, script-relative discovery, or
   repository-relative paths;
2. **restricted runtime config** — regenerate from code with fresh
   authorization; do not blindly substitute a path string;
3. **historical audit immutable** — preserve exact bytes and old path;
4. **migration metadata** — permitted to name the old root while explaining
   the migration.

The default safe rewrite plan is dry-run. There are no files approved for
automatic in-place replacement. Never rewrite hash-bound manifests, receipts,
signatures, attempts, capsules, audit reports, or provenance merely to make
their old path disappear.

## Phase 5: restore assets

### Models

For every `model.*` asset:

1. inspect its `reconstruction_command`, acquisition manifest, repository ID,
   allowlist, and immutable revision;
2. renew gated/private access if required;
3. run the downloader only in a separately approved session;
4. prohibit remote repository code unless the reviewed acquisition explicitly
   allows it;
5. verify exact selected filenames, sizes, hashes, and revision;
6. store files below a `0700` directory with `0600` files;
7. keep attempt/download logs out of the authorization surface.

Do not run inference as part of restoration acceptance.

### Media and source data

Prefer exact upstream re-download from the official route. Verify the
source-specific manifest, aggregate sizes, and per-file hashes before
promotion. A public URL or private HF repository is not by itself
redistribution authorization.

Do not migrate:

- EPIC range staging chunks;
- unreviewed raw media through project Git/HF;
- restricted media merely because the destination repository is private;
- mixed-license media without item-level rights review.

### Private derived/index artifacts

Restore only the manifest-approved subset. Verify:

- dependency source/media/model identities;
- declared index/manifest SHA-256;
- file count and byte count;
- absence of symlinks and unexpected files;
- exact private modes;
- scientific-integrity boundaries such as sealed or untouched identities.

Use `scripts/prepare_hf_upload.py` only to generate an inert plan, and
`scripts/verify_hf_mirror.py` to verify a separately restored mirror. Neither
script is upload authorization.

## Phase 6: machine-readable acceptance

First run without claiming readiness to see all blockers:

```bash
python scripts/verify_migration_readiness.py \
  --repo-root "$AV_TRACE_ROOT" \
  --skip-tests \
  --format json \
  --json-output /tmp/av-trace-readiness-preflight.json
```

Then run the full model-free acceptance:

```bash
python scripts/verify_migration_readiness.py \
  --repo-root "$AV_TRACE_ROOT" \
  --hf-authenticated \
  --format json \
  --json-output /tmp/av-trace-readiness.json
```

Add `--require-gpu` only when the recovered workload contract requires one.
Use `--full-hash` only when the operator intentionally accepts the I/O cost of
hashing all directly hashable assets. The default avoids re-hashing very large
payloads when a source-specific manifest already carries per-file identities.

The verifier checks:

- required repository files;
- path rebinding and unclassified old-root references;
- Python, core dependencies, Git, Git LFS, FFmpeg, and FFprobe;
- HF authentication attestation without reading a token;
- upstream-redownload asset presence, exact inventory, supporting manifest
  hashes, and recorded model redownload revisions;
- media/index declared identities;
- exact `0600`/`0700` permissions and no symlinks;
- absence of old authorization/attempt state;
- optional read-only R22 audit archive;
- GPU visibility when required;
- focused model-free tests.

Output is `READY` only when every blocking check passes. Otherwise it is
`BLOCKED` and the JSON contains a stable blocker list.

## Phase 7: model-free smoke tests

The verifier runs:

```bash
python -m pytest -q \
  tests/test_migration_bootstrap.py \
  tests/test_hf_migration_tools.py \
  tests/test_manifest.py \
  tests/test_cli.py
```

These tests must not download assets, contact model services, load model
weights, or require a GPU.

Additional model-free suites may be run after the focused gate. Any test whose
fixture requires real media, model snapshots, private authorizations, or a
network route must remain outside this acceptance step.

## Phase 8: rebuild derived state

After `READY`:

1. rebuild deterministic/project-owned caches and outputs from code;
2. keep HF/Transformers caches machine-local and disposable;
3. regenerate media indexes only after their source dependencies verify;
4. regenerate runtime plans with the new root and current environment;
5. compute new plan hashes;
6. obtain fresh authorization tied to those new plan hashes;
7. archive old plans as historical, never as current.

The readiness result does not authorize a model run, acquisition, upload, or
public release. Those remain separate actions.

## Stop conditions

Report `BLOCKED` and stop when any of the following is true:

- GitHub/HF/source access has not been newly established;
- a required upstream revision is unavailable or mutable;
- a required file count, byte count, hash, or model revision differs;
- Git LFS, FFmpeg, or FFprobe is unavailable;
- a required GPU is not visible;
- a restricted file/directory has an open mode or symlink;
- an old authorization/attempt marker is present as runtime state;
- an absolute old-root reference is unclassified or remains in executable
  public code;
- a restricted runtime plan was string-rewritten instead of regenerated;
- R22 audit material is writable or mixed into runtime authorization;
- rights/privacy/redistribution approval is missing;
- focused model-free tests fail.

