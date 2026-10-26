# Mini-pilot new-source dossier preflight

**Date:** 2026-09-22  
**Decision:** `MINI_PILOT_NEW_SOURCE_DOSSIERS_REPAIR`  
**Evidence mode:** saved local evidence only; no network, downloads, or new probes

## 1. Boundary and result

This finalization read the frozen source-pool plan and all **44**
files already present under
`data/restricted/source_dossiers/mini_pilot_v1/evidence/`. Those files total
**645,319 bytes** and record
**624,677 HTTP response-body
bytes**. HTTP request-header wire bytes were not recorded, so they are not
invented here.

No full media was downloaded. No HLS media segment, original Commons WebM,
USGS video, transcript, clip, frame, or audio payload was downloaded. The
saved NASA `.m3u8` is a 1,960-byte master manifest, not a media rendition.
No temporary media buffer was created, so deletion is
`NOT_APPLICABLE_NO_MEDIA_PAYLOAD_FETCHED`.

No human annotation was performed. No controller/evaluator keys or restricted
labels were accessed.

No source meets the conservative `GO_TO_BOUNDED_ACQUISITION` rule. The rule
requires both an exact official/owner-controlled route and a genuinely
supported processing/annotation boundary. Therefore **0 of 4** new source
groups are eligible and the overall state is repair.

## 2. Per-source decisions

| Source | Decision | Exact-route result | Recorded response-body bytes | Saved evidence bytes |
|---|---|---|---:|---:|
| `SG-USGS-SHIFT-CURVES` | `REPAIR_METADATA_OR_RIGHTS` | No exact object; saved USGS responses are WAF/403/405 | 7,974 | 13,294 |
| `SG-USGS-SIX-ERUPTIONS` | `REPAIR_METADATA_OR_RIGHTS` | No exact object; saved USGS responses are WAF/405 | 6,447 | 9,688 |
| `SG-NASA-PATHFINDERS` | `REPAIR_METADATA_OR_RIGHTS` | Exact NASA+ HLS master `output/11211.m3u8`; no segment/container parse | 598,661 | 608,582 |
| `SG-COMMONS-BLOCKCHAIN` | `REPAIR_METADATA_OR_RIGHTS` | Exact Commons original metadata; original not fetched; range behavior untested | 11,595 | 13,755 |

### `SG-USGS-SHIFT-CURVES`

`REPAIR_METADATA_OR_RIGHTS`. The archive contains only failed USGS responses:
CloudFront 403 denials or AWS WAF CAPTCHA/405 bodies. The frozen plan records
prior observations of the title, 01:17:31 duration, Public Domain marking, and
Download Video/Transcript controls, but the current evidence directory does
not preserve a successful official item page and contains no exact video or
transcript URL. Object length, MIME, ETag, Last-Modified, range support,
container duration, streams, codecs, time base, and source lineage remain
unfrozen. Processing and annotation authority is not established by WAF
responses.

### `SG-USGS-SIX-ERUPTIONS`

`REPAIR_METADATA_OR_RIGHTS`. All saved landing and copyright requests are
2,149-byte AWS WAF human-verification responses with HTTP 405. The plan's
00:55:55, Public Domain, and download-control observations are not backed by a
successful archived page in this dossier. The exact video/transcript objects
and every technical identity field remain unknown. Photograph, map,
observatory/partner footage, music, audience, processing, and annotation
boundaries also remain held.

### `SG-NASA-PATHFINDERS`

`REPAIR_METADATA_OR_RIGHTS`. Saved first-party NASA+ evidence genuinely binds:

- post `2391`, content-id `9199`, title, and 3,600-second runtime;
- the exact NASA+ HLS master at asset `11211`;
- a no-redirect final host of `nasaplus.akamaized.net`;
- MIME `application/x-mpegURL`, ETag
  `"d7385fa64fa464adf4810c1464062354:1694525641.792554"`,
  Last-Modified `Tue, 12 Sep 2023 13:34:01 GMT`, and manifest-level
  `Accept-Ranges: bytes`;
- advertised H.264/AAC A/V variants, an audio-only variant, and in-stream
  English closed captions.

That is sufficient to freeze the master route, but not to authorize bounded
media acquisition. No segment was fetched, no container was parsed, and no
exact media duration/time base/synchronization/hash was measured. More
importantly, every saved JPL item/policy request is a 403 response. General
NASA guidance warns that third-party material conveys no downstream rights
and that source disclosure implies no permission; it does not clear this
documentary's score, archive/partner footage, JPL/Caltech material, marks, or
likenesses. The component-level processing/annotation boundary is unresolved.

