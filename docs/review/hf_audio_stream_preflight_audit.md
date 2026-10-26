# Audit of live Hugging Face audio stream preflight

**Task:** 68  
**Audit date:** 2026-09-09  
**Live result timestamp:** 2026-09-09T06:18:13Z  
**Audit conclusion:** PASS for integrity and bounded-transfer compliance;
NO-GO for acquisition and long-video pilot-core inclusion

## Scope and method

This audit independently checked:

- `data/acquisition_preflight/hf_audio_stream_preflight_plan.json`;
- `data/acquisition_preflight/hf_audio_stream_preflight_result.json`;
- the closed allowlist, transfer client, parser, and decision logic in
  `tools/hf_audio_stream_preflight.py`;
- the focused tests in `tests/test_hf_audio_stream_preflight.py`;
- exact identities in
  `data/rehearsal_plan/audio_asset_recon_candidates.csv`; and
- repository files for candidate-named or exact-size media artifacts.

No network request was made during this audit, no live request was retried, and
no media was downloaded.

## Audit findings

### Schema and plan identity

- Result and plan schema versions are both `1.0.0`.
- The result mode is `live_bounded_metadata_and_stream_headers` and contains
  exactly five candidates in the same order as the plan.
- Every result identity exactly equals its plan identity: candidate ID,
  repository, immutable revision, object path, byte size, SHA-256, and blob ID.
- The plan still equals the code-level closed allowlist and all five identities
  still match the source CSV.

### Transfer and request accounting

- Aggregate request count: **9**.
- HEAD records: **5**; all recorded zero response-body bytes.
- Range GET records: **4**; each returned HTTP 206 with an exact 1,048,576-byte
  `Content-Length` and matching `Content-Range` against the pinned object size.
- Aggregate response-body bytes: **4,194,304**, equal to both the sum of request
  records and the sum of candidate totals.
- Maximum observed response: **1,048,576 bytes**.
- The run stayed below the 8 MiB per-response, 12 MiB per-candidate, and 64 MiB
  aggregate limits, and below 256 range requests per candidate.
- None of the four requested ranges covered a complete object. Each successful
  FLARE object used disjoint 1 MiB head and tail windows only.

### Credentials, signed URLs, and persisted media

- Serialized request records contain no authorization field, bearer token,
  `HF_TOKEN`, URL user information, or signed-query markers such as Policy,
  Signature, or Credential.
- Redirect locations are query-free. They expose only the permitted host/path
  diagnostics retained by the implementation.
- No file named like any of the five candidate media objects exists in the
  audited project paths, and no media file has one of the five pinned complete
  object sizes.
- The only live preflight output is the JSON metadata/result record. Thus no
  complete media object was downloaded or persisted by this run.

### Parser coherence

For `ccp-005` and `ccp-006`:

- `mvhd.duration / mvhd.timescale` exactly reproduces the reported container
  duration.
- Every track's media duration units/timescale reproduce its reported media
  duration; track movie durations reproduce against the movie timescale.
- Counted `vide` and `soun` handlers reproduce the reported one video and one
  audio track per object.
- Re-running the decision functions over the serialized parser fields returns
  `PLAUSIBLY_SYNCHRONIZED`, duration `FAIL`, and
  `NO_GO_DURATION_OUT_OF_RANGE` for both objects.

For all three Omni objects, HTTP 403 occurred during HEAD route attempts before
identity binding or stream parsing. Their zero track counts are untouched base
result placeholders accompanied by `NOT_RELIABLY_INSPECTED`, unresolved
fields, and an identity/transfer no-go. They must not be interpreted as
video-only or audio-negative objects.

## Candidate conclusions

| candidate | audio track declared | content/audio semantics verified | duration eligible | access authorized | full acquisition authorized | pilot-core status |
|---|---|---|---|---|---|---|
| `ccp-005` | yes, one `soun` track | no | no: 745.96421875 s | no | no | exclude; compatibility fixture only |
| `ccp-006` | yes, one `soun` track | no | no: 766.862 s | no | no | exclude; compatibility fixture only |
| `omni-video_284` | unresolved | no | unresolved | no; HTTP 403 | no | exclude pending optional gate resolution |
| `omni-video_617` | unresolved | no | unresolved | no; HTTP 403 | no | exclude pending optional gate resolution |
| `omni-video_611` | unresolved | no | unresolved | no; HTTP 403 | no | exclude pending optional gate resolution |

The FLARE demo objects are useful exact, audio-track-bearing engineering and
container-compatibility examples, but neither reaches the 1,200-second lower
bound. The Omni objects remain access-blocked and unverified, not audio-negative.
None of the five is authorized or scientifically eligible for the long-video
pilot core.

## Recommended route

1. Preserve the 1,200–5,400-second scientific duration gate. Do not relax the
   20-minute lower bound to admit the FLARE demos.
2. Keep the two FLARE objects outside the pilot core as exact engineering and
   compatibility fixtures. Any future sample decoding would still require
   separate authority and would be content verification, not a correction to
   their duration failure.
3. Expand discovery and identity freezing for exact long-video objects that
   already satisfy the duration requirement.
4. Pursue Omni gate/access only if expected scientific value justifies the
   effort and an item-scoped bounded-preflight authorization can be obtained.
   A successful gate resolution should lead first to another bounded identity
   and stream inspection, not to full acquisition.
5. Keep decoded audio semantics, access, processing, full acquisition,
   annotation, and publication decisions as explicit independent approvals.

## Validation

The focused suite now includes live-result invariant checks for identity,
request accounting, limits, secret redaction, range completeness, parser
arithmetic, and decision reproduction. Test outcomes are recorded in
`orchestration/results/68_stream_result_review.txt`.
