# LongVideoBench five-member tar-range preflight

**Generated:** `2026-09-08T08:48:05Z`  
**Repository:** `longvideobench/LongVideoBench`  
**Pinned revision:** `60d1c89c1919a198b73be39c2babb213b29d6a5c`  
**Decision:** **GO_HEADER_INDEX_COMPLETE**

## Live result

- Exact video members located from validated tar headers: **5/5**.
- Exact subtitle members located from validated tar headers: **5/5**.
- Video tar headers read: **3992**; metadata-body bytes read: **0**.
- Subtitle tar headers read: **9345**; metadata-body bytes read: **0**.
- HTTP response-body bytes read: **6,830,592** of **268,435,456** allowed.
- Largest response body: **512** bytes of **8,388,608** allowed.
- Effective hosts (query strings omitted): `us.aws.cdn.hf.co`.
- No target MP4 payload, complete multipart part, complete subtitle archive, token, cookie, or Authorization header was written.

`tar_end_global_offset` / `tar_end_offset` are exclusive payload endpoints. HTTP ranges in the CSV are inclusive.
Targets are matched by exact POSIX basename (never substring/suffix); the full stored member path is retained.

## Target videos

| Candidate | Video ID | Stored member | Bytes | Header offset | Data offset | Status |
|---|---|---|---:|---:|---:|---|
| `ccp-008` | `-PgbM2MhcYQ` | `videos/-PgbM2MhcYQ.mp4` | 62830440 | 21181553664 | 21181554176 | `LOCATED_HEADER_ONLY` |
| `ccp-009` | `-eRimFrm6kQ` | `videos/-eRimFrm6kQ.mp4` | 90220390 | 131314835456 | 131314835968 | `LOCATED_HEADER_ONLY` |
| `ccp-003` | `-7wwfGJXEZg` | `videos/-7wwfGJXEZg.mp4` | 153008405 | 11441267200 | 11441267712 | `LOCATED_HEADER_ONLY` |
| `ccp-011` | `H5vpBCLo74U` | `videos/H5vpBCLo74U.mp4` | 36357778 | 148729746944 | 148729747456 | `LOCATED_HEADER_ONLY` |
| `ccp-012` | `TMe7oXMJoSM` | `videos/TMe7oXMJoSM.mp4` | 238302656 | 57208697344 | 57208697856 | `LOCATED_HEADER_ONLY` |

## Target subtitles

| Candidate | Video ID | Stored member | Bytes | Header offset | Data offset | Status |
|---|---|---|---:|---:|---:|---|
| `ccp-008` | `-PgbM2MhcYQ` | `subtitles/-PgbM2MhcYQ_en.json` | 142437 | 115429376 | 115429888 | `LOCATED_HEADER_ONLY` |
| `ccp-009` | `-eRimFrm6kQ` | `subtitles/-eRimFrm6kQ_en.json` | 96086 | 78963712 | 78964224 | `LOCATED_HEADER_ONLY` |
| `ccp-003` | `-7wwfGJXEZg` | `subtitles/-7wwfGJXEZg_en.json` | 57351 | 61218304 | 61218816 | `LOCATED_HEADER_ONLY` |
| `ccp-011` | `H5vpBCLo74U` | `subtitles/H5vpBCLo74U_en.json` | 69540 | 50750976 | 50751488 | `LOCATED_HEADER_ONLY` |
| `ccp-012` | `TMe7oXMJoSM` | `subtitles/TMe7oXMJoSM_en.json` | 43973 | 110000640 | 110001152 | `LOCATED_HEADER_ONLY` |

## Authorization boundary

The parent session supplied that Hugging Face login is verified and the dataset gate has been passed. This run is limited to authenticated bounded metadata/header-only preflight. Full-corpus download remains prohibited. Target media acquisition, processing, annotation, and release remain separate later stages.
