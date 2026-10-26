# Real-video rehearsal acceptance and rejection criteria

**Version:** 1.1.0  
**Prepared:** 2026-09-07  
**Applies to:** the 4–5 video / 12-family real rehearsal package  
**Normative precedence:** project charter, accepted decision log, benchmark
specification, annotation guideline, schemas, and semantic validator

This document authorizes no media download, crawling, playback, or real
annotation. Those actions remain gated by the project charter and asset-level
review.

## 1. Decision vocabulary

| Value | Meaning |
|---|---|
| `PROVISIONAL_NOT_APPROVED` | Metadata-only candidate; no approval or media action authorized |
| `unknown_hold` | Fail-closed; cannot pass acquisition, annotation, or release gate |
| `rejected` | Candidate/family cannot proceed under the current version |
| `quarantined` | Removed from active use pending a reason-coded new version |
| `accepted` | Human and machine acceptance criteria pass; not yet immutable |
| `frozen` | Accepted object and all referenced manifests, backend artifacts, and trajectories are immutable |

Planning priority, an official dataset release, a public URL, or an existing
benchmark annotation never constitutes approval.

## 2. Candidate-stage acceptance

### 2.1 Dataset reconciliation gate

A candidate advances only if all are true:

1. official release locator is recorded;
2. immutable revision/commit is recorded;
3. item/video/source ID is recorded;
4. upstream dataset and source-video provenance are recorded;
5. metadata duration is plausibly within 1,200–5,400 seconds;
6. the item is a complete source video, not merely a clip;
7. source duplication/re-upload relationships are checked;
8. likely audio and modality properties are labeled as provisional;
9. official access method and terms are identified;
10. no field was guessed to make the row look complete.

The record must also preserve canonical upstream namespace/ID, parent asset,
lineage relation, complete-source availability, source-time join status,
`checked_against_scope`, and dedup disposition. An annotation row, package
sample, clip, or filename lead is not a complete source. A short SHA, file blob
revision, or mutable branch is not an immutable release revision.

**Reject codes:** `RECON_NO_OFFICIAL_ITEM_ID`, `RECON_NO_PINNED_REVISION`,
`RECON_UPSTREAM_PROVENANCE_UNKNOWN`, `RECON_CLIP_NOT_SOURCE_VIDEO`,
`RECON_DUPLICATE_SOURCE`, `RECON_DURATION_OUT_OF_RANGE`,
`RECON_GUESSED_OR_UNVERIFIABLE`.

### 2.2 Rights/access gate

An asset advances to transfer only if:

- the manifest validates against acquisition-manifest schema 0.2.0;
- acquisition authority and method are affirmative;
- local processing is affirmative;
- derivative release is affirmative for planned derivatives;
- annotation release is affirmative;
- transcript release is affirmative when transcripts will be used or released;
- raw-media release is affirmative for
  `PUBLIC_CORE_FIXED_BACKEND_TRIPLETS`;
- no applicable decision is `unknown_hold`;
- exact authority evidence and snapshot hashes are present;
- privacy/safety and embedded-component reviews pass;
- named reviewers and dates are present.

Controlled assets may advance only as
`EXTERNAL_COMPATIBILITY_UNPOOLED` when their terms permit the planned controlled
evaluation. They never fill a public-core quota.

**Reject or hold codes:** `RIGHTS_UNKNOWN_HOLD`, `RIGHTS_NO_ACQUISITION_AUTHORITY`,
`RIGHTS_NO_PROCESSING_AUTHORITY`, `RIGHTS_NO_DERIVATIVE_RELEASE`,
`RIGHTS_NO_ANNOTATION_RELEASE`, `RIGHTS_NO_TRANSCRIPT_RELEASE`,
`RIGHTS_NO_RAW_RELEASE_PUBLIC_CORE`, `RIGHTS_COMPONENT_UNRESOLVED`,
`RIGHTS_PRIVACY_SAFETY_FAIL`, `ACCESS_NO_AUTHORIZED_ROUTE`,
`ACCESS_TERMS_INCOMPATIBLE`.

### 2.3 Technical/audio gate

This gate begins only after Stage 2 / Gate A has authorized transfer for the
exact asset and rendition. Stage 1 metadata triage never permits acquisition,
playback, probing, or content inspection.

An authorized asset passes only if:

- probed duration is 1,200–5,400 seconds inclusive;
- complete video decodes with stable source time;
- original audio exists and decodes;
- audio is usable for the slot(s), with intelligible speech where speech is
  required and identifiable non-speech events where ambient is required;
- source and stream hashes are recorded;
- no unrecoverable corruption, severe drift, or missing section exists;
- at least two plausible evidence clusters exist;
- a far slot has candidate clusters separated by at least 600 seconds;
- a near slot has distinct required clusters separated by at least 30 seconds
  but less than 600 seconds;
