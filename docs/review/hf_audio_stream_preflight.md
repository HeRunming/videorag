# Bounded Hugging Face stream-header preflight

**Task:** 67  
**Date:** 2026-09-09  
**Execution state:** live parent execution completed on 2026-09-09; independent
result audit completed

## Scope

This preflight is restricted to these five exact immutable objects:

| candidate | repository | revision | path | bytes |
|---|---|---|---|---:|
| `ccp-005` | `AnonymousFLARE/FLARE_demo` | `a7e85c038a16b86afe1109b33cd131ec80d67cb3` | `sample_0/K759eXmaMTY.mp4` | 59,708,138 |
| `ccp-006` | `AnonymousFLARE/FLARE_demo` | `a7e85c038a16b86afe1109b33cd131ec80d67cb3` | `sample_1/3uV8XZcIBbk.mp4` | 138,115,547 |
| `omni-video_284` | `NJU-LINK/OmniVideoBench` | `1b1aa0899fca5aa92e4fe5dcd3b60be58efff6ca` | `videos/video_284.mp4` | 190,135,475 |
| `omni-video_617` | `NJU-LINK/OmniVideoBench` | `1b1aa0899fca5aa92e4fe5dcd3b60be58efff6ca` | `videos/video_617.mp4` | 61,884,190 |
| `omni-video_611` | `NJU-LINK/OmniVideoBench` | `1b1aa0899fca5aa92e4fe5dcd3b60be58efff6ca` | `videos/video_611.mp4` | 95,163,435 |

The complete pinned SHA-256 and blob identities are in
`data/acquisition_preflight/hf_audio_stream_preflight_plan.json`. The program
contains the same closed allowlist and rejects a changed, reordered, missing,
or broadened plan. It also confirms the plan identities against
`data/rehearsal_plan/audio_asset_recon_candidates.csv` before any network
operation.

## Transfer boundary

`tools/hf_audio_stream_preflight.py`:

- loads the logged-in Hugging Face token with
  `huggingface_hub.get_token()` and retains it only in memory;
- supports repeated `--proxy` options in explicit order;
- uses manual redirects and sends authorization only to the canonical
  `huggingface.co` origin;
- allows `HEAD`, but permits media bodies only through a bounded `Range` GET;
- rejects a range answered as full-object HTTP `200`;
- validates status, `Content-Length`, `Content-Range`, requested boundaries,
  total object size, and identity content encoding;
- rejects a complete-object range;
- limits each response to 8 MiB, each candidate to 12 MiB and 256 range
  requests, and the five-object aggregate to 64 MiB;
- starts with disjoint 1 MiB head and tail windows;
- walks top-level ISO-BMFF box headers by fetching only missing short header
  ranges, then fetches only the complete `ftyp` and `moov` boxes;
- caps `moov` at 8 MiB, which guarantees that all five candidates can remain
  within the 64 MiB aggregate even in the conservative worst case; and
- releases cached response bodies after each candidate and never writes media
  bytes, decoded data, thumbnails, bearer credentials, or signed URLs.

Redirect records retain query-free endpoints only. Transport exception text is
not retained because it may contain credentials or signed query parameters.

## Identity rule

A candidate proceeds to parsing only when:

1. the final `HEAD` content length equals the pinned object size;
2. any observed `X-Repo-Commit` equals the pinned immutable revision;
3. any observed `X-Linked-Size` equals the pinned size; and
4. an HF linked-object ETag header equals the pinned LFS SHA-256.

The bounded preflight cannot recompute a full-object SHA-256. The report states
this limitation explicitly. The pinned blob ID remains part of the closed plan
and source-CSV validation, but it is not inferred from partial media bytes.

## Parser and decisions

The defensive parser supports 32-bit and 64-bit box sizes and inspects:

- `ftyp`;
- `moov` and `mvhd`;
- every `trak`;
- `tkhd`, `mdia`, `mdhd`, and `hdlr`.

It enforces parent bounds, nonzero progress, maximum depth/count limits,
required singleton boxes, valid timescales, and finite known durations.
Fragmented MP4 (`moof` or `mvex`), missing `moov`, oversized `moov`, unknown
duration sentinels, malformed sizes, or unsupported full-box versions fail
closed.

The container duration is `mvhd.duration / mvhd.timescale`. Declared audio and
video tracks are counted from `hdlr` values `soun` and `vide`. A/V timelines are
called `PLAUSIBLY_SYNCHRONIZED` only when both the media-header duration and,
when present, the movie-timescale track-header duration for every audio/video
track are positive and within the larger of two seconds or 0.5% of the
container duration.

