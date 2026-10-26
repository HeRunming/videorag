# Untouched test group ledger v1

**Date:** 2026-10-14  
**Freeze decision:** `READY`  
**Final marker:** `UNTOUCHED_TEST_GROUP_LEDGER_V1_READY`  
**Controlled test construction:** `LOCKED`  
**Acquisition / rights readiness:** `REPAIR`

## Decision

This ledger prospectively freezes **12** untouched-test source groups before semantic review or model-guided authoring. They span **6** dataset/publisher production strata. Every row is a **conditional reserve**: the ledger does not claim that media was acquired, rights were cleared, semantic review was performed, or any H2 family exists.

The freeze is `READY` because exact participant/session/production identities and full closures can be sealed honestly. Execution remains `REPAIR` and locked because current access registries do not authorize the required acquisition and processing.

## Frozen groups

| Slot | Source group | Exact object/session | Dataset or production lineage | Exposure state | Rights/access |
|---|---|---|---|---|---|
| TS-01 | `P01` | `P01_101` | `EPIC_KITCHENS_100` | `RESERVED_UNTOUCHED_METADATA_ONLY` | `REPAIR` |
| TS-02 | `P02` | `P02_108` | `EPIC_KITCHENS_100` | `RESERVED_UNTOUCHED_METADATA_ONLY` | `REPAIR` |
| TS-03 | `P04` | `P04_123` | `EPIC_KITCHENS_100` | `RESERVED_UNTOUCHED_METADATA_ONLY` | `REPAIR` |
| TS-04 | `cc4d_p04_e05` | `25_22` | `CAPTAINCOOK4D` | `RESERVED_UNTOUCHED_METADATA_ONLY` | `REPAIR` |
| TS-05 | `cc4d_p06_e02` | `16_18` | `CAPTAINCOOK4D` | `RESERVED_UNTOUCHED_METADATA_ONLY` | `REPAIR` |
| TS-06 | `cc4d_p07_e02` | `16_23` | `CAPTAINCOOK4D` | `RESERVED_UNTOUCHED_METADATA_ONLY` | `REPAIR` |
| TS-07 | `assembly101_p9056` | `nusar-2021_action_both_9056-b08a_9056_user_id_2021-02-22_141934` | `ASSEMBLY101` | `RESERVED_UNTOUCHED_METADATA_ONLY` | `REPAIR` |
| TS-08 | `assembly101_p9083` | `nusar-2021_action_both_9083-c03a_9083_user_id_2021-02-16_114344` | `ASSEMBLY101` | `RESERVED_UNTOUCHED_METADATA_ONLY` | `REPAIR` |
| TS-09 | `assembly101_p9055` | `nusar-2021_action_both_9055-a07_9055_user_id_2021-02-09_092331` | `ASSEMBLY101` | `RESERVED_UNTOUCHED_METADATA_ONLY` | `REPAIR` |
| TS-10 | `EC-USGS-SHIFT-CURVES` | `USGS-media-video-developing-and-applying-shift-curves-using-grsat` | `USGS_PUBLIC_MEDIA` | `RESERVED_UNTOUCHED_IDENTITY_ONLY` | `HOLD_PENDING_EXACT_ROUTE_AND_RIGHTS_REPAIR` |
| TS-11 | `EC-NASA-TO-THE-RESCUE` | `NASA+-jpl-to-the-rescue` | `NASA_JPL_DOCUMENTARY` | `RESERVED_UNTOUCHED_IDENTITY_ONLY` | `HOLD_PENDING_EXACT_ROUTE_AND_JPL_COMPONENT_AUTHORITY` |
| TS-12 | `EC-NARA-CITY-UNDER-ICE` | `NAID:2569752` | `NARA_ARCHIVAL_FILM` | `RESERVED_UNTOUCHED_IDENTITY_ONLY` | `HOLD_PENDING_IDENTITY_DURATION_RESTRICTION_AND_ROUTE` |

Lineage composition:

- `ASSEMBLY101`: 3 group(s)
- `CAPTAINCOOK4D`: 3 group(s)
- `EPIC_KITCHENS_100`: 3 group(s)
- `NARA_ARCHIVAL_FILM`: 1 group(s)
- `NASA_JPL_DOCUMENTARY`: 1 group(s)
- `USGS_PUBLIC_MEDIA`: 1 group(s)

## Group closure

A frozen group includes the complete participant/session/production lineage and all media, synchronized or alternate views, annotations, labels, transcripts, clips, features, model artifacts, benchmark artifacts, and future derivatives.

Participant blocks are split-level closures. An unviewed clip, alternate camera, encode, transcript, label file, embedding, or future derivative cannot be separated from a contaminated participant or production lineage.

## Before controlled test construction

Only these technical preflights are permitted:

- `RIGHTS_AND_ACCESS_DOCUMENT_REVIEW`
- `BYTE_COUNT_AND_OBJECT_IDENTITY_CHECK`
- `CONTAINER_STREAM_INVENTORY_WITHOUT_CONTENT_INSPECTION`
- `WALL_CLOCK_DURATION_CHECK`
- `CRYPTOGRAPHIC_HASH_COMPUTATION_AND_COMPARISON`