### `SG-COMMONS-BLOCKCHAIN`

`REPAIR_METADATA_OR_RIGHTS`. The official MediaWiki API provides unusually
strong metadata identity: pageid `126021487`, current oldid `1032015587`,
original upload timestamp and uploader, exact original URL, size
`82,285,120`, MIME `video/webm`, SHA-1
`53f1de165f9b9c98a6bf1562315fb6ce5a4a61cc`, VP9 video, Opus stereo audio,
and duration **2,354.101 seconds (39:14.101)**.

The frozen plan's **3,656-second (01:00:56)** duration does not describe this
exact object and must be corrected. The API states that the file was imported
from YouTube video `hXBZ-BXfCSY`, names Molly White as author, and reports
CC BY 3.0 with required attribution to Molly White and no share-alike term.
However, it also exposes `License review needed (video)` and a `LicenseReview`
template. Saved evidence does not independently establish recording-owner
authority or the license scope for slides, websites, screenshots, marks, and
sensitive examples. The original object's range behavior was not tested and
the WebM was not downloaded or decoded.

## 3. Use and release boundary

For all four sources:

- acquisition: **HOLD**;
- internal processing: **HOLD**;
- human annotation: **HOLD**;
- raw-media release: **NOT AUTHORIZED**;
- clip/frame/audio release: **NOT AUTHORIZED**;
- transcript release: **NOT AUTHORIZED**;
- annotation release: **HOLD** pending source-specific attribution and rights;
- derived-feature release: **HOLD** pending non-reconstructiveness and rights.

Public availability, a government host, a general agency policy, or a
repository license field is not treated as sufficient item/component
authorization.

## 4. Exact missing repair/replacement capacity

Four eligible new-source positions are still required. If none of the current
records can be repaired, the exact minimum replacement count is **four**:

1. **Instructional/procedural field demonstration:** repair
   `SG-USGS-SHIFT-CURVES`; otherwise replace it with one distinct 20–90 minute
   low-privacy institutional procedural A/V source with successful official
   item/license snapshots, exact first-party video/transcript routes, and
   affirmative processing/annotation authority.
2. **Volcanology public information:** repair
   `SG-USGS-SIX-ERUPTIONS`; otherwise independently dossier a distinct USGS
   Public Lecture such as *Volcano Watchers* or *Unrest at Long Valley
   Caldera* under the same route, transcript, rights, and component gates.
3. **Engineering/mission history:** repair `SG-NASA-PATHFINDERS` only if
   JPL/Caltech and documentary-component authority can be established;
   otherwise replace it. `cand-005` *Planetary Defenders* and `cand-008` *The
   Changing Face of Mars* are only leads and are not eligible without fresh
   exact-route and component-rights dossiers.
4. **Technology-policy lecture:** repair `SG-COMMONS-BLOCKCHAIN` by resolving
   recording-owner authority and component scope for oldid `1032015587`;
   otherwise use an owner-controlled/institutional lecture with an explicit
   recording license and cleared slides/privacy. `cand-059` *Before Vermont*
   remains only an unapproved lead.

## 5. Evidence archive and files

Every saved evidence path, byte count, and SHA-256 appears in its per-source
JSON dossier:

- `data/restricted/source_dossiers/mini_pilot_v1/SG-USGS-SHIFT-CURVES.json`
- `data/restricted/source_dossiers/mini_pilot_v1/SG-USGS-SIX-ERUPTIONS.json`
- `data/restricted/source_dossiers/mini_pilot_v1/SG-NASA-PATHFINDERS.json`
- `data/restricted/source_dossiers/mini_pilot_v1/SG-COMMONS-BLOCKCHAIN.json`

Aggregate status:

- `data/rehearsal_plan/mini_pilot_source_dossier_status.json`

## 6. Next authorized action

Do **not** acquire media. In a separately authorized task, obtain the missing
successful official metadata/rights evidence and named processing/annotation
approval, or dossier four qualifying replacements. Then rerun this gate. Only
a source that separately passes exact route, bounded technical identity,
processing, annotation, component, privacy, and lineage checks may advance to
`GO_TO_BOUNDED_ACQUISITION`.
