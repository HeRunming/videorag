# AV-TRACE candidate-pool source metadata and rights-evidence review

**Review date:** 2026-09-05  
**Reviewer role:** independent metadata-only source and rights-evidence review  
**Scope:** all 30 rows in `top30_review_queue.csv`, plus a stratified 20-row sample outside the top 30  
**Media handling:** no video, audio, subtitle, transcript, or thumbnail files were downloaded  
**Legal posture:** this is a source-metadata and evidence-sufficiency audit, not legal advice

## Executive decision

The pool remains **Gate A NO-GO**. No reviewed asset is rights-cleared. All surviving reviewed rows are `metadata_only_hold`; three newly identified rows are rejected, and the pre-existing short-duration reject remains rejected.

The audit found material metadata quality problems: one definite NARA title/identifier mismatch, one incorrect NARA identifier, one noncanonical Commons filename, two NASA titles over the 90-minute ceiling, and numerous inaccurate or unsupported duration values. General NASA, NARA, and NOAA policy pages are useful warnings or procedural references, but none substitutes for an asset- and component-specific rights record covering acquisition, processing, derivatives, transcripts, annotations, and worldwide raw redistribution.

## Counts

### Top-30 queue

| Measure | Count |
|---|---:|
| Reviewed | 30 |
| Verified without field correction | 9 |
| Verified with confirmed correction | 9 |
| Downgraded from `candidate_review` to `metadata_only_hold` | 16 |
| Rejected | 2 |
| Unresolved | 10 |
| Broken/unverified canonical URL or guessed-path findings | 4 |
| Rights-cleared | 0 |

The four top-30 URL/path problems are `cand-027` (official URL but mismatched asset), `cand-063`, `cand-064`, and `cand-076` (the exact official file page could not be located at the supplied path). `cand-072` also had a noncanonical path, but it was corrected to a confirmed official Commons file page and therefore is not counted as remaining broken.

### Stratified reserve sample outside the top 30

| Measure | Count |
|---|---:|
| Reviewed | 20 |
| NASA / NARA / NOAA / Commons strata | 8 / 4 / 6 / 2 |
| Verified without field correction | 4 |
| Verified with confirmed correction | 8 |
| Rejected, including retained prior reject | 2 |
| Unresolved | 6 |
| Broken/unverified supplied URL findings | 2 |
| Rights-cleared | 0 |

The two reserve URL findings are the generic 2025 Wikimania paths in `cand-074` and `cand-075`; official 2025 event/program material exists, but the exact Commons file pages supplied were not verified and no replacement filename was guessed.

### Audited set and full CSV after corrections

- **Audited set:** 50 distinct rows; 30 verified in total (13 without correction and 17 with correction), 16 unresolved, and 4 rejected. These outcome categories are mutually exclusive.
- **Status changes:** all 16 audited `candidate_review` rows were downgraded to `metadata_only_hold`; no row is or was marked rights-cleared.
- **Broken-URL count:** 0 URLs were conclusively established as HTTP-broken. Six supplied URLs nevertheless failed URL-integrity review because the path was unverified/guessed or the URL resolved to a mismatched asset: four in the top 30 and two in the reserve sample.
- **Full 76-row pool after edits:** 72 `metadata_only_hold`, 4 `reject`, 0 `candidate_review`, and 0 rights-cleared.
- **Unaudited reserve:** 26 rows remain explicitly labeled `not_reviewed_this_audit`; their prior metadata-only status is not a new verification result.

## Method and decision rules

1. Open or search for each canonical landing page on the named official domain only.
2. Compare the official display title and exposed identifier to the CSV title/ID pair.
3. Record an exact duration only when an official primary page exposed one. If not exposed or not independently readable, clear the duration field rather than preserve an estimate as if verified.
4. Treat an official landing page as identity evidence, not as rights clearance.
5. Reject a confirmed duration outside the frozen 20–90 minute interval or a confirmed title/identifier mismatch that points to a different asset.
6. Treat generic policy pages as source-family context only. Missing item restrictions, component credits, uploader authority, revision pinning, or authorized transfer route requires `metadata_only_hold`.
7. Do not follow or extract raw media URLs, embedded player streams, captions, transcripts, thumbnails, or downloadable files.

