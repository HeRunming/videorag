# Granite 3.3 8B acquisition repair and CPU load-smoke review

**Task:** 169 repair  
**Date:** 2026-10-02 (Asia/Shanghai)  
**Decision:** `GRANITE33_8B_ACQUISITION_READY`

## Executive decision

The exact Granite snapshot is acquired, locally hash-verified, CPU-loadable,
and atomically promoted to:

`data/restricted/strong_baselines/models/ibm-granite--granite-3.3-8b-instruct--51dd4bc2ade4`

The final clean bounded CPU canary passed the two pre-registered Task-158
public fictional cases:

- `sbc-controller-001`: strict controller object, correct action index, and
  exact six-field evidence state;
- `sbc-finalizer-001`: strict final-answer envelope, observed-evidence-locked
  citation, correct answer mode, and grounded `octagonal` answer.

This decision establishes acquisition and tiny load-smoke readiness only.
`competence_claimed=false`; the full Task-158 competence suite remains unrun.
No GPU, API, Qwen Omni, or scientific-family content was used.

## Exact identity and promoted payload

- Repository: `ibm-granite/granite-3.3-8b-instruct`
- Revision: `51dd4bc2ade4059a6bd87649d68aa11e4fb2529b`
- Architecture/model type: `GraniteForCausalLM` / `granite`
- Selected files: 13
- Weight bytes: `16,341,771,384`
- Total selected payload: `16,346,508,463` bytes (15.2239 GiB)
- Weight format: four sharded safetensors files
- Local integrity records: `SHA256SUMS` and `LOCAL_MANIFEST.json`
- Directory/file modes: `0700` / `0600`
- Symlinks, pickle weights, repository Python, and native libraries: none
- Runtime policy: `local_files_only=True`, `trust_remote_code=False`

The stage already contained the fully downloaded exact payload when this
repair began. No model bytes were downloaded or replaced during the repair.
`validate_snapshot` rechecked every size and upstream identity, the complete
safetensors tensor/index relationship, the local manifest, and SHA-256 list
before and after the same-parent atomic rename.

## Diagnosis and narrow repair

The original canary used only 96 new tokens per case. That cap could not fit a
minimal valid finalizer envelope: a compact conforming example is about 242
tokens with the exact local Granite tokenizer. The observed
`Unterminated string starting at` error was therefore consistent with
generation truncation, not a model-load failure.

The repair stayed within the already frozen Task-158 contract:

- raised the canary generation cap to the existing Task-158 limit of 512
  tokens;
- retained greedy single-output generation;
- made the controller/finalizer prompts compact and explicit about exact
  JSON field types;
- reused the canonical Task-158 strict JSON, evidence-state, final-answer,
  citation-lock, and model-authorship validators;
- permitted at most one schema-only retry, as already contracted;
- preserved every raw model-authored attempt in the smoke report;
- forbade semantic retry and verified that a schema retry cannot alter
  semantic atoms; and
- added explicit semantic checks against the frozen case scoring targets.

No parser extraction, JSON completion, field filling, enum substitution,
answer insertion, citation substitution, or other semantic repair was added.
The final passing run required zero retries for both cases.

## Final CPU canary

Evidence:

`data/restricted/strong_baselines/acquisition_records/granite33-8b-51dd4bc2ade4/cpu_load_smoke.json`

Runtime:

- status: `LOAD_SMOKE_COMPLETE`
- device/dtype: CPU / `torch.bfloat16`
- model/tokenizer: `GraniteForCausalLM` / `GPT2Tokenizer`
- Transformers/PyTorch: `5.2.0` / `2.10.0`
- threads: 8
- address-space cap: 48 GiB
- network attempts: 0
- elapsed time: 233.453 seconds
- peak RSS: 18,044,952 KiB
- schema-only retries used: 0 controller, 0 finalizer

Controller result:

- prompt/completion tokens: 548 / 91
- action index: 0 (`search_visual`)
- exact six-field state: pass
- all six state components: pass

Finalizer result:

- prompt/completion tokens: 451 / 361
- strict canonical envelope: pass
- citation ID/interval/modalities against observed evidence: pass
- answer mode: `answer`, pass
- required grounded term `octagonal`: present in the model-authored natural
  language answer
- unsupported claims: 0

The raw outputs and parsed objects are retained verbatim in the smoke evidence
and copied into the acquisition manifest.

## License and security boundary

The exact API metadata, API license tag, and exact model-card front matter
declare Apache-2.0. The exact model revision does not contain a LICENSE or
NOTICE file; canonical Apache-2.0 text remains separately archived with
explicit provenance. This is accepted only for restricted internal technical
use. Redistribution remains unauthorized.

No credentials were persisted. Local CPU inference occurred only for the
bounded canary; no external or paid model API was called. Official Hugging
Face metadata access remains recorded as acquisition evidence. No GPU was
reserved or used, unrelated Ray/H20 processes were not touched, no scientific
family/key was opened, and Qwen Omni was not downloaded.

## Validation

```text
ruff check tools/granite33_8b_acquisition.py \
  tests/test_granite33_8b_acquisition.py
```

Result: `All checks passed!`

```text
pytest -q tests/test_granite33_8b_acquisition.py \
  tests/test_strong_baseline_adapters.py
```

Result: `45 passed`.

```text
python tools/granite33_8b_acquisition.py \
  --repo-root . --validate-existing
```

Result: `GRANITE33_8B_SNAPSHOT_VALID`.

## Status separation

- Exact snapshot acquired and promoted: **yes**
- Exact snapshot locally hash-verified: **yes**
- CPU tokenizer/model load: **pass**
- Tiny public fictional controller smoke: **pass**
- Tiny public fictional finalizer smoke: **pass**
- Structural/grounding checks: **pass**
- Full competence suite: **not run**
- Model competence: **not claimed**
- Scientific evaluation: **not authorized**
- Redistribution: **not authorized**

Final token: `GRANITE33_8B_ACQUISITION_READY`
