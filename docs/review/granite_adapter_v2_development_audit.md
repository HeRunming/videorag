# Granite-native adapter v2 development audit

**Task:** 175  
**Date:** 2026-10-02 (Asia/Shanghai)  
**Decision:** `GRANITE_ADAPTER_V2_DEV_READY`  
**Competence claim:** none  
**Scientific execution:** not authorized and not performed

## Executive finding

The prospective Granite-native adapter v2 is implemented and passes its
development-only software checks. It addresses the observed Task-172
interface failure mode by separating native action selection from evidence
state, and by splitting finalization into independently constrained,
model-authored factors followed by rejection-only projection and mechanical
serialization.

This audit does not reopen Task 172. The frozen
`GRANITE33_COMPETENCE_NO_GO` decision remains unchanged. No model inference
or competence evaluation was performed in Task 175.

## Inputs inspected

The development process used Tasks 158, 170, and 172 documentation and only
the already-consumed Task-172 public-fictional artifacts:

- `data/rehearsal_plan/strong_baseline_competence_suite_v1.json`;
- `data/restricted/strong_baselines/granite33_competence_v1/submission.json`;
- `data/restricted/strong_baselines/granite33_competence_v1/raw_attempts.jsonl`;
- `data/restricted/strong_baselines/granite33_competence_v1/component_audit.json`;
- Task-158 design/audit/result;
- Task-170 acquisition audit/result; and
- Task-172 audit/result.

No future unseen labels, newly generated suite, scientific family, scientific
answer key, or scientific media were read.

## Findings

### A. Factorized native controller — pass

The controller exposes each exact frozen menu entry as one no-argument native
function declaration. Native function choice and evidence-state heads are
parsed into separate outcomes. A valid action remains available as an
independent result when state syntax or consistency fails.

The evidence-state factor has exact fields and controlled enums. Its
projection can only accept the unchanged state or return a typed rejection.
Tests show that contradictory full coverage plus missing evidence is rejected
without altering either action or state.

### B. Strict constrained enums — pass

The implementation constrains:

- action function names to the current menu;
- all six evidence-state vocabularies;
- final disposition fields;
- case-local claim handles;
- observed citation IDs;
- diagnosis modality/cause keys and hop enums; and
- Boolean versus string field types.

Unknown enums and out-of-scope IDs fail closed.

### C. Factorized finalizer and mechanical serialization — pass

Disposition, natural-language answer, claim drafts, citation selections, and
diagnosis are independent model-authored factors. Serialization:

- preserves answer and claim text exactly;
- expands only already-selected observation IDs into their exact public
  interval/modality records;
- derives the redundant citation map from those same selections; and
- validates the resulting canonical envelope against the existing Task-158
  schema and evidence lock.

Missing claims, citations, or answer text cause rejection. There is no answer
substitution or semantic field fill.

### D. Raw-output and retry controls — pass

Every factor result retains all raw response bytes. Attempt sequencing allows
one initial response and at most one schema-only retry. The retry:

- must follow an allowlisted structural error;
- cannot be issued after a valid response;
- cannot be followed by a second retry; and
- must preserve scalar content when both attempts are parseable.

There is no semantic retry or cross-factor retry.

### E. Consumed Task-172 development regression — pass with limits

The offline regression verified exact consumed artifact identities and
confirmed:

- 54 preserved Task-172 attempt records;
- 24/24 legacy controller action indices can be represented as v2 menu
  functions;
- 23/24 legacy evidence-state objects satisfy factor-local syntax/enums;
- finalizer disposition factors are valid in 16/16 consumed outputs;
- answer-text factors are valid in 12/16;
- claim-draft factors are valid in 7/16;
- citation-selection factors are valid in 15/16; and
- 0/16 old finalizer outputs can be serialized by v2 without changing their
  authored content.

These counts are not model competence scores. The regression does not call
the Task-158 evaluator and does not claim that Granite produced native-v2
responses.

### F. Future unseen sealed-suite GENERATOR — pass, not instantiated

The new generator is capable of creating a fresh public/private suite pair
and pre-execution seal from a caller-supplied new seed. It rejects the
consumed Task-158/172 seed and separates public cases from private labels.

Task 175 did not instantiate the generator. No future seed, suite cases,
private labels, output directory, model run, or evaluation exists.

### G. Isolation and non-interference — pass

- Frozen v1 package files were not changed.
- Task-172 sealed artifacts were read only.
- No model weights were loaded.
- No GPU or external API was used.
- No network request was made.
- No future holdout or scientific family was opened.
- No unrelated work was reverted.

## Validation

```text
ruff check src/av_trace_strong_baselines_v2 \
  scripts/generate_granite_adapter_v2_suite.py \
  tests/test_granite_native_adapter_v2.py
```

Result: `All checks passed!`

```text
pytest -q tests/test_granite_native_adapter_v2.py
```

Result: `8 passed`.

Compatibility tests are reported in
`orchestration/results/175_granite_adapter_v2_development.txt`.

```text
pytest -q tests/test_granite_native_adapter_v2.py \
  tests/test_strong_baseline_adapters.py \
  tests/test_granite33_8b_acquisition.py \
  tests/test_granite33_competence.py \
  tests/test_granite33_competence_audit.py
```

Result: `62 passed`.

## Decision

The software, generator capability, and consumed-development regression are
ready for a separately governed future unseen-suite freeze and execution.
They do not establish competence and do not authorize a Task-172 rerun or
scientific execution.

`GRANITE_ADAPTER_V2_DEV_READY`
