# Secondary-pair bounded A/V technical closure v1

**Final marker:** `SECONDARY_PAIR_AV_TECHNICAL_CLOSURE_READY`  
**Evidence date:** `2026-10-13`  
**Mode:** deterministic, offline validation of retained headers, parsed container metadata, official metadata, and governance records.

## Decision summary

| Asset | Technical readiness | Authority closed | Exact acquisition now |
|---|---:|---:|---|
| EPIC `P23_102` | yes | yes for CC BY-NC noncommercial acquisition | `AUTHORIZED_NOW_CC_BY_NC_NONCOMMERCIAL_ONLY` |
| CaptainCook4D `25_109` GoPro 360p | yes | no | `NOT_AUTHORIZED_GOVERNANCE_AUTHORITY_OPEN` |

The CaptainCook4D result deliberately separates a technically usable exact route/object from legal-governance authority. Technical readiness does not grant acquisition authority.

## Exact-object and range validation

| Asset | Exact identity binding | 206 exchanges | Total bytes | Route |
|---|---|---:|---:|---|
| EPIC `P23_102` | `EXACT_OFFICIAL_PATH_ETAG_SIZE_AND_MANIFEST_MD5_BOUND` | 4 | 10814161307 | public official data.bris route |
| CaptainCook4D `25_109` | `EXACT_OFFICIAL_SHARED_TOKEN_FILENAME_AND_SIZE_BOUND` | 3 | 201079756 | official Box token through the completed star route; hy timed out with zero bytes |

Every accepted exchange returned `206`, a response-length-consistent `Content-Range`, `video/mp4`, and the same asset total. EPIC also matches its official path, ETag, last-modified value, and manifest MD5 metadata. CaptainCook4D matches the official shared-static token, the `25_109_360p.mp4` disposition filename, redirect host class, and the common exact byte total. No CaptainCook4D full-object checksum is claimed.

## Container facts

| Fact | EPIC `P23_102` | CaptainCook4D `25_109` |
|---|---:|---:|
| `moov` absolute offset | 10809773840 | 198755331 |
| `moov` bytes | 4387467 | 2324425 |
| `moov` ends at object EOF | yes | yes |
| Video codec | `hvc1` | `avc1` |
| Dimensions | 1920x1080 | 640x360 |
| Video duration (s) | 3569.52 | 2126.958167 |
| Audio codec | `mp4a` | `mp4a` |
| Audio channels | 2 | 2 |
| Audio sample rate (Hz) | 48000 | 48000 |
| Audio duration (s) | 3569.536 | 2126.933333 |
| Absolute A/V duration delta (s) | 0.016 | 0.024833 |

Both exact objects contain native video and audio tracks in the same `moov` container. The duration deltas are bounded container facts, not sample-level synchronization, semantic, speech, or content claims.

## Rights and governance

### EPIC `P23_102`

Exact acquisition is authorized now only for a noncommercial use that uses the official public route and complies with CC BY-NC 4.0: appropriate credit, a license reference, and modification notice where applicable. This closure does not authorize raw-media release.

### CaptainCook4D `25_109`

The official README statements for Apache-2.0, University of Florida IRB approval, and written participant consent are verified. However, the operative linked IRB and consent documents are not archived, and identity-bearing processing authority remains open. Therefore the route/object is technically ready but exact acquisition is not authorized now.

## Deleted payload state

The three authoritative `/tmp` evidence directories contain exactly the pinned header, summary, and parsed-JSON files. Retained media payload files: **0**. Retained media payload bytes: **0**. The sparse head/tail response bodies used to derive the metadata were deleted.

## Claim boundary

This closure makes no semantic, V+S+A, human-review, SES, H-tier, Gate A, or sample-level A/V-sync claim. It performs no network access and reads no media payload.

## SECONDARY_PAIR_AV_TECHNICAL_CLOSURE_READY