- obvious title, metadata, subtitle, or burned-in-text leakage does not defeat
  every intended question;
- the source is distinct from other selected assets.

**Reject codes:** `TECH_SILENT`, `TECH_NO_VIDEO`, `TECH_AUDIO_UNUSABLE`,
`TECH_SPEECH_UNINTELLIGIBLE`, `TECH_NO_AMBIENT_CONTENT`, `TECH_TOO_SHORT`,
`TECH_TOO_LONG`, `TECH_CORRUPT`, `TECH_TIMESTAMP_UNSTABLE`,
`TECH_NO_TEMPORAL_SEPARATION`, `TECH_DUPLICATE_ASSET`,
`TECH_NO_SLOT_YIELD`.

## 3. Family authoring acceptance

### 3.1 Question and answer

Accept only if:

- the answer is expressible as registered atomic claims;
- the question is answerable from the source;
- title, metadata, common knowledge, or prohibited modality is insufficient;
- wording is identical across `CLEAN`, `BLOCKED`, and `RESTORED`;
- the required modality, hop count, and temporal class match the assigned slot;
- no condition, intervention, or expected missingness is leaked.

For this rehearsal, **one-hop** means one controlled inference node is sufficient
for the target claim; **two-hop** means a chain or composition of at least two
controlled inference nodes is necessary. Merely citing two clips is not
automatically two-hop.

**Reject codes:** `QUESTION_METADATA_ANSWERABLE`,
`QUESTION_COMMON_KNOWLEDGE`, `QUESTION_WRONG_MODALITY`,
`QUESTION_WRONG_HOP_COUNT`, `QUESTION_WRONG_TEMPORAL_CLASS`,
`QUESTION_CONDITION_LEAK`, `QUESTION_UNSTABLE_ACROSS_STATES`,
`QUESTION_NO_STRUCTURED_ANSWER`.

### 3.2 Evidence and graph

Accept only if:

- all evidence intervals are finite, within source bounds, and have end after
  start;
- modality is one of `vision`, `speech`, `ambient`;
- burned-in text is `vision`;
- ASR/subtitles are speech-derived and not independent visual evidence;
- stream IDs, hashes, asset IDs, and transformations resolve;
- observations are atomic and provenance-bearing;
- all required claims have complete support derivations;
- only registered hop types are used;
- the graph is acyclic;
- all IDs and references pass semantic rules `ID-*`, `TIME-*`, `PROV-*`, and
  `GRAPH-*`.

**Reject codes:** `EVIDENCE_OUT_OF_BOUNDS`, `EVIDENCE_NON_ATOMIC`,
`EVIDENCE_MODALITY_MISLABELED`, `EVIDENCE_PROVENANCE_INVALID`,
`GRAPH_DANGLING_REFERENCE`, `GRAPH_CYCLE`, `GRAPH_INCOMPLETE_DERIVATION`.

## 4. Alternative search and SES acceptance

### 4.1 Full-source alternative search

The alternative finder must:

- be blinded to the author's preferred SES before the first full-source pass;
- inspect the complete source;
- log every plausible alternate route;
- identify duplicates and deterministic derivatives;
- leave no material source region unresolved;
- state whether exhaustive enumeration is credible.

If exhaustive search is not credible, reject the family.

### 4.2 Accepted SES

Every accepted minimal SES must:

1. cover at least one required claim;
2. have a complete induced support derivation;
3. be demonstrated satisfiable;
4. become insufficient for at least one listed required claim when any evidence
   member is removed;
5. not be a strict evidence-set superset of another accepted SES for the same
   claim set;
6. be demonstrated by validator A and validator B.

For slots marked `required_at_least_1_alternative_ses`, accept only if at least
two distinct accepted minimal SESs cover the target claim set. Distinctness
requires a semantically separate evidence route, not a copy, transcript/ASR
encoding pair, alternate container, or deterministic derivative.

**Reject codes:** `ALT_SEARCH_NOT_BLIND`, `ALT_SEARCH_NOT_FULL_SOURCE`,
`ALT_SEARCH_NOT_EXHAUSTIVE`, `ALT_SES_REQUIRED_BUT_ABSENT`,
`SES_UNSATISFIABLE`, `SES_NOT_MINIMAL`, `SES_STRICT_SUPERSET`,
`SES_INCOMPLETE_DERIVATION`, `SES_NOT_TWO_VALIDATORS`.

## 5. Necessity and intervention acceptance

### 5.1 Necessity group

A necessity group passes only if:

- it targets required claims;
- every member resolves to an evidence unit;
- it intersects every accepted SES for the target claims;
- removing all members breaks every target claim;
- its required modalities are induced from all accepted alternatives;
- all derived leaks are enumerated and controlled.

**Reject codes:** `NEC_NO_TARGET_REQUIRED_CLAIM`,
`NEC_MEMBER_UNRESOLVED`, `NEC_NOT_HITTING_SET`,
`NEC_REMOVAL_DOES_NOT_BREAK_TARGET`, `NEC_MODALITY_INCORRECT`,
`NEC_DERIVED_LEAK_SURVIVES`.

### 5.2 `CLEAN`

Accept only if:

- no blocking/restoration intervention is active;
- at least one accepted SES is reachable;
- source and accessible evidence are sufficient;
- the common backend and budget are frozen.

### 5.3 `BLOCKED`

Accept only if:

- exactly one mechanism is used:
  `necessity_group_withholding` or `modality_channel_outage`;
- every member and deterministic leak of the chosen group is inaccessible, or
  exactly the declared necessary channel/route is disabled;
- no accepted SES remains reachable;
- the underlying source remains sufficient;
- question, graph, source, indexes, rank order in unaffected channels, costs,
  messages, and budget are unchanged;
- no answer-bearing redaction, condition label, timing artifact, or distinctive
  error string is introduced.

### 5.4 `RESTORED`

Accept only if:

- before the trigger it is state-equivalent to `BLOCKED`;
- the trigger is a predeclared fixed call index or `get_channel_status`;
- the trigger does not depend on model identity, answer content, correctness,
  rationale, or hidden state;
- restoration reverses exactly the registered blocking operation;
- no new semantic evidence is introduced;
- at least one accepted SES becomes reachable within the unchanged remaining
  budget;
- clean-equivalent restored outputs preserve payload/result IDs, ordering,
  hashes, and costs unless a registered semantically empty wrapper is required.

**Reject codes:** `INT_MULTIPLE_MECHANISMS`, `INT_BLOCKED_SES_SURVIVES`,
`INT_NONISOLATED_CHANGE`, `INT_ANSWER_BEARING_ARTIFACT`,
`INT_SOURCE_MADE_INSUFFICIENT`, `REST_PRETRIGGER_MISMATCH`,
`REST_MODEL_DEPENDENT_TRIGGER`, `REST_CHANGES_BUDGET`,
`REST_ADDS_SEMANTIC_EVIDENCE`, `REST_NOT_EXACT`,
`REST_NO_REACHABLE_SES`.

## 6. Human trajectory acceptance

Both validators must independently:

1. produce a supported answer in `CLEAN` using an accepted SES;
2. not support the blocked target in `BLOCKED`;
3. diagnose the evidence as present in the source but inaccessible;
4. recover a supported answer in `RESTORED`;
5. remain within the common budget;
6. emit schema-valid and semantically valid trajectories with resolving
   citations.

The family fails if either validator supports the blocked target, fails to
recover after restoration, or requires a non-predeclared route.

**Reject codes:** `VAL_CLEAN_UNSOLVED`, `VAL_BLOCKED_TARGET_SUPPORTED`,
`VAL_BLOCKED_DIAGNOSIS_WRONG`, `VAL_RESTORED_UNSOLVED`,
`VAL_BUDGET_EXCEEDED`, `VAL_CITATION_INVALID`,
`VAL_TRAJECTORY_SCHEMA_FAIL`, `VAL_TRAJECTORY_SEMANTIC_FAIL`.

## 7. Shortcut and artifact acceptance

Run all applicable audits:

- question-only;
- metadata-only;
- transcript-only;
- silent-video;
- ambient-only;
- temporal shuffle;
- snippet-only;
- duplicate evidence;
- contamination;
- intervention artifact.

An audit is **critical** when passing it would make the assigned modality,
temporal order, or intervention unnecessary. A critical failure rejects the
family unless a versioned repair changes the question/graph and repeats
alternative search, necessity testing, and validation.

Examples:

- a vision slot fails if transcript-only solves it;
- a speech slot fails if silent video solves it;
- an ambient slot fails if speech transcript alone reveals the event;
- a far/two-hop slot fails if one short snippet solves it;
- any slot fails if a classifier can identify `BLOCKED` from an artifact rather
  than evidence access.

**Reject codes:** `SHORTCUT_QUESTION_ONLY`, `SHORTCUT_METADATA_ONLY`,
`SHORTCUT_TRANSCRIPT_ONLY`, `SHORTCUT_SILENT_VIDEO`,
`SHORTCUT_AMBIENT_ONLY`, `SHORTCUT_TEMPORAL_SHUFFLE`,
`SHORTCUT_SNIPPET_ONLY`, `SHORTCUT_DUPLICATE_EVIDENCE`,
`SHORTCUT_CONTAMINATION`, `SHORTCUT_INTERVENTION_ARTIFACT`.

