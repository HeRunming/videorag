# EPIC development authoring packets audit

**Task:** 171  
**Date:** 2026-10-02  
**Decision:** `EPIC_DEV_AUTHORING_PACKETS_READY`  
**Artifact class:** development-only, non-distributable authoring rehearsal

## 1. Scope and decision

Task171 converts the five `KEEP` proposals in Task167 into a restricted packet
registry and blank workflow forms. The packets are ready as **rehearsal
artifacts only**. They are not authorized for distribution and they contain no
human identity, semantic observation, decision, H1/H2 assignment, accepted
SES, necessity finding, minimality finding, or Gate-A result.

The five substantive proposal packets are:

1. `EPIC-DEV-P27-CLEANER-FROM-CUPBOARD`;
2. `EPIC-DEV-P27-UNWRAP-FROZEN-ITEM`;
3. `EPIC-DEV-P28-DRY-HANDS-WITH-TOWEL`;
4. `EPIC-DEV-P28-PEEL-POTATO`; and
5. `EPIC-DEV-P28-ADD-ADJUST-STIR`.

The two Task167 `REJECT` records are retained separately as machine-rejection
calibrations:

- `EPIC-DEV-P27-LONG-HANDLED-CLEANING-TOOL`; and
- `EPIC-DEV-P28-YELLOW-PACKET-AFTER-RINSE`.

Their inclusion does not reopen them and does not represent a human rejection
decision.

## 2. Inputs and evidence boundary

The implementation read Tasks 146, 153, 159, and 167 and reused only existing
local artifacts:

- Task167's restricted development registry;
- the two existing local EPIC source bindings and hashes;
- Task153's inventory, plan, blank-form, import, and exposure-ledger tooling;
- Task146's source-group assignment and exposure-conflict logic; and
- Task159's development-only authoring and calibration boundaries.

No network access, acquisition, annotation vault, benchmark label, narration
annotation, EPIC-SOUNDS annotation, or new media decoding was used. The packet
builder copies no media and creates no media derivative.

## 3. Packet layout

The root is:

`data/rehearsal_plan/epic_dev_authoring_packets_v1/`

Coordinator artifacts:

- `coordinator/packet_registry.json`;
- `coordinator/packet_manifest.json`;
- `coordinator/blank_import_report.json`;
- `coordinator/role_assignment_matrix.json`; and
- `coordinator/source_exposure_ledger.json`.

Prescreener artifacts:

- one nonsemantic Task153 inventory for `P27_101`;
- one nonsemantic Task153 inventory for `P28_103`;
- one deterministic six-interval Task153 plan per source;
- one blank Task153 prescreener form per source;
- one fail-closed blank Task153 import per source; and
- one empty Task153 exposure ledger per source.

Author/verifier artifacts:

- one blank `question_claim_author_or_verifier` form for each of the five
  retained proposals.

Calibration artifacts:

- two standalone Task167 rejection examples.

All packet files are mode `0600` and the packet root is mode `0700`.

## 4. Registry bindings

The coordinator registry is bound to the exact Task167 registry by:

- file SHA-256;
- Task167 internal registry payload SHA-256; and
- each proposal's Task167 payload SHA-256.

Each retained proposal is bound to:

- source ID and source-group ID;
- machine-provisional question and answer;
- atomic claim hypotheses;
- evidence hypotheses with exact intervals, modality, carrier class, and
  canonical local index references;
- its source's Task153 plan ID and plan SHA-256;
- all six Task153 source-prescreen sample IDs and exact intervals; and
- its blank author/verifier form.

All copied semantics remain explicitly hypotheses. Evidence entries retain
`human_semantic_validation_status=NOT_PERFORMED`.

## 5. Semantic firewall and Task153 intervals

The prescreener packets are separated from the proposal registry and
author/verifier packets. A prescreener is instructed to receive only:

- the source;
- the nonsemantic inventory;
- the Task153 source-uniform plan; and
- the blank Task153 form.

They must not receive proposal questions, answers, claims, preferred evidence,
machine ranks, or rejection calibrations. Each source has six deterministic
20-second intervals produced by Task153's
`source-uniform-temporal-bin-sha256-jitter-v1` algorithm.

The checked-in blank imports correctly return
`SEMANTIC_AV_SOURCE_PRESCREEN_REPAIR`, because no human prescreen has occurred.
Both Task153 exposure ledgers contain zero events.

## 6. Blank author/verifier forms

