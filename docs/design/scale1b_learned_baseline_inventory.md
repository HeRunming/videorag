# Scale-1B learned baseline and local capability inventory

**Task:** 92  
**Inventory time:** 2026-09-11, Asia/Shanghai  
**Scope:** planning only; no heavyweight model was downloaded and no production
code or Pilot-0/Scale-1A artifact was changed.

## Decision

```text
READY_FOR_BOUNDED_DOWNLOADS
```

This is authorization for staged, checksum-recorded downloads and smoke tests,
not a claim that learned baselines are runnable at benchmark scale today. The
host has ample CPU RAM and disk, but no usable CUDA device was visible during
this inventory. Official Hugging Face metadata for the minimal candidates was
retrieved through the configured proxy, while ordinary sandbox networking
could not resolve that proxy. Network use is therefore **context-dependent and
must be re-preflighted** before every download wave.

## 1. Locally verified capability inventory

### 1.1 Host

| Item | Locally observed value | Consequence |
|---|---|---|
| OS/kernel | Linux x86_64, kernel `5.4.241-1-tlinux4-0017.7` | Supported by current PyTorch/PyAV environment |
| CPU | 2 sockets, 96 physical cores/socket, 384 logical CPUs; AMD EPYC 9K84 | Strong CPU preprocessing/index construction capacity |
| RAM | 2.2 TiB total, about 1.6 TiB available at inventory time | CPU smoke inference and large embedding/index buffers are feasible |
| Swap | 0 | Workers must fail before exhausting RAM; no swap safety net |
| Repository filesystem | `dop-fuse`, 22 PiB total, about 5.1 PiB available | Storage is not the immediate bottleneck |
| GPU | `nvidia-smi` exists but cannot communicate with the driver; `torch.cuda.is_available() == False`, device count 0 | Treat the current runtime as CPU-only. Do not promise GPU throughput |

GPU readiness must be established in the actual execution allocation, not
inferred from an installed CUDA-enabled Torch build.

### 1.2 Runtime and packages

| Package/tool | Version/status |
|---|---|
| Python | `3.13.11` |
| PyTorch | `2.10.0` |
| torchvision | `0.25.0+8ac84ee` |
| torchaudio | `2.10.0+27b7ebd` |
| Transformers | `5.2.0` |
| tokenizers | `0.22.2` |
| accelerate | `1.9.0` |
| datasets | `4.0.0` |
| huggingface-hub | `1.5.0` |
| PyAV | `16.1.0` |
| NumPy / SciPy | `1.26.4` / `1.18.0` |
| flash-attn | `2.8.3`, but unusable without a working CUDA device |
| qwen-vl-utils | `0.0.14` |
| Pillow | `12.1.0` |
| ffmpeg / ffprobe executables | unavailable |
| PyAV FFmpeg libraries | available: libavcodec 62, libavformat 62, libswresample 6, etc. |
| sentence-transformers | not installed |
| open-clip-torch | not installed |
| FAISS CPU/GPU | not installed |
| rank-bm25 | not installed |
| bitsandbytes | not installed |
| librosa / soundfile | not installed |
| scikit-learn | not installed |

The minimal stack deliberately uses native Transformers, Torch, NumPy and
PyAV. It does not require FAISS for Scale-1A-sized exact matrix search, external
ffmpeg, `sentence-transformers`, or `open-clip-torch`. BM25 should initially be
implemented with the repository's deterministic tokenizer and a small audited
implementation rather than adding an unnecessary package.

Python 3.13 is a compatibility risk for model-specific dependencies. Each
candidate must pass an import/load smoke test before any full snapshot or index
build is approved. Existing NOAA model execution also required the following
NumPy compatibility aliases before Transformers audio imports:

```python
if not hasattr(np, "long"):
    np.long = np.int64
if not hasattr(np, "ulong"):
    np.ulong = np.uint64
```

This must be tested explicitly rather than silently assumed for CLAP.

### 1.3 Existing exact local model snapshots

Both snapshots are under `data/restricted/noaa01/models/`, whose directory
permissions are `0700`. Their files have locally recorded SHA-256 manifests.

