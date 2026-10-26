# AV-TRACE controller interface v2

**Version:** 2.0.0  
**Frozen:** 2026-09-21  
**Status:** preregistered synthetic/development protocol; no model has been run  
**Authority:** this document, the two v2 schemas, and
`data/rehearsal_plan/controller_v2_holdout_contract.json`

## 1. Decision and scope

Controller v2 is a deliberately narrow interface change motivated by the
Task-114/115 finding that monolithic action-plus-state output mixed action
selection failures, state-estimation failures, and serialization failures.
It does not change the AV-TRACE thesis, backend, tools, public evidence,
budgets, final-answer semantics, or model authorship.

The v2 turn has two model-authored heads:

1. **Action head:** grammar-constrained selection of one public menu index.
2. **State head:** a separate grammar-constrained estimate of the existing
   six-field public evidence state.

If and only if the chosen public action is `finalize`, the ordinary
model-authored grounded finalizer is called. The controller runtime MUST NOT
turn an action index, state estimate, observation, required term, or evaluator
label into an answer. There is no deterministic answer fallback and no
semantic rewriting of model output.

This is synthetic/development-only. It is not a scientific evaluation, cannot
reopen an excluded family, and contains no evaluation-family content.

## 2. Public inputs and information boundary

Both heads may receive only:

- the fictional question and public claim-slot descriptions;
- public pointer previews and citable observations already acquired;
- recent public action/response events;
- public budget, available tools, no-progress count, and action menu;
- the policy name (`react` or `evidence_sufficiency`);
- for the state head only, the action index authored by the action head.

Neither head may receive expected actions, expected state fields, oracle
support maps, required answer terms, state-role labels, private claim/evidence
IDs, route certificates, evaluator annotations, or paired-run outcomes.

The public holdout packet and restricted evaluator key are separate artifacts:

- `data/rehearsal_plan/controller_v2_holdout/public_execution_packet.json`
  is the only case packet supplied to an implementation or execution worker.
- `data/rehearsal_plan/controller_v2_holdout/restricted_evaluator_key.json`
  contains expected outputs and scoring labels and is supplied only to the
  evaluator after immutable run outputs have been committed.

Repository path separation is not a cryptographic access control. The key is
therefore also marked evaluator-only, should be mode `0600`, and MUST be
withheld by task-scoped file allowlists or a separate evaluator process. The
contract binds both files by SHA-256 so either file changing breaks the seal.

## 3. Exact output languages

### 3.1 Action head

The complete model output is one JSON object:

```json
{"action_index": 2}
```

No other key or text is permitted. The static schema permits the global menu
index set `{0,1,2,3}`. Before decoding, the grammar compiler MUST replace that
enum with the case-local `allowed_action_indices`, which is always exactly
`[0, ..., len(action_menu)-1]`. The selected action object is copied from the
public menu by the runtime only after parsing; this is action dispatch, not
answer generation.

### 3.2 Public-state head

The complete model output is exactly these six fields:

```json
{
  "p_sufficient": 0.25,
  "covered_claim_handles": [],
  "missing_modalities": ["speech"],
  "missing_hops": ["speech_content"],
  "missingness_cause": "evidence_accessible_but_not_found",
  "recovery_intent": "search_speech"
}
```

Fixed enums are fully specified in
`docs/spec/controller_v2_state_schema.json`. Claim handles are dynamically
restricted to the case's public claim slots. Arrays must be duplicate-free and
in canonical order. The five sufficiency bins are exactly
`0.0, 0.25, 0.5, 0.75, 1.0`; implementations may not silently round arbitrary
numbers into a bin.

The state object is diagnostic public state. It is never interpreted as answer
text, never expanded into claims, and never used to populate citations.

## 4. Deterministic fail-closed parser

Each head is parsed independently in this order:

1. Accept UTF-8 bytes only and enforce the schema byte limit.
2. Permit only JSON whitespace before or after the single JSON value.
3. Parse with duplicate-key rejection and rejection of NaN, Infinity,
   comments, code fences, trailing commas, and trailing content.
4. Require a JSON object with exactly the schema's required keys.
5. Validate primitive types without coercion; booleans are not integers.
6. Validate fixed enums and case-local dynamic enums.
7. For state arrays, reject duplicates and non-canonical ordering.
8. Return the parsed values unchanged. No trimming, case-folding, sorting,
   rounding, alias mapping, field insertion, or repair is permitted.

Parser errors are stable codes:

```text
OUTPUT_TOO_LARGE
INVALID_UTF8
EMPTY_OUTPUT
MALFORMED_JSON
DUPLICATE_KEY
TRAILING_CONTENT
WRONG_TOP_LEVEL_TYPE
FIELD_SET_MISMATCH
TYPE_MISMATCH
ENUM_VIOLATION
DYNAMIC_ENUM_VIOLATION
DUPLICATE_ARRAY_ITEM
NONCANONICAL_ARRAY_ORDER
```

Grammar compilation/runtime failure is recorded separately as
`CONSTRAINT_RUNTIME_FAILURE`; it is not converted into a model choice.
There is no repair call in v2. A v1 arm retains its frozen at-most-one-repair
behavior and is reported with its actual call count.

Cross-field plausibility is deliberately **not parser validity**. For example,
full claim coverage paired with a missing modality is syntactically valid but
state-semantically wrong. This preserves the required error decomposition.

## 5. Invocation order and authorship

For every case:

1. Freeze and hash the exact public payload.
2. Invoke the action head once under the case-specific grammar.
3. Parse and record its raw bytes, parse result/error, token count, latency,
   request hash, grammar hash, and model identity.
