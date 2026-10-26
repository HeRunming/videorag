# AV-TRACE new-machine bootstrap

**As of:** 2026-10-23  
**Default mode:** dry-run and read-only  
**Scope:** create a clean runtime without uploading data, copying credentials,
running models, or treating old execution records as authorization.

The machine-readable path policy is
`data/migration/path_rebinding_manifest.json`. The environment planner is
`scripts/bootstrap_new_machine.py`; it does not install packages or access the
network.

## Safety boundary

On a new machine:

- clone code and reviewed public metadata, not the old working tree;
- never copy a real GitHub or Hugging Face token into this repository;
- do not copy shell history, browser cookies, credential caches, proxy
  credentials, SSH private keys, or `.env` files from the old machine;
- do not copy old attempt markers, authorization JSON, approval receipts, or
  authorization nonces as runnable state;
- treat R22 capsules/markers as read-only historical audit material only;
- do not copy model weights when the HF asset manifest says
  `redownload_upstream`;
- do not move large media merely to make the new tree look complete;
- do not run a model during bootstrap or readiness verification.

## 1. Inspect the source environment

On the current machine, the following is safe and model-free:

```bash
cd /path/to/av-trace
python scripts/bootstrap_new_machine.py --mode check
```

The command inventories:

- `pyproject.toml`, including Python `>=3.11` and the core dependencies
  `av`, `jsonschema`, `numpy`, and `Pillow`;
- Python and installed distribution versions;
- `git`, Git LFS, `ffmpeg`, `ffprobe`, `nvidia-smi`, and the `hf` CLI;
- optional media/model packages such as PyAV, Torch, Transformers,
  `huggingface-hub`, OpenCV, Safetensors, PyArrow, and XGrammar;
- uses of the old absolute root and their migration classification.

It does **not** call `pip`, authenticate, clone, download, upload, rewrite,
chmod, run a model, or read a token.

The 2026-10-23 source host is not a target specification. In particular, its
observed Python 3.13/model stack may be useful audit evidence but should not be
blindly reproduced. Prefer Python 3.11 or 3.12 unless a separately tested
workload requires 3.13. Select the Torch build only after confirming the new
machine's NVIDIA driver/CUDA compatibility.

## 2. Select the new root and secret locations

Use one canonical repository root:

```bash
export AV_TRACE_ROOT="$HOME/src/AV-TRACE"
export AV_TRACE_REPO_URL="git@github.com:ORG/AV-TRACE.git"
```

Do not commit those site-specific values. Runtime code should resolve paths
from `--repo-root`, `AV_TRACE_ROOT`, or its own script location, and stored
project paths should be repository-relative.

Use a private HF cache below a protected local volume:

```bash
export HF_HOME="$AV_TRACE_ROOT/data/restricted/_hf_home"
export HF_HUB_CACHE="$HF_HOME/hub"
export TRANSFORMERS_CACHE="$HF_HOME/transformers"
```

If restricted data must live on another volume, document a reviewed
machine-local mapping outside Git. Do not replace repository-relative paths in
historical JSON to simulate portability.

## 3. GitHub authentication and clone

For a public repository, no GitHub token should be needed. For a private
repository, obtain a **new**, least-privilege credential on the new machine.
Do not migrate the old host's credential.

Preferred interactive setup:

```bash
gh auth login
gh auth status
```

Non-interactive CI template, only when the secret manager injects the value:

```bash
# Template only; never write a real value into a file or shell history.
export GH_TOKEN='${INJECT_FROM_SECRET_MANAGER}'
gh auth status
```

Clone without automatically materializing LFS payloads:

```bash
umask 077
GIT_LFS_SKIP_SMUDGE=1 git clone --filter=blob:none \
  "$AV_TRACE_REPO_URL" "$AV_TRACE_ROOT"
cd "$AV_TRACE_ROOT"
```

Run:

```bash
git lfs version
git lfs env
```

