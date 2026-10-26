# ffprobe MP4 metadata shim

**Status:** `FFPROBE_MP4_METADATA_SHIM_READY`  
**Date:** 2026-10-14

## Purpose

`tools/ffprobe_mp4_metadata_shim.py` is an executable, dependency-free
compatibility shim for the exact invocation used by
`tools/epic_p23_102_exact_acquisition.py`:

```text
ffprobe -v error -print_format json -show_format -show_streams INPUT
```

It emits the `streams` and `format` JSON fields consumed by the existing
P23_102 validator. It is intended for environments where the external ffprobe
binary is unavailable, not as a general replacement for FFmpeg.

Example:

```bash
tools/ffprobe_mp4_metadata_shim.py \
  -v error \
  -print_format json \
  -show_format \
  -show_streams \
  data/restricted/epic_p23_102_source_v1/media/P23/P23_102.MP4
```

The exact acquisition tool can select it explicitly:

```bash
python tools/epic_p23_102_exact_acquisition.py \
  --ffprobe "$PWD/tools/ffprobe_mp4_metadata_shim.py"
```

## Parsing and I/O boundary

The shim parses ISO Base Media File Format metadata directly with positional
local-file reads. It:

- supports 32-bit sizes, 64-bit extended sizes, and top-level size-to-EOF
  boxes;
- supports `moov` before or after `mdat`;
- walks `moov/trak/mdia/minf/stbl`;
- reads `mvhd`, `tkhd`, `mdhd`, `hdlr`, and `stsd`;
- extracts visual dimensions from visual sample entries;
- extracts channels and 16.16 sample rate from audio sample entries;
- parses `esds` descriptors sufficiently to distinguish MPEG-4 AAC in
  `mp4a`;
- reports movie and media durations without reading timing/sample tables;
- maps supported sample-entry FourCCs to ffprobe-style codec names; and
- does not read any `mdat` payload range or decode video/audio samples.

The local P23_102 smoke test records all read ranges and asserts that none
overlap the `mdat` payload. It also caps total metadata bytes read below 1 MiB
and the largest individual read below 64 KiB for that asset.

## P23_102 output

For the assembled local exact object, the shim reports:

| Field | Value |
|---|---:|
| video codec | `hevc` |
| video sample entry | `hvc1` |
| video dimensions | `1920x1080` |
| video time base | `1/90000` |
| video duration | `3569.520000` |
| audio codec | `aac` |
| audio sample entry | `mp4a` |
| audio channels/layout | `2` / `stereo` |
| audio sample rate | `48000` |
| audio time base | `1/48000` |
| audio duration | `3569.536000` |
| container duration | `3569.536000` |

These fields satisfy the identity and duration checks in
`validate_ffprobe_report`.

## Fail-closed behavior

The process exits nonzero and writes no JSON report when required metadata is
malformed, ambiguous, or unsupported. Examples include:

- boxes extending beyond their parent or file;
- duplicate required singleton boxes;
- missing `moov`, `mvhd`, `trak`, `mdia`, `mdhd`, `hdlr`, `minf`, `stbl`, or
  `stsd`;
- fragmented files containing top-level `moof`;
- compressed `cmov` metadata;
- unknown full-box versions;
- multiple sample descriptions for one track;
- unsupported handlers, sample entries, MPEG-4 audio object types, or
  fractional sample rates; and
- metadata boxes or parser work exceeding the fixed safety caps.

This conservative behavior is deliberate: the shim must not infer validator
fields from incomplete or uncertain metadata.

## Limitations

- Local regular MP4/MOV files only; no URLs, pipes, devices, or standard input.
- Non-fragmented files only; `moof`/fragment timelines are rejected.
- No sample, packet, frame, audio, subtitle, or bitstream decoding.
- No validation that declared codec configuration can actually decode.
- No sample-table validation and no frame-rate, frame-count, packet-count,
  bitrate-per-stream, language, disposition, profile, level, pixel format, or
  color metadata.
- Stream duration is the `mdhd` media duration. Edit lists and presentation
  offsets are not applied.
- Container duration is the `mvhd` duration.
- One `stsd` sample description per track is required.
- Video support is limited to explicit mappings in `VIDEO_CODECS`; audio
  support is limited to explicit mappings in `AUDIO_CODECS` plus recognized
  `mp4a` object types.
- Channel layouts are named only for mono and stereo. Larger channel counts
  are reported numerically without a guessed layout.
- The accepted CLI surface is intentionally narrow: JSON output,
  `-show_format`, `-show_streams`, `-v error|quiet`, and `-hide_banner`.

## Tests

`tooling/tests/test_ffprobe_mp4_metadata_shim.py` creates synthetic fixtures
covering:

- head and tail `moov`;
- 32-bit and 64-bit `moov` sizes;
- version 0 and version 1 movie/media/track headers;
- `hvc1` dimensions;
- `mp4a` AAC channels and sample rate;
- exact-acquisition argv compatibility;
- malformed and fragmented fail-closed cases; and
- a bounded, metadata-only smoke against the assembled local P23_102 when it
  is present.

Run:

```bash
pytest -q tooling/tests/test_ffprobe_mp4_metadata_shim.py
ruff check \
  tools/ffprobe_mp4_metadata_shim.py \
  tooling/tests/test_ffprobe_mp4_metadata_shim.py
```

`FFPROBE_MP4_METADATA_SHIM_READY`