4. If action parsing fails, record no dispatched action. The state head is
   still invoked with `selected_action_index: null` so state syntax and
   estimation remain measurable.
5. Invoke the state head once under its grammar, supplying the authored action
   index or `null`; the expected state is never supplied.
6. Dispatch only a valid selected menu action.
7. If that action is `finalize`, invoke the unchanged model-authored grounded
   finalizer. Invalid finalizer output fails closed; no controller field is
   mapped into an answer.

All calls use the exact pinned Qwen2.5-7B-Instruct snapshot from Task 114,
greedy decoding, the frozen context/token limits in the holdout contract,
offline/local-only loading, and network denial.

## 6. Four independent correctness axes

Metrics MUST NOT collapse the following:

### 6.1 Syntax validity

- `action_syntax_valid`: action bytes pass the action parser.
- `state_syntax_valid`: state bytes pass the state parser.
- `finalization_syntax_valid`: reached finalizer output passes the unchanged
  strict finalization validator.
- Runtime/process failures have their own denominator-preserving counts.

### 6.2 Action correctness

Among all cases, a valid selected index is correct only when its referenced
public action exactly matches the evaluator key's preregistered action
fingerprint. A malformed action output is incorrect, not missing from the
denominator. Menu position alone has no semantic meaning.

### 6.3 State-estimation correctness

State correctness is scored on all cases independently of action correctness.
Each of the six fields receives an exact binary score against the evaluator
key. `state_exact` requires all six. Also report `state_exact_given_action_ok`
to diagnose coupling, but never use that conditional metric as the sole gate.

### 6.4 Finalization correctness

Finalization is scored only for the eight preregistered terminal cases and is
reported both:

- **reached correctness:** correctness among terminal cases where a valid
  `finalize` action was actually selected; and
- **end-to-end terminal correctness:** all eight terminal cases in the
  denominator, with a wrong/non-finalize action counted as failure.

Answer cases require all public claims, required content, and exact public
observation citations. Abstention cases require an allowed non-answer verdict,
no answer text/assertions, the preregistered missingness diagnosis, and no
unsupported claim. Unsupported required claims must remain zero.

## 7. Sealed unseen holdout

The holdout has 28 fictional cases, exactly four in each primary stratum:

```text
routing
pointer_read
finalize
abstain
missingness
recovery
adversarial_menu_order
```

Cases may have secondary capabilities, but balance is determined only by
`primary_stratum`. Questions, entities, observations, IDs, and answer content
are distinct from Task 111. No source media, evaluation family, or benchmark
annotation is used.

The public packet exposes inputs only. The evaluator key contains action
fingerprints, exact six-field state labels, and terminal scoring labels. Its
SHA-256 commitment is public in the contract; its contents must remain unseen
until both arms' immutable outputs are sealed.

## 8. Preregistered v1/v2 paired protocol

### 8.1 Arms

- **v1:** current frozen monolithic action-plus-state interface, current
  validator, and at most one repair. No v1 code, prompt, suite, or historical
  result is edited.
- **v2:** this two-head interface, one constrained call per head, no repair.
- **finalizer:** identical unchanged finalizer, payload, model snapshot, and
  validation in both arms.

Both arms receive the same 28 public cases, action menus, case order, budgets,
model snapshot/revision, quantization/dtype, seed, decoding settings, and
offline process limits. Run-order is fixed as v1 then v2 by case ID. Results
are paired by case; no prompt, grammar, threshold, or label may change after
the first model call in either arm.

### 8.2 Absolute v2 gates

All are required:

| Gate | Frozen threshold |
|---|---:|
| Action syntax validity | 28/28 |
| State syntax validity | 28/28 |
| Action correctness | at least 24/28 |
| Action correctness in every primary stratum | at least 3/4 |
| Exact six-field state correctness | at least 21/28 |
| Each individual state field | at least 24/28 |
| End-to-end terminal correctness | at least 7/8 |
| Supported answers on four answer-terminal cases | at least 3/4 |
| Correct abstentions on four abstain-terminal cases | 4/4 |
| Unsupported required claims | 0 |
| Evaluation-family/private-label exposure | 0 |

Any process failure stays in the denominator. Constraint-runtime failure,
label leakage, key access by the implementation worker, post-run tuning, or a
holdout seal mismatch is an automatic protocol `NO_GO`.

### 8.3 Paired v2-over-v1 gates

In addition to the absolute gates:

- v2 action-correct count must be no lower than v1;
- v2 exact-state count must be at least four cases higher than v1;
- v2 end-to-end terminal-correct count must be no lower than v1;
- v2 unsupported-required-claim count must be no higher than v1 and must be
  zero absolutely.

Report the complete 2x2 paired transition table for action correctness,
state exactness, and terminal correctness. Report syntax, action, state, and
finalization separately even if the overall decision is `NO_GO`.

Passing this holdout permits only a subsequent excluded
synthetic/development controller-v2 run. It does not reopen or authorize any
scientific evaluation family.

## 9. Freeze and change control

Before any v2 model call:

- all contract, schema, public-packet, and evaluator-key hashes must match;
- the Task-111 protected artifact hashes must still match the audit;
- an execution worker must attest that the evaluator key was inaccessible;
- an evaluator must attest that no output was visible before labels were
  frozen;
- any change creates version 2.1+ and a new unseen holdout.

No tuning, pilot run, prompt selection, or threshold adjustment is permitted
on these 28 cases.
