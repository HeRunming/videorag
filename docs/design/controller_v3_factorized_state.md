# AV-TRACE controller v3: factorized public-state development design

**Date:** 2026-09-22  
**Status:** development protocol; Task-111 cases are consumed  
**Scope:** fictional synthetic development only

## Decision boundary

Controller v3 is a development-only response to the safe aggregate v2 result:
the v2 action and state grammars were reliable, but semantic state estimation
was weak and no exact six-field state was produced. This work does **not** use
the restricted v2 evaluator key, v2 per-case labels, raw v2 outputs, NOAA,
r017, or any evaluation family. The sealed v2 holdout is not a tuning set.

The only case-level development source is the original Task-111 synthetic
suite. Every v3 case is marked `consumed: true`. The only v2 comparison allowed
is the aggregate table already published in
`docs/review/controller_v2_holdout_evaluation.md`; its denominators differ, so
the comparison is descriptive rather than a paired performance claim.

## Runtime architecture

One turn makes seven independent constrained calls:

1. native `action_index` head;
2. `p_sufficient`;
3. `covered_claim_handles`;
4. `missing_modalities`;
5. `missing_hops`;
6. `missingness_cause`;
7. `recovery_intent`.

Each state head sees the same public payload and only its own field name and
explicit case-local choice list. It does not see the selected action, another
head's output, an expected value, oracle support, required answer terms, or an
evaluator label. Choice order is deterministically shuffled by case and head,
so index position has no global semantic meaning.

The complete state-head language is:

```json
{"choice_index": 2}
```

The runtime validates the index and copies the selected enum value as that
head's authored classification. If a head fails, its value remains absent and
the six-field public state is `null`: there is no deterministic semantic
filling, normalization, repair, or cross-head inference.

The action language remains:

```json
{"action_index": 1}
```

Dispatching the selected public menu item is not answer generation.

## Finalization boundary

If and only if the action model selects `finalize`, v3 invokes the existing
`run_grounded_generator` finalizer. Its question, public claim slots,
observations, validation, repair allowance, verdict semantics, citations, and
answer authorship are unchanged. Factorized state is not passed to the
finalizer and is never mapped into answer text, claims, citations, or verdict.

## Offline and logging boundary

The model is the exact local Qwen2.5-7B-Instruct snapshot at revision
`a09a35458c702b33eeacc393d103063234e8bc28`, CPU bfloat16, greedy decoding,
local-files-only, with the worker launched in a denied network namespace.

Persisted call rows include hashes, raw model output, token counts, latency,
memory, parse status, and constraint-engine status. They exclude system
prompts, payloads, private labels, oracle support, and required terms.
Development labels remain only in the consumed suite contract/results under
`data/restricted/scale1b/controller_v3_dev/`.

## Metrics and competence gate

All 16 Task-111 cases are scored for action and all six state heads. Eight cases
are terminal: six original finalizer cases plus the two Task-111 controller
cases whose expected action is `finalize`. A malformed output remains in every
denominator.

Before any new unseen holdout, all conditions must pass:

| Gate | Threshold |
|---|---:|
| Action syntax and every state-head syntax | 100% |
| Action correctness | at least 80% |
| Each state-head semantic accuracy | at least 75% |
| Exact joint six-head state | at least 50% |
| End-to-end terminal correctness | at least 75% |
| Unsupported required claims | 0 |

Passing authorizes only design of a new unseen fictional holdout. It does not
authorize r017, NOAA, or a scientific evaluation family.