| Model | Exact local directory | Weight size | Weight SHA-256 | Current role |
|---|---|---:|---|---|
| `openai/whisper-tiny.en` | `whisper-tiny.en-87c7102` | 151,060,136 B | `db59695928ded6043adaef491a53ef4e12da9611184d77c53baa691a60b958ad` | Timestamped English speech observation candidate |
| `MIT/ast-finetuned-audioset-10-10-0.4593` | `ast-audioset-f826b80` | 346,404,948 B | `ae0c1e2ad4e1381d851fa9bf298ba13ebc9c5a914cdee2dbe427a6583869924d` | Audio-event routing/diagnostic layer, not text retrieval |

Their combined directories occupy approximately 502 MB. AST is not a
replacement for audio-text retrieval because it predicts a fixed AudioSet
label vocabulary; it remains useful for event proposals and CLAP cross-checks.

### 1.4 Network status

Facts observed in this task:

1. An ordinary sandboxed `curl` could not resolve `https://proxy.example.invalid:3128`.
2. A separately authorized `curl` through the same proxy successfully read
   official Hugging Face model API metadata for the selected candidates.
3. No heavyweight weights were downloaded.
4. Hugging Face CLI authentication was not conclusively re-verified in this
   task because the follow-up command stalled and was stopped.

Required assumptions:

- Proxy hostname/port are supplied through environment variables; artifacts
  must not store credentials or private proxy details beyond the fact that a
  proxy is required.
- `HF_ENDPOINT=https://hf-mirror.com` may be used only as a transport fallback.
  Exact repository commit, file list, byte count and locally computed SHA-256
  remain authoritative.
- Prior work found mirror HEAD-metadata incompatibility with
  `snapshot_download`; pinned direct `resolve/<commit>/<file>` transfers are
  the robust fallback.

## 2. Minimal credible learned stack

The objective is not to collect many popular models. The smallest useful stack
must create independent experimental variation on:

- **Acquire:** lexical speech versus learned visual/audio retrieval and fusion;
- **Ground:** evidence-conditioned structured generation versus direct
  multimodal context;
- **Act:** reactive tool use versus explicit evidence-sufficiency control.

### 2.1 Primary baseline matrix

| Component | Exact candidate | Verified revision | License evidence | Modality / output | Estimated resources | Scientific role and limitations |
|---|---|---|---|---|---|---|
| Lexical speech | Deterministic BM25 over pinned Whisper chunks; no external model | Repository/config hash | Repository code license; Whisper snapshot separately pinned | text query → ranked speech segments | CPU; negligible model storage | Non-learned control. Measures the gain from semantic encoders without conflating ASR |
| Learned visual-text retrieval | `google/siglip2-base-patch16-224` | `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2` | Official HF metadata tag `apache-2.0`; archive model card | sampled frames + text → normalized similarity | 1.501 GB weight, 1.539 GB full snapshot; expected 2–4 GB inference RAM/VRAM plus batches | Primary visual retriever. Frame pooling is not native temporal reasoning |
| Learned audio-text retrieval | `laion/clap-htsat-unfused` | `8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a` | Official HF metadata tag `apache-2.0`; archive model card | waveform + text → normalized similarity | 614.5 MB weight, 617.9 MB snapshot; expected 2–4 GB inference RAM/VRAM | Primary non-speech/audio semantic retriever. Domain calibration and long-window pooling require validation |
| Learned multimodal fusion | Train-split-only regularized logistic calibration over BM25, SigLIP2 and CLAP scores, modality availability and rank features | New artifact pinned by code/config/training-row hashes | No new model license; derived features inherit source constraints | query and per-modality candidates → fused score | CPU; KB–MB parameters | Supplies an actually learned fusion baseline without another foundation model. It is admissible only after a non-evaluation training split exists; otherwise report fixed RRF as a non-learned fallback |
| Evidence-conditioned generator | `Qwen/Qwen2.5-1.5B-Instruct` | `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` | Official HF metadata and included `LICENSE`: `apache-2.0` | question + acquired observation text/metadata → strict claims/citations JSON | 3.087 GB weight, 3.099 GB snapshot; roughly 4–8 GB BF16/FP32/working RAM depending precision and context | Smallest credible local generator/controller. May be weak; that is diagnostically acceptable. Textualized evidence is not native A/V generation |
| Direct multimodal baseline | `HuggingFaceTB/SmolVLM2-2.2B-Instruct` | `482adb537c021c86670beed01cd58990d01e72e4` | Official HF metadata tag `apache-2.0`; archive model card | sampled video frames + question, optionally transcript/event text → structured answer | 8.987 GB weights, 8.992 GB snapshot; target ≥16 GB GPU, CPU smoke only on current host | Direct visual/video comparator. It does **not** establish native ambient-audio understanding; transcript/AST/CLAP text supplied to it must be disclosed |
| Learned ReAct controller | Same pinned Qwen 1.5B backbone, ReAct tool prompt and JSON action grammar | Same as generator plus prompt/config hashes | Same as generator | public state/tool responses → one tool call or finalization | Same loaded model; bounded context, temperature 0 | Tests query reformulation and reactive recovery. Same backbone isolates controller protocol but does not represent model diversity |
| Learned evidence-sufficiency controller | Same pinned Qwen 1.5B backbone, explicit public claim-slot coverage state and insufficiency decision | Same as generator plus distinct prompt/config hashes | Same as generator | public state/tool responses → tool call, abstention or supported finalization | Same loaded model; bounded context, temperature 0 | Tests stopping, missing-modality diagnosis and abstention. Must not see evaluator-private support sets or intervention state |