## 8. Machine gates

Before `accepted`:

- annotation and review templates are complete;
- episode family validates against `episode_schema.json`;
- both trajectories validate against `trajectory_schema.json`;
- all required semantic validator rules pass;
- pair-diff isolation passes;
- deterministic replay passes.

Before `frozen`:

- all referenced manifests, source/stream hashes, backend version, index hash,
  costs, prompts/configuration, family object, and trajectories are immutable;
- no applicable `unknown_hold` remains;
- all repair actions are closed;
- adjudicator signs the final version.

Schema-valid but semantically invalid families are rejected.

## 9. Package-level acceptance

The rehearsal package is **complete** only if:

- 4–5 source-disjoint videos were selected through the funnel;
- no selected video supplies more than three retained families;
- all 12 slot records have a final disposition;
- every retained family has exactly three states;
- at least one retained family exists in each modality stratum;
- at least one retained one-hop and one retained two-hop family exist;
- at least one retained near and one retained far family exist;
- both mechanisms have retained families;
- at least one retained family has an accepted alternative SES;
- every retained family meets all family-level criteria;
- every rejection and substitution is retained in the audit trail;
- every timing field is completed or reason-coded `not_applicable`;
- no provisional candidate is reported as approved.

The modality matrix is **planned coverage**, not achieved coverage. A modality
cell counts as achieved only for an accepted family after authorized stream
verification and human evidence review establish the required modality.

The preferred balanced target is all 12 accepted slots. If fewer pass, report:

`accepted_count / 12`, by slot and reason. A partial result is a valid rehearsal
outcome and does not authorize imputation.

## 10. Measured timing fields

Use active person-minutes, not rounded person-days:

| Field | Start | Stop | Include |
|---|---|---|---|
| `source_intake_minutes` | Candidate reconciliation begins | Pinned row submitted | Release/item/provenance lookup and duplicate check |
| `rights_access_review_minutes` | Rights reviewer opens record | Gate decision signed | Authority, terms, component, and transfer review |
| `technical_audio_review_minutes` | Authorized probe begins | Technical disposition submitted | Probe, playback sampling, audio and timestamp checks |
| `question_authoring_minutes` | Author starts question work | Question/answer draft submitted | Question and answer specification |
| `claim_graph_minutes` | Claim decomposition begins | Graph draft submitted | Claims, hops, edges |
| `evidence_unit_minutes` | Evidence marking begins | Evidence draft submitted | Intervals, modality, provenance |
| `alternative_search_minutes` | Blind full-source search begins | Route log locked | Complete-source search and candidate route logging |
| `necessity_testing_minutes` | SES tests begin | Necessity recommendation submitted | Satisfiability, leave-one-out, hitting set, leaks |
| `intervention_construction_minutes` | Family construction begins | Triplet submitted | Clean/blocked/restored and pair-diff setup |
| `validator_a_minutes` | Validator A opens blind packet | Three-state result submitted | All A trajectory work |
| `validator_b_minutes` | Validator B opens blind packet | Three-state result submitted | All B trajectory work |
| `adjudication_minutes` | Adjudication packet opens | Decision signed | Review, meetings, and decision writing |
| `semantic_lint_minutes` | Machine/human lint begins | Report submitted | Schema and semantic failure triage |
| `replay_repair_minutes` | Replay or repair begins | Replay disposition | Reproduction and approved repair |
| `rejection_minutes` | Rejection analysis begins | Rejection form signed | Final reason coding and salvage/substitution handoff |
| `blocked_wait_hours` | Work is externally blocked | Block resolves | Access, reviewer, tooling, or approval wait; exclude active work |
| `elapsed_calendar_hours` | First work timestamp | Final disposition | End-to-end wall time |

`total_person_minutes` is the sum of active minute fields, not elapsed time.
Record rework in the field where it occurred and preserve attempt/version IDs.

## 11. Required rehearsal reporting

Report counts and distributions for:

- candidates by dataset family and funnel stage;
- rights/access, technical, construct, validator, shortcut, and machine
  rejections;
- videos selected and families accepted per video;
- active labor and waiting time by stage;
- accepted SES count per family;
- alternative-SES presence;
- number and size of necessity groups;
- evidence temporal separation;
- modality and hop agreement;
- validator state-outcome agreement;
- initial and final pair-isolation, schema, semantic, and replay rates;
- substitutions, repeated attempts, and quarantines.

No percentage is reported without numerator and denominator. Rejected-candidate
labor is part of the cost estimate and must not be discarded.
