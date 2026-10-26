# P23_102 technical smoke v2 independent-authorization repair

**Date:** 2026-10-14  
**Decision:** `P23_102_TECHNICAL_SMOKE_V2_AUTHORIZATION_REPAIR_READY`

## Binding red-team blockers closed

1. **Immutable unauthorized freeze.** Execution no longer depends on changing
   the frozen config or adapter boolean. A separately supplied exact-schema,
   hash-bound, expiring, one-run overlay with distinct live-wiring and red-team
   approvals is mandatory. No overlay was created.
2. **Learned R/N lifecycle.** Learned prefixes use a dedicated worker that is
   closed before two fresh continuation workers are opened.
3. **Leakage reporting.** Recursive mechanical private-surface scanning is
   separate from `runtime_leakage_classifier=NOT_ESTIMABLE_SINGLE_SOURCE`.
4. **Online thresholds.** Provider-call and assignment limits, cumulative
   typed failures, privacy, isolation, checkpoint, and output failures are
   enforced before further work with exact `>=` threshold semantics.
5. **Durability.** The initial manifest precedes assignment 1; raw and terminal
   rows append durably; abort and unstarted ledgers survive interruption.
6. **Process diagnostics.** Every process failure has canonical diagnostic
   bytes, SHA-256, and byte length.
7. **Qwen integrity.** Every file listed in the local acquisition manifest is
   validated by size and SHA-256, including the weight file.
8. **B/R/N identity.** A scoped canonical public-start probe is persisted for
   every applicable paired cell.
9. **Provenance.** Final manifests carry actual UTC, output root, authorization,
   freeze, adapter, runner, module/model, plan, and validated-file identities.
10. **Checkpoint contract.** The exact object, canonical hash, index, delivery
    cardinality, and R/N prefix identity are checked.
11. **Adversarial tests.** Focused tests cover unknown/minimal authorization,
    wrong output root, same-size model tamper, embedded private leakage,
    classifier status, prefix-worker freshness, exact thresholds,
    interruption durability, wrong-identical checkpoint, and process raw hash.

## Preserved limitations

The immutable freeze remains unauthorized without an external overlay. The
smoke is development-only and machine-provisional. A successful future smoke
would establish mechanical plumbing only; it cannot establish answer quality,
model competence or performance, modality necessity, causal effects, H2,
Gate A, accepted SESs, human validity, or source generalization.

No live inference or media decoding was performed during this repair.

`P23_102_TECHNICAL_SMOKE_V2_AUTHORIZATION_REPAIR_READY`
