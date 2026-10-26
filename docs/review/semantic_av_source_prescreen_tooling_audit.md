# Semantic A/V source-prescreen tooling audit

**Date:** 2026-09-23  
**Scope:** new pre-authoring schemas, deterministic planner, import validator,
construct-ledger exposure bridge, tests, and portable blank example  
**Decision:** `SEMANTIC_AV_SOURCE_PRESCREEN_READY`

## Scope control

The implementation adds only new semantic-prescreen artifacts. It does not
modify canonical media or indexes, the candidate registry, the family miner,
or any human H-tier schema. Media extraction remains adapter-only.

The design follows the repairs required by Tasks 141, 144, 149, and 152:

- event-centric eligibility is screened by human semantic observation rather
  than machine AST/CLIP labels;
- dynamic non-text vision and concrete non-speech audio are explicit;
- transcript/OCR/caption/narration substitutions are explicit;
- source sampling occurs before authoring and without semantic labels;
- licensed-dataset annotations remain sealed from selection and planning;
- prescreens confer authoring eligibility only; and
- no necessity, H1, H2, gold, or saturation status can be assigned.

## Artifacts

Schemas:

- `docs/spec/semantic_av_source_prescreen_inventory_schema.json`
- `docs/spec/semantic_av_source_prescreen_plan_schema.json`
- `docs/spec/semantic_av_source_prescreen_annotation_schema.json`
- `docs/spec/semantic_av_source_prescreen_import_schema.json`
- `docs/spec/semantic_av_source_prescreen_exposure_ledger_schema.json`

Tools:

- `tools/semantic_av_source_prescreen_common.py`
- `tools/semantic_av_source_prescreen_plan.py`
- `tools/semantic_av_source_prescreen_import.py`

Tests:

- `tests_validation/test_semantic_av_source_prescreen.py`

Portable blank artifacts:

- `data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_inventory.json`
- `data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_plan.json`
- `data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_form.json`
- `data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_import.json`
- `data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_exposure_ledger.json`

## Fail-closed properties

1. **No semantic planner input.** Inventory and plan schemas reject embedded
   media and semantic metadata; plan samples contain only source identity,
   hashes, intervals, and non-executing adapter requests.
2. **Deterministic source-uniform allocation.** Source counts differ by at most
   one; temporal bins and SHA-256 jitter are deterministic; non-overlap and
   plan hashes are validated.
3. **Complete human fields.** Completed import requires all interval reviews,
   speech presence, four substitution-risk assessments, candidate-fact carrier
   consistency, recurrence, privacy, safety, rationale, and decision-specific
   repairs/constraints.
4. **No H-tier path.** Schemas and import output fix necessity, H1, and H2 to
   false. The tooling does not import or mutate H-tier schemas.
5. **Exposure is durable.** A valid completed prescreen emits one source-level
   exposure event per reviewed source group.
6. **Blind-role prevention.** The bridge records conservative
   `external_prior_work` exposure in the existing construct source ledger
   before assignment freeze. Existing source-level conflict logic then rejects
   the prescreener as either blind finder or saturation auditor.
7. **Late bridging is rejected.** Frozen assignments and construct ledgers
   with review events cannot be rewritten by the bridge.
8. **Blank fixture is non-authoritative.** It imports as
   `SEMANTIC_AV_SOURCE_PRESCREEN_REPAIR`, has zero exposure events, and contains
   no reviewer or semantic observation.

## Validation

Focused semantic-prescreen tests:

```text
pytest -o addopts='' -q tests_validation/test_semantic_av_source_prescreen.py
11 passed
```

Combined semantic-prescreen and construct-validity tests passed `37/37`.
The full `tests_validation` suite passed `59/59`. Focused Ruff and
`py_compile` checks also passed. Complete commands and timings are recorded in
`orchestration/results/153_semantic_av_source_prescreen_tooling.txt`.

## Residual boundaries

- Sampling is a prescreen, not full-source coverage.
- The tool cannot establish that a modality is necessary.
- Adapter implementations and media extraction are out of scope.
- Rights/access/privacy governance remains independently required.
- A `READY` source may still fail authoring, validation, adjudication, or
  saturation.

## Decision

The requested fail-closed pre-authoring workflow, deterministic sample-plan
generation, import validation, source-level exposure record, and blind-role
exclusion are implemented without crossing the ownership boundary.

`SEMANTIC_AV_SOURCE_PRESCREEN_READY`
