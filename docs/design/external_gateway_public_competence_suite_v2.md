# External-gateway public-fictional competence suite v2

**Frozen:** 2026-10-12  
**Status:** `REPAIR_NOT_AUTHORIZED`  
**Current decision:** `PUBLIC_FICTIONAL_TECHNICAL_ROW_NO_GO`

## 1. Scope and non-claim

This is a new v2 replacement for the rejected v1 suite. It is a prospective,
source-free, public-fictional **technical** sensitivity for controller and
finalizer behavior. It may test action selection, evidence-state reporting,
closed-world abstention, exact claim grounding, citation selection, and
diagnosis coherence.

It cannot establish audiovisual, scientific, benchmark, or H2 competence. A
future technical `GO` would only support the
`PUBLIC_FICTIONAL_TECHNICAL_ROW_GO` row. It must never be reported as a
standalone “Gate C” result and must not unlock scientific execution by itself.

No gateway or model was run while designing, generating, validating, or
testing v2.

## 2. Separate public/private artifacts

The artifacts are deliberately separate:

- public packets and governance metadata:
  `data/rehearsal_plan/external_gateway_public_competence_suite_v2_public.json`;
- private evaluator key:
  `data/restricted/external_gateway_public_competence_suite_v2_private.json`.

The public artifact contains no evaluator labels, strata, expected action
positions, answer forms, expected citations, diagnosis targets, or other
target-signaling metadata. Recursive validation rejects these keys and
target-signaling terms.

The private file is written with mode `0600`; `data/restricted` is already
owner-only (`0700` or more restrictive in the intended deployment). Authorized
roles are limited to the suite custodian and independent evaluator. The model,
gateway runner, prompt renderer, and public-baseline code are not authorized
to read the private key.

This repository has no locally available cryptographic secret service,
hardware-backed seal, or independently controlled evaluator account. File
permissions are useful separation but are not a secure private sealing
workflow against a privileged local process. Therefore the frozen execution
state is **REPAIR/NOT_AUTHORIZED**, not a claim of sealing.

## 3. Frozen case design

Generation uses seed `202610120207`. IDs, claim handles, observation IDs,
packet order, action order, and action target positions are derived
deterministically from that seed. IDs are opaque hashes rather than semantic
labels.

There are 48 substantive cases:

- 24 controller cases: four each for ordinary route acquisition, blocked
  route checking, restored-route retry, supported finalization, premature-stop
  prevention, and closed-world absence;
- 24 finalizer cases: four each for supported single claims, supported dual
  claims, support with distractors, source absence, inaccessible evidence, and
  accessible-but-not-found evidence.

Every private stratum has four distinct `public_input` hashes. No within-
stratum packet clones are allowed. Action positions span multiple indexes and
are not encoded in case IDs or wording.

The public artifact also freezes malformed parser fixtures for action choice,
diagnosis, claim drafts, and citation selection. Tests add injected failures
and cross-case state-reuse attacks.

## 4. Closed-world scoring

Scoring is contradiction-aware and fail-closed:

- required claims use exact normalized semantic-form allowlists;
- forbidden normalized forms detect explicit contradictions, including the v1
  target-substring attack;
- substring presence of an accepted phrase is insufficient;
- a malformed finalizer projection counts every required claim in that case as
  missing;
- absent required claims, extra registered claims, wrong citations, and
  unobserved citations are counted conservatively;
- abstention requires empty answer content and no claims;
- diagnosis compares the complete modality probability map, complete cause
  probability map, exact hop set, and recovery declaration;
- an all-ones or overinclusive diagnosis is wrong even when it includes the
  correct class.

This design intentionally prefers narrow exactness over permissive semantic
repair. There is no evaluator-side answer completion or target substitution.

## 5. Public-only adversarial baselines

Three deterministic baselines use the public artifact only:

1. always choose action position zero and otherwise abstain;
2. copy the first observation into a claim;
3. emit an all-ones/overinclusive diagnosis.

