# Audio candidate prescreen packets audit

**Task:** 194  
**Date:** 2026-10-10  
**Decision:** `AUDIO_CANDIDATE_PRESCREEN_PACKETS_READY`  
**Artifact class:** reviewer-blind, non-distributable prescreen preparation

## 1. Scope and governing boundary

Task194 prepares portable human listening and semantic-prescreen packets for
the four Task193 pilot-repair candidates:

| Blind code | Source | Focal interval | Coordinator-only Task193 binding |
|---|---|---:|---|
| `C01` | `15_29` | 832–876 s | A-only blender/processor bursts |
| `C02` | `16_20` | 676–748 s | A-only alert-tone clusters |
| `C03` | `P27_101` | 1288–1301 s | V+A wrapper opening |
| `C04` | `P28_103` | 196–224 s | V+A potato peeling/scraping |

The descriptive binding in the last column is documented here for audit. It
does **not** appear in the candidate packet or reviewer form. Reviewers receive
only a blind candidate code, source binding, time bounds, deterministic media
adapter requests, prompts, and a blank form.

This work follows:

- Task153's human semantic source-prescreen concepts and fail-closed import
  behavior;
- Task146's source-group exposure ledger and blind-role exclusions;
- Task171's restricted portable packet and null-identity conventions;
- Task193's exact source hashes, intervals, and machine-expert-provisional
  status; and
- Pivot v2's rule that source-world non-speech audio must not be merely
  speech, music/score, generic noise, a machine label, or a spoken/visible
  substitute.

The packets create no human finding, identity, assignment, decision,
necessity/minimality result, H tier, Gate-A result, media derivative, or
distribution/execution authority.

## 2. Packet layout

The root is:

`data/rehearsal_plan/audio_candidate_prescreen_packets_v1/`

Each of `candidates/C01` through `candidates/C04` contains:

- `candidate_packet.json`;
- `reviewer_form.json`;
- `blank_import.json`; and
- a short `README.md`.

Coordinator artifacts are:

- `coordinator/packet_manifest.json`;
- `coordinator/blank_prescreener_exposure_ledger.json`;
- `coordinator/source_exposure_ledger.json`; and
- `coordinator/reviewer_assignments.json`.

Calibration artifacts are:

- `calibrations/calibration_01.json` — generic utensil impacts; and
- `calibrations/calibration_02.json` — a speech-dominated interval.

All packet directories are mode `0700`; all packet files are mode `0600`.

## 3. Deterministic bounded media-adapter requests

No media is embedded. Every request has:

- an existing restricted adapter reference;
- the exact source SHA-256;
- explicit start and end seconds;
- a recomputed bounded duration;
- `extract_media=false`;
- `persist_media=false`; and
- `execute=false`.

Each candidate has exactly five requests in a fixed order:

1. the focal interval as audio-only;
2. the same focal interval as synchronized A/V; and
3. three bounded audio-only recurrence probes.

The paired first and second requests have identical source and interval
bindings. Each individual request is at most 90 seconds. The builder rejects
an invalid bound, source overflow, hash mismatch, phase/order change, duration
mismatch, or media/execution flag change.

The recurrence probes are coordinator-selected bounded inspections based on
Task193's recurrence audit and existing full-timeline retrieval evidence. They
are not a full-source recurrence search and the form fixes
`full_source_closure_claimed=false`.

## 4. Reviewer blindness and inspection order

Candidate packets deliberately omit:

- Task193 fact IDs;
- retrieval concept labels;
- CLAP/model identities;
- ranks, similarities, margins, confidence, or other scores;
- proposed questions;
- proposed answers;
- proposed modality profiles; and
- expected candidate-specific event identities or counts.

The review order is mandatory:

1. complete the audio-only focal observation and count;
2. only then inspect synchronized A/V and ground the source-world fact; and
3. only then inspect recurrence probes.

The completed form must attest this order and supply phase timestamps.
Import rejects a missing attestation, inverted timestamps, or failure to
attest that machine semantics were hidden.

Calibration files are generic protocol examples, not source media or candidate
answer keys. The packet contract states that expected calibration outputs are
not visible during candidate review.

## 5. Human questions and fail-closed eligibility

The reviewer form requires:

- descriptions of concrete non-speech events;
- a distinct-episode count and repeated-subevent count, with exact/range/not
  countable modes;
- a tentative audio-only source-world fact;
- speech and music presence/dominance;
- synchronized A/V grounding and a second count;
- an explanation when vision changes the count;
- whether audio plausibly changes answerability;
- speech, music, vision, and transcript/caption/OCR/narration substitution
  risk;
