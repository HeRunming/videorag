# GPT-OSS-20B acquisition/runtime preflight

**Date:** 2026-09-22  
**Task:** 126  
**Decision:** `GPT_OSS_20B_ACQUISITION_NO_GO`  
**Machine-readable record:** `data/restricted/scale1b/manifests/gpt_oss_20b_preflight.json`

## Executive decision

Do **not** acquire `openai/gpt-oss-20b` yet. The planned identity is
revision `6cee5e81ee83917806bbde320786a8fb61efebee`, but Task 126 did not
complete a fresh archive of the exact official tree, file sizes, Git/LFS hash
identities, exact config/tokenizer, or license text before the user ordered a
hard stop on network/exploration. Runtime compatibility is also not proven:
the installed Transformers recognizes GPT-OSS and MXFP4, but importing the
model class fails in the current Python environment, no accelerator is usable,
and the installed MXFP4 path would fall back to BF16 on CPU.

No weight was downloaded, no inference was run, no API was called, and no
evaluation family or key was touched.

## Evidence boundary

The pre-existing strong-agent plan records an official-source review of the
OpenAI-owned Hugging Face model card and exact revision tree. It identifies:

- repository `openai/gpt-oss-20b`;
- revision `6cee5e81ee83917806bbde320786a8fb61efebee`;
- Apache-2.0 metadata;
- Harmony formatting, function calling, structured output, and reasoning;
- 21B total / 3.6B active MoE;
- three MXFP4 safetensors shards totaling approximately 13.8 GB;
- approximately 41.3 GB for the whole repository.

Task 126 treats those as **prior dated observations**, not substitutes for the
required exact acquisition manifest. A direct official-HF fetch failed because
network name resolution was unavailable. A proxy attempt was interrupted and
left no archived files. Network work then stopped by explicit instruction.

Consequently, public/ungated state, exact license text, exact shard names and
sizes, Git blob OIDs, LFS SHA-256 values, index mapping, and absence of code or
pickle files remain explicit blocking gaps.

## Runtime and architecture findings

The current environment contains Python 3.13.11, PyTorch 2.10.0,
Transformers 5.2.0, Accelerate 1.9.0, safetensors 0.7.0, Triton 3.6.0,
OpenAI Harmony 0.0.8, and vLLM 0.16.0.post1. Transformers locally registers:

- `gpt_oss -> GptOssConfig`;
- `gpt_oss -> GptOssForCausalLM`;
- `mxfp4 -> Mxfp4Config` and `Mxfp4HfQuantizer`.

Local Transformers defaults describe a 36-layer decoder-only MoE with 128
local experts, four experts per token, hidden size 2880, 64 attention heads,
eight KV heads, a 131,072-token maximum, and alternating sliding/full
attention. These defaults are architecture evidence only; the pinned
revision's `config.json` was not archived, so exact-revision values remain
unverified.

The support is not operationally proven. Importing
`GptOssForCausalLM` currently traverses SciPy and fails because the installed
SciPy references `numpy.long`, which is unavailable with the installed NumPy.
No model load was attempted.

## MXFP4 and fallback constraints

Transformers' installed MXFP4 quantizer requires PyTorch and, for native
quantized execution, a supported CUDA GPU (compute capability at least 7.5)
or supported XPU plus Triton and the `kernels` package. This host exposes no
usable CUDA device and does not have `kernels` installed. For a pre-quantized
MXFP4 checkpoint on a CPU-only host, this Transformers version changes to
BF16 dequantization.

The host has ample memory—about 2.43 TB total and 1.66 TB available during the
probe—and ample workspace disk. A 21B-parameter BF16 representation is roughly
42 GB before model/runtime overhead, so RAM capacity is feasible. CPU
throughput, load behavior, peak RSS, and Harmony tool-call correctness remain
unmeasured. Plan at least 64 GiB and preferably 96 GiB for a bounded BF16
preflight. Native MXFP4 is not ready on this host.

## Security and redistribution

The future primary path must use `local_files_only=true`,
`trust_remote_code=false`, safetensors-only weights, no pickle formats, no
symlinks, and no unexpected Python/shared-library/executable files. Dynamic
download of Hugging Face community kernels during evaluation is forbidden;
any accelerator-kernel path must be pinned, reviewed, staged, and operated
offline as a distinct runtime.

No redistribution is authorized. An internal restricted snapshot may be
considered only after exact license/notice/model-card review. Public artifacts
may contain identifiers, locally computed hashes and sizes, environment
metadata, and AV-TRACE-authored validation code—not upstream weights or
tokenizer files absent a separate redistribution review.

## Bounded acquisition plan

Acquisition may be reconsidered only after all of the following:

1. Archive the exact official model API/tree and small metadata files for the
   pinned revision, without credentials.
2. Freeze one MXFP4 safetensors representation and exact index/config/tokenizer
   allowlist. Reject optional original/full-precision and executable/pickle
   material.
3. Prove the selected payload is at most **25 GiB** using exact upstream sizes.
4. Repair and pin an isolated runtime in which GPT-OSS config/model imports and
   tokenizer/config loading pass offline with remote code disabled.
5. Select either a reviewed accelerator MXFP4 runtime with vendored kernels or
   a measured CPU BF16 fallback. Silent dtype/runtime fallback is forbidden.
6. Only after those gates, download shards sequentially under `umask 077`,
   verify upstream identities and local SHA-256, validate safetensors/index
   consistency, and atomically promote.

## Fallback

The already acquired exact Qwen2.5-7B snapshot can remain only as the
historical weak-controller/runtime harness comparator; it is not a strong
fallback because it already failed the competence sequence. If GPT-OSS remains
blocked, the registry's strong open alternative is
`Qwen/Qwen3-30B-A3B-Instruct-2507` at revision
`13b91ea9539e6cc1c464d15a6e053e40f3ca1845`, requiring a separate registry
amendment and preflight. It is not authorized for download by this decision.
