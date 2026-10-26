# Exogenous restoration protocol v2 audit

**Audit date:** 2026-09-23  
**Decision token:** `CAUSAL_INTERVENTION_V2_READY`  
**Scientific execution:** `NOT_AUTHORIZED`

## 1. Decision

`CAUSAL_INTERVENTION_V2_READY`

The pre-annotation causal contract is repaired and machine-checkable. The
decision means that the primary intervention design is ready to govern future
family conversion and execution planning. It does not mean that any real
family, human review, leakage test, model run, or scientific result exists.

Scientific execution remains blocked until the execution gates in the frozen
plan pass.

## 2. Evidence reviewed

The repair reviewed the repository-local:

- Task 141 hostile red-team and its causal objections;
- Task 138 evaluation preregistration;
- frozen CVPR pivot;
- main blueprint v2;
- metrics protocol 0.3.0;
- episode schema 0.2.0;
- semantic validator specification and implementation;
- tool API restoration contract;
- positive family fixture and schema/semantic tests; and
- Task 140 saturation-auditor audit and schema.

No web browsing was required. No source, model, API, or literature freshness
claim is made.

## 3. Implemented repair

### 3.1 Exogenous primary restoration

- Frozen a zero-based fixed action index of 4.
- The event occurs after four completed action/response cycles and before the
  next model decision.
- The schedule is identical across systems within a family.
- It cannot depend on tool choice, `get_channel_status`, system identity,
  answer content, correctness, confidence, rationale, latency, or another
  state's outcome.
- Primary-matrix systems must be declared staged/event-capable before
  assignment. Non-staged systems are structurally ineligible, not assigned a
  synthetic recovery outcome.

### 3.2 Matched `RESTORED` and `NO_TRIGGER`

- One blocked prefix is frozen, then replayed into fresh isolated `R/N`
  continuation sessions.
- Both arms receive the exact same neutral public checkpoint event.
- Public transcript bytes must match through and including that event.
- Only the evaluator-private route availability changes in `R`.
- If the prefix terminates early, both assignments retain the same terminal
  prefix, receive no post-terminal event, and remain in the ITT denominator.

### 3.3 ITT and estimands

- The primary restoration contrast is `RESTORED - NO_TRIGGER`.
- Every preregistered assignment remains in the denominator, including early
  terminators and typed invalid runs under fail-closed scoring.
- Trigger-reached, route-inspected, valid-only, and tool-calling populations
  are sensitivity or per-protocol populations only.
- `RESTORED - BLOCKED` is retained only as a mechanism-specific descriptive
  state contrast.
- Subtracting BLOCKED diagnostic success from RESTORED supported-answer
  success remains prohibited.

### 3.4 Action-contingent restoration

`get_channel_status` restoration is explicitly
`SECONDARY_PER_PROTOCOL_ACTION_CONTINGENT`. It has separate assignments,
denominators, and tables, is selected on post-assignment behavior, cannot be
pooled with the exogenous condition, and cannot support the primary causal
claim.

### 3.5 Mechanism separation

The contract distinguishes:

- `SILENT_ROUTE_WITHHOLDING`, with no explicit outage marker and balanced
  non-semantic public surface; and
- `EXPLICIT_CHANNEL_OUTAGE`, with a standardized typed unavailable response.

They have separate co-primary `R-N` ITT estimands. A pooled primary
restoration estimate is disallowed.

### 3.6 State-surface and contamination controls

The plan requires:

- a field-level state-surface manifest;
- explicit invariant, intended-difference, mediator, and forbidden-private
  classifications;
- no model-visible state role, assignment arm, trigger flag, route bit,
  intervention/necessity IDs, accepted-SES labels, answer keys, or order ID;
- fresh provider and continuation sessions;
- no shared model KV/prompt, retrieval, or tool-response cache;
- no cross-state generated memory;
- exact `R/N` prefix-plus-event hash matching; and
- `INVALID_CROSS_STATE_CONTAMINATION` on any collision or cross-state read.

### 3.7 Counterbalanced order

The plan freezes four Williams sequences:

1. `C-B-N-R`
2. `B-R-C-N`
3. `R-N-B-C`
4. `N-C-R-B`

Assignment is seeded, stratified by intervention mechanism, and derived from
immutable source, family, and system identifiers before outcomes.