`verification_result` and `verification_notes` columns were added to both candidate CSVs so the row-level basis is machine-readable. The controlled results used are `verified`, `verified_with_corrections`, `unresolved`, `rejected`, and `not_reviewed_this_audit`.

## Official rights-evidence findings

### NASA

NASA's current media guidance says NASA content is generally usable for educational or informational purposes but explicitly excludes identifiable third-party copyrighted material and separately addresses names, insignia, logos, likenesses, and commercial use. Consequently, the general NASA Brand Center page cannot clear a complete documentary with music, partner footage, archival inserts, contractor material, or participant likenesses. NASA+ and SVS pages were accepted as official identity/metadata records only.

All NASA rows reviewed remain on hold unless rejected for duration. JPL productions also need a Caltech/JPL production and component-rights determination rather than an inference from NASA hosting.

### NARA

NARA's motion-picture permissions guidance is the more relevant family-level evidence page and now replaces the generic research landing page in both CSVs. NARA states that not all holdings are public domain and that users are responsible for copyright and other restrictions. Catalog custody, availability, or a NARA channel upload is therefore not affirmative asset-level clearance.

Several live catalog records could not be rendered into independently readable metadata in this review environment. Those rows were marked unresolved rather than accepted from the URL alone.

### NOAA

The NOAA disclaimer explains that government-produced information is generally not copyrighted, while materials credited to non-NOAA sources may be protected and NOAA logos are not freely reusable. Ocean Today webinar pages establish official titles and stated lengths, but guest contributions, expedition footage, music, slides, charts, speaker releases, and an authorized acquisition/export route still require item-level evidence.

### Wikimedia Commons

A Commons file page can state a free license, but Commons' own reuse guidance places responsibility on the reuser to verify the license and comply with attribution or share-alike requirements; other rights may remain. Each candidate therefore still needs a pinned page ID and revision ID, exact license/version, author/source chain, uploader authority, and component review for slides, recordings, music, software screens, quoted media, and audience likenesses.

## Top-30 material findings

### Confirmed corrections

- `cand-001`: runtime corrected to `00:28:26`.
- `cand-005`: unsupported `00:53:14` replaced by `~01:15:00`, based on an official U.S. government screening notice; the exact NASA+ runtime was not exposed in the bounded page result.
- `cand-014`: runtime corrected to `00:57:32`.
- `cand-016`: runtime corrected to `01:47:10` and status changed to `reject` because it exceeds 90 minutes.
- `cand-017`: runtime corrected to `00:59:35`.
- `cand-012`: runtime corrected to `00:55:42`.
- `cand-030`: runtime normalized to `00:40:22`; official NARA metadata corroborates identifier 35956.
- `cand-031`: identifier and landing page corrected from NAID 35959 to NAID 38755. NAID 35959 is a different record, “Miscellaneous German Films.” The exact runtime remains approximate.
- `cand-052`: runtime corrected to `01:03:00` from the official NOAA page.
- `cand-072`: generic guessed Commons title/path replaced with the confirmed official file title `Wikimania 2024 - Gdańsk Main Hall - Day 1 - Opening ceremony & Wikimedian of the Year Awards.webm`; duration corrected to `00:52:28`.

### Rejections

- `cand-016` — `JPL and the Space Age: The Breaking Point`: official runtime `01:47:10`, outside the frozen range.
- `cand-027` — `Project Gemini: A Bridge to the Moon`: NAID 45017 is associated by official NARA transcript metadata with `The Eagle Has Landed` (Apollo 11), so the supplied title/ID pair is a mismatched asset. No replacement ID was guessed.

### Unresolved top-30 rows

- `cand-006`: official NASA+ title/page found; exact runtime not verified.
- `cand-026`, `cand-040`, `cand-042`: official NARA URLs, but live title/ID/runtime/use-restriction fields were not independently readable.
- `cand-059`, `cand-061`, `cand-057`: official Commons title pages found, but exact duration and pinned revision/license provenance were not verified.
- `cand-063`, `cand-064`: exact official Commons file page not located.
- `cand-076`: official Wikimania 2025 GLAM event context exists, but exact supplied Commons filename/path was not verified.

