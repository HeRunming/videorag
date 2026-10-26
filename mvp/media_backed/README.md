# Media-backed perception fixtures

This directory exercises a deterministic perception layer over the decoded
bytes of the synthetic MVP MP4s. It does **not** change the current
`av_trace_mvp` backend or the normative Pilot-0 protocol.

## Safety and provenance contract

- `PyAVMediaReader` requires the caller to register the exact
  `sha256:<hex>` media digest before decoding.
- A missing file, hash mismatch, malformed container, missing requested stream,
  incomplete interval, or decode error fails closed with no observations.
- Decoding seeks to the requested source-time interval. Codec pre-roll may be
  decoded internally, but only clipped requested-time frames/samples are
  returned.
- Every citable visual, ambient, and speech observation includes the media
  hash, exact decoded interval, adapter version, and confidence.
- Perception adapters accept only decoded pixels/samples and explicit request
  parameters. They never open timeline, transcript, evidence, family, graph, or
  oracle JSON.
- Annotation comparison occurs only in evaluator test
  `tests_media/test_perception.py::test_annotation_is_evaluator_only_not_adapter_input`.

## Adapters

| Adapter | Version | Input | Output |
|---|---|---|---|
| PyAV reader | `pyav-interval-reader/1.0.0` | Registered MP4 bytes and requested interval | RGB frames, mono samples, exact coverage |
| Visual | `synthetic-pixel-vision/1.0.0` | RGB pixels | Shape, palette color, arrow direction, OCR-like visible tokens |
| Ambient | `synthetic-waveform-ambient/1.0.0` | Waveform | Pulse count, dominant frequency bands, bell/click/hum/chime signature |
| Speech | `synthetic_codec/1.0.0` | Waveform | Symbolic text from alternating tonal symbols |

The speech implementation is deliberately labeled **`synthetic_codec`**, not
ASR. It implements the versioned `SpeechAdapter` interface
(`speech-adapter/1.0`) so a frozen-ASR or subtitle adapter can be substituted
without changing tool-facing calls.

## Mutation fixtures

`fixtures/fixture_hashes.json` registers each checked-in fixture:

- `syn_source_01_blank_24_30.mp4`: visual event pixels are replaced; the early
  triangle observation disappears while the later circle remains.
- `syn_source_02_mute_38_44.mp4`: the three-pulse bell waveform is muted; its
  ambient observation disappears while video remains usable.
- `syn_source_01_speech_72_78_to_659hz.mp4`: the 523 Hz speech symbol is
  replaced by the 659 Hz symbol; decoded text changes from `DELTA SEVEN` to
  `OPEN GATE`, while untouched speech and visual evidence remain.
- `syn_source_01_truncated.mp4`: registered truncated bytes fail interval
  decoding.
- `corrupt.mp4`: registered non-container bytes fail opening/decoding.

These mutations are test engineering artifacts, not legal Pilot-0 intervention
states.

## Probe

Pass the registered hash explicitly:

```bash
python scripts/probe_media_evidence.py \
  mvp/generated/full/media/syn_source_01.mp4 \
  --sha256 sha256:b270a8deb3fda7cee58afd9ab38148c9d521803aadc0b00435a03ae77100df3b \
  --start 24 --end 30 --no-audio
```

Focused test command:

```bash
pytest -q tests_media
```
