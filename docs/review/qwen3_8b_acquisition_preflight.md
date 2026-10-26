# Qwen3-8B acquisition repair and adapter-v2 CPU smoke review

**Task:** 181 repair of Task 179  
**Date:** 2026-10-08 (Asia/Shanghai)  
**Decision:** `QWEN3_8B_ACQUISITION_READY`

## Executive decision

The exact Qwen3-8B snapshot is acquired, locally hash-verified, CPU-loadable,
and atomically promoted to:

`data/restricted/strong_baselines/models/Qwen--Qwen3-8B--b968826d9c46`

The bounded smoke loaded the model on CPU in BF16 and exercised the Task-175
v2 factorized interface on two inline public fictional cases: two controller
factors and five finalizer factors. The smoke completed and retained all seven
raw outputs. Some model-authored factors and both cross-factor assemblies were
rejected exactly as the strict adapter requires; they were not repaired.

This is acquisition and interface load-smoke readiness only.
`competence_claimed=false`. No sealed competence suite, scientific source,
GPU, or external/paid model API was used.

## Exact identity and promoted payload

- Repository: `Qwen/Qwen3-8B`
- Revision: `b968826d9c46dd6066d109eabc6255188de91218`
- Architecture/model type: `Qwen3ForCausalLM` / `qwen3`
- Selected files: 10
- Weight bytes: `16,381,516,776`
- Total selected payload: `16,392,983,007` bytes
- Weight format: five sharded safetensors files
- Local integrity records: `SHA256SUMS` and `LOCAL_MANIFEST.json`
- Directory/file modes: `0700` / `0600`
- Runtime policy: `local_files_only=True`, `trust_remote_code=False`

The complete Task-179 stage was reused without redownload. Task 181 rechecked
every selected file size and pinned upstream identity, each local SHA-256, the
complete safetensors tensor/index relationship, the local manifest, and the
SHA-256 list. The same-parent `os.replace` promotion occurred only after the
snapshot and smoke gates passed. The final snapshot was then validated again.

## Root cause and narrow repair

Task 179 successfully loaded the tokenizer and model, then crashed before
recording its first factor because `_factor_outcome` directly constructed
`RawFactorAttempt` without the required `kind` argument.

The repair:

- imports `AttemptKind`;
- constructs the attempt with `attempt_index=1`,
  `kind=AttemptKind.INITIAL`, and the exact adapter-input bytes;
- adds a regression test checking the initial-attempt provenance and exact
  byte retention; and
- tightens smoke validation to require `raw_outputs_preserved=true`, initial
  attempt-kind provenance, adapter-input retention, and matching raw/adapter
  SHA-256 values.

No prompt, case, model, parser, schema, retry allowance, or scoring policy was
changed. No JSON completion, field filling, enum substitution, answer
substitution, citation substitution, semantic repair, voting, or retry was
added.

## Final bounded CPU BF16 smoke

Evidence:

`data/restricted/strong_baselines/acquisition_records/qwen3-8b-b968826d9c46/cpu_load_smoke.json`

Runtime:

- status: `LOAD_SMOKE_COMPLETE`
- device/dtype: CPU / `torch.bfloat16`
- model/tokenizer: `Qwen3ForCausalLM` / `Qwen2Tokenizer`
- Transformers/PyTorch: `5.2.0` / `2.10.0`
- Python: `3.13.11`
- threads: 8
- address-space cap: 48 GiB
- network attempts: 0
- elapsed time: 267.907 seconds
- peak RSS: 16,838,872 KiB
- factors generated: 7
- schema-only retries used: 0
- semantic repair: false
- raw outputs preserved: true

### Controller case

`qwen3-acq-controller-001`

- `action_choice`: `INVALID_OUTPUT`,
  `NATIVE_ARGUMENTS_NOT_EMPTY_OBJECT`
- `evidence_state`: `VALID`
- projection: `REJECTED`,
  `FULL_COVERAGE_WITH_MISSING_REQUIREMENT`

The raw native tool call selected `select_action_00` but also authored
arguments, which the no-argument action contract forbids. The evidence-state
factor was independently retained as valid. Its cross-field inconsistency was
rejected rather than rewritten.

### Finalizer case

`qwen3-acq-finalizer-001`

- `disposition`: `INVALID_OUTPUT`, `FACTOR_VALUE_ENUM`
- `answer_text`: `VALID`
- `claim_drafts`: `VALID`
- `citation_selections`: `VALID`
- `diagnosis`: `INVALID_OUTPUT`, `MODEL_OUTPUT_MALFORMED_JSON`
- projection: `NOT_RUN`

The disposition authored `p_sufficient=0.95`, outside the strict factor enum.
The diagnosis hit the pre-registered 256-token generation bound while copying
schema content and remained malformed. The three valid model-authored factors
were preserved unchanged; no invalid factor was completed or semantically
repaired.

These outputs are interface-smoke diagnostics, not a competence result.

## License and security boundary

The exact repository API, model card, and repository LICENSE identify
Apache-2.0. Exact metadata and license evidence remain archived under the
acquisition-record directory. Restricted internal preflight use is accepted;
redistribution remains unauthorized.

The selected snapshot is safetensors-only and excludes repository Python,
pickle weights, and native libraries. No credentials were persisted. No
Qwen-Omni artifact was downloaded. No unrelated Ray/H20 work was touched.

## Validation

```text
ruff check tools/qwen3_8b_acquisition.py \
  tooling/tests/test_qwen3_8b_acquisition.py \
  src/av_trace_strong_baselines_v2 \
  tests/test_granite_native_adapter_v2.py
```

Result: `All checks passed!`

```text
pytest -q tooling/tests/test_qwen3_8b_acquisition.py \
  tests/test_granite_native_adapter_v2.py
```

Result: `20 passed`.

```text
python tools/qwen3_8b_acquisition.py \
  --repo-root . --validate-existing
```

Result: `QWEN3_8B_SNAPSHOT_VALID`.

## Status separation

- Exact snapshot acquired and promoted: **yes**
- Exact snapshot locally hash-verified: **yes**
- CPU tokenizer/model BF16 load: **pass**
- Seven-factor public fictional smoke: **complete**
- Raw factor outputs and provenance retained: **yes**
- Semantic repair: **none**
- Full competence suite: **not run**
- Model competence: **not claimed**
- Scientific evaluation: **not authorized**
- Redistribution: **not authorized**

Final token: `QWEN3_8B_ACQUISITION_READY`
