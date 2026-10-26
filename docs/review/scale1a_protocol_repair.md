# Task 97 — Scale-1A protocol repair

Date: 2026-09-11

## Decision

```text
SCALE1A_ENGINEERING_GO
SCALE1A_DIAGNOSTIC_INCONCLUSIVE
FINAL_BENCHMARK_NOT_YET_VALIDATED
```

Task 97 repaired all engineering blockers identified by Task 96. It did not
force a scientific GO.

## Repairs

### Speech localization and lineage

The frozen checkpoint transcripts are now represented by one searchable and
citable record per non-overlapping 30-second ASR chunk. The legacy 4,283
fine/context transcript projections remain inside immutable checkpoints for
provenance but are ignored by the derived index.

The rebuilt index contains 461 speech records and a complete
`chunk_id -> derived search record IDs` map. Every chunk currently maps to
exactly one record. Speech citations use the truthful chunk interval.

### BLOCKED closure

For `r016` and `r017`, intervention construction starts with each registered
support speech record, resolves its parent chunk, computes all records derived
from that chunk, and adds that closure to suppression. The persisted proof
shows zero support-chunk-derived records reachable before restoration.

### Action-level trajectories

The old metric simulations were replaced by a stateful fixed backend and blind
policy session. The regenerated 140 trajectories contain 606 actions, actual
tool responses or restricted response references, trigger events, costs,
budgets, observations, final outputs, validation, and route certificates.

All citable inspect/read calls decode the exact interval from the original
media. No decoded derivative is persisted.

### Strict Ground/Act metrics

The evaluator now validates public claim handles, claim-level citations,
unknown/private identifiers, required-claim semantics, and support links.
Answer Score, Citation F1, Supported-Claim Rate, Success@Budget, Premature
Stop, and Recovery are computed from separate execution evidence.

### Visual hard negatives

Visual candidates do not possess two independent content-level non-support
checks. They are honestly retained as
`machine_provisional_hard_negative_candidate`, marked ineligible for validated
hard-negative metrics, and excluded from the corresponding diagnostic gate.
Speech/ambient candidates retain their computed source-derived checks.

## Regeneration and invariants

All requested derived artifacts and public reports were regenerated. Source
media, model snapshots, and all 20 expensive inference checkpoints were
preserved. Hash verification reports 20/20 unchanged checkpoints.

Five families are retained (`r004`, `r007`, `r011`, `r016`, `r017`); `r014`
remains excluded due to `VISION_SUPPORT_NOT_TOP20`.

## Verification

```text
PYTHONPATH=src pytest -q \
  tests_scale1a tests/test_scale1a_model_acquisition.py

33 passed
```

```text
PYTHONPATH=src pytest -q \
  tests tests_mvp tests_media tests_agent_runtime \
  tests_validation tests_media_pipeline tests_real_av tests_scale1a

476 passed
```

```text
PYTHONPATH=src python scripts/verify_scale1a.py --repo-root . --strict

passed=true
failures=[]
decision=SCALE1A_ENGINEERING_GO
```

Checkpoint-derived deterministic replay:

```text
all_match=true
checkpoint_count=20
```

## Remaining scientific limitations

The diagnostic decision stays inconclusive because the current low-N,
machine-adjudicated deterministic pilot does not pass every frozen diagnostic
criterion. In particular, validated visual hard negatives are unavailable,
the displacement recovery/control criterion does not pass under honest
eligibility, and `r007` remains outside Recall@5.

Nothing in this result establishes human gold evidence, modality necessity,
minimal sufficient evidence, learned-agent performance, or publication-ready
benchmark validity.
