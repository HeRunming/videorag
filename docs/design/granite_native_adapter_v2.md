# Granite-native adapter v2

**Task:** 175  
**Date:** 2026-10-02 (Asia/Shanghai)  
**Status:** development implementation only  
**Scientific execution:** not authorized

## 1. Purpose and boundary

This is a prospective, versioned replacement for the monolithic Granite
controller/finalizer output interface used in Task 172. It responds only to
already-consumed development evidence:

- all 24 controller responses were strict parseable JSON and carried an
  in-range action index;
- raw action correctness was 11/24 (45.8%);
- raw `p_sufficient` was correct in 17/24 (70.8%);
- all 12 answer-mode finalizers put the required answer terms in their
  natural-language answer; and
- canonical controller/finalizer envelopes were usually invalid.

Those observations motivate interface factorization; they do not establish
competence. Task 172 remains a frozen no-go and is not rerun here.

The implementation is isolated under
`src/av_trace_strong_baselines_v2/`. It does not modify the frozen Task-158
adapter, Task-172 submission, evaluator, seal, or model artifacts.

## 2. Design principles

1. **Operational action is independent from diagnostic state.** A malformed
   or inconsistent state cannot erase a valid native function selection.
2. **Every semantic field remains model-authored.** Projection validates and
   may reject; it never fills, rewrites, reconciles, or guesses a field.
3. **Enums are strict and public.** Every finite decision vocabulary is
   enumerated in a factor-local output contract.
4. **Canonical envelopes are serialization targets, not generation targets.**
   The adapter assembles already-authored factors mechanically.
5. **Raw attempts are immutable evidence.** Initial and retry bytes are stored
   exactly. A factor may have at most one schema-only retry.
6. **No answer substitution.** Claim text and natural-language answer are
   distinct model-authored factors. The serializer cannot copy one into the
   other or derive either from evidence payloads.
7. **Future testing is prospective.** A new unseen suite must be generated
   from a new seed and sealed before execution. Task 175 does not instantiate
   that suite.

## 3. Controller interface

### 3.1 Native function choice

For each frozen action-menu entry, `build_native_action_plan` exposes one
Granite-native no-argument function:

```json
{
  "type": "function",
  "function": {
    "name": "select_action_01",
    "description": "Select this exact frozen menu action: {...}",
    "parameters": {
      "type": "object",
      "properties": {},
      "additionalProperties": false
    }
  }
}
```

The invocation contract requires a tool choice and disables parallel calls.
The returned function name maps bijectively to the prevalidated menu entry.
The model does not regenerate tool arguments, so there is no deterministic
query or interval repair. The action itself remains the action the model
selected.

The normalized factor result is:

```json
{
  "function_name": "select_action_01",
  "arguments": {}
}
```

Only the names declared for the current menu are accepted.

### 3.2 Evidence-state heads

The six evidence-state heads are a separate strict constrained-JSON factor:

```json
{
  "p_sufficient": 0.0,
  "covered_claim_handles": [],
  "missing_modalities": ["vision"],
  "missing_hops": ["entity_identity"],
  "missingness_cause": "evidence_accessible_but_not_found",
  "recovery_intent": "search_vision"
}
```

Constraints include:

- `p_sufficient` in `{0, 0.25, 0.5, 0.75, 1}`;
- case-local claim handles only;
- canonical ordered subsets for modality and hop arrays;
- exact cause and recovery-intent enums; and
- no unknown or additional fields.

### 3.3 State-consistency projection

`project_evidence_state` consumes only model-authored state plus the public
claim/evidence context. It either:

- returns the exact validated state unchanged; or
- returns a typed rejection with no state object.

It rejects examples such as:

- full claim coverage while a modality or hop is still missing;
- covered claims when no observation exists;
- `p_sufficient=1` with incomplete coverage or missing evidence;
- `finalize_answer` without complete support;
- `finalize_abstain` with high sufficiency;
- a search intent without the matching missing modality; and
- restoration/status intent without an inaccessible-source cause.

The projection does **not** enforce agreement between the chosen action and
the diagnostic recovery intent. Those are intentionally separate model
predictions and may be analyzed independently. A valid action is preserved
even if state projection rejects.

### 3.4 Controller serialization

Only when both factors are valid and the state projection accepts does the
adapter mechanically serialize:

```json
{
  "adapter_schema_version": "av-trace.granite-native-adapter/2.0",
  "native_function_name": "select_action_01",
  "action_index": 1,
  "action": {"tool": "search_visual", "arguments": {"...": "..."}},
  "evidence_state": {"...": "..."}
}
```

No missing head, action, or tool argument is synthesized.

## 4. Finalizer interface

The canonical final answer is split into five model-authored factors.

### 4.1 Disposition

The model authors:

- `p_sufficient`;
- `verdict`;
- `answer_mode`; and
- `termination_reason`.

All four values use strict enums.

### 4.2 Natural-language answer

