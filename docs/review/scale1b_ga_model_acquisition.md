# Scale-1B Wave G/A Qwen acquisition

**Decision:** `QWEN_GROUNDED_GENERATOR_SNAPSHOT_READY`

## Exact identity

- Repository: `Qwen/Qwen2.5-1.5B-Instruct`
- Revision: `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`
- Payload bytes: `3098971928`
- Selected weights: one unsharded `model.safetensors` representation
- Exact-revision tree contains no shard index; the complete shard set is the single selected file.
- Snapshot promoted: `true`

## Offline CPU smoke

- `local_files_only=True`: `True`
- Network attempts observed: `0`
- Model/tokenizer: `Qwen2ForCausalLM` / `Qwen2Tokenizer`
- dtype/device: `torch.bfloat16` / `cpu`
- Context length: `32768`
- Load latency: `2.813694477081299` seconds
- Peak RSS: `3995236` KiB
- Deterministic decoding: `do_sample=False`, `max_new_tokens=128`
- At most one schema-repair generation is allowed per case.

| Case | Attempts | Repair used | Input tokens | Output tokens | Latency (s) |
|---|---:|---:|---:|---:|---:|
| normal | 2 | True | 389 | 16 | 5.750699281692505 |
| insufficient | 2 | True | 371 | 41 | 7.811444774270058 |

The prompts and outputs use only synthetic objects and contain no project transcript, source-media content, or restricted benchmark annotations.

## Release boundary

- Restricted internal inference is authorized only when the technical gate is ready.
- Model redistribution is **not authorized** pending a separate release review.
- Snapshot readiness does not imply learned-generation or learned-agent benchmark readiness.

## Compatibility note

The installed Transformers import path reaches SciPy modules that still reference removed NumPy scalar aliases. The offline loader applies the same local `np.long`/`np.ulong` compatibility shim already used by the project's audited Whisper/AST loaders; no dependency or model file was modified.
