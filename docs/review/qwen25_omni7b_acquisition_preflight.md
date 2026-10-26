# Task197 — Qwen2.5-Omni-7B acquisition technical validation repair

**Date:** 2026-10-10 Asia/Shanghai  
**Decision:** `QWEN25_OMNI7B_ACQUISITION_READY`  
**Scope:** acquisition and technical runtime readiness only; **no competence claim**

## 1. Repair outcome

Task197 repairs the stale Task196 preflight after the exact 15-file snapshot was
fully downloaded and promoted by intervening work. Task197 did **not** download
or modify model bytes. It validated the existing immutable snapshot, refreshed
metadata already archived on disk, reviewed the installed Transformers path,
and ran a CPU-only native A/V canary under the requested hard limits.

The exact binding remains:

```text
Qwen/Qwen2.5-Omni-7B
ae9e1690543ffd5c0221dc27f79834d0294cba00
processor revision: same exact commit
tokenizer revision: same exact commit
role: DIRECT_AV_MODEL
```

Technical result:

- exact metadata/card/license/tree: validated;
- exact selected snapshot: validated;
- all five LFS shard hashes: validated;
- safetensors index shard set and tensor set: validated;
- native processor: loaded and executed locally;
- native installed thinker: loaded locally in BF16 on CPU;
- one native video-plus-audio forward pass: succeeded;
- one bounded strict final generation: succeeded and passed the Task158 direct
  final-envelope validator;
- competence: **not evaluated and not claimed**.

## 2. Controlling Task158 direct-A/V contract

The canary follows the Task158 contract rather than treating ordinary free-form
chat as sufficient:

- exact immutable model/processor/tokenizer binding;
- one non-agent direct A/V finalization;
- source-ordinal then chronological media ordering;
- question-independent, source-uniform packing;
- explicit interval and modalities;
- 32,768 processor-token and 512 generated-token caps;
- exactly one strict final object;
- citations locked to the exact exposed observation, interval, and modalities;
- model authorship for answer-bearing fields;
- no semantic repair, answer substitution, voting, best-of-N, or hidden
  truncation of a completed raw response.

The exposure used by both the adapter check and model canary is:

```json
{
  "exposure_id": "exposure.task196.synthetic.0",
  "source_ordinal": 0,
  "interval": {"start_s": 0.0, "end_s": 2.0},
  "modalities": ["vision", "ambient"],
  "packing_policy": "question_independent_source_uniform_chronological"
}
```

## 3. Exact metadata and license validation

The current exact-revision responses and bytes are archived under:

```text
data/restricted/strong_baselines/acquisition_records/
  qwen25-omni7b-ae9e1690543f/
```

Their HTTP response dates are October 10, 2026, 06:34:04–06:34:06 UTC. Offline
revalidation established:

- repo ID and revision exactly match the frozen binding;
- repository is public and ungated in the archived response;
- tree has exactly the frozen 20 files;
- tree byte counts, Git object IDs, and LFS IDs match the frozen plan;
- no repository `.py`, native-library, ONNX, checkpoint-bin, or other selected
  remote-code file is present;
- `README.md` is 36,838 bytes, Git blob
  `9eb4a8e90deb0e208a9db6fdf1ea2e4c6dbf518f`, SHA-256
  `56f828c01cf5a3073a3968883c4dcbfef715af67b9295b66eb4d4941eef1680e`;
- `LICENSE` is 11,343 bytes, Git blob
  `9b1dd49441cd594560125cc7d79e886d0816cd8f`, SHA-256
  `8d5eb5f806d01e8f5ea2c5a52f7d68ebc54b196b1cfbe1cd5dfa4b94e482a9c6`;
- metadata declares `license_name: apache-2.0`, and the exact LICENSE bytes are
  Apache License 2.0.

This supports restricted internal technical use. It does not itself authorize
redistribution or public release; the manifest keeps those authorizations
false.

## 4. Snapshot, index, and tensors

Snapshot:

```text
data/restricted/strong_baselines/models/
  Qwen--Qwen2.5-Omni-7B--ae9e1690543f
```

