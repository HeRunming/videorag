# Pilot-v4 unified pre-distribution human packets audit

**Task:** 199  
**Date:** 2026-10-10  
**Decision:** `PILOT_V4_HUMAN_PACKETS_READY`  
**Artifact class:** pre-distribution human-packet preparation only

## 1. Decision and boundary

The unified packet set is ready as a **blank, restricted, non-distributable
preparation artifact**. It covers all 12 Task195 pilot-v4 candidate slots
across the exact six selected source groups and supplies the requested
coordinator, prescreener, author/verifier, audio-prerequisite, and calibration
materials.

This readiness token means that packet construction, binding, role separation,
schema validation, fail-closed blank imports, and restricted permissions pass.
It does not authorize packet distribution or human annotation.

The packet set creates:

- human identities: **0**;
- populated reviewer assignments: **0**;
- source-exposure events: **0**;
- human observations: **0**;
- human decisions: **0**;
- accepted SESs: **0**;
- H1 records: **0**;
- H2 records: **0**; and
- Gate A GO assertions: **0**.

Gate A remains `REPAIR` under Tasks149 and 195. Task199 does not alter that
decision.

## 2. Inputs read and preserved

The builder binds the packet registry to the current local copies of:

- Task146 source-level blindness governance;
- Task149 Pivot v2;
- Task153 semantic A/V source-prescreen tooling;
- Task171 EPIC authoring-packet conventions;
- Tasks192 and 195 pilot candidate integrations;
- Task193 semantic-audio discovery;
- Task194 blinded listening packets;
- the current pilot-v4 candidate matrix;
- the EPIC, CaptainCook4D, and NOAA development candidate registries;
- the Task194 packet manifest; and
- the current source-candidate registry.

The packet set does not change any candidate/source registry, source media,
index, machine finding, rights decision, split designation, or Task145
intervention artifact.

## 3. Packet layout and exact counts

Root:

`data/rehearsal_plan/pilot_v4_human_packets/`

Coordinator files:

- `coordinator/packet_registry.json`;
- `coordinator/packet_manifest.json`;
- `coordinator/reviewer_assignments.json`;
- `coordinator/source_exposure_ledger.json`; and
- `coordinator/blank_import_report.json`.

Source-prescreener files:

- six source-specific Task153 directories;
- one nonsemantic inventory per source;
- one deterministic six-interval plan per source;
- one blank Task153 form per source;
- one blank fail-closed Task153 import per source; and
- one empty Task153 exposure ledger per source.

Slot files:

- 12 slot directories, exactly two per source;
- one blank author/verifier form per slot;
- one blank fail-closed Task199 import per slot; and
- four embedded Task194 prerequisite directories for `C01`–`C04`.

Calibration files:

- two synthetic blank calibration packets;
- both explicitly excluded from pilot source, slot, and outcome denominators.

The final tree contains 96 files in 27 directories including the root:

- JSON files: 73;
- Markdown instruction files: 23;
- directories: mode `0700`; and
- files: mode `0600`.

## 4. Coordinator registry and null role assignments

The coordinator registry binds:

- six sources;
- 12 candidate slots;
- exactly two slots per source;
- six Task153 source packets;
- 12 author/verifier forms;
- four Task194 audio-prescreen prerequisites;
- two excluded calibration packets;
- the Task195 matrix file and matrix ID;
- current rights/release boundaries; and
- current development/source-split boundaries.

`coordinator/reviewer_assignments.json` is a Task146-compatible six-role
ledger with:

- 12 families × six roles = 72 rows;
- `assignment_status=DRAFT_NOT_DISTRIBUTABLE`;
- `distribution_authorized=false`;
- 72 null reviewer IDs;
- 72 null assignment timestamps;
- `frozen_at=null`; and
- `assignment_freeze_sha256=null`.

No assignment freeze is attempted. A later coordinator must first bridge all
actual Task153, Task194, and author/verifier exposure, populate genuine
pseudonymous identities, validate source-level conflicts, and separately
obtain distribution authority.

## 5. Source exposure and source-level blindness

`coordinator/source_exposure_ledger.json` contains the exact six source-group
map and both slots for each group. Its pre-distribution snapshot is hash-bound
and contains zero events; its review-event list is empty.

The packet contracts enforce source-level, not merely slot-level, blindness:

- a Task153 prescreener sees source-uniform samples but no candidate question,
  answer, claim, preferred evidence, profile, machine rank, or sibling-slot
  hypothesis;
- a Task194 audio prescreener sees only the blind candidate code and bounded
  adapter requests, not the expected event identity/count, proposed question,
  proposed answer, or proposed profile;
- an author/verifier sees only the assigned slot's candidate hypotheses and
  not the other slot from the same source;
- prescreener and author exposure must be recorded for the complete source
  group; and
- both roles are excluded source-wide from
  `blind_alternative_evidence_finder` and
  `blind_post_adjudication_saturation_auditor`.

Author/verifier forms also hide machine ranks/confidence, validator decisions,
adjudication decisions, and accepted SES material.

## 6. Task153 source-specific semantic prescreens

All six sources now have source-specific Task153 packets, including sources
that previously had only a combined nonsemantic plan or no plan:

1. `P27_101`;
2. `P28_103`;
3. `16_20`;
4. `15_29`;
5. `26_22`; and
6. `cand-052`.

Each plan uses Task153's frozen
`source-uniform-temporal-bin-sha256-jitter-v1` algorithm with six 20-second
intervals. Inventories include only source ID, source-group ID, duration,
content hash, and a non-executing restricted adapter reference. They contain
no semantic labels and no embedded media.

All six checked-in forms are blank:

- `completion_status=not_started`;
- reviewer ID and timestamps are null;
- no sample observation or candidate fact exists;
- no source eligibility decision exists; and
- necessity/H1/H2 remain false.