## Reserve-sample findings

The 20-row sample was selected across every source family and included high-risk series, war-film records, webinars, and recent Commons event uploads.

### Confirmed reserve corrections

- `cand-008`: `01:18:51`.
- `cand-009`: `00:31:15`.
- `cand-010`: title corrected to `JPL and the Space Age: Explorer One`; runtime `00:53:20`.
- `cand-013`: `01:00:00`.
- `cand-015`: `00:59:56`.
- `cand-018`: `01:52:15`; rejected as over 90 minutes.
- `cand-019`: `01:29:24`.
- `cand-047`: `00:30:00`, not approximately one hour.
- `cand-049`: `00:41:00`, not approximately one hour.

`cand-029` remains rejected because its 18-minute duration is below the frozen minimum. NOAA rows `cand-045`, `cand-046`, `cand-053`, and `cand-054` had official title/length support but remain rights holds.

Reserve rows `cand-020`, `cand-028`, `cand-033`, `cand-034`, `cand-074`, and `cand-075` remain unresolved, and their unverified duration values were removed.

## Duplicate/reupload and source-balance assessment

No reviewed URL is an explicit raw-media bypass or third-party mirror. The principal identity risks were instead guessed/stale Commons paths and NARA identifier mismatches.

Obvious concentration families remain:

- **JPL and the Space Age:** ten rows in the full pool and four in the top 30. These are separate episodes, not byte-identical duplicates, but they share production, archive, narration, rights, and domain characteristics. Treat them as one high-correlation source family for selection caps.
- **NARA `Why We Fight`:** seven closely related series entries in reserve. They are not substitutes for source diversity and have repeated propaganda, foreign-footage, music, and safety concerns.
- **NARA `The Big Picture`:** five entries with shared Army production conventions and likely correlated rights/content risks.
- **NOAA Ocean Today webinars:** all ten NOAA rows belong to one presentation format and host family; partner clips and guest content recur.
- **Wikimania opening/closing ceremonies:** multiple annual event records are near-duplicate formats and may include recurring music, stage visuals, and crowd likenesses.
- **Topical re-use families:** Apollo/Voyager/Hubble candidates across NASA and NARA may reuse the same archival footage even when the programs and landing records are distinct. Later media inspection must perform component-level duplicate detection after Gate A.

The nominal top-30 family mix remains NASA 12, NARA 6, NOAA 4, and Commons 8. That is numerically diverse by host, but not independent by production family or modality. NASA/JPL and NARA dominate mission/archive documentary material, while NOAA and Commons are primarily webinar/lecture speech. The pool is therefore speech-heavy; claims of balanced vision, ambient audio, speech, and cross-modal evidence are not supported by metadata alone.

## File changes

Modified only candidate metadata files, as permitted:

- `data/candidates/source_candidates.csv`
- `data/candidates/top30_review_queue.csv`

Changes include confirmed title/ID/URL/duration corrections, conservative status changes, the NARA permissions evidence URL, and row-level verification fields. No media bytes or derivative artifacts were created.

## Required follow-up before any acquisition

1. Obtain asset-level rights records and immutable evidence snapshots for every proposed transfer.
2. Resolve all `unresolved` identity/duration findings from a directly readable official record or written rightsholder confirmation.
3. Pin Commons `pageid`/`oldid`, license version, attribution, author/source chain, and uploader authority.
4. Review component credits for music, stock/archive footage, partner material, slides, trademarks, and identifiable people.
5. Record an expressly authorized acquisition method; an embedded player or public stream is not enough.
6. Enforce production-family caps and conduct post-authorization duplicate-footage analysis before selecting a source-disjoint core.

**Conclusion:** the corrected pool is suitable only as a metadata discovery inventory. It is not a cleared acquisition queue and must not be used to satisfy the project's 20–30 rights-cleared public-core target.
