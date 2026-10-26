# Parent row resolution review

**Date:** 2026-09-07  
**Task:** 48 — Ingest verified parent metadata and resolve candidate rows  
**Decision:** metadata ingestion complete; 3 strict technical candidates; no approval

## Executive result

- verified metadata Parquets: **3/3**;
- source size/SHA-256 matches: **3/3**;
- schemas inspected with PyArrow 21.0.0: **3/3**;
- embedded binary/image/audio/video payload columns or declared features: **0**;
- requested canonical IDs present: **7/9**;
- requested canonical IDs absent: **2/9**;
- matching QA rows preserved: **21**;
- source-level aggregates created: **9** (seven present, two explicit absent);
- exact-second in-range, source-ID-disjoint candidates: **3**;
- requested 4–5-row shortlist achieved: **no**.

## Verified source artifacts

| Local metadata snapshot | Bytes | SHA-256 | Rows |
|---|---:|---|---:|
| `data/hf_recon/snapshots/hf_longvideobench_LongVideoBench-Meta_cdf3444602208c95f453e7683583a077ce38ddbf_validation.parquet` | 426,680 | `5f370287edbfb9875562b116686d50208d0d40615f5b407f970448868b6bc108` | 1337 |
| `data/hf_recon/snapshots/hf_longvideobench_LongVideoBench-Meta_cdf3444602208c95f453e7683583a077ce38ddbf_test.parquet` | 1,612,265 | `9015fc7f9e83e4a6479fa533c2c7df8c42a9bab67a7e01be6320262e249a1bec` | 5341 |
| `data/hf_recon/snapshots/hf_lmms-eval_Video-MME_ead1408f75b618502df9a1d8e0950166bf0a2a0b_test.parquet` | 405,167 | `7fffab8ed38ecc2f9f0eca4c44d8a11636f0ee96116ede83580c8b9ae0faf986` | 2700 |

The local copies were hashed after copying and exactly match the verified
`/tmp` inputs and official LFS SHA-256 values. They contain metadata only.

## Schema result

LongVideoBench-Meta contains scalar string/integer/double QA and source-path
fields. Video-MME contains scalar metadata plus `options: list<string>`.
Physical Arrow types and Hugging Face schema metadata declare no binary,
image, audio, or video payload features.

## Target resolution

| Parent dataset | Target ID | Result | Split | Zero-based row indices | Duration | Source path/URL | Subtitle |
|---|---|---|---|---|---|---|---|
| LongVideoBench | `-WnyRMZqV1U` | absent | — | — | — | — | — |
| LongVideoBench | `20lTg3yUrO4` | absent | — | — | — | — | — |
| LongVideoBench | `-7wwfGJXEZg` | present (3 QA rows) | test | 2397, 2398, 2399 | 1515.20 | `-7wwfGJXEZg.mp4` | `-7wwfGJXEZg_en.json` |
| LongVideoBench | `-PgbM2MhcYQ` | present (3 QA rows) | test | 2646, 2647, 2648 | 2987.08 | `-PgbM2MhcYQ.mp4` | `-PgbM2MhcYQ_en.json` |
| LongVideoBench | `-eRimFrm6kQ` | present (3 QA rows) | validation | 488, 489, 490 | 1540.88 | `-eRimFrm6kQ.mp4` | `-eRimFrm6kQ_en.json` |
| LongVideoBench | `-hgJVx12Qk4` | present (3 QA rows) | test | 3682, 3683, 3684 | 1001.90 | `-hgJVx12Qk4.mp4` | `-hgJVx12Qk4_en.json` |
| Video-MME | `K759eXmaMTY` | present (3 QA rows) | test | 1230, 1231, 1232 | `medium` (categorical) | `https://www.youtube.com/watch?v=K759eXmaMTY` | not declared |
| Video-MME | `3uV8XZcIBbk` | present (3 QA rows) | test | 984, 985, 986 | `medium` (categorical) | `https://www.youtube.com/watch?v=3uV8XZcIBbk` | not declared |
| Video-MME | `jWa2yrLGxCM` | present (3 QA rows) | test | 1584, 1585, 1586 | `medium` (categorical) | `https://www.youtube.com/watch?v=jWa2yrLGxCM` | not declared |

Repeated QA rows are explicit rather than collapsed: each original row is
preserved with all source fields, and one aggregate records invariant
source-level fields plus QA IDs/task types.

## Extracted snapshots

| Artifact | SHA-256 |
|---|---|
| `data/hf_recon/snapshots/longvideobench_parent_rows_cdf3444602208c95f453e7683583a077ce38ddbf_targets.json` | `61709bc37b7e79383bb3884b0b740767a49c000f8be5cf74e6d117b8e41fd29a` |
| `data/hf_recon/snapshots/videomme_parent_rows_ead1408f75b618502df9a1d8e0950166bf0a2a0b_targets.json` | `2cd7cec8c3a2b3cff434d945fc918ca3dd778ac0d430cba54757b0dcd3eb3b0d` |

Both use deterministic procedure `task48-parent-metadata-ingest-v1`: verify size/hash, inspect schema,
read split rows in physical order, exact-match canonical IDs, preserve all
fields and zero-based row indices, then aggregate by target without dropping QA
rows.

## Candidate consequence

The exact 1,200–5,400-second gate passes only:

| Rank | Candidate | Canonical source | Duration (s) | Parent split | Status |
|---:|---|---|---:|---|---|
| 1 | `ccp-008` | `longvideobench:-PgbM2MhcYQ` | 2987.08 | LongVideoBench-Meta/test | `PRE_DOWNLOAD_TECHNICAL_CANDIDATE_NOT_APPROVED` |
| 2 | `ccp-009` | `longvideobench:-eRimFrm6kQ` | 1540.88 | LongVideoBench-Meta/validation | `PRE_DOWNLOAD_TECHNICAL_CANDIDATE_NOT_APPROVED` |
| 3 | `ccp-003` | `longvideobench:-7wwfGJXEZg` | 1515.2 | LongVideoBench-Meta/test | `PRE_DOWNLOAD_TECHNICAL_CANDIDATE_NOT_APPROVED` |

This is a **3-row pre-download technical shortlist**, not the requested 4–5,
because Video-MME supplies categorical rather than exact-second duration,
`-hgJVx12Qk4` is below the floor, and two LongVideoBench IDs are absent.

## Safety, rights, and media boundary

No video, audio, clip, archive, subtitle payload, thumbnail, embedding, feature,
pickle, model, or YouTube payload was created or downloaded. The three copied
Parquet files are metadata tables. `media_downloaded` remains false.

All rights/access states remain hold. No acquisition approval or executable
media-transfer plan was created. Metadata does not verify video/audio streams,
speech, ambient sound, decodability, completeness, or authorization.