Per-candidate decisions are:

- `GO_STREAM_DECLARED_AUDIO_AND_DURATION_PASS`;
- `NO_GO_NO_AUDIO_TRACK`;
- `NO_GO_DURATION_OUT_OF_RANGE`;
- `NO_GO_UNSUPPORTED_OR_INCOMPLETE_CONTAINER`; or
- `NO_GO_IDENTITY_OR_TRANSFER_VALIDATION`.

A GO means only that the exact object passed identity checks, parsed as
non-fragmented ISO-BMFF, declared audio and video tracks, had plausibly aligned
declared timelines, and had a container duration in the inclusive
1,200–5,400-second gate.

It does **not** establish audible samples, speech, ambient sound, semantic
modality roles, decode quality, rights, authorization, or scientific
suitability.

## Offline validation

Synthetic in-memory tests cover:

- synchronized audio+video and duration pass;
- video-only;
- duration below and above the gate;
- 64-bit boxes and version-1 duration fields;
- malformed box sizes;
- missing `moov`;
- fragmented MP4;
- a range ignored with HTTP `200`;
- a prohibited complete-object range;
- mismatched `Content-Range`;
- per-response and aggregate body limits;
- credential and signed-URL redaction;
- exact HEAD identity binding;
- box-guided retrieval of a `moov` outside both initial windows; and
- ordered route failover.

The Task 67 isolated implementation worker did not run the live command.

Validation results:

- focused Task 67 tests: **17 passed**;
- full configured test suite: **176 passed, 11 subtests passed**;
- offline exact-plan/source-CSV validation: **PASS**.

After the live result was added, Task 68 added result-invariant regression
checks and reran validation:

- focused stream-preflight tests: **19 passed**;
- full configured test suite: **178 passed**; and
- offline exact-plan/source-CSV validation: **PASS**.

## Live execution result

The parent ran the documented command on 2026-09-09 and wrote
`data/acquisition_preflight/hf_audio_stream_preflight_result.json` at
`2026-09-09T06:18:13Z`.

| candidate | identity / access result | declared tracks | duration | duration gate | disposition |
|---|---|---:|---:|---|---|
| `ccp-005` | exact pinned identity matched | 1 video + 1 audio | 745.96421875 s | FAIL | engineering/compatibility fixture only |
| `ccp-006` | exact pinned identity matched | 1 video + 1 audio | 766.862 s | FAIL | engineering/compatibility fixture only |
| `omni-video_284` | HTTP 403 before identity inspection | uninspected | unresolved | unresolved | access-blocked/unverified |
| `omni-video_617` | HTTP 403 before identity inspection | uninspected | unresolved | unresolved | access-blocked/unverified |
| `omni-video_611` | HTTP 403 before identity inspection | uninspected | unresolved | unresolved | access-blocked/unverified |

For both FLARE objects, the parser found one `vide` and one `soun` handler and
classified the declared timelines as `PLAUSIBLY_SYNCHRONIZED`. This establishes
an audio-track declaration, not decoded or audible content and not speech,
ambient, or semantic suitability. Both objects are below the inclusive
1,200-second lower bound and therefore are not long-video pilot-core
candidates.

The three Omni records contain zero track counts only because the fail-closed
result template was never replaced after HTTP 403. They are **not**
audio-negative findings: identity, container, duration, and tracks all remain
unverified.

The run made nine request records: five HEAD attempts and four successful
1 MiB range responses. Total transferred body bytes were 4,194,304, the
largest response was 1,048,576 bytes, and all configured per-response,
per-candidate, request-count, and aggregate limits were respected. No request
covered a complete object. The result contains no authorization headers,
tokens, URL user information, or signed URL query strings. No preflight media
file was persisted.

## Acquisition decision

None of the five objects is authorized for full acquisition or scientifically
eligible for the long-video pilot core. Access reachability, declared tracks,
content/audio semantics, duration eligibility, processing rights, and full
acquisition authorization remain separate gates.

The next route is to:

1. keep `ccp-005` and `ccp-006` as exact engineering/container compatibility
   fixtures only;
2. expand discovery of immutable exact long-video candidates rather than
   relaxing the 20-minute lower bound; and
3. resolve Omni gate/access only if the expected scientific value warrants a
   new item-scoped authorization, followed by another bounded inspection—not
   full acquisition.

The detailed independent audit is in
`docs/review/hf_audio_stream_preflight_audit.md`, and the authoritative
post-preflight decision is in
`data/rehearsal_plan/audio_asset_post_preflight_decision.json`.