### 2.2 Optional upgrade, not in the first download wave

`Qwen/Qwen2.5-7B-Instruct` at
`a09a35458c702b33eeacc393d103063234e8bc28` was verified through official HF
metadata as Apache-2.0 and approximately 15.24 GB. It is useful only after a
working GPU allocation is demonstrated and the 1.5B stack has completed the
validation ladder. It must not delay Scale-1B.

### 2.3 Fallbacks

| Failure | Fail-closed fallback |
|---|---|
| SigLIP2 cannot load | Use existing handcrafted visual routing only and label learned visual retrieval unavailable; do not declare retrieval-ready |
| CLAP cannot load | Keep AST event-label plus lexical event search as non-learned diagnostic; do not declare learned audio retrieval-ready |
| Learned fusion lacks a leakage-safe train split | Use equal-weight reciprocal-rank fusion, explicitly `learned=false`; fusion gate remains false |
| Qwen 1.5B is too slow or incompatible | Try CPU one-family smoke with shorter context; otherwise use a versioned API model only under the provenance contract below. Deterministic policies remain protocol controls, not learned substitutes |
| SmolVLM2 is infeasible | Omit the direct multimodal row and retain the existing deterministic direct-context protocol probe, clearly non-learned |
| No usable GPU | Complete retrieval embedding builds on controlled CPU shards if timing is acceptable; generation/agent scale runs remain not ready |

## 3. Integration contract

No production integration is performed by Task 92. A later implementation
worker should add adapters rather than weaken current privacy boundaries.

### Retrieval

- Reuse full-timeline segmentation/index artifacts from Scale-1A.
- Add versioned embedding fields or sidecar matrices keyed only by
  answer-independent segment IDs.
- Use `src/av_trace_media_pipeline/indexing.py` for segment identity and index
  manifests.
- Replace the lexical scoring implementation behind `search_visual`,
  `search_speech`, and `search_ambient_audio`, not their public semantics.
- Return only opaque pointer, modality, interval, generic preview and score.
- Keep accepted evidence IDs, family IDs, answer aliases and intervention
  roles out of searchable documents and model prompts.
- Exact search can use Torch/NumPy matrix multiplication at this scale; add
  FAISS only after measured need and with its index parameters pinned.

### Generation

- Feed only observations actually acquired by the policy.
- Preserve Task-90 public claim handles and observation IDs.
- Require one strict JSON object:

```json
{
  "verdict": "answer|insufficient",
  "answer": "string or null",
  "asserted_claims": [
    {
      "claim_handle": "slot.<modality>.<n>",
      "text": "claim text",
      "citation_ids": ["opaque observation id"]
    }
  ],
  "claim_to_citations": {
    "slot.<modality>.<n>": ["opaque observation id"]
  },
  "abstention": false,
  "insufficiency_reason": null
}
```

- Validate once, allow at most one schema-repair turn under a separately
  charged budget, then fail closed to an invalid/abstaining output.
- Evaluator-private claim mapping remains post-validation.

### Agent

- Use `src/av_trace_agent_runtime/` JSONL isolation or an equivalent opaque-ID
  wrapper.
- Freeze identical tool availability, top-k, maximum steps, cost limit,
  context truncation and decoding parameters across learned ReAct and learned
  sufficiency controllers.
- Log prompt-template hash, model snapshot hash, input hash, output hash,
  random seed, wall time, token counts, tool calls and parse/repair outcomes.
- Never expose state role (`CLEAN/BLOCKED/RESTORED`), trigger, answer key,
  evidence route or evaluator IDs.

## 4. Validation ladder