All three are validated during freeze checks and must return
`PUBLIC_FICTIONAL_TECHNICAL_ROW_NO_GO`. If any public-only baseline meets the
prospective thresholds, validation fails and the suite cannot be authorized.

## 6. Prospective thresholds

The frozen thresholds require:

| Check | Requirement |
|---|---:|
| Complete case set | exactly 48 |
| Valid case projection | at least 94% |
| Controller action accuracy | at least 86% |
| Exact controller evidence state | at least 80% |
| Exact finalizer outcome | at least 80% |
| Exact coherent diagnosis | at least 84% |
| Cross-state isolation | required |
| Missing/unsupported required claims | 0 |
| Contradictory claims | 0 |
| Unobserved citations | 0 |
| Integrity failures | 0 |

There is no intermediate result token. The evaluator emits exactly one of:

- `PUBLIC_FICTIONAL_TECHNICAL_ROW_GO`;
- `PUBLIC_FICTIONAL_TECHNICAL_ROW_NO_GO`.

The frozen, not-run state is the latter because execution is not authorized.

## 7. Overlap audit

The prospective audit covers all currently available public development
material in the governed lineage:

- Granite adapter-v2 development registry;
- Granite adapter-v2 public holdout;
- Qwen3 adapter-v2 public holdout;
- the earlier public strong-baseline competence suite;
- the rejected external-gateway v1 public artifact; and
- every available external-gateway smoke rendered prompt.

For every v2 packet and every rendered factor prompt, the audit checks:

- exact normalized text overlap;
- exact canonical object hashes;
- exact rendered-prompt hashes;
- maximum question token Jaccard, capped prospectively at `0.72`; and
- maximum rendered-prompt token Jaccard, capped prospectively at `0.92`.

Comparator file hashes are frozen. Validation recomputes the audit and fails
if comparators drift or a threshold is exceeded.

## 8. Governed runner compatibility and provenance

The suite binds exactly to:

- runner schema `av-trace.external-gateway-strong-agent-run/1.0`;
- attempt schema `av-trace.external-gateway-factor-attempt/1.0`;
- packet schema `av-trace.external-gateway-public-packet/1.0`; and
- the existing factor parsers and prompt renderer in
  `tools/external_gateway_strong_agent.py`.

An evaluable submission must include:

- the exact public payload hash and packet hash for every case;
- all required factors and only those factors;
- raw output plus its SHA-256;
- the exact recomputed rendered-prompt SHA-256 and byte count;
- model slug, catalog record hash, catalog file hash;
- provider identity and wire API;
- tcodex and upstream runtime versions;
- wrapper and native binary hashes;
- zero semantic retries or repairs;
- zero model fallback or substitution; and
- at most one schema-only retry per factor.

Forged declarations do not override attempt-level evidence. The evaluator
cross-checks attempt model/runtime identity against the runner binding.

## 9. Atomic one-shot semantics

The public artifact freezes a `NOT_RUN` ledger template with a one-full-run
maximum. Evaluation requires a separately armed ledger. Consumption creates
an exclusive `*.consumed` receipt with `O_EXCL`, writes and `fsync`s it, and
rejects any second creation. This blocks repeated evaluation even if the
original mutable ledger is replayed.

Authorization must additionally supply a secure private-key delivery method
that does not expose the private artifact to the model or runner. That method
is not available locally, so no ledger is armed and no run is permitted.

## 10. Safe commands

These commands perform no inference:

```text
PYTHONPATH=src python tools/external_gateway_public_competence_suite_v2.py \
  --write-freeze

PYTHONPATH=src python tools/external_gateway_public_competence_suite_v2.py \
  --validate-freeze

PYTHONPATH=src python tools/external_gateway_public_competence_suite_v2.py \
  --validate-baselines
```

There is intentionally no gateway/model execution CLI in the v2 tool.

