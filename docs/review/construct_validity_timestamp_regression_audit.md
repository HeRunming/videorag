# Construct-validity assignment-freeze timestamp regression audit

**Date:** 2026-10-10  
**Task:** 200  
**Decision:** `CONSTRUCT_VALIDITY_FULL_SUITE_READY`  
**Readiness token:** `CONSTRUCT_VALIDITY_FULL_SUITE_READY`

## Scope and finding

Task171 reported six pre-existing failures in
`tests_validation/test_construct_validity.py`. A fresh full
`tests_validation` run reproduced exactly those six failures. Every affected
family was demoted to its machine starting tier with
`ASSIGNMENTS_NOT_FROZEN_BEFORE_DISTRIBUTION`.

The Task146 temporal contract is:

```text
pre-distribution snapshot captured_at
    <= every assignment assigned_at
    <= assignment ledger frozen_at
    <= every completed review started_at
```

The importer also rejects review exposure before the freeze. This is the
correct fail-closed behavior and was not weakened.

The regression was in the completed-review test fixture. `build_packet()`
created the source-exposure snapshot using the current wall clock, while the
fixture subsequently assigned and froze every reviewer at fixed timestamps on
September 23, 2026. Once runtime advanced beyond that date, the fixture
asserted that a later snapshot preceded its earlier assignment and freeze.
The six failures were therefore a stale mixed-clock fixture, not a validator
defect.

## Narrow repair

The repair adds optional explicit generation clocks while retaining runtime
UTC as the default:

- `build_packet(..., generated_at=...)` binds the packet manifest,
  pre-distribution snapshot, and draft assignment ledger to one timestamp;
- `construct_validity_packet.py --generated-at ...` exposes that control for
  deterministic checked-in blank examples;
- `evaluate_packet(..., generated_at=...)` and
  `construct_validity_import.py --generated-at ...` provide the corresponding
  deterministic dry-run report timestamp; and
- blank-ledger helpers accept the injected packet timestamp.

The completed-review fixture now uses this coherent fixed timeline:

```text
packet/snapshot: 2026-09-23T23:00:00+00:00
assigned:        2026-09-23T23:01:00+00:00
frozen:          2026-09-23T23:30:00+00:00
review starts:   2026-09-24T01:00:00+00:00 or later
```

The validator still rejects an unfrozen packet, review before freeze, identity
drift, assignment hash tampering, missing exposure events, and source-group
blindness conflicts.

## Portable blank example

The affected portable example was regenerated twice in `/tmp` with:

```bash
python tools/construct_validity_packet.py \
  --registry data/rehearsal_plan/construct_validity_example_registry.json \
  --sample data/rehearsal_plan/construct_validity_portable_example/coordinator_sample_source.json \
  --output-dir /tmp/task200_construct_validity_packet \
  --generated-at 2026-09-23T11:44:32+00:00

python tools/construct_validity_import.py \
  --packet-dir /tmp/task200_construct_validity_packet \
  --output /tmp/task200_import_dry_run.json \
  --generated-at 2026-09-23T11:44:34+00:00
```

The regenerated packet directory was byte-identical to the checked-in packet,
and the dry-run report was byte-identical to the checked-in
`import_dry_run.json`. No tracked packet content needed a semantic rewrite.

Blank-example boundary:

- assignment status: `DRAFT_NOT_DISTRIBUTABLE`;
- distribution authorized: false;
- reviewer identities: 0;
- assigned timestamps: 0;
- exposure events: 0;
- human review occurred: false;
- decision: `INCOMPLETE_NO_HUMAN_DECISION`; and
- H-tier count: 0.

The forms README now documents that `--generated-at` is only for reproducible
fixtures. Real packet builds and imports should omit it and retain runtime UTC.

## Validation evidence

### Full construct-validation suite

```text
pytest -o addopts='' -q tests_validation
82 passed in 153.86s
```

The six Task171 failures are repaired.

### Focused construct-validity suite

```text
pytest -o addopts='' -q tests_validation/test_construct_validity.py
26 passed in 110.58s
```

### Ruff and compile

Focused Ruff on the four construct-validity tools and focused test:

```text
All checks passed!
```

Focused `py_compile`:

```text
PY_COMPILE_OK
```

A repository-wide `python -m ruff check .` was also attempted. It reports 566
pre-existing findings across generated `build/lib`, vendored source-recon
scripts, and unrelated tools. No Task200-focused Ruff finding remains, and no
unrelated file was changed to suppress that existing backlog.

### Schema and instance validation

All seven `docs/spec/construct_validation_*_schema.json` files passed Draft
2020-12 meta-validation. The checked-in portable assignment registry,
reviewer-assignment ledger, source-exposure ledger, 32 annotation forms,
8 adjudication forms, 8 saturation-audit forms, and import report passed their
current validators.

Independent import assertions:

```text
decision=INCOMPLETE_NO_HUMAN_DECISION
human_review_occurred=false
H-tier count=0
```

### Tamper and blindness checks

Nine focused fail-closed governance/tamper tests passed:

- immutable form assignment tampering;
- completed forms without pre-distribution freeze;
- source-group blind-role conflict at freeze;
- both blind roles after cross-family exposure;
- known prior source exposure;
- missing completed-role exposure event;
- frozen assignment-ledger hash tampering; and
- invented human tier at the registry boundary.

Result:

```text
9 passed, 17 deselected in 38.41s
```

## Boundary and decision

Task200 repairs only fixture clock control, deterministic blank-example
generation, and regression assertions/documentation. It does not relax
Task146 source blindness, temporal ordering, assignment hashing, exposure
logging, or identity matching. It creates no reviewer identity, review,
decision, human gold, H1, or H2 record.

`CONSTRUCT_VALIDITY_FULL_SUITE_READY`
