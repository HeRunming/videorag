# Parent live metadata reconciliation

**Task:** 66  
**Date:** 2026-09-09  
**Source audit:** `data/rehearsal_plan/audio_asset_recon_live_evidence.json`

## Finding

The retained parent audit is a genuine metadata-only `PARTIAL` run: 11 request
records, 7 successful HTTP responses, and 169,359 metadata body bytes. It is
not replaced or edited by this task.

| Check | Parent outcome | Reconciled meaning |
|---|---|---|
| `cand-061` Commons API | connect timeout, then HTTP 403 | endpoint/access failure; file absence not established |
| `cand-056` Commons API | connect timeout, then HTTP 403 | endpoint/access failure; file absence not established |
| `cand-023` NASA page | HTTP 200, expected title absent | disputed title-to-ID mapping; identity hold |
| `cand-048` NOAA page | title and 3,000 s duration markers matched | coherent page-level identity/duration declaration only |
| `cand-051` NOAA page | title and 3,720 s duration markers matched | coherent page-level identity/duration declaration only |
| four HF repository APIs | HTTP 200 | repository metadata available; optional missing fields must not erase pinned facts |

No response proves a decoded audio stream, content modality, processing right,
annotation right, or transfer authority.

## Candidate drift decision

Local records bind `cand-023`, title `The World Avoided: Successful
Stratospheric Ozone Protection`, duration 2,243 s, to NASA SVS ID 11205. The
current official response at that page did not contain the expected title. The
audit retained the body hash and normalization result but not the HTML body, so
it cannot support a more specific claim that the page was repurposed rather
than that the local mapping was stale or wrong.

The scientifically honest disposition is therefore
`STALE_OR_MISMATCHED_ID_HOLD`. The old URL and historical duration remain in
the record for auditability, explicitly marked as disputed. `cand-023` is
removed from active primary recommendations and from item-scoped preflight
requests. No replacement URL is invented.

## Metadata merge repair

The repaired merge has these invariants:

1. `None`, absent keys, and empty strings from live metadata do not alter a
   pinned non-empty value.
2. Equal non-empty values are confirmations.
3. Different non-empty values are appended to `metadata_conflicts`; pinned
   values are preserved; candidate disposition becomes
   `METADATA_CONFLICT_HOLD`; and the live logical check fails.
4. Revision and route values follow the same rule as size, blob ID, hash, path,
   and duration.
5. The candidate evidence summary exposes disposition and conflicts.

Regression tests cover absent HF optional fields, conflicting HF sizes,
`cand-023` title mismatch behavior, and Commons item-page fallback limits.

## Commons fallback assessment

A safe fallback is implemented against each already-pinned official Commons
item page. It is a bounded HTML metadata GET subject to the same host,
content-type, redirect, and byte limits. It validates only that the expected
filename/title marker appears. It does not parse or infer original media URLs
or stream properties, and it never requests media bytes. Consequently, a
successful fallback reduces uncertainty about page identity but leaves exact
object and rights gates unresolved.

## Revised recommendation and gates

Active order: `cand-061`, `cand-048`, `cand-051`; reserve: `cand-056`.
`cand-023` is held. Compatibility HF objects remain deferred. Before any media
action, each selected item still needs an immutable exact object, duration in
1,200–5,400 seconds, explicit bounded-preflight/acquisition/processing
authority, component/privacy review, and later independent decoded-audio
verification.

All authorization arrays are empty.
