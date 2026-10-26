# Verified parent metadata ingestion

**Date:** 2026-09-07  
**Procedure:** `task48-parent-metadata-ingest-v1`  
**Network access:** none  
**PyArrow:** 21.0.0

## Integrity checks

| Local metadata snapshot | Bytes | SHA-256 | Rows |
|---|---:|---|---:|
| `data/hf_recon/snapshots/hf_longvideobench_LongVideoBench-Meta_cdf3444602208c95f453e7683583a077ce38ddbf_validation.parquet` | 426,680 | `5f370287edbfb9875562b116686d50208d0d40615f5b407f970448868b6bc108` | 1337 |
| `data/hf_recon/snapshots/hf_longvideobench_LongVideoBench-Meta_cdf3444602208c95f453e7683583a077ce38ddbf_test.parquet` | 1,612,265 | `9015fc7f9e83e4a6479fa533c2c7df8c42a9bab67a7e01be6320262e249a1bec` | 5341 |
| `data/hf_recon/snapshots/hf_lmms-eval_Video-MME_ead1408f75b618502df9a1d8e0950166bf0a2a0b_test.parquet` | 405,167 | `7fffab8ed38ecc2f9f0eca4c44d8a11636f0ee96116ede83580c8b9ae0faf986` | 2700 |

Every `/tmp` input was checked before use. Processing would abort on any byte
size or SHA-256 mismatch. Each repository copy was hashed again and matched.

## Payload-column inspection

All Arrow fields and Hugging Face feature metadata were inspected. No binary,
fixed-size-binary, image, audio, or video payload field was found. Video-MME's
only nested field is `options: list<string>`. The files are metadata-only
Parquets and are not counted as media.

## Extraction result

- requested IDs: **9**;
- present IDs: **7** — `-7wwfGJXEZg`, `-PgbM2MhcYQ`, `-eRimFrm6kQ`, `-hgJVx12Qk4`, `K759eXmaMTY`, `3uV8XZcIBbk`, `jWa2yrLGxCM`;
- absent IDs: **2** — `-WnyRMZqV1U`, `20lTg3yUrO4`;
- matching original QA rows: **21**;
- source-level aggregates: **9**, including explicit absent records.

| Extracted artifact | Bytes | SHA-256 |
|---|---:|---|
| `data/hf_recon/snapshots/longvideobench_parent_rows_cdf3444602208c95f453e7683583a077ce38ddbf_targets.json` | 23,990 | `61709bc37b7e79383bb3884b0b740767a49c000f8be5cf74e6d117b8e41fd29a` |
| `data/hf_recon/snapshots/videomme_parent_rows_ead1408f75b618502df9a1d8e0950166bf0a2a0b_targets.json` | 15,304 | `2cd7cec8c3a2b3cff434d945fc918ca3dd778ac0d430cba54757b0dcd3eb3b0d` |

Each matching row retains the source dataset, revision, upstream and local
Parquet paths, source hash/size, split, zero-based row index, and every original
row field. Aggregates retain invariant source metadata and QA IDs/task labels.

## Interpretation constraints

- LongVideoBench numeric durations are used as exact metadata durations.
- Video-MME `duration=medium` remains a categorical label and is not converted
  into seconds.
- Video-MME has no subtitle field in the verified schema; no subtitle
  availability is inferred.
- Metadata paths and URLs do not prove file availability or media properties.
- Video/audio/speech/ambient/container status remains unverified.
- Rights remain hold and no acquisition approval exists.