Validation required directory mode 0700, file mode 0600, the exact 15 selected
files plus local manifests, exact byte counts, exact Git/LFS identities, and an
exact `SHA256SUMS` file. Total selected payload remains 22,374,798,886 bytes;
the five safetensors shards total 22,362,861,192 bytes.

All five shard SHA-256 values match the frozen LFS identities:

| Shard | SHA-256 |
|---|---|
| `model-00001-of-00005.safetensors` | `5edb02fd7c98803239468375cc9dc1bff492865c2aa086b78f348597021d6cbc` |
| `model-00002-of-00005.safetensors` | `7c99b55c6e5bc63fd4b19d4dc23cdc3ddac4b0101bb3c0958cc2b5d05c2bbafe` |
| `model-00003-of-00005.safetensors` | `ad00c3ac296300db905934ed213c4077ff49b85d30c0099270c814e2c77ec812` |
| `model-00004-of-00005.safetensors` | `152bc7d81441eaba22547d8d96c03d32dd592ce0e0e1d0e449347a4b23a532d3` |
| `model-00005-of-00005.safetensors` | `b8b18276481ba8cdf4fe2c98ac4c7a2da6e0d1c8a51850d162a391760cb2b81e` |

`model.safetensors.index.json` references exactly those five shards.
`safetensors.safe_open` enumerated every referenced shard, and the union of
shard tensor names exactly equals the index `weight_map` key set (2,448 tensors
in the full checkpoint). Task197 performed no redownload.

## 5. Reviewed installed Transformers path

Observed runtime:

- Python 3.13.11;
- torch 2.10.0;
- transformers 5.2.0;
- safetensors 0.7.0;
- accelerate 1.9.0;
- PyAV 16.1.0;
- NumPy 1.26.4.

Installed-library classes are available for the processor, thinker, and full
model. For this text-output direct baseline, Task197 selected
`Qwen2_5OmniThinkerForConditionalGeneration`, matching the installed
Transformers example and avoiding the unnecessary talker/token-to-wave path.
The full checkpoint is still the frozen snapshot; the loader consumes the
`thinker.*` tensors and reports talker/token-to-wave tensors as expected
unexpected keys for this narrower installed class. There were no missing
thinker parameters in the load report.

The thinker path includes the audio tower, vision encoder, text model, and LM
head and accepts `input_features`, `pixel_values_videos`, video grids, feature
masks, and `use_audio_in_video=True`. The canary therefore exercised native
video and in-video audio perception, not packed text descriptions.

`spk_dict.pt` is not needed by the thinker. The reviewed full-model path uses
`torch.load(..., weights_only=True)`, but Task197 did not execute it.

`trust_remote_code=False` was mandatory throughout. Repository code was not
executed. Local-only and offline environment flags were set. The processor
loader attempted to instantiate one socket object; the in-process network guard
blocked it, no connection or bytes were sent, and local loading continued.
All later model, forward, and generation phases recorded zero network attempts.

## 6. Fictional local A/V fixture and processor packing

Task197 reused the existing source-free fixture rather than generating or
opening scientific media:

```text
data/restricted/strong_baselines/acquisition_records/
  qwen25-omni7b-ae9e1690543f/synthetic/task196_fictional_av.mp4
```

It is 16,673 bytes with SHA-256
`cb83ca16625a2cc1440188c8063e4b84dea88f0f21ba2edcd444d59bf1aa5d49`:
2.0 seconds, 96×96, 4 fps, eight synthetic frames, one mono AAC stream at
16 kHz, a blue square, and 440 Hz then 660 Hz synthetic tones.

PyAV decoded the clip to:

- video: `[8, 96, 96, 3]`, `uint8`;
- audio: `[32000]`, `float32`, peak about 0.15175.

The native processor produced 1,031 input tokens and both modality tensors:

- `pixel_values_videos`: `[2304, 1176]`;
- `video_grid_thw`: `[1, 3]`;
- `video_second_per_grid`: `[1]`;
- `input_features`: `[1, 128, 30000]`;
- `feature_attention_mask`: `[1, 30000]`.