- bounded recurrence findings and authoring implications;
- privacy and safety review; and
- `READY`, `REPAIR`, or `NO_GO` authoring eligibility.

`READY` is fail-closed. It requires a confirmed source-world non-speech event,
an audio answerability signal, no speech or music dominance, no unresolved
high/critical privacy or safety concern, and an authoring constraint whenever
high/full substitution remains. `REPAIR` requires an explicit repair action.
`NO_GO` is preserved even when other validation errors exist.

The only import tokens are:

- `AUDIO_CANDIDATE_PRESCREEN_PACKETS_READY`;
- `AUDIO_CANDIDATE_PRESCREEN_PACKETS_REPAIR`; and
- `AUDIO_CANDIDATE_PRESCREEN_PACKETS_NO_GO`.

Every checked-in blank form imports as `REPAIR` with
`completion_status=incomplete`. This is intentional: packet readiness is not
a human candidate decision.

## 6. Source-level exposure and blind-role bar

A completed form requires a stable pseudonymous reviewer ID, training
attestation, first-exposure timestamp, completion timestamp, and source
content exposure attestation. Import emits one source-level event containing:

- reviewer ID;
- source and source-group IDs;
- candidate code;
- all adapter request IDs;
- source-content and candidate-semantic-fact exposure; and
- both blind-role exclusions.

The bridge converts this into Task146-compatible `external_prior_work` in the
construct-validity pre-distribution source ledger, using conservative
`source_content` and `preferred_evidence` exposure categories. It also rebinds
the draft assignment ledger to the updated snapshot hash.

The bridge rejects:

- a frozen assignment ledger;
- a construct ledger with review events;
- mismatched source-group maps; and
- an unknown source group.

The existing Task146 conflict checker then bars the prescreener from:

- `blind_alternative_evidence_finder`; and
- `blind_post_adjudication_saturation_auditor`

for the entire exposed source group. A focused test verifies both exclusions.

## 7. Null identities, assignments, decisions, and H tiers

The checked-in coordinator artifacts contain:

- reviewer identities: 0;
- populated reviewer assignments: 0;
- prescreener exposure events: 0;
- human decisions: 0;
- human reviews: 0; and
- H1/H2 assignments: 0/0.

The six-role assignment matrix is
`DRAFT_NOT_DISTRIBUTABLE`, has null reviewer IDs and timestamps, has no freeze
hash, and has `distribution_authorized=false`.

Forms and imports fix all of the following false:

- necessity;
- minimality;
- H1;
- H2;
- human gold; and
- Gate-A result/eligibility.

## 8. Calibration examples

The generic utensil-impact calibration teaches reviewers not to infer a
specific ingredient, recipe step, or outcome from nonspecific metallic
impacts, and to assess visual substitution and recurrence before authoring.

The speech-dominated calibration teaches that intelligible speech with a faint
background click or hum does not pass the non-speech-audio screen. It directs
reviewers to mark speech dominance and high transcriptive substitution risk.

Both are synthetic textual examples. They are not human decisions, source
media, machine labels, proposed answers, or H-tier records.

## 9. Schemas, tooling, and validation

Added schemas:

- `docs/spec/audio_candidate_prescreen_packet_schema.json`;
- `docs/spec/audio_candidate_prescreen_form_schema.json`; and
- `docs/spec/audio_candidate_prescreen_import_schema.json`.

Added tooling:

- `tools/audio_candidate_prescreen_packets.py`.

Added tests:

- `tests_validation/test_audio_candidate_prescreen_packets.py`.

Validation completed:

- deterministic checked-in generation and verifier: pass;
- all three Draft 2020-12 schemas: pass;
- focused Task194 tests: 10 passed;
- combined Task194/Task153/Task171 tests: 27 passed;
- Ruff: pass;
- `py_compile`: pass;
- blank import fail-closed behavior: pass;
- packet/form hash and interval tamper rejection: pass;
- speech-dominance and inspection-order fail-closed checks: pass;
- source-ledger bridge and both blind-role conflict checks: pass; and
- recursive restricted permissions: pass.

## 10. Final decision

`AUDIO_CANDIDATE_PRESCREEN_PACKETS_READY`

READY means that the four blank, deterministic, reviewer-blind prescreen
packets and their governance controls are complete and fail closed. It does
not mean any Task193 candidate has passed human listening, semantic
prescreening, source-authoring eligibility, recurrence closure, necessity,
minimality, construct validation, Gate A, rights/release review, or scientific
acceptance.
