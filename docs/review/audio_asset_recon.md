# Audio asset reconnaissance

**Task:** 66 reconciliation of Tasks 64–65  
**As of:** 2026-09-09  
**Decision:** **FAIL CLOSED — shortlist only; no media action authorized**

## Reconciled result

The parent environment completed a metadata-only live run after the isolated
Task 65 worker could not resolve either supplied proxy. The retained parent
evidence is `data/rehearsal_plan/audio_asset_recon_live_evidence.json` and must
not be replaced by a fabricated pass.

Parent result:

```text
status: PARTIAL
request_count: 11
successful_request_count: 7
response_body_bytes: 169359
```

The seven successful metadata responses were the NASA page for `cand-023`, the
NOAA pages for `cand-048` and `cand-051`, and the four Hugging Face repository
APIs for FLARE demo, FLARE, OmniVideoBench, and LongVideoBench. NOAA title and
duration normalization passed for both candidates. The NASA page request
returned HTTP 200, but normalization failed because the expected title was not
present. The two Commons API checks failed with HTTP 403 after the first proxy
route timed out; those outcomes are endpoint/access failures, not evidence that
the files are missing.

No media payload, media-object Range GET, stream-header preflight, or media
acquisition occurred.

## Exact current recommendation

Only candidates whose retained title, identity, and duration remain coherent
are active:

| Rank | Candidate | Status | Remaining gates |
|---:|---|---|---|
| 1 | `cand-061` | primary; pinned Commons filename and 5,375 s duration remain coherent; live API inaccessible | official page/revision/original/hash/size, license/component review, bounded-preflight authority, decoded audio |
| 2 | `cand-048` | primary; live NOAA title and 3,000 s duration matched | exact official delivery object, rights, bounded-preflight authority, decoded audio |
| 3 | `cand-051` | primary; live NOAA title and 3,720 s duration matched | exact official delivery object, rights, bounded-preflight authority, decoded audio |
| 4 | `cand-056` | reserve; pinned Commons filename and 3,067 s duration remain coherent; live API inaccessible | official page/revision/original/hash/size, license/component review, bounded-preflight authority, decoded audio |

`cand-023` is no longer an active primary recommendation. It is
`STALE_OR_MISMATCHED_ID_HOLD`: the current official response for SVS ID 11205
did not contain `The World Avoided: Successful Stratospheric Ozone Protection`.
Because the response body was intentionally not retained, the direct evidence
cannot distinguish a stale ID, a repurposed page, or an originally incorrect
mapping. The historical 2,243 s value is retained only as pinned metadata bound
to a disputed identity. No replacement URL is asserted or invented.

All authorization arrays remain empty.

## Fail-closed metadata merge

`tools/audio_asset_recon.py` now treats pinned and live evidence as separate
layers:

- absent or empty live fields cannot erase a pinned size, hash, blob ID,
  revision, duration, object path, or official route;
- equal live values confirm the pinned value;
- a different non-empty live value is recorded in `metadata_conflicts`, leaves
  the pinned value unchanged, changes disposition to `METADATA_CONFLICT_HOLD`,
  and fails the corresponding logical normalization check;
- the live candidate summary exposes both disposition and conflicts;
- pinned HF sizes and blob IDs therefore survive the reduced live sibling
  objects seen by the parent run.

The normalized CSV has 16 rows and now includes a serialized
`metadata_conflicts` field. The pinned exact HF identities remain intact,
including 59,708,138 and 138,115,547 bytes for the FLARE demo MP4s and
190,135,475, 61,884,190, and 95,163,435 bytes for the selected OmniVideoBench
MP4s.

## Commons fallback boundary

If the Commons API fails, live mode may now fetch the already listed official
Commons item page as bounded HTML metadata and confirm only that the pinned
filename/title appears. This fallback does **not** infer file absence and does
not establish revision, hash, size, original-file URL, license, duration, or
audio. It does not issue a media HEAD unless the API has first supplied a
validated official original URL.

## Evidence boundary and remaining gates

- MIME, filename extensions, captions, corpus descriptions, task labels, and
  audio-codec declarations do not establish decoded audio.
- The exact FLARE and OmniVideoBench objects remain deferred compatibility
  objects because duration, rights, and decoded audio are unresolved.
- The five LongVideoBench current renditions remain rejected for audio use
  because prior independent probes found zero audio streams; no synchronized
  alternate has been identified.
- Every retained public candidate still needs immutable object identity,
  explicit processing authority, separate annotation/release review, and an
  authorized post-acquisition stream/decode verification.

Machine-readable decisions:

- `data/rehearsal_plan/audio_asset_recon_candidates.csv`
- `data/rehearsal_plan/audio_asset_proposed_allowlist.json`
- `data/rehearsal_plan/audio_asset_stream_preflight_proposal.json`

Detailed parent-live reconciliation is in
`docs/review/audio_asset_parent_live_reconciliation.md`.