The model authors a single `text` string. This string is never copied into
claim text and claim text is never copied into this string.

### 4.3 Claim drafts

Each claim draft contains:

- `claim_id`;
- a case-local `registered_claim_id`;
- model-authored `text`; and
- numeric `confidence` in `[0,1]`.

Claim IDs and claim handles must be unique. An answer claim must exist on its
own; the serializer does not create one from the natural-language answer.

### 4.4 Citation selections

For each registered claim, the model selects only observation IDs from the
current observed-evidence lock:

```json
{
  "registered_claim_id": "public.slot.1",
  "observation_ids": ["public.obs.1"]
}
```

The model does not have to copy intervals and modalities. After validating
the selected IDs, the serializer mechanically copies the exact public
interval and modality metadata belonging to each selected observation. This
is metadata expansion, not semantic citation selection.

### 4.5 Diagnosis

The model separately authors:

- exact vision/speech/ambient probability fields;
- a strict ordered subset of registered hop enums;
- exact cause probability fields;
- Boolean `recovery_route_declared`; and
- description text.

### 4.6 Cross-factor projection and canonical serialization

The projection checks only consistency:

- claim-draft and citation-selection handles must match in order;
- answer mode requires every public claim, nonempty answer text, sufficient
  disposition, and at least one observed citation per claim;
- abstention requires empty claims, citations, and answer text;
- partial answer requires a strict subset with nonempty content;
- answer mode and termination reason must agree.

Failure rejects the envelope. It does not:

- insert required answer terms;
- copy the natural-language answer into a claim;
- create a missing claim;
- select an observation;
- change a diagnosis;
- change answer mode or verdict; or
- turn an answer into an abstention.

On acceptance, `serialize_finalizer_factors` constructs the existing
`final_answer` plus `claim_to_citations` envelope and passes it through the
Task-158 canonical schema, evidence-lock, and authorship checks.

## 5. Retry and provenance policy

Each factor has one initial attempt and at most one schema-only retry.

- A retry is allowed only after an allowlisted structural or serialization
  error.
- If the first output is already valid, an extra retry is invalid.
- If both outputs parse, their scalar content multiset must be identical.
- A retry after an enum, range, unknown-ID, or consistency error is a
  prohibited semantic retry.
- All exact response bytes, attempt indices, attempt kinds, and SHA-256 values
  are retained in `RawFactorAttempt`.

Retries are per factor. A failure in one factor does not permit regeneration
of another valid factor, and there is no cross-factor repair.

## 6. Consumed Task-172 development regression

`run_task172_structural_regression` reads only:

- the public fictional Task-158 suite already consumed by Task 172;
- the sealed Task-172 submission;
- the sealed raw attempts; and
- the Task-172 component audit.

It does not call the model or frozen evaluator. It mechanically partitions the
old monolithic JSON solely to exercise v2 validators. Results are structural
diagnostics, not a v2 model result:

- action factor parseability: 24/24;
- evidence-state factor syntax/enum validity: 23/24;
- finalizer disposition factor validity: 16/16;
- answer-text factor validity: 12/16, because four abstentions omitted the
  field in the old envelope;
- claim-draft factor validity: 7/16;
- citation-selection factor validity: 15/16; and
- no consumed finalizer row was mechanically serializable under v2 without
  changing model-authored content.

The old action indices are converted to equivalent native function names only
for this offline compatibility exercise. That conversion is not a claim that
Task 172 used native Granite tool calls.

## 7. Future unseen sealed-suite GENERATOR

`FutureSealedSuiteGenerator` and
`scripts/generate_granite_adapter_v2_suite.py` can create a future suite with:

- 24 controller cases;
- 16 finalizer cases;
- 11 runtime/fail-closed fixtures;
- a public suite without scoring targets;
- a separate private-label file;
- a generation manifest;
- a caller-supplied new seed;
- rejection of the consumed Task-158/172 seed;
- public-fictional abstract colors, shapes, codes, and sounds only; and
- a seal written before model execution.

Task 175 only tests the generator contract and the consumed-seed guard. It
does not choose a new seed, call `generate_bundle`, call `seal_to`, write a
future suite, expose future labels, run a model, or evaluate a future suite.

## 8. Files

- `src/av_trace_strong_baselines_v2/contracts.py`
- `src/av_trace_strong_baselines_v2/adapter.py`
- `src/av_trace_strong_baselines_v2/development.py`
- `src/av_trace_strong_baselines_v2/suite_generator.py`
- `scripts/generate_granite_adapter_v2_suite.py`
- `tests/test_granite_native_adapter_v2.py`
- `data/rehearsal_plan/granite_adapter_v2_dev_registry.json`

## 9. Non-claims

This implementation does not claim:

- Granite competence;
- improved action, state, answer, abstention, or restoration accuracy;
- successful native-v2 model output;
- a rerun or reinterpretation of the Task-172 frozen result;
- creation or evaluation of the future unseen suite; or
- authorization to read or execute scientific families.