All six imports return
`SEMANTIC_AV_SOURCE_PRESCREEN_REPAIR`, as required before real human
completion.

## 7. Author/verifier hypothesis boundary

Each of the 12 author/verifier forms carries only role-appropriate,
machine-provisional material for its assigned slot:

- candidate question and answer hypotheses;
- atomic claim hypotheses;
- evidence hypotheses and source-time bounds;
- prospective profile hypothesis;
- open alternative-route risks;
- the current source rights/release boundary; and
- the development-only/fresh-regeneration split boundary.

Every semantic item remains marked as not human validated. Review fields are
empty and cannot contain a checked-in decision. The form fixes false:

- distribution authorization;
- human decision;
- accepted SES creation;
- necessity and minimality;
- H1 and H2;
- human gold;
- future-test eligibility;
- public release authorization; and
- Gate A GO.

The immutable assignment is bound to the complete Task195 candidate-slot
payload hash, the Task195 matrix file hash, the source content hash, and the
source-specific Task153 plan hash.

## 8. Task194 blinded listening order

The four audio-bearing slots use the exact Task194 bindings:

| Task194 code | Pilot-v4 slot | Required order |
|---|---|---|
| `C01` | `PV4-CC15-01` | audio-only → synchronized A/V → recurrence probes |
| `C02` | `PV4-CC16-02` | audio-only → synchronized A/V → recurrence probes |
| `C03` | `PV4-P27-02` | audio-only → synchronized A/V → recurrence probes |
| `C04` | `PV4-P28-01` | audio-only → synchronized A/V → recurrence probes |

The Task194 packet, form, and blank import are copied byte-for-structure into
the corresponding slot prerequisite directory and revalidated against the
Task194 schemas. The author/verifier form records that Task194 completion is a
prerequisite and serializes the same required phase order.

All four Task194 imports remain incomplete
`AUDIO_CANDIDATE_PRESCREEN_PACKETS_REPAIR`; no listening result or audio
authoring eligibility is claimed.

## 9. Excluded calibrations

The two calibration packets are synthetic text-only exercises:

1. recurrent/single-frame/underspecified object shortcut; and
2. speech-dominated interval with faint generic background sound.

They contain blank response fields, null reviewers, no visible expected
decision, no source binding, and no human outcome. Both are explicitly
excluded from:

- the six-source count;
- the 12-slot count;
- profile and structural quotas;
- human acceptance/rejection rates; and
- H-tier or Gate-A accounting.

## 10. Rights, release, and source-split boundaries

Task199 preserves the Task195 per-source boundaries:

- EPIC exact source manifests do not grant human annotation or public
  redistribution authority;
- CaptainCook4D linked operative consent/IRB documents remain unarchived and
  annotation/release remain unauthorized;
- NOAA `cand-052` ownership/license/release and human-annotation authority
  remain unestablished; and
- public release/redistribution remains unauthorized for every packet.

All 12 records remain development-only and future-test-ineligible. Parent
development artifacts are not promoted or copied into a human tier. Fresh
normal-mode regeneration remains required. Source groups may not be split to
evade role-exposure or dataset-split boundaries.

## 11. Fail-closed schemas and imports

Added four Draft 2020-12 schemas:

- `docs/spec/pilot_v4_human_packet_registry_schema.json`;
- `docs/spec/pilot_v4_author_verifier_form_schema.json`;
- `docs/spec/pilot_v4_human_packet_import_schema.json`; and
- `docs/spec/pilot_v4_excluded_calibration_schema.json`.

Added deterministic builder/verifier:

- `tools/pilot_v4_human_packets.py`.

Added focused tests:

- `tests_validation/test_pilot_v4_human_packets.py`.

Blank human workflow imports intentionally fail closed:

- six Task153 imports: `SEMANTIC_AV_SOURCE_PRESCREEN_REPAIR`;
- four Task194 imports:
  `AUDIO_CANDIDATE_PRESCREEN_PACKETS_REPAIR`;
- 12 slot imports: `PILOT_V4_HUMAN_PACKETS_REPAIR`; and
- one coordinator import: `PILOT_V4_HUMAN_PACKETS_REPAIR`.

The separate builder/verifier readiness result is
`PILOT_V4_HUMAN_PACKETS_READY`. It describes only preparation completeness.

## 12. Validation evidence

Builder and tamper self-tests:

```text
python tools/pilot_v4_human_packets.py --self-test
PILOT_V4_HUMAN_PACKETS_READY
```

The self-tests reject:

- author/verifier identity injection; and
- alteration of Task194's blinded inspection order.

Schema meta-validation:

```text
4 Draft 2020-12 Task199 schemas: PASS
```

Focused Task199 tests:

```text
pytest -o addopts='' -q tests_validation/test_pilot_v4_human_packets.py
7 passed
```

Combined Task199/Task194/Task153/Task171 compatibility:

```text
pytest -o addopts='' -q \
  tests_validation/test_pilot_v4_human_packets.py \
  tests_validation/test_audio_candidate_prescreen_packets.py \
  tests_validation/test_semantic_av_source_prescreen.py \
  tests_validation/test_epic_dev_authoring_packets.py
34 passed
```

Focused lint:

```text
python -m ruff check \
  tools/pilot_v4_human_packets.py \
  tests_validation/test_pilot_v4_human_packets.py
All checks passed
```

Focused `py_compile`: pass.

Recursive permission audit:

```text
all directories 0700
all files 0600
```

## 13. Final decision

`PILOT_V4_HUMAN_PACKETS_READY`

The unified packet set is complete and fail closed as a pre-distribution
preparation artifact. Distribution, human review, human decisions, accepted
SESs, H tiers, release, scientific execution, and Gate A GO remain
unauthorized or unestablished.