Each stage is a hard prerequisite for the next.

### L0 — environment/import

1. Verify local snapshot file set, byte sizes and SHA-256.
2. Set offline flags and remove credentials from the inference process.
3. Import the exact processor/model classes under Python 3.13.
4. Load on CPU with `local_files_only=True`; record peak RSS and load time.
5. For an intended GPU run, independently require successful `nvidia-smi`,
   `torch.cuda.is_available()`, allocation/forward pass and VRAM measurement.

Pass: no network request, no unpinned custom code, finite parameters/output.  
Fail: missing files, implicit network access, unsupported architecture or OOM.

### L1 — one-segment inference

- SigLIP2: one decoded frame and two text queries; finite normalized vectors,
  deterministic ranking on replay.
- CLAP: one 10-second PyAV waveform and two queries; finite vectors and
  deterministic ranking.
- Qwen: one tiny evidence bundle; valid structured finalization.
- SmolVLM2: a small fixed frame set; valid response, with native-audio absence
  recorded.

Pass: same top ranking/JSON under two runs with fixed config, tolerating only a
declared floating-point epsilon.

### L2 — one-family end to end

Use one provisional family in CLEAN, BLOCKED and RESTORED:

- build embeddings without evaluator labels;
- run all enabled search routes;
- acquire exact media-backed observations;
- run grounded generation;
- run both learned controllers;
- enforce opaque IDs, budget, citations, intervention suppression and recovery;
- compare against deterministic protocol controls.

Pass: 12 expected policy/state trajectories complete or fail with a registered
reason; no privacy leakage or silent fallback.

### L3 — all-six compatibility

Run all six Task-85 provisional families against the Scale-1A full timeline,
not the 18-window bounded index. Report:

- Recall@K, first accepted-evidence rank and All-Evidence@K;
- Evidence Recall, Answer Score, Citation F1, Supported-Claim Rate;
- Success@Budget, Premature Stop and Recovery;
- bounded-to-full degradation and inspected-video fraction;
- null metrics and `LOW_N_DESCRIPTIVE_PILOT`.

Pass: every configured row is present; failed model calls are explicit; no
metric is imputed from a deterministic policy.

### L4 — reproducibility and failure injection

- Repeat embedding/index build and inference with fixed seeds/config.
- Hash model snapshots, processors, prompts, segment manifests, embeddings,
  indices, actions, responses and aggregate outputs.
- Test corrupt snapshot, unavailable channel, empty audio, malformed JSON,
  timeout, OOM, over-budget and API failure.
- OOM/timeout must yield a typed failure or abstention, never a partial answer
  scored as successful.
- Require deterministic index order and stable retrieval ranks; text
  generation should use greedy decoding. If exact generation bytes vary,
  retain complete provenance and report the variance.

### API-only handling

API models are optional, not substitutes for local reproducibility. Every call
must record provider, exact advertised model/version, endpoint class,
UTC timestamp, decoding parameters, prompt-template hash, redacted request
hash, response hash, usage and error. Mutable aliases without a dated/versioned
identifier are exploratory only. Restricted raw media or transcripts must not
be sent off-host without separate authorization. Cache only policy-safe
redacted payloads in restricted storage.

## 5. Bounded artifact and download plan

### 5.1 Storage layout

```text
data/restricted/scale1b/
  models/
    google--siglip2-base-patch16-224--75de2d55ec2d/
    laion--clap-htsat-unfused--8fa0f1c6d043/
    Qwen--Qwen2.5-1.5B-Instruct--989aa7980e4c/
    HuggingFaceTB--SmolVLM2-2.2B-Instruct--482adb537c02/
  manifests/
    download_plan.json
    download_manifest.json
    runtime_inventory.json
  embeddings/
  fusion/
  logs/
```

The root and snapshots should be `0700`; files should be `0600`.

### 5.2 Download waves

1. **Wave R, retrieval (about 2.16 GB):** SigLIP2 + CLAP.
2. **Wave G/A, generation and controllers (about 3.10 GB):** Qwen 1.5B.
3. **Wave D, optional direct baseline (about 8.99 GB):** SmolVLM2, only after
   L0/L1 and compute preflight.
4. **Wave U, optional upgrade (about 15.24 GB):** Qwen 7B, excluded until a
   suitable GPU is proven.

Official metadata verified on 2026-09-11:

