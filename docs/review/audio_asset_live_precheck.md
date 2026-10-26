# Live audio-candidate metadata precheck

**Tasks:** 65 execution, reconciled by Task 66  
**Date:** 2026-09-09  
**Decision:** **NO-GO — no stream-header preflight, acquisition, processing,
annotation, release, or transfer is authorized**

## Two distinct execution environments

### Isolated Task 65 worker

The worker attempted both configured proxies, but both names failed DNS
resolution. It received no HTTP response and no body bytes. That result showed
only that the isolated worker lacked a usable transport path; it did not show
that the official endpoints were unavailable.

### Parent live execution

The parent subsequently ran the repaired command with the same two proxy
routes and wrote the retained evidence file. Its exact aggregate result was:

```text
status: PARTIAL
request_count: 11
successful_request_count: 7
response_body_bytes: 169359
```

Successful checks/responses:

- NASA official-page GET for `cand-023` (HTTP 200; 66,685 bytes);
- NOAA official-page GET and title/duration normalization for `cand-048`;
- NOAA official-page GET and title/duration normalization for `cand-051`;
- HF API metadata for `AnonymousFLARE/FLARE_demo`;
- HF API metadata for `AnonymousFLARE/FLARE`;
- HF API metadata for `NJU-LINK/OmniVideoBench`;
- HF API metadata for `longvideobench/LongVideoBench`.

Failed checks:

- Commons API for `cand-061`: first proxy connect timeout, then HTTP 403;
- Commons API for `cand-056`: first proxy connect timeout, then HTTP 403;
- NASA normalization for `cand-023`:
  `OFFICIAL_PAGE_TITLE_MARKER_NOT_FOUND`.

The Commons outcomes are access/endpoint failures, not missing-file findings.
The NASA outcome is an identity contradiction requiring a hold, not a harmless
parser warning.

## Repaired interpretation

The parent HF API responses omitted optional sibling fields that had existed in
pinned repository snapshots. The old merge path overwrote pinned sizes/blob IDs
with null or empty values. The repaired merge now preserves stronger pinned
values when a live field is absent and records any different non-empty value as
an explicit fail-closed conflict.

A bounded official Commons item-page HTML fallback is available on the next
live run if the API remains blocked. It can confirm only the page/filename
identity marker. It cannot replace API evidence for revision, hash, size,
original URL, license, duration, or audio.

## Candidate decision

Active public ordering after identity reconciliation:

1. `cand-061` — primary speech-oriented Commons candidate; API metadata still
   unresolved.
2. `cand-048` — primary NOAA candidate; current title and 3,000 s page duration
   coherently matched.
3. `cand-051` — primary NOAA candidate; current title and 3,720 s page duration
   coherently matched.
4. `cand-056` — speech-oriented Commons reserve; API metadata still unresolved.

`cand-023` is `STALE_OR_MISMATCHED_ID_HOLD` and is excluded from active
primary/reserve recommendations. The captured response behavior cannot prove
whether SVS 11205 was repurposed, became stale, or was incorrectly mapped in
the local source data. A replacement URL must come from direct first-party
evidence; none is proposed here.

The exact FLARE and OmniVideoBench objects remain deferred compatibility
objects. Pinned size/hash/blob/revision evidence is preserved, but exact
duration, independently decoded audio, and item-level processing/annotation
rights remain unresolved.

## Exact next action

The parent may rerun the repaired **metadata-only** live command. If Commons API
access still fails, inspect the official item-page fallback result without
promoting it beyond identity confirmation. Continue item-scoped identity and
authority work for `cand-061`, `cand-056`, `cand-048`, and `cand-051`.
Investigate `cand-023` separately; do not select a substitute URL by inference.

The machine-readable authorization state remains:

```json
{
  "authorized_for_stream_header_preflight": [],
  "authorized_for_full_acquisition": [],
  "authorized_for_transfer": []
}
```
