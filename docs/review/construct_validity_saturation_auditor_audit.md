# Construct-validity saturation-auditor implementation audit

**Date:** 2026-09-23  
**Scope:** reviewer-role schemas, validators/import, packet generation, tests, and reviewer documentation  
**Readiness token:** `CONSTRUCT_VALIDITY_SIX_ROLE_TOOLING_READY`

## Decision

`CONSTRUCT_VALIDITY_SIX_ROLE_TOOLING_READY`

The construct-validity tooling now represents six distinct human roles per
family and fails closed before H2 when the blind post-adjudication saturation
audit is missing, non-independent, out of sequence, incompletely logged,
linked to a changed adjudication, or reports a new or unresolved sufficient
route.

This readiness token applies to tooling only. It does not assert that human
review occurred, that any family reached H1/H2, or that the mini-pilot may be
reported as a scientific result.

## Implemented controls

- Added a normative saturation-audit schema and validator.
- Generated a separate role directory containing only source provenance,
  duration, and the frozen question; accepted SESs, preferred SESs, machine
  ranks/confidence/tier evidence, validator decisions, and adjudication
  decisions are excluded.
- Required a sixth pseudonymous identity distinct from the four
  pre-adjudication reviewers and adjudicator.
- Required adjudication to finish before the audit starts and required the
  auditor to record the SHA-256 of the frozen adjudication form.
- Required ordered, gap-bounded, full-source coverage plus search methods,
  queries, exact route intervals, modalities, derivation lineage, sufficiency,
  and reopen status.
- Preserved the P/H boundary: H1 remains available after the original four-role
  validation gate; H2 now additionally requires a passing adjudication and a
  passing saturation audit. A new sufficient route reopens the family and
  returns it to its starting P tier until repair and re-review.
- Regenerated the checked-in blank portable example; it remains explicitly
  unfilled and imports as `INCOMPLETE_NO_HUMAN_DECISION`.

## Verification

- `pytest -q tests_validation` — **39 passed**.
- `pytest -q tests_validation/test_construct_validity.py` — **17 passed**.
- Focused Ruff over the three construct-validity tools and focused test file —
  **passed** (legacy executable-bit rule excluded because these pre-existing
  shebang files are stored non-executable).
- Draft 2020-12 validation of all five construct-validation schemas — **passed**.
- Checked-in blank packet dry-run — **passed fail-closed** with 8/8 saturation
  forms unstarted, `human_review_occurred=false`, and no H-tier promotion.

## Remaining blockers

- No real human identities, approvals, review decisions, H1 records, or H2
  records exist; none were fabricated.
- The real mini-pilot still requires six trained, distinct people per family
  and coordinator-controlled staged distribution.
- Any saturation discovery requires evidence-graph/necessity/C-B-R repair,
  fresh adjudication, and a fresh independent audit before H2.
- Existing source, family-mining, rights, and later evaluation gates remain
  unchanged and must pass separately.

## Changed files

Core implementation and contracts:

- `tools/construct_validity_common.py`
- `tools/construct_validity_packet.py`
- `tools/construct_validity_import.py`
- `docs/spec/construct_validation_annotation_schema.json`
- `docs/spec/construct_validation_import_schema.json`
- `docs/spec/construct_validation_saturation_audit_schema.json`
- `tests_validation/test_construct_validity.py`
- `docs/annotation/construct_validity_protocol.md`
- `docs/annotation/forms/README.md`
- `data/rehearsal_plan/construct_validity_mini_pilot_plan.json`

Regenerated portable example:

- `data/rehearsal_plan/construct_validity_portable_example/import_dry_run.json`
- `data/rehearsal_plan/construct_validity_portable_example/packet/README.md`
- `data/rehearsal_plan/construct_validity_portable_example/packet/packet_manifest.json`
- `data/rehearsal_plan/construct_validity_portable_example/packet/construct_validation_annotation_schema.json`
- `data/rehearsal_plan/construct_validity_portable_example/packet/construct_validation_saturation_audit_schema.json`
- Each of the following eight family directories gained
  `blind_post_adjudication_saturation_auditor/README.md` and `form.json`, and
  its existing `blind_alternative_evidence_finder/form.json` was updated with
  the explicit machine-rank blind:
  - `current.noaa01-r004-surf-av`
  - `current.noaa01-r016-three-factors-vs`
  - `future.ambient.factory.alarm`
  - `future.ambient.factory.alarm.second`
  - `future.v.museum.tour`
  - `future.va.wildlife`
  - `future.vsa.field.demonstration`
  - `future.vsa.field.demonstration.second`

Audit outputs:

- `docs/review/construct_validity_saturation_auditor_audit.md`
- `orchestration/results/140_construct_validity_saturation_auditor.txt`