| Repository | Commit | Full snapshot bytes | Weight files |
|---|---|---:|---|
| `google/siglip2-base-patch16-224` | `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2` | 1,539,458,338 | `model.safetensors` 1,500,800,904 B |
| `laion/clap-htsat-unfused` | `8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a` | 617,901,754 | `pytorch_model.bin` 614,525,833 B |
| `Qwen/Qwen2.5-1.5B-Instruct` | `989aa7980e4cf806f80c7fef2b1adb7bc71aa306` | 3,098,973,447 | `model.safetensors` 3,087,467,144 B |
| `HuggingFaceTB/SmolVLM2-2.2B-Instruct` | `482adb537c021c86670beed01cd58990d01e72e4` | 8,992,155,310 | two safetensors totaling 8,987,374,056 B |

Before each wave:

1. retrieve official API metadata for the exact commit;
2. archive model card, license where present, file list and byte sizes;
3. require `private=false`, `gated=false`, unchanged license metadata;
4. generate an allowlist; no wildcard download outside that list;
5. download to a temporary restricted directory;
6. verify expected file count/size, compute SHA-256 for every file, run
   `safetensors.safe_open` where applicable, then atomically promote;
7. write a canonical manifest containing repository, commit, URL, ETag if
   supplied, size and SHA-256.

### 5.3 Command templates

Preferred pinned CLI template:

```bash
umask 077
export HF_HOME=/path/to/av-trace
export HF_HUB_DISABLE_TELEMETRY=1
hf download REPO_ID \
  --revision FULL_40_HEX_COMMIT \
  --local-dir TEMP_RESTRICTED_SNAPSHOT_DIR \
  --include FILE_1 --include FILE_2
```

Pinned direct-transfer fallback:

```bash
umask 077
curl --fail --location --retry 3 \
  --output TEMP_RESTRICTED_SNAPSHOT_DIR/FILE \
  "https://huggingface.co/REPO_ID/resolve/FULL_40_HEX_COMMIT/FILE?download=true"
sha256sum TEMP_RESTRICTED_SNAPSHOT_DIR/FILE
```

The execution worker must supply proxy variables externally and must not write
them into manifests or logs. A mirror URL may replace the hostname only after
the official commit and allowlist are frozen.

Offline load:

```bash
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
python SCALE1B_SMOKE_SCRIPT \
  --model-dir EXACT_LOCAL_SNAPSHOT \
  --local-files-only
```

## 6. Go/No-Go gates

### `LEARNED_RETRIEVAL_READY`

All are required:

- SigLIP2 and CLAP snapshots pass file/hash/offline-load checks;
- BM25, visual and audio segment indices cover the same frozen timeline;
- learned fusion is trained only on a disjoint training split, or its absence
  is explicit and this gate remains false;
- one-segment and all-six-family runs complete;
- no answer/evidence labels enter embedding text or fusion features;
- retrieval outputs are deterministic and contain only public fields.

### `LEARNED_GENERATION_READY`

All are required:

- Qwen 1.5B loads offline and completes L1–L3 within declared resource limits;
- structured output validation, one-repair maximum and fail-closed behavior
  pass;
- claim/citation metrics operate on model-authored assertions;
- partial/blocked evidence tests show no evaluator-private leakage;
- SmolVLM2 is optional and separately labeled if unavailable.

### `LEARNED_AGENT_READY`

All are required:

- both learned controllers run through the same fixed backend and budget;
- prompts/configs are independently hashed and controllers have distinct state
  transitions, not merely different labels;
- all tool actions pass the opaque-ID wire protocol;
- CLEAN/BLOCKED/RESTORED and no-trigger controls pass;
- timeout, malformed output, OOM and over-budget behavior fail closed;
- trajectories are not silently replaced by deterministic policy outputs.

### `SCALE1B_READY`

Requires the three gates above plus:

- Scale-1A full-timeline index is frozen and Pilot-0 trust invariants hold;
- at least one usable execution device is measured for each selected model;
- all-six learned runs and a deterministic replay are complete;
- source/model/prompt/index/output manifests are internally consistent;
- results retain `MACHINE_ADJUDICATED_PROVISIONAL_MVP`,
  `LOW_N_DESCRIPTIVE_PILOT` and `FINAL_BENCHMARK_NOT_YET_VALIDATED`;
- a separate red-team finds no leakage, stale hash or metric substitution.

At inventory time none of these four execution gates is yet satisfied. The
only current decision is that the exact, staged download plan is sufficiently
bounded to begin with Wave R after a fresh network preflight.