This is below the 32,768 processor-token cap.

## 7. Bounded CPU canary

Command:

```text
python tools/qwen25_omni7b_acquisition.py --cpu-canary
```

Enforced policy:

- CPU only, `CUDA_VISIBLE_DEVICES` empty;
- CUDA discovery intentionally not performed;
- BF16 thinker weights;
- eight CPU threads;
- `local_files_only=True`;
- `trust_remote_code=False`;
- offline Hugging Face/Transformers environment;
- process-tree RSS sampled from `/proc`;
- hard RSS cap 96 GiB (103,079,215,104 bytes);
- hard timeout 1,800 seconds;
- 512-token generation cap;
- no scientific media, GPU, or model API.

Final successful run, October 10, 2026 07:12:54–07:16:38 UTC:

| Measurement | Result |
|---|---:|
| Parent wall time | 224.96 s |
| Peak process-tree RSS | 18,639,175,680 bytes (17.36 GiB) |
| Processor load | 1.28 s |
| Processor execution | 0.13 s |
| Thinker load | 0.91 s |
| One native A/V forward pass | 42.57 s |
| Strict generation | 174.50 s |
| Generated tokens | 382 |
| Forward logits | `[1, 1031, 152064]`, BF16 |

The load and forward pass succeeded far below both hard limits.

### Strict final-output boundary

The first generation attempt is retained as negative evidence. It generated a
schema-valid JSON prefix and then unrelated trailing text up to the 512-token
cap. The full raw output was correctly rejected with
`MODEL_OUTPUT_TRAILING_CONTENT`; it was not truncated, repaired, or accepted.

Archived first attempt:

```text
task197_cpu_canary_attempt1.json
task197_cpu_canary_raw_output_attempt1.txt
```

The rerun used a deterministic generation-time stopping criterion that stops
only after the decoded generated sequence itself is exactly one complete JSON
object with no non-whitespace suffix. This is an output boundary, not a repair:
no already-generated bytes are removed or rewritten. The final 382-token raw
output is preserved byte-for-byte and passed `DirectAVAdapter.parse_and_validate`
with model-authored final fields and the exact evidence lock.

Final evidence:

```text
task197_cpu_canary.json
task197_cpu_canary_raw_output.txt
task197_cpu_canary_stdout.txt
task197_cpu_canary_stderr.txt
```

Final raw-output SHA-256:

```text
5b2362af745f34dc0dc1b01c3244b2fa87412d69f6b5eab21abc164d64ce1d2d
```

No schema repair or semantic repair was attempted.

## 8. Interpretation and boundary

`READY` means only that the exact acquired snapshot is technically usable in
this reviewed local CPU path and can process the fictional native A/V fixture,
execute a forward pass, and emit one schema-valid strict final object within
the resource limits.

It does **not** establish that the generated answer was semantically correct,
that the model recognized the blue square or tone frequencies, that it passes
the frozen fictional competence suite, or that it is suitable for scientific
evaluation. The canary output is deliberately not scored for competence.

Boundary:

- scientific media read: no;
- scientific source/evaluator key accessed: no;
- GPU used or reserved: no;
- external/paid model API called: no;
- Ray/H20 process touched: no;
- competence passed: no claim;
- scientific evaluation authorized: no.

## 9. Validation and deliverables

Validation:

- `ruff check tools/qwen25_omni7b_acquisition.py tests/test_qwen25_omni7b_acquisition.py`: PASS;
- Python compile: PASS;
- focused acquisition tests: PASS;
- snapshot/index/tensor validation: PASS;
- bounded CPU native A/V canary: PASS.

Updated deliverables:

- `tools/qwen25_omni7b_acquisition.py`;
- `tests/test_qwen25_omni7b_acquisition.py`;
- `data/restricted/strong_baselines/manifests/qwen25_omni7b_acquisition.json`;
- `docs/review/qwen25_omni7b_acquisition_preflight.md`;
- `orchestration/results/197_qwen25_omni7b_acquisition_repair.txt`.

## Final token

`QWEN25_OMNI7B_ACQUISITION_READY`
