# Direct LongVideoBench candidate expansion review

**Task:** 50  
**Evidence/ranking operation date:** 2026-09-07  
**Integration/shortlist decision date:** 2026-09-08  
**Execution constraint:** local files only; network disabled  
**Decision effect:** technical shortlist update only; no authorization

## 1. Inputs and integrity

The review used only these immutable local snapshots at
`longvideobench/LongVideoBench-Meta@cdf3444602208c95f453e7683583a077ce38ddbf`:

| Split | File | SHA-256 | Rows | Metadata-only schema |
|---|---|---|---:|---|
| validation | `data/hf_recon/snapshots/hf_longvideobench_LongVideoBench-Meta_cdf3444602208c95f453e7683583a077ce38ddbf_validation.parquet` | `5f370287edbfb9875562b116686d50208d0d40615f5b407f970448868b6bc108` | 1,337 | yes |
| test | `data/hf_recon/snapshots/hf_longvideobench_LongVideoBench-Meta_cdf3444602208c95f453e7683583a077ce38ddbf_test.parquet` | `9015fc7f9e83e4a6479fa533c2c7df8c42a9bab67a7e01be6320262e249a1bec` | 5,341 | yes |

The 16-column schema contains identifiers, relative media/subtitle paths,
multiple-choice text, duration/category metadata, and subtitle start offset.
It has no media-bearing or binary field.

## 2. Aggregation and hard filter

Rows were grouped by exact `video_id`. A source was eligible only if:

- its canonical ID did not occur in the existing candidate pool;
- its aggregate had one exact duration in the inclusive range 1,200–5,400 s;
- all rows belonged to one split;
- the relative video path was exactly `<video_id>.mp4`;
- the immutable metadata revision was the supplied revision; and
- the proposed record retained `PROVISIONAL_NOT_APPROVED`, unverified media,
  audio, speech, and ambient states, and `unknown_hold` source-media rights.

The two Parquets contained 3,761 unique videos. The hard filter left 459 unseen
eligible IDs. The eligible set had 458 three-row aggregates and one two-row
aggregate. All 459 had a subtitle path, so the subtitle-path preference was
satisfied by both selected candidates rather than being exclusive to one.

## 3. Deterministic profiles

The speech/cross-modal profile sorted by subtitle presence, topic novelty,
question-category novelty, number of rows with explicit subtitle/speech
alignment, temporal wording, QA-row count, proximity to 1,800 s, and canonical
ID. `H5vpBCLo74U` ranked first.

The ambient/visual-temporal profile sorted by subtitle presence, topic novelty,
question-category novelty, number of rows with music/singing/song/applause or
sound wording, temporal wording, QA-row count, duration descending, and
canonical ID. `TMe7oXMJoSM` ranked first.

This procedure ranks inspection value from released text. It does not promote
those textual signals to verified modality facts.

## 4. Selected source aggregates

### `ccp-011` — `longvideobench:H5vpBCLo74U` — primary

- split: test;
- zero-based Parquet rows: 2976, 2977, 2978;
- row IDs: `H5vpBCLo74U_0`, `H5vpBCLo74U_1`, `H5vpBCLo74U_2`;
- duration: 1,805.13 seconds;
- video path: `H5vpBCLo74U.mp4`;
- subtitle path: `H5vpBCLo74U_en.json` (present; payload not acquired);
- subtitle offset: 0.0 seconds;
- topic: `KC-Knowledge-Computer-Science`;
- QA category: `T2E` for all three rows;
- source inspection summary: three distinct questions pair subtitle phrases
  with on-screen changes in instructional slides.

The metadata makes this plausibly useful for speech/cross-modal authoring. It
does not verify audible speech, subtitle accuracy, synchronization, or that both
modalities are necessary.

### `ccp-012` — `longvideobench:TMe7oXMJoSM` — active reserve

- split: validation;
- zero-based Parquet rows: 602, 603, 604;
- row IDs: `TMe7oXMJoSM_0`, `TMe7oXMJoSM_1`, `TMe7oXMJoSM_2`;
- duration: 2,805.11 seconds;
- video path: `TMe7oXMJoSM.mp4`;
- subtitle path: `TMe7oXMJoSM_en.json` (present; payload not acquired);
- subtitle offset: 0.0 seconds;
- topic: `KA-Knowledge-Art`;
- QA category: `TAA` for all three rows;
- source inspection summary: all three questions concern performance or scene
  changes, and two explicitly mention singing or lyrics.

The metadata makes this plausibly useful for ambient/visual-temporal authoring.
It does not verify a usable non-speech event, original audio, temporal evidence
locations, or cross-modal necessity.

## 5. Diversity and duplicate limits

The prior strict shortlist covered News Programs/E3E, Knowledge Geography/O3O,
and Knowledge History/E3E. The additions introduce Computer Science/T2E and
Art/TAA, different splits, and durations of about 30 and 47 minutes. Neither ID,
path, exact duration, nor exact question text collides with an existing pool
record or with the other addition. These checks avoid obvious metadata-level
identity duplication; they cannot rule out alternate encodes, excerpts, or
re-uploads.

## 6. Complete five-source metadata report

All row positions below are zero-based within the named Parquet split.

| Candidate | Role | Split rows / row IDs | Duration | Video path | Subtitle status | Topic | QA categories |
|---|---|---|---:|---|---|---|---|
| `ccp-008` | primary | test 2646–2648 / `-PgbM2MhcYQ_0..2` | 2,987.08 s | `-PgbM2MhcYQ.mp4` | `-PgbM2MhcYQ_en.json`, offset 0.0; payload not acquired | `NP-News-Programs` | `E3E` ×3 |
| `ccp-009` | primary | validation 488–490 / `-eRimFrm6kQ_0..2` | 1,540.88 s | `-eRimFrm6kQ.mp4` | `-eRimFrm6kQ_en.json`, offset 0.0; payload not acquired | `KG-Knowledge-Geography` | `O3O` ×3 |
| `ccp-003` | primary | test 2397–2399 / `-7wwfGJXEZg_0..2` | 1,515.20 s | `-7wwfGJXEZg.mp4` | `-7wwfGJXEZg_en.json`, offset 0.0; payload not acquired | `KH-Knowledge-History` | `E3E` ×3 |
| `ccp-011` | primary | test 2976–2978 / `H5vpBCLo74U_0..2` | 1,805.13 s | `H5vpBCLo74U.mp4` | `H5vpBCLo74U_en.json`, offset 0.0; payload not acquired | `KC-Knowledge-Computer-Science` | `T2E` ×3 |
| `ccp-012` | active reserve | validation 602–604 / `TMe7oXMJoSM_0..2` | 2,805.11 s | `TMe7oXMJoSM.mp4` | `TMe7oXMJoSM_en.json`, offset 0.0; payload not acquired | `KA-Knowledge-Art` | `TAA` ×3 |

## 7. Final decision and controls

Add both candidates, producing a five-ID strict technical shortlist. Treat
`ccp-008`, `ccp-009`, `ccp-003`, and `ccp-011` as primary technical candidates
and `ccp-012` as the active reserve. `LVB-01` is narrowed to exactly those five
IDs.

Every access packet stays `DRAFT_NOT_SUBMITTED`. Every selected candidate stays
`PROVISIONAL_NOT_APPROVED` and `unknown_hold`. No media/audio/subtitle payload,
acquisition, processing, annotation, or release approval was created.

The complete 459-source aggregate and both deterministic rank orders are preserved in
`data/hf_recon/snapshots/direct_lvb_candidate_ranking_cdf3444602208c95f453e7683583a077ce38ddbf.json`.
