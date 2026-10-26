# Strong-baseline adapter v1 implementation audit

**Audit date:** 2026-09-24  
**Decision:** `STRONG_BASELINE_ADAPTER_READY`  
**Scientific execution:** `NOT_AUTHORIZED`

## Scope audited

The audit reviewed only the new Task 158 implementation:

- `src/av_trace_strong_baselines/`;
- `scripts/generate_strong_baseline_competence_suite.py`;
- `scripts/evaluate_strong_baseline_competence.py`;
- `tests/test_strong_baseline_adapters.py`;
- `data/rehearsal_plan/strong_baseline_competence_suite_v1.json`; and
- this design/review/result documentation.

No canonical index, candidate registry, source tool, restricted evaluator key,
scientific family, or historical baseline output was needed.

## Findings

### A. Requested adapter coverage — PASS

The dry matrix contains:

- native direct A/V;
- single-shot RAG;
- same-backbone ReAct;
- same-backbone evidence sufficiency;
- shared grounded finalizer;
- oracle-complete evidence;
- partial evidence;
- TRACE-style adaptation with mandatory non-reproduction label;
- `DET-REACT`;
- `DET-SUFF`; and
- restoration `NO-TRIGGER`.

### B. Common budget and tool schema — PASS

The common budget is executable code rather than documentation only. Changed
action, cost, search-depth, context, generation, repair, or model-call limits
fail construction. Tool objects validate against the frozen canonical
vocabulary. Full action envelopes validate against the existing
`agent_action_schema.json`.

### C. Evidence and privacy boundary — PASS

The observed-evidence lock requires exact observation IDs, intervals, and
modalities. Pointers are non-citable. Recursive public-surface validation
rejects evaluator-private fields and historical private-ID patterns. The
competence model projection omits case IDs and scoring targets.

### D. No deterministic answer substitution — PASS

Answer-bearing paths require model-authorship provenance. Deterministic
controls cannot carry final answers and cannot substitute for learned system
rows. The only permitted repair is structural/schema-only and rejects semantic
error codes.

### E. Exact model identity and fail-closed status — PASS

Model, tokenizer, and processor revisions require immutable 40-character
revisions. Wrong identity and unverified load stop before a driver call.
Timeout, OOM, provider failure, and invalid output preserve typed invalid
status without a fallback answer.

### F. Task 145 staged event — PASS

The fork requires exactly four completed cycles, fresh mutable namespaces,
identical R/N public bytes through the neutral checkpoint, and unchanged
remaining budget. Only the private route availability differs. The direct
non-staged row is declared structurally ineligible before assignment.

### G. Fictional competence suite — PASS

The deterministic generator produces exactly:

- 40 substantive controller/finalizer cases plus 11 fail-closed runtime
  fixtures; and
- 24 substantive direct-A/V cases plus 6 processor/identity/provider failure
  fixtures.

The suite hash is
`sha256:7b8f8d021b24cb244f0df0f6b02b3da91120df3817a5366350895eb24f4646dc`.
It records `model_used=false`, `scientific_source_used=false`,
`evaluator_private_key_used=false`, `execution_status=NOT_RUN`, and
`model_results_present=false`.

The thresholds exactly preserve Task 148. The evaluator rejects a changed
suite hash, an incomplete case set, an unverified load, or a wrong snapshot.

### H. Negative coverage — PASS

Tests explicitly cover:

- private-field leakage;
- private identifier leakage;
- semantic fallback;
- malformed output;
- deterministic answer substitution;
- unknown and interval-mismatched citations;
- cross-state cache collision;
- wrong snapshot;
- unverified load;
- wrong restoration boundary;
- nonchronological direct packing;
- same-backbone mismatch;
- unsupported claims;
- modified threshold/suite hash; and
- deterministic controls being misused as learned substitutes.

## Validation performed

```text
ruff check src/av_trace_strong_baselines \
  scripts/generate_strong_baseline_competence_suite.py \
  scripts/evaluate_strong_baseline_competence.py \
  tests/test_strong_baseline_adapters.py
```

Result: `All checks passed!`

```text
pytest -q tests/test_strong_baseline_adapters.py
```

Result at audit authoring: `31 passed`.

Additional compatibility tests are reported in
`orchestration/results/158_strong_baseline_adapter_implementation.txt`.

## Non-results and remaining blockers

The audit does not claim:

- any selected snapshot was downloaded or loaded;
- any real model generated an output;
- any model passed competence;
- any direct model satisfied native A/V behavior in practice;
- any scientific family is H2;
- the Task 145 metadata leakage classifier passed; or
- scientific evaluation is authorized.

Those remain external gates. They do not block the adapter implementation
from being ready for a later governed integration.

## Decision

The implementation meets its software and dry-fixture scope without crossing
the acquisition or scientific-execution boundary.

`STRONG_BASELINE_ADAPTER_READY`
