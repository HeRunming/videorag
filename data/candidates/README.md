# AV-TRACE Pilot-0 metadata-only source candidates

**Verification date:** 2026-09-05  
**Scope:** candidate discovery only; no media, subtitle, transcript, thumbnail, or audio/video bytes were downloaded.  
**Legal posture:** this inventory is not legal advice. No row is rights-cleared and no row passes Gate A.

## Files

- `source_candidates.csv` — 76 candidate assets from NASA, NARA, NOAA, and Wikimedia Commons, including row-level `verification_result` and `verification_notes`.
- `top30_review_queue.csv` — ranked human-review queue selected for source/domain/modality variety and likely temporally separated evidence, with the same audit fields.
- `source_family_notes.md` — source-specific interpretation, risk, and follow-up notes.
- `../../docs/review/candidate_pool_review.md` — independent 2026-09-05 audit of all top-30 rows and a stratified 20-row reserve sample.

## Status semantics

- `candidate_review`: legacy discovery-stage status meaning an official landing record and key metadata appeared concrete enough for human rights/content review. The 2026-09-05 independent audit conservatively downgraded every such row; none currently remains.
- `metadata_only_hold`: useful discovery lead, but one or more critical facts remain unresolved (for example exact runtime, item/revision identity, direct authorized acquisition route, or embedded-component rights).
- `reject`: known incompatibility with the frozen Pilot-0 source rule, such as duration below 20 minutes.

A status may only move through the project acquisition-manifest process. Candidate discovery does not substitute for a manifest, evidence snapshot, named reviewer, or affirmative decisions for acquisition, processing, derivatives, annotations, transcripts, and raw-media release.

## Pool summary

| Source family | Candidate pool | Top-30 queue |
|---|---:|---:|
| NASA | 25 | 12 |
| NARA | 19 | 6 |
| NOAA | 10 | 4 |
| Wikimedia Commons | 22 | 8 |
| **Total** | **76** | **30** |

After the independent audit, pool statuses are 72 `metadata_only_hold` and 4 `reject`; no row remains `candidate_review` or rights-cleared. The top-30 contains 28 `metadata_only_hold` and 2 `reject` records. Holds remain in the queue only as discovery leads and require item-level rights and metadata resolution.

## Important data conventions

- The files contain no raw-media URL intended to bypass a landing page. Most supplied URLs were confirmed as official landing or policy pages, but the audit identified mismatched, noncanonical, or unverified paths; consult `verification_result` and `verification_notes`.
- `approx_duration` is metadata-only. A leading `~` means the exact duration must be confirmed. Every selected asset must ultimately fall within the frozen 20–90 minute interval.
- `source_revision_or_access_date` records the available source revision or the access date. Commons records are intentionally held until an exact `pageid` and `oldid` are pinned.
- `stable_source_id` is an official identifier where verified. Where an official page has no exposed immutable ID, it is a transparent page-derived discovery key and must not be mistaken for an archival identifier.
- `metadata_verification_level` distinguishes directly verified landing-page fields from title-level or discovery metadata needing another pass.
- Transcript/caption availability was recorded without fetching transcript or subtitle bytes.
- Source pages that merely embed YouTube or another platform remain metadata-only unless an official authorized acquisition/export path is confirmed. Generic downloaders and cookie-based extraction are prohibited.
- Candidate durations and modality descriptions are screening estimates, not media-probe results.

## Human review order

For each top-30 row, the reviewer should first:

1. resolve exact item identity, duration, publisher/rightsholder, and authorized acquisition path;
2. capture an immutable or hashed rights-evidence snapshot;
3. decide whether music, subtitles, third-party inserts, marks, identifiable people, minors, and sensitive content can be accepted;
4. confirm that the complete asset—not only its landing page or repository metadata—permits the intended acquisition, local processing, public derivatives/transcripts, and raw redistribution;
5. inspect the asset only after Gate A authorizes transfer, then confirm usable video, speech, non-speech audio, temporal separation, and source-disjointness.

## Deduplication and safety

Obvious mirror/reupload pairs were represented by one canonical official landing page. Closely related episodes in a series remain separate candidates but should be source-concentration checked before final selection. Records with war imagery, racist historical material, medical contexts, minors, or cultural sensitivity are explicitly warned or held; they should be rejected if the privacy/safety burden is not justified by benchmark value.