Each author/verifier form contains immutable machine-provisional assignment
material and empty review fields for:

- question and answer checking;
- claim-by-claim checking;
- evidence-by-evidence checking;
- alternative-route checking;
- full-source recurrence;
- OCR, transcript, caption, and narration substitution;
- privacy and safety;
- proposed repairs; and
- general notes.

Every form has:

- `completion_status=not_started`;
- `reviewer_id=null`;
- no timestamps;
- no recorded findings;
- no decision field capable of assigning H1/H2; and
- an immutable-assignment SHA-256 checked on import.

## 7. Source-level exposure and role exclusion

Task146 and Task153 require blindness at the source-group level, not merely at
the proposal level. Task171 therefore treats both roles below as exposed:

- `semantic_av_source_prescreener`; and
- `question_claim_author_or_verifier`.

Either role would be barred for the whole source group from:

- `blind_alternative_evidence_finder`; and
- `blind_post_adjudication_saturation_auditor`.

The coordinator matrix contains only null reviewer IDs and null assignment
times. The source-exposure ledger contains no events. A synthetic validation
self-test, not persisted as human activity, exercises the existing Task146
conflict checker and confirms that both prescreener-style external exposure
and author/verifier exposure reject subsequent blind-role assignment.

## 8. Permanent eligibility boundary

The following are fixed false in the registry, forms, manifest, and import:

- future-test eligibility;
- Gate-A eligibility;
- distribution authorization;
- human review;
- human decision;
- necessity;
- minimality;
- H1;
- H2; and
- human gold.

These EPIC sources and all Task171 derivatives remain permanently
future-test-ineligible and Gate-A-ineligible. A future completed rehearsal
could generate development feedback only; it could not promote these packets
into a primary test set or Gate A.

## 9. Calibration/rejection examples

The first calibration demonstrates rejection for same-source cluster
duplication and visually underspecified object identity. The second
demonstrates rejection for a recurrent sink/water cluster plus package/OCR and
appearance shortcuts.

Both examples preserve Task167's machine dispositions and explicitly state
that they are not human decisions. They are used to teach fail-closed
rejection rather than encourage forced authoring.

## 10. Fail-closed validation

Added schemas:

- `docs/spec/epic_dev_authoring_packet_registry_schema.json`;
- `docs/spec/epic_dev_authoring_role_form_schema.json`; and
- `docs/spec/epic_dev_authoring_import_schema.json`.

Added builder/verifier:

- `tools/epic_dev_authoring_packets.py`.

Added tests:

- `tests_validation/test_epic_dev_authoring_packets.py`.

Validation results:

- three Draft 2020-12 schemas meta-validated;
- coordinator registry, five author/verifier forms, and blank import validated;
- all packet JSON parsed;
- checked-in verifier returned `EPIC_DEV_AUTHORING_PACKETS_READY`;
- focused Task171 tests: `6 passed`;
- targeted Task153 and Task146 compatibility tests: `15 passed`;
- focused Ruff: pass;
- focused `py_compile`: pass;
- Task153 interval tampering is rejected;
- author-form identity injection is rejected;
- immutable assignment mutation is rejected; and
- source-level blind-role conflict self-test is rejected as required.

A broader combined run also exposed six pre-existing construct-validity test
failures in current-tree completed-review fixtures, all reporting
`ASSIGNMENTS_NOT_FROZEN_BEFORE_DISTRIBUTION`. Task171 does not alter those
tools or fixtures; the targeted Task146 source-conflict and blank-governance
tests pass.

Key hashes:

- `2b5bf70d2ba1f77fbf9b7b03c20507df69aaaf4024657f210baf3a5d558bc820`
  — packet registry;
- `f6aeeb3da2e9efd84c890eed24681fc2d6b813680dd786ae5fc1abb74d504368`
  — packet manifest;
- `2a6a99db8485b0633bf19dbcda21ca98dd0aa4de6ec03c1de4f862ae05ff5ca6`
  — blank import report; and
- `57ceeb6cd6c371b55397cdfa1a44989849d01a2365f1a3dc95b943d8f2cc70a6`
  — builder/verifier.

## 11. Final decision

`EPIC_DEV_AUTHORING_PACKETS_READY`

READY means the non-distributable development packet set is complete,
deterministic, semantically firewalled, source-exposure governed, and
fail-closed. It does not mean any source or proposal has passed human
prescreen, author verification, Gate A, construct validation, or scientific
acceptance.
