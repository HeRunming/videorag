# EPIC P23_102 exact acquisition

**Date:** 2026-10-13  
**Disposition:** `EPIC_P23_102_ACQUISITION_READY`

## Outcome

Parallel segments were assembled in exact byte order; the official MD5, local SHA-256, restrictive-custody, and ffprobe checks passed.

The scope is exactly the official `P23/videos/P23_102.MP4` object. No semantic
annotation body was opened or used, no semantic review was performed, and
CaptainCook4D `25_109` was not acquired.

## Exact identity

| Field | Expected | Observed |
|---|---:|---:|
| Bytes | `10814161307` | `10814161307` |
| Official MD5 | `4698fcbf13782f6396029761eb3bd5f2` | `4698fcbf13782f6396029761eb3bd5f2` |
| SHA-256 | computed locally | `58f53a4ae0089bb3df4299d112d3e16740a36febd7da9aabea76bf17963da822` |
| Final mode | `0600` | `0o600` |

Canonical resumable staging bytes retained: `0`.

## Stream validation

| Stream fact | Required | Observed |
|---|---|---|
| Video codec tag | `hvc1` | `hvc1` |
| Video dimensions | `1920x1080` | `1920x1080` |
| Video duration | near official `3569.52 s` | `3569.52` |
| Audio codec tag | `mp4a` | `mp4a` |
| Audio layout | stereo | `stereo` |
| Audio sample rate | `48000 Hz` | `48000` |
| A/V duration delta | `<= 0.25 s` | `0.016000000000076398` |

## Provenance and usage boundary

The official Data.Bris README binds the deposit to CC BY-NC 4.0. Attribution is
required and commercial use is not authorized. This acquisition is restricted
to local noncommercial research and technical validation. It does not authorize
public release, redistribution, human annotation, or imply privacy/release
clearance.

The command-independent manifest is
`data/restricted/epic_p23_102_source_v1/manifests/epic_p23_102_exact_manifest.json`.
Transfer progress, range-attempt records, hashes, raw ffprobe output, and the
validation report are retained under the restricted source directory.

`EPIC_P23_102_ACQUISITION_READY`
