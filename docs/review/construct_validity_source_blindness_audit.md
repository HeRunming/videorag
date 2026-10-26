# Construct-validity source-level blindness audit

**Date:** 2026-09-23  
**Scope:** portable-example regeneration and narrowly necessary
construct-validity tests/style cleanup  
**Decision:** `CONSTRUCT_VALIDITY_SOURCE_BLINDNESS_READY`  
**Readiness token:** `CONSTRUCT_VALIDITY_SOURCE_BLINDNESS_READY`

## Decision

The remaining source-level reviewer-blindness blocker is closed. The checked-in
portable example was regenerated with the current packet builder, contains the
new coordinator assignment and source-exposure ledgers under their current
schemas, remains an unfilled non-distributable packet, and imports fail closed
as `INCOMPLETE_NO_HUMAN_DECISION`.

No human identity, reviewer assignment, exposure, review decision, approval,
H1 tier, or H2 tier was fabricated.

## Portable-example regeneration

Regenerated:

`data/rehearsal_plan/construct_validity_portable_example/packet/`

from:

- `data/rehearsal_plan/construct_validity_example_registry.json`; and
- `data/rehearsal_plan/construct_validity_portable_example/coordinator_sample_source.json`.

The regenerated packet has:

- 8 families across 6 source groups;
- 48 role assignments, exactly six per family;
- `coordinator/reviewer_assignments.json`;
- `coordinator/source_exposure_ledger.json`;
- packet copies of the annotation, adjudication, saturation-audit,
  reviewer-assignment, and source-exposure schemas;
- `assignment_status=DRAFT_NOT_DISTRIBUTABLE`;
- `distribution_authorized=false`;
- `packet_distribution_authorized=false`;
- 48 null reviewer IDs and 48 null assignment timestamps;
- 48 forms with `completion_status=not_started` and null reviewer IDs;
- zero pre-distribution exposure events and zero review events; and
- no computed human tier.

The refreshed
`data/rehearsal_plan/construct_validity_portable_example/import_dry_run.json`
records:

```text
decision=INCOMPLETE_NO_HUMAN_DECISION
human_review_occurred=false
H-tier count=0
```

The importer was also rerun independently against the checked-in packet and
returned the same fail-closed decision.

## Regression protection

`tests_validation/test_construct_validity.py` now checks the checked-in
portable example directly. It requires the draft/non-distributable manifest
and assignment states, null identities and assignment times, empty exposure
ledgers, an importer result matching the checked-in dry-run artifact apart
from its runtime timestamp, `INCOMPLETE_NO_HUMAN_DECISION`, and no H-tier
promotion.

Focused Ruff cleanup was limited to construct-validity files: import ordering,
one equivalent dictionary-values iteration, removal of one unused import, and
executable modes for the shebang-bearing construct-validity tools. No
source/index/mining/intervention file was changed for this repair.

## Validation evidence

### Full validation suite

```text
pytest -o addopts='' -q tests_validation
48 passed in 131.02s
```

`-o addopts=''` was used so pytest printed the full summary instead of
combining the repository's configured `-q` with the command-line `-q`.

### Focused construct-validity suite

```text
pytest -o addopts='' -q tests_validation/test_construct_validity.py
26 passed in 100.07s
```

### Focused lint

```text
python -m ruff check \
  tools/construct_validity_common.py \
  tools/construct_validity_packet.py \
  tools/construct_validity_import.py \
  tools/construct_validity_sampler.py \
  tests_validation/test_construct_validity.py
All checks passed!
```

### Focused compile

```text
python -m py_compile \
  tools/construct_validity_common.py \
  tools/construct_validity_packet.py \
  tools/construct_validity_import.py \
  tools/construct_validity_sampler.py \
  tests_validation/test_construct_validity.py
exit code: 0
```

### Construct schema validation

All seven `docs/spec/construct_validation_*_schema.json` files passed
`Draft202012Validator.check_schema`:

1. adjudication;
2. annotation;
3. import report;
4. registry;
5. reviewer assignment;
6. saturation audit; and
7. source exposure ledger.

All regenerated portable instances also passed their validators: 32 annotation
forms, 8 adjudication forms, 8 saturation-audit forms, the assignment
registry, reviewer-assignment ledger, source-exposure ledger, and import
report.

### Independent rejection checks

Separate temporary copies of the regenerated packet established that:

- reusing one source-group author's identity as another family's blind
  alternative-evidence finder is rejected during assignment freeze with a
  source-level reviewer-assignment conflict;
- changing a reviewer ID after assignment freeze is rejected at import with
  `assignment_freeze_sha256 mismatch`; and
- changing the captured timestamp in the source-exposure snapshot without
  recomputing its digest is rejected at import with
  `pre-distribution exposure snapshot hash mismatch`.

## Final status

The portable example is current, blank, non-distributable, schema-valid, and
fail closed. Full and focused validation, lint, compile, schema checks, and
independent conflict/tamper checks pass.

`CONSTRUCT_VALIDITY_SOURCE_BLINDNESS_READY`