Do not run `git lfs pull` globally. Review each LFS object against the public
release boundary and the asset manifest first. Restricted media, model weights,
and authorization/audit payloads are not made safe merely because Git LFS can
transport them.

## 4. Create the Python environment

Example venv:

```bash
python3.11 -m venv "$AV_TRACE_ROOT/.venv"
source "$AV_TRACE_ROOT/.venv/bin/activate"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e "$AV_TRACE_ROOT"
python -m pip install pytest huggingface-hub httpx requests cryptography
```

The bootstrap script only prints these commands; it never runs them.

Install optional stacks by workload, not as an unreviewed monolith:

```bash
# Choose the correct official CPU/CUDA Torch index for the new driver first.
python -m pip install torch torchvision torchaudio

# Install only the optional packages required by the planned workload.
python -m pip install transformers safetensors opencv-python pyarrow xgrammar
```

Install system tools through the new machine's approved package manager:

- Git and Git LFS;
- FFmpeg with both `ffmpeg` and `ffprobe`;
- an NVIDIA driver visible to `nvidia-smi` when GPU work is required;
- compiler/system libraries required by locally selected Python wheels.

Record exact versions after installation. PyAV embeds/links FFmpeg libraries,
but that does not replace the external `ffmpeg`/`ffprobe` acceptance checks.
Media byte-level reproducibility may depend on PyAV, FFmpeg, and codec build
versions.

## 5. Hugging Face authentication

After a new token is issued to the new machine/operator:

```bash
install -d -m 0700 "$HF_HOME" "$HF_HUB_CACHE" "$TRANSFORMERS_CACHE"
hf auth login
hf auth whoami
```

Paste the token only through the hidden interactive prompt. Do not put it on a
command line. For ephemeral automation, use a secret manager:

```bash
# Template only.
export HUGGINGFACE_HUB_TOKEN='${INJECT_FROM_SECRET_MANAGER}'
```

Some libraries also recognize `HF_TOKEN`; choose one site policy and avoid
duplicating secrets. The migration scripts in this package do not read either
variable. Proxy templates, if required by the site, must remain blank in
versioned files:

```bash
export HTTPS_PROXY=''
export HTTP_PROXY=''
export NO_PROXY=''
```

## 6. Dry-run planner

Generate a machine-specific command plan without executing it:

```bash
python scripts/bootstrap_new_machine.py \
  --mode plan \
  --new-root "$AV_TRACE_ROOT" \
  --repo-url "$AV_TRACE_REPO_URL" \
  --format json \
  --json-output /tmp/av-trace-bootstrap-plan.json
```

Run the local dependency and path check:

```bash
python scripts/bootstrap_new_machine.py \
  --mode check \
  --repo-root "$AV_TRACE_ROOT" \
  --format json \
  --json-output /tmp/av-trace-bootstrap-check.json
```

An exit code of `1` means a public-code or unclassified use of the old root was
found. Historical immutable references do not fail this check.

## 7. Secure directory modes

Before placing any restricted bytes:

```bash
install -d -m 0700 "$AV_TRACE_ROOT/data/restricted"
find "$AV_TRACE_ROOT/data/restricted" -type d -exec chmod 0700 {} +
find "$AV_TRACE_ROOT/data/restricted" -type f -exec chmod 0600 {} +
```

The final verifier requires exact `0700` for restricted directories and `0600`
for restricted files and rejects symlinks. Apply the same boundary to
machine-local access review, acquisition preflight, HF recon, and source recon
trees if they are restored.

## 8. Handoff

Continue with `docs/migration/migration_runbook.md`. Bootstrap is complete only
when:

1. code is cloned into the chosen root;
2. the environment and required system executables exist;
3. fresh GitHub/HF authentication is confirmed where needed;
4. old absolute paths are classified with no current public-code blocker;
5. restricted storage is private;
6. no old authorization state has been activated.