### 3.8 Metadata-only leakage classifier

The gate is specified, not run. It:

- uses protocol state labels only and creates no human label;
- permits only non-semantic public-surface metadata;
- forbids question/answer text, transcripts, OCR/captions, media features,
  embeddings, retrieval scores, semantic payloads, SES/claim labels, and
  source identity;
- freezes L2 logistic regression with leave-one-source-group-out evaluation;
- uses `R` versus `N` through the checkpoint as the primary task;
- requires balanced accuracy not above the majority baseline, a
  source-blocked permutation \(p \ge 0.05\), no deterministic single-feature
  predictor, and exact `R/N` transcript hashes; and
- fails closed as `LEAKAGE_GATE_REPAIR` or `LEAKAGE_GATE_NO_GO`.

Its current status is `NOT_RUN_BLOCKS_SCIENTIFIC_EXECUTION`.

### 3.9 Terminology

The required phrase is:

> all accepted SESs discovered under the frozen saturation protocol

Universal “all possible SESs” and “exhaustive SESs” wording is prohibited.

## 4. Files created

- `docs/design/exogenous_restoration_protocol_v2.md`
- `docs/spec/metrics_protocol_v2.md`
- `docs/spec/exogenous_restoration_execution_plan_schema_v2.json`
- `data/rehearsal_plan/exogenous_restoration_protocol_v2.json`
- `tests/test_exogenous_restoration_protocol_v2.py`
- `docs/review/exogenous_restoration_protocol_v2_audit.md`
- `orchestration/results/145_exogenous_restoration_protocol.txt`

The implementation is additive because the existing 0.2.0 family schema and
runtime encode only three states and preserve historical fixtures. Mutating
them in place would create an unsafe compatibility break and a larger
concurrent-edit surface. The v2 documents explicitly supersede conflicting
legacy restoration and estimand language for new primary causal evaluation.

No canonical index, candidate registry, family-mining output, reviewer schema,
or scientific episode was modified.

## 5. Validation

Passed:

```text
python -m json.tool data/rehearsal_plan/exogenous_restoration_protocol_v2.json
python -m json.tool docs/spec/exogenous_restoration_execution_plan_schema_v2.json
pytest -q tests/test_exogenous_restoration_protocol_v2.py
8 passed
pytest -q tests/test_exogenous_restoration_protocol_v2.py tests/test_schemas.py tests/test_semantic.py
43 passed
```

Focused adversarial tests reject or detect:

- `get_channel_status` dependence in the primary schedule;
- a state-revealing sham message;
- replacement of primary `R-N` with `R-B`;
- promotion of action-contingent restoration to a primary claim;
- pooled mechanism semantics;
- omitted ITT inclusion of early terminators/invalids;
- weakened session/cache/state-surface invariants; and
- unbounded SES terminology.

## 6. Artifact hashes

```text
8acf4dc6f955cb6468b187255a9ac3ddd0a54a9a4648184b448d98eb2e8df516  docs/design/exogenous_restoration_protocol_v2.md
b162182b129d1b392200c565e81591dde826ebc14331aedd416f53b63da40314  docs/spec/metrics_protocol_v2.md
c04697462bc8e5ef426ef4c0c5d9b789f30709cfe6425c40aa3fe07e3a40de4a  docs/spec/exogenous_restoration_execution_plan_schema_v2.json
aede6e80596feaa3a483d63b9941dcd854df5a511c193cec14295b5e1a8ac654  data/rehearsal_plan/exogenous_restoration_protocol_v2.json
782f4fb07182b0205a14a0d2475e1861db008406eddf8ce92fd41286a223e5d0  tests/test_exogenous_restoration_protocol_v2.py
```

These hashes cover the pre-audit implementation artifacts. The audit and
orchestration report are intentionally not self-hashed.

## 7. Remaining blockers

- No real family has demonstrated H2 eligibility under this contract.
- No state-surface manifest has been instantiated for a real family/backend.
- No staged adapters have been certified for the primary matrix.
- No `R/N` prefix-fork replay has run.
- No fresh-session/cache attestation has been collected.
- No order assignments have been generated for an authorized run matrix.
- The metadata-only leakage classifier gate has not run.
- No scientific episode is authorized or executed.

## 8. Final

`CAUSAL_INTERVENTION_V2_READY`