The exhaustive forbidden set includes:
- `CANDIDATE_MINING_OR_YIELD_ESTIMATION`
- `LEARNED_RETRIEVAL_OR_EMBEDDING_INDEX_INSPECTION`
- `ASR_OCR_AUDIO_TAGGING_OR_TRANSCRIPT_GENERATION`
- `CLAP_CLIP_SIGLIP_OR_OTHER_LEARNED_RANKING`
- `LLM_VLM_SUMMARIZATION_OR_MODEL_GUIDED_AUTHORING`
- `PROMPT_TUNING_PROMPT_SELECTION_OR_EVALUATION_DESIGN_USING_THE_GROUP`
- `HUMAN_SEMANTIC_PRESCREEN_WATCHING_OR_LISTENING`
- `OPENING_TRANSCRIPTS_CAPTIONS_NARRATIONS_LABELS_QA_OR_SEMANTIC_TIMESTAMPS`
- `QUESTION_ANSWER_CLAIM_EVIDENCE_SHORTCUT_MODALITY_HOP_OR_DISTANCE_AUTHORING`
- `DEVELOPMENT_OR_CALIBRATION_MODEL_RUNS_ON_ANY_GROUP_ARTIFACT`

This explicitly forbids candidate mining, learned-retrieval inspection, ASR, CLAP/CLIP/SigLIP ranking, prompt tuning, and human semantic prescreening.

## Exposure states and custodian-only reveal

The initial states are metadata-only or identity-only untouched reservation. Technical preflight may advance a row only to `TECHNICALLY_PREFLIGHTED_UNTOUCHED`. Any semantic/model exposure before a separately authorized unlock moves the full closure to `CONTAMINATED_INVALID_FOR_UNTOUCHED_TEST`.

Playable media, authenticated routes, semantic metadata, annotations, transcripts, features, retrieval indexes, and model outputs remain custodian-only. A technical reviewer may receive only the minimum rights, byte, stream, duration, and hash facts. Development staff receive no pre-unlock reveal.

## Split lock

- Algorithm: `SHA-256`
- Split-lock SHA-256: `abec2314728f48cc9a4bf7a91145fc1610e197f06ff02d5a32852c310d74f4f4`
- The hash binds the ordered 12 group hashes plus governance, custody, replacement, exclusion, and contamination policies.
- Any mutation requires a versioned addendum and recomputed group and split hashes before further access.

## Replacement policy

Replacement is allowed only before semantic/model exposure and only from the predeclared untouched queue for the same dataset/production lineage. It must preserve 12 occupied slots and the frozen lineage counts. Candidate yield, perceived difficulty, model behavior, or H2 outcome can never trigger a replacement.

If no same-lineage untouched reserve survives, the slot remains vacant and the ledger becomes `REPAIR`; another convenient lineage cannot silently backfill it.

## Explicit exclusions

P23/P27/P28, CaptainCook4D wave0 development groups, assigned development/calibration groups, all NOAA `cand-*` groups, and any reserve after mining or semantic/model exposure are test-ineligible with their complete closures.

- `P27` / `EPIC:P27`: `TRAIN_DEVELOPMENT_AND_ALREADY_TOUCHED`
- `P28` / `EPIC:P28`: `TRAIN_DEVELOPMENT_AND_ALREADY_TOUCHED`
- `P23` / `EPIC:P23`: `DEVELOPMENT_ONLY_DIAGNOSTIC_AND_ALREADY_TOUCHED`
- `cc4d_p01_e08` / `CC4D:P01`: `CAPTAINCOOK4D_WAVE0_DEVELOPMENT_GROUP`
- `cc4d_p02_e02` / `CC4D:P02`: `CAPTAINCOOK4D_WAVE0_DEVELOPMENT_GROUP`
- `cc4d_p03_e03` / `CC4D:P03`: `CAPTAINCOOK4D_WAVE0_DEVELOPMENT_GROUP`
- `cc4d_p05_e07` / `CC4D:P05`: `DEV_CALIBRATION_ASSIGNMENT_AND_TECHNICAL_PREFLIGHT_HISTORY`
- `P12` / `EPIC:P12`: `DEV_CALIBRATION_ASSIGNMENT`
- `assembly101_p9051` / `ASSEMBLY101:9051`: `DEV_CALIBRATION_ASSIGNMENT`
- `SG-OXFORD-QM-001` / `OXFORD_QM:LECTURE01`: `TRAIN_DEVELOPMENT_SOURCE`
- `SG-OXFORD-DHL-CONSCIOUSNESS` / `OXFORD_DHL:CONSCIOUSNESS`: `TRAIN_DEVELOPMENT_SOURCE`
- `SG-MIT-RES12-003-L01` / `MIT_RES12:LECTURE01`: `DEV_CALIBRATION_SOURCE`
- `SG-YALE-PHYS200-L01` / `YALE_PHYS200:LECTURE01`: `DEV_CALIBRATION_SOURCE`

## Contamination events

The committed event list is empty: no known contamination event is recorded by this ledger. This is not proof of acquisition, rights, or H2. Every future event must identify the actor/tool, group and closure, exposure class, visible semantic fields, disposition, and replacement addendum.

A contamination event invalidates the complete participant and production closure. The custodian must seal access, append the event, apply only the same-lineage replacement rule, and recompute the split lock.

## Audit result

- Frozen groups: **12**
- Distinct lineages: **6**
- Known contamination events: **0**
- Audit: **PASS**

`UNTOUCHED_TEST_GROUP_LEDGER_V1_READY`
