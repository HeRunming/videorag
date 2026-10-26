# NOAA-01 downloaded-media audit

**Audit date:** 2026-09-09  
**Decision:** **CONDITIONAL_GO**

## Executive finding

The exact five NOAA-01 MP4s passed the restricted internal technical audit.
All five independently recomputed file sizes and SHA-256 digests match the
frozen plan, completed acquisition manifest, and adjacent metadata sidecars.
The aggregate is exactly **1,955,298,193 bytes**.

All five containers opened through bounded PyAV child processes and declared at
least one video and one audio stream. Beginning, middle, and near-end checks
decoded a video frame and an audio window for every file: **15/15 positions**
passed for both modalities. Every audio window contained decoded samples and
finite normalized peak/RMS statistics. One sampled beginning window was
technically silent at the audit threshold; that is not a decode failure and no
semantic interpretation is made.

All five durations agree with the frozen preflight values under the stated
`max(1 second, 0.1%)` tolerance. Conservative A/V start/end timeline checks
passed for all five.

The host has PyAV 16.1.0 but no external `ffprobe` or `ffmpeg` executable.
Therefore external-tool confirmation was not performed and the result is
**CONDITIONAL_GO**, not an unconditional go. This limitation is isolated from
the media findings: the PyAV container, stream, and decode checks all passed.

## Recovery review and corrections

Task 79 reviewed the interrupted Task 78 implementation line by line rather
than accepting it unchanged. Corrections included:

- binding both authorization records and the addendum to the exact candidate
  set, paths, operations, frozen plan hash, aggregate size, and continuing
  prohibitions;
- clarifying that the addendum narrowly overrides the acquisition record's
  processing/decoding hold only for this audit and does not establish
  ownership, licensing, or release rights;
- normalizing external `ffprobe` stream fields into the same units and names as
  PyAV, so an installed `ffprobe` would not falsely fail timeline checks;
- requiring strict permissions for every managed restricted file and
  directory, not only payloads and sidecars;
- strengthening sidecar checks for expected and observed source identity and
  independently recorded whole-file hashes;
- requiring decoded frames and audio windows to correspond to the requested
  beginning/middle/near-end positions, with finite RMS/peak values;
- reopening the container for each modality/position decode to avoid
  cross-seek decoder state;
- checking that the restricted tree did not change during media inspection and
  that the decoder reported no filesystem-output path;
- scanning all JSON controls and the generated audit itself without disclosing
  values, then validating the report's internal counts and decision dimensions.

## Authorization and scientific boundary

The dated addendum activates only **restricted internal technical inspection
and decoding** for the exact five listed assets. It continues to prohibit:

- public release or redistribution;
- benchmark annotation or semantic labeling;
- access to any unlisted object;
- persistent frames, audio, clips, transcripts, waveforms, or other derived
  media.

This audit does **not** assess or establish speech intelligibility,
ambient/non-speech usefulness, minimal modality necessity, scientific episode
suitability, ownership, licensing, privacy clearance, or public-release
eligibility. It also does not itself grant authorization for a later content
reconnaissance stage.

## Integrity, provenance, and restricted-tree safety

- Integrity matches: **5/5**
- Aggregate: **1,955,298,193 bytes**
- Payload and sidecar modes: `0600`
- Restricted root, raw, and manifest directory modes: `0700`
- Regular-file, non-symlink, lexical and resolved containment checks: **PASS**
- Partial, stale-lock, orphan-state, orphan-sidecar, duplicate-basename,
  unexpected-payload, unexpected-file, and symlink checks: **PASS**
- Plan, both authorization records, acquisition manifest, and five sidecars
  scanned for credentials and signed-query indicators: **9/9 PASS**
- Generated restricted audit scanned and internally validated: **PASS**
- Restricted tree unchanged during probe/decode inspection: **PASS**
- Persistent extracted media found: **none**

Full local integrity hashes remain only in
`data/restricted/noaa01/manifests/noaa01_media_audit.json` and are not repeated
here. This non-restricted report also omits source URLs, ETags, and
Last-Modified details.

## Container, duration, and timeline results

| Candidate | PyAV duration (s) | Absolute preflight difference (s) | Video | Audio | Absolute start offset (s) | Absolute end offset (s) |
|---|---:|---:|---|---|---:|---:|
| `cand-045` | 1772.440000 | 0.000000 | H.264, 1280×720 | AAC, 44.1 kHz, mono | 0.000000 | 0.366000 |
| `cand-047` | 1983.781800 | 0.068867 | H.264, 640×360 | AAC, 48 kHz, stereo | 0.000000 | 0.000008 |
| `cand-049` | 2465.329542 | 0.035791 | H.264, 640×360 | AAC, 48 kHz, stereo | 0.000000 | 0.000008 |
| `cand-051` | 3718.581542 | 0.053125 | H.264, 640×360 | AAC, 48 kHz, stereo | 0.000000 | 0.000008 |
| `cand-052` | 3781.144042 | 0.039958 | H.264, 640×360 | AAC, 48 kHz, stereo | 0.000000 | 0.000008 |

Declared A/V stream presence passed **5/5**. Duration agreement passed **5/5**.
Conservative timeline plausibility passed **5/5**.

## Decode smoke results

For each file, a bounded PyAV child process checked:

1. beginning;
2. approximately the middle;
3. near the end.

At each of the 15 positions, the audit required:

- a decoded video frame near the requested time;
- a decoded audio window covering the requested time;
- nonzero decoded sample count;
- finite normalized peak and RMS values.

Results:

- files passing all three video positions: **5/5**;
- files passing all three audio positions: **5/5**;
- files passing the combined three-position A/V smoke test: **5/5**;
- individual requested positions passing combined video/audio checks:
  **15/15**;
- persistent decoded frames/audio/clips/waveforms: **none**.

The statistics are deliberately non-semantic. No listening, transcription, or
content labeling was performed.

## Decision

**CONDITIONAL_GO**

Technical basis:

- acquisition integrity: **PASS**;
- declared stream presence: **PASS**;
- actual decode success: **PASS**;
- duration agreement: **PASS**;
- conservative timeline plausibility: **PASS**;
- external `ffprobe`/`ffmpeg` confirmation: **OUTSTANDING — tools absent**.

Public release, redistribution, annotation, semantic review, and scientific
suitability remain held. A later restricted content-reconnaissance stage would
require its own applicable authorization; this audit does not grant it.

## Reproduction

```bash
pytest -q tests/test_noaa_download_media_audit.py
python tools/noaa_download_media_audit.py
pytest -q
pytest -q tests tests_agent_runtime tests_data tests_media \
  tests_media_pipeline tests_mvp tests_validation
```

The audit tool writes only the fixed restricted JSON report. It never invokes a
downloader and never creates persistent extracted media.
