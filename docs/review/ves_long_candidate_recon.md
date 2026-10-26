# VES-Bench long-candidate metadata reconciliation

Date: 2026-09-09  
Repository: `buaaplay/VES-Bench`  
Immutable revision: `b1cdbb370ad866090e6fec82ccb9e699b10edbc7`

## Decision

**Blocked; no exact long-video candidate pool or stream-preflight object list
can be frozen from the fetched metadata.**

This is not an access or join failure. The fetched Parquet is authentic,
parseable, and joins exactly to all 348 MP4 siblings. The blocker is that its
actual schema has **no item-level video-duration field**. The nested
`evidence.start_sec` and `evidence.end_sec` values are question-evidence
intervals, not whole-video durations. Treating their endpoints as durations
would violate the required 1,200–5,400 second gate and Task 70's instruction
to fail on absent duration.

Therefore:

- `data/rehearsal_plan/ves_long_candidate_pool.csv` is a closed, header-only
  pool with zero selected rows;
- `data/acquisition_preflight/ves_long_stream_preflight_plan.json` is
  explicitly `BLOCKED` and has zero ranked objects;
- no media acquisition, Range request, stream claim, content claim, or rights
  upgrade is authorized.

The requested 8–12 candidates and 5–8 preflight objects are intentionally not
fabricated.

## Snapshot and object validation

| Artifact | Exact result |
|---|---|
| Local Parquet | `data/hf_recon/snapshots/hf_buaaplay_VES-Bench_b1cdbb3_VES-Bench.parquet` |
| Repository path | `VES-Bench.parquet` |
| Size | `422415` bytes |
| SHA-256 | `be2dca2e9e7561ca9606291fd22f86c0a54eea353fac8c8ac3cf964b4c612376` |
| Blob ID | `74c9e646c04f2a9923d3de0ffe017d9f62a1fbe2` |
| API snapshot | `data/hf_recon/snapshots/hf_api_buaaplay_VES-Bench.json` |
| API size / SHA-256 | `79549` / `a1f844b2f6632e4e8a01038342239854338c9ca85e21ea9e3642cef486a69c6a` |

The Parquet local size and SHA-256 match both the task-provided values and the
exact LFS identity in the pinned API snapshot. The API snapshot identifies the
expected repository and immutable revision and reports a public, ungated
repository.

The sibling index contains 348 MP4 objects. For every object:

- `rfilename` is unique;
- blob ID is unique;
- LFS SHA-256 is unique;
- sibling size equals LFS size;
- the metadata path is exactly `videos/{video_id}.mp4`.

All 348 unique metadata video IDs join one-to-one by exact `video_path` to the
348 exact MP4 siblings. There are no missing MP4s, ambiguous paths, duplicate
object identities, or conflicting size/hash identities.

## Actual Parquet schema

The parsed Parquet has 600 rows and these ten top-level columns:

1. `id` — `int64`
2. `task` — `large_string`
3. `dataset` — `large_string`
4. `video_id` — `large_string`
5. `video_path` — `large_string`
6. `question` — `large_string`
7. `options` — struct of `A`, `B`, `C`, and `D`
8. `answer` — `large_string`
9. `evidence` — list of structs containing `id`, `start_sec`, `end_sec`, and
   `description`
10. `source_question_id` — `large_string`

Observed row facts:

- 600 unique row IDs and 600 unique `source_question_id` values;
- 348 unique video IDs and video paths;
- 568 rows labeled `youtube` and 32 rows labeled `ego4d`;
- 300 `temporal_ordering` rows and 300 `event_counting` rows;
- 2,025 evidence intervals;
- maximum evidence endpoint: `1080.0` seconds.

There is no `duration`, `video_duration`, `duration_seconds`, or equivalent
top-level field. `1080.0` seconds is the latest annotated evidence endpoint,
not evidence that the corresponding object ends there. It is also below the
frozen 1,200-second lower bound.

## Why candidate selection must stop

An eligible candidate requires an exact metadata duration in the inclusive
range `[1200, 5400]` seconds. No selected item can satisfy that predicate when
duration is absent. Object byte size cannot substitute for duration, and
question/evidence timestamps cannot establish the media endpoint.

The repaired tool supports deterministic source/topic/modality-diverse
selection when a unique item-level duration column is present. Its tests cover:

- inclusive duration boundaries;
- absent/null/conflicting duration;
- duplicate or ambiguous joins;
- missing/non-MP4 objects;
- conflicting LFS identity;
- deterministic ranking;
- exact evidence-row binding;
- no wildcard or acquisition authority;
- no network/media-body route.

For the real snapshot, the same tool emits the blocked artifacts rather than
silently selecting short or duration-unknown objects.

## Metadata-derived modality hypothesis audit

Question and evidence text can support triage hypotheses only. Across all 348
exactly joined objects, the deterministic text classifier emits:

| Unverified role hypothesis | Count |
|---|---:|
| Mixed A/V | 206 |
| Environmental/non-speech | 104 |
| Speech-heavy | 38 |

Topic hypotheses across all joined objects are:

| Unverified topic hypothesis | Count |
|---|---:|
| General visual events | 70 |
| Technology/science | 56 |
| Sports/performance | 53 |
| Outdoors/travel | 47 |
| Home/DIY | 37 |
| History/news | 29 |
| Food/cooking | 23 |
| Animals/nature | 22 |
| Retail/daily life | 11 |

These labels do **not** establish that an audio stream exists, that speech or
environmental sound is audible, that language is known, or that content is
suitable. VES-Bench metadata describes visual benchmark events and contains no
audio track, codec, channel, language, music, speech, or ambient-audio field.
Every role remains
`UNVERIFIED_PENDING_STREAM_AND_CONTENT_CHECKS`.

## Rights and authority audit

Rights remain unresolved:

- no dataset card or substantive dataset/media license is represented by the
  pinned API snapshot;
- public, ungated hosting is technical accessibility, not transfer,
  processing, annotation, publication, or redistribution authorization;
- upstream source ownership, original-source locators, and asset-level
  provenance are not supplied by the Parquet;
- YouTube-like IDs are identifiers, not proof of licensing or source
  disjointness;
- the Ego4D-labeled subset may carry separate agreement constraints that are
  not resolved here.

All source-media, processing, annotation, and release rights remain
`UNKNOWN_HOLD`.

## Required resolution

Before an 8–12 item pool can be frozen, obtain authoritative item-level
durations bound to the same exact repository revision and MP4 object paths.
If no metadata source supplies those durations, a separate review must
explicitly authorize a bounded container-duration/stream preflight. That later
plan must remain exact-object-only and may then rank 5–8 objects, but Task 70
does not grant that authority.

## No-media confirmation

No network access was used. No MP4 body or byte range was requested. No video
payload exists under `data/hf_recon/snapshots/`; only the JSON and Parquet
metadata snapshots are present for this repository.
