# Synthetic AV-TRACE MVP data

This directory contains a tiny, deterministic audio-visual corpus for exercising
the AV-TRACE matched `CLEAN`–`BLOCKED`–`RESTORED` hypothesis without network
access, downloaded media, or external models.

## Generate

From the repository root:

```bash
python scripts/generate_synthetic_mvp.py --mode quick --probe
python scripts/generate_synthetic_mvp.py --mode full --probe
```

The default seed is `20260905`. `quick` generates one four-minute source, two
families, and six episodes. `full` generates four sources of 4, 5, 6, and 8
minutes, eight families, and 24 episodes.

## Output layout

Each mode writes below `mvp/generated/<mode>/`:

- `media/*.mp4`: low-resolution, one-frame-per-second playable MP4s with AAC
  audio;
- `timelines/*.json`: exact source-time event intervals;
- `transcripts/*.json`: exact symbolic speech text;
- `audio_events/*.json`: ambient/speech labels and synthesis parameters;
- `evidence/*.json`: human-readable evidence records and family uses;
- `manifests/*.json`: acquisition manifests marked
  `synthetic_project_owned`;
- `families/*.json`: schema-compliant three-episode families;
- `corpus_index.json`: coverage, paths, media hashes, and normative schema
  hashes;
- `generation_report.json`: deterministic metadata digest and validation
  result.

## Speech and media design

The speech channel is intentionally **symbolic**, not natural-language TTS.
Distinct deterministic tonal patterns occupy the registered speech intervals,
while `transcripts/*.json` supplies the exact textual speech track. Video marks
only that speech is active; it does not render speech content and therefore does
not create a visual answer leak. Ambient events use procedural bells, hums, and
chimes. Vision events use literal colored shapes and labels. All content is
project-owned and generated from code.

## Coverage

The full corpus has:

- both `necessity_group_withholding` and `modality_channel_outage`;
- vision, speech, and ambient evidence;
- one vision-only, two speech-only, one ambient-only, and four cross-modal
  families;
- multiple temporally separated evidence chains (up to 336 seconds apart);
- one family with two accepted alternative minimal SES routes;
- exactly three episodes per family.

The normative Pilot-0 semantic validator reserves
`PUBLIC_CORE_FIXED_BACKEND_TRIPLETS` for 20–90 minute sources. Because these
engineering fixtures are intentionally 4–8 minutes, their episode families use
the schema-supported `restricted_compatibility` /
`EXTERNAL_COMPATIBILITY_UNPOOLED` labels. This is a duration/track distinction,
not a rights limitation: every project-owned manifest passes the public-release
manifest gate with all release decisions allowed.

## Determinism

JSON is emitted with stable key ordering, fixed timestamps, and a seeded
generator. Re-running with the same config, seed, and encoder stack produces the
same metadata digest and was tested to produce identical MP4 hashes locally.

**MP4 byte identity is not guaranteed across different PyAV, FFmpeg, libx264, or
AAC encoder builds.** Encoded pictures, samples, timestamps, event timing, and
all metadata remain deterministic by construction; exact container bytes are
only expected to match when the codec/toolchain build is the same.

## Validation and tests

Generation fails closed unless:

1. every manifest passes `av_trace.validate_manifest_gate` at the public-release
   gate; and
2. every family passes `av_trace.validate_family` against its matching manifest.

Run the dedicated tests with:

```bash
PYTHONPATH=src pytest -q tests_mvp/test_synthetic_data.py
```
