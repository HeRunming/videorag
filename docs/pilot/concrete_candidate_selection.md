# Concrete candidate selection for the real-media rehearsal

**Task date:** 2026-09-08  
**Mode:** verified local official metadata only; no network  
**Media or subtitle payload downloaded:** no  
**Approval status:** every candidate remains `PROVISIONAL_NOT_APPROVED`; source-media rights remain `unknown_hold`

## Task 50 outcome

Task 50 recomputed the two supplied LongVideoBench-Meta Parquet hashes and
inspected their logical schemas with PyArrow 21.0.0. Both hashes match the
pinned official snapshot records:

| Split | Rows | Row groups | Bytes | SHA-256 |
|---|---:|---:|---:|---|
| validation | 1,337 | 2 | 426,680 | `5f370287edbfb9875562b116686d50208d0d40615f5b407f970448868b6bc108` |
| test | 5,341 | 6 | 1,612,265 | `9015fc7f9e83e4a6479fa533c2c7df8c42a9bab67a7e01be6320262e249a1bec` |

Both files have the same 16 metadata/text columns: `video_id`, `id`,
`video_path`, `subtitle_path`, `correct_choice`, `question`, `option0` through
`option4`, `duration`, `duration_group`, `question_category`, `topic_category`,
and `starting_timestamp_for_subtitles`. No binary, image, audio, or video
payload column or declared media feature is present.

Aggregating all 6,678 QA rows produced 3,761 unique `video_id` values. After
excluding every pre-Task-50 candidate-pool LongVideoBench canonical ID and
requiring an internally consistent single split, exact duration of
1,200–5,400 seconds inclusive, and the valid relative path `<video_id>.mp4`,
459 unseen canonical IDs remained eligible. Of those, 458 had three QA rows and
one had two; each source aggregate had one question category and one topic
category. Every eligible aggregate had a non-empty subtitle metadata path, so
subtitle presence did not distinguish only one candidate.

## Deterministic selection

Two separate profiles were ranked after the hard filter:

1. **Speech/cross-modal inspection lead:** subtitle path present; topic and
   question-category novelty versus the current three; count of QA rows that
   explicitly align a screen state/change with subtitle, conversation, or
   speech wording; temporal wording count; QA-row count; distance from 1,800
   seconds; then `video_id`.
2. **Ambient/visual-temporal inspection lead:** subtitle path present; topic and
   question-category novelty; count of QA rows mentioning music, singing, song,
   applause, sound, or related words; temporal/change wording count; QA-row
   count; duration descending; then `video_id`.

These lexical/category signals are deterministic metadata triage only. They do
**not** verify an audio stream, speech, ambient sound, cross-modal necessity,
source timestamps, AV-TRACE hop structure, or complete-source availability.

The selected additions are:

| Rank | Candidate / role | Canonical source | Split and zero-based rows | Exact duration | Paths | Topic / QA category | Metadata-only rationale |
|---:|---|---|---|---:|---|---|---|
| 4 | `ccp-011` / primary | `longvideobench:H5vpBCLo74U` | test rows 2976–2978; IDs `H5vpBCLo74U_0..2` | 1,805.13 s | `H5vpBCLo74U.mp4`; `H5vpBCLo74U_en.json`; subtitle offset 0.0 | `KC-Knowledge-Computer-Science`; `T2E` ×3 | All three questions bind a described screen change to a subtitle phrase. This is a plausible speech/cross-modal authoring lead, not verified modality necessity. |
| 5 | `ccp-012` / active reserve | `longvideobench:TMe7oXMJoSM` | validation rows 602–604; IDs `TMe7oXMJoSM_0..2` | 2,805.11 s | `TMe7oXMJoSM.mp4`; `TMe7oXMJoSM_en.json`; subtitle offset 0.0 | `KA-Knowledge-Art`; `TAA` ×3 | The questions describe performance/scene changes; two mention singing or lyrics. This is a plausible ambient/visual-temporal authoring lead, not verified modality necessity. |

The two additions differ in duration, split, topic, and question category. Their
canonical IDs and paths are distinct from all earlier pool rows and from each
other. No exact-question overlap or exact-duration identity signal was found,
but duplicate/re-upload identity remains unverified without authorized media
fingerprinting.

## Final strict technical shortlist

| Rank | Candidate | Role | Canonical source | Duration (s) | Split | Topic / parent QA category |
|---:|---|---|---|---:|---|---|
| 1 | `ccp-008` | primary | `longvideobench:-PgbM2MhcYQ` | 2,987.08 | test | `NP-News-Programs`; `E3E` ×3 |
| 2 | `ccp-009` | primary | `longvideobench:-eRimFrm6kQ` | 1,540.88 | validation | `KG-Knowledge-Geography`; `O3O` ×3 |
| 3 | `ccp-003` | primary | `longvideobench:-7wwfGJXEZg` | 1,515.20 | test | `KH-Knowledge-History`; `E3E` ×3 |
| 4 | `ccp-011` | primary | `longvideobench:H5vpBCLo74U` | 1,805.13 | test | `KC-Knowledge-Computer-Science`; `T2E` ×3 |
| 5 | `ccp-012` | active reserve | `longvideobench:TMe7oXMJoSM` | 2,805.11 | validation | `KA-Knowledge-Art`; `TAA` ×3 |

The strict shortlist now reaches five source-ID-disjoint canonical IDs. This is
a pre-download technical shortlist only. It is not an acquisition list or an
approval to process, annotate, or release anything.

## Earlier reconciliation retained

Task 48 resolved the original nine requested parent IDs: seven were present,
two (`-WnyRMZqV1U`, `20lTg3yUrO4`) were absent, and 21 QA rows were preserved.
`-hgJVx12Qk4` was below the duration floor at 1,001.90 seconds. The three
Video-MME rows had only categorical duration labels, which were not converted
to seconds. Task 49 then inspected 303 TraceAV modality rows and found no
eligible TraceAV-to-LongVideoBench addition under the exact parent-row rule.
Task 50 does not alter those findings; it adds direct LongVideoBench source
candidates because AV-TRACE may author new questions/evidence graphs over
reused source videos without requiring an upstream TraceAV/LongVidSearch
annotation.

## Evidence boundaries

- `video_path` and `subtitle_path` are metadata strings, not proof that files
  are available, complete, decodable, or authorized.
- No MP4, audio, subtitle JSON, frame, waveform, transcript, or media-derived
  payload was downloaded or inspected.
- Video, audio, speech, ambient sound, subtitle contents, source-time evidence,
  and cross-modal necessity remain unverified for all five candidates.
- Distinct canonical IDs establish pool-level ID disjointness only; content or
  re-upload disjointness still requires an authorized comparison.
- No terms were accepted and no acquisition, processing, annotation, or release
  approval was created.

The complete 459-source aggregate and both deterministic rank orders are preserved in
`data/hf_recon/snapshots/direct_lvb_candidate_ranking_cdf3444602208c95f453e7683583a077ce38ddbf.json`.
