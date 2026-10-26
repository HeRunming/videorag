# LVB-01 downloaded-media audit

**Audit date:** 2026-09-09  
**Decision:** **CONDITIONAL_GO**

## Executive finding

The five MP4 files and five subtitle JSON files are intact, provenance-bound to
the frozen plan and acquisition manifest, confined to the restricted tree, and
usable for a **limited internal rehearsal**. Independently recomputed payload
bytes are exactly **581,129,056**, and all ten independently recomputed SHA-256
digests and sizes match the acquisition manifest and adjacent sidecars. No
partial, lock, orphan sidecar, duplicate payload basename, symlink, unexpected
payload, secret, or signed-URL indicator was found.

All five MP4 containers open and decode video frames at the beginning, middle,
and near end through bounded PyAV child processes. All five contain one H.264
video stream, but **none contains an audio stream**. Therefore these downloads
are not complete source AV assets: audio-based or ambient-audio rehearsal is not
technically available from the acquired MP4s. Each subtitle file parses and
provides an ordered, non-empty speech proxy with broad timeline coverage.

The host has PyAV 16.1.0, but no `ffprobe` or `ffmpeg` executable. The requested
external `ffprobe` check could therefore not be run. This tool limitation,
together with the absence of audio and caveats in cue-end semantics, is why the
decision is conditional rather than an unconditional go.

## Decision boundaries

| Question | Finding |
|---|---|
| Technically usable downloaded asset? | **Yes, conditionally:** video plus subtitle proxy; no embedded audio |
| Ready for limited internal rehearsal? | **Yes:** visual/subtitle workflows only, subject to the conditions below |
| Scientifically suitable AV-TRACE episode? | **Not established** |
| Rights/public-release eligible? | **Not established** |

Successful integrity checks and decoding do not establish modality necessity,
episode scientific quality, source-media rights, privacy clearance, or
public-release eligibility.

## Conditions for rehearsal

1. Treat every downloaded MP4 as **video-only**.
2. Do not run or represent an audio, ambient, speech-waveform, or full-AV
   rehearsal from these MP4s.
3. Subtitles may be used only as a source-level speech proxy. Four files have
   predominantly point-like, approximately 10 ms cue durations; use ordered
   start times and broad coverage, not cue end times as reliable speech spans.
4. Run the same audit in an environment with `ffprobe`/`ffmpeg` before treating
   the explicit external-tool requirement as closed.
5. Keep scientific suitability and rights/publication decisions as separate
   unresolved gates.

## Integrity and provenance

- Frozen plan:
  `data/acquisition_plan/lvb01_exact_asset_plan.json`
- Acquisition manifest:
  `data/restricted/lvb01/manifests/lvb01_acquisition_manifest.json`
- Machine-readable audit:
  `data/restricted/lvb01/manifests/lvb01_media_audit.json`
- Payload count: **10**
- Video subtotal: **580,719,669 bytes**
- Subtitle subtotal: **409,387 bytes**
- Aggregate: **581,129,056 bytes**
- All ten size/hash comparisons against plan, manifest, and sidecar: **PASS**
- All payload and sidecar files: mode `0600`
- Restricted root, video, subtitle, and manifest directories: mode `0700`
- Intermediate `raw` directory: mode `0755`, but not group/other writable and
  protected by the enclosing `0700` restricted root
- Path containment, regular-file checks, and symlink prohibition: **PASS**
- `.partial`, stale lock, orphan sidecar, duplicate basename, symlink,
  unexpected payload/file checks: **PASS**
- Plan, manifest, and all ten sidecars scanned for credential keys, token/signed
  query indicators, query-bearing URLs, and URL userinfo: **PASS**

The full recomputed SHA-256 values remain in the restricted audit JSON and are
not repeated in this non-restricted summary.

## Video results

`Δ` is `|decoded duration - candidate-pool metadata duration|`. Relative
differences are percentages.

| Candidate | Decoded duration | Expected | Δ | Relative Δ | Video | Audio | Geometry / rate | Decode smoke |
|---|---:|---:|---:|---:|---:|---:|---|---|
| `ccp-008` | 2987.080 s | 2987.080 s | 0.000 s | 0.000000% | 1× H.264 | 0 | 1280×720, 25 fps | beginning/middle/end PASS |
| `ccp-009` | 1540.872667 s | 1540.880 s | 0.007333 s | 0.000476% | 1× H.264 | 0 | 1280×720, 24000/1001 fps | beginning/middle/end PASS |
| `ccp-003` | 1515.200 s | 1515.200 s | 0.000 s | 0.000000% | 1× H.264 | 0 | 1280×720, 25 fps | beginning/middle/end PASS |
| `ccp-011` | 1805.125 s | 1805.130 s | 0.005 s | 0.000277% | 1× H.264 | 0 | 1276×720, 24 fps | beginning/middle/end PASS |
| `ccp-012` | 2805.1023 s | 2805.110 s | 0.0077 s | 0.000274% | 1× H.264 | 0 | 1280×720, 30000/1001 fps | beginning/middle/end PASS |

All containers identify as the QuickTime/MOV ISO-BMFF family, have positive
duration, have no zero-length streams, and match expected duration within the
audit tolerance `max(1 second, 0.1%)`. No decoded frames or derived media were
persisted.

The missing-audio result is not a decode failure: the containers report no
audio streams at all. Consequently no audio window could be tested.

## Subtitle results

Every subtitle is UTF-8 JSON with a top-level array. Every entry is an object
with keys `start`, `end`, and `line`. The audit did not print or persist full
subtitle text.

| Candidate | Entries | First timestamp | Last timestamp | Last/video | Empty | Order errors | Overlaps | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `ccp-008` | 1,229 | 2.450 s | 2977.500 s | 99.679% | 0 | 0 | 0 | 98.45% of cues ≤50 ms |
| `ccp-009` | 860 | 1.910 s | 1542.720 s | 100.120% | 0 | 0 | 0 | final cue 1.847 s beyond video; 94.19% ≤50 ms |
| `ccp-003` | 523 | 3.909 s | 1517.039 s | 100.121% | 0 | 0 | 0 | final cue 1.839 s beyond video; 90.25% ≤50 ms |
| `ccp-011` | 595 | 3.230 s | 1800.140 s | 99.724% | 0 | 0 | 0 | 99.83% of cues ≤50 ms |
| `ccp-012` | 475 | 0.810 s | 2785.630 s | 99.306% | 0 | 0 | 0 | no structural timeline warning |

All temporal values are finite and non-negative; every end is at or after its
start; starts are ordered; and no overlap was detected. The two small
end-of-video overruns are below the gross mismatch threshold and are recorded
as warnings. No obvious timeline mismatch was found.

## Initial modality evidence

| Candidate | Video stream | Audio stream | Subtitle/speech proxy | Ambient/non-speech |
|---|---|---|---|---|
| `ccp-008` | available | absent | available | unverified and unavailable in downloaded MP4 |
| `ccp-009` | available | absent | available | unverified and unavailable in downloaded MP4 |
| `ccp-003` | available | absent | available | unverified and unavailable in downloaded MP4 |
| `ccp-011` | available | absent | available | unverified and unavailable in downloaded MP4 |
| `ccp-012` | available | absent | available | unverified and unavailable in downloaded MP4 |

This is source-level technical availability only. It makes no claim that speech
or ambient audio is necessary for any future episode.

## Reproduction

```bash
python tools/lvb_download_media_audit.py
pytest -q tests/test_lvb_download_media_audit.py
pytest -q
```

The audit script writes only its restricted JSON report. It does not modify or
delete acquired payloads and does not create benchmark annotations.
