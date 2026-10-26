# Mini-pilot four-source exact acquisition

**Date:** 2026-09-23  
**Decision:** `MINI_PILOT_FOUR_SOURCE_ACQUISITION_READY`  
**Scope:** restricted noncommercial custody and local validation only

## Outcome

All 4 authorized source groups were acquired from the exact frozen first-party routes, validated locally with PyAV, and atomically promoted. No mirror, YouTube, Vimeo, Internet Archive, login, cookie, or terms-acceptance route was used.

## Per-source results

| Source | Primary media bytes | Primary SHA-256 | Duration | B/M/E video+audio decode | Transcript/caption |
|---|---:|---|---:|---|---|
| `SG-OXFORD-QM-001` | 302,443,579 | `c83b4e0ed82e20bfed1cab701057ac16c6c13872f1fae9f7e56b65ae17dd0bcc` | 2645.280000 s | PASS | transcript 48568 B `cfd9fb3f2a32bd1e128e9fea0ec36e7b2cb716932d22d4644a355366e747dcd3` |
| `SG-OXFORD-DHL-CONSCIOUSNESS` | 369,848,995 | `6748569f9e9ac6a49985fa5410461f60fadba4054a28a4cd8ede9785c217f33a` | 2918.760000 s | PASS | transcript 53415 B `e59234aa60c911d457ddfe851c64c4ce93ed3befa4c8ad5cb59335424fa8b1a5` |
| `SG-MIT-RES12-003-L01` | 84,051,067 | `8fe1fd3c25cae687735aaecbcc5a6aa7bd9a668c310bd579622372ed05449889` | 2859.933333 s | PASS | captions 97032 B `f2a664bfa20696bb45115bbcffc4f60bbef0cbaa6e93db072b052afa45d7a742`; transcript 77130 B `7d3c5c6f75dfdc5e8c0c069969a12d761c9433fc6738a936aeebc5fa6e217311` |
| `SG-YALE-PHYS200-L01` | 377,169,329 | `fff84141b2791164b52847c35f988456699dd0f350b8853c8b1cb451f4430016` | 4400.900907 s | PASS | transcript 67399 B `102351dfd4fc464242a1e2b330ccd7933c370b841f0d10378a0649d1114a02f0` |

## Validation and custody

- Every primary object matched the dossier URL, final host, byte length, MIME, ETag, and Last-Modified immediately before transfer.
- Every payload matched its expected byte count; HTML/error-body and file-signature checks passed.
- PyAV opened each container, matched declared duration/streams within tolerance, decoded finite beginning/middle/end audio and video, found synchronized timestamps, and completed a full demux-to-EOF scan without error.
- SRT/WebVTT/PDF/HTML transcript or caption syntax and identity checks passed. MIT and Yale retained payload hashes exactly match the archived dossier evidence hashes.
- Staging contained no symlinks or unexpected executable, pickle, or archive payloads.
- Source directories are mode `0700`; retained files and manifests are mode `0600`.

## Transfer accounting

- Aggregate retained source-directory bytes: **1,133,952,259**
- Aggregate acquired payload bytes (media plus required transcripts/captions): **1,133,856,514**
- Incomplete transfers: **0**
- Failed transfers: **0**
- Retained resumable partials: **0**

## Rights and use boundary

- Oxford sources: CC BY-NC-SA 2.0 UK; preserve attribution/share-alike and screen slides, figures, likeness/voice, quotations, and images before any release.
- MIT source: CC BY-NC-SA 4.0 and the dossier-recorded MIT OCW terms; preserve attribution and noncommercial controls; public redistribution remains unapproved.
- Yale source: course-level CC BY-NC-SA 3.0 notice with unresolved third-party/privacy/personality boundaries; restricted internal use only and public release remains blocked.
- This task performed no human annotation, model inference, candidate-family generation, controller/evaluator key access, public release, redistribution, or commercial use.

## Changed paths

- `data/restricted/mini_pilot_sources_v1/acquisition_manifest.json`
- `data/restricted/mini_pilot_sources_v1/SG-OXFORD-QM-001/`
- `data/restricted/mini_pilot_sources_v1/SG-OXFORD-DHL-CONSCIOUSNESS/`
- `data/restricted/mini_pilot_sources_v1/SG-MIT-RES12-003-L01/`
- `data/restricted/mini_pilot_sources_v1/SG-YALE-PHYS200-L01/`
- `docs/review/mini_pilot_four_source_acquisition.md`
- `orchestration/results/132_four_source_exact_acquisition.txt`

## Next authorized action

Proceed only to restricted local processing and candidate-family mining under the existing dossier boundaries, preserving attribution and component/privacy flags. Restricted human annotation may occur only in a later separately authorized task; public release and commercial use remain prohibited.

Final decision: `MINI_PILOT_FOUR_SOURCE_ACQUISITION_READY`
