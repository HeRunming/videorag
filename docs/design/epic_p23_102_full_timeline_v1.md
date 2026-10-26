# EPIC P23_102 full-timeline/index pipeline v1

**Date:** 2026-10-13  
**Implementation token:** `EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY`  
**Built-index token:** intentionally not issued

## Purpose and status

This design implements a deterministic and resumable full-timeline/index
pipeline for exactly:

`data/restricted/epic_p23_102_source_v1/media/P23/P23_102.MP4`

The exact media is 10,814,161,307 bytes and was not present as a completed
acquisition when this pipeline was implemented. The implementation therefore
does **not** wait for, download, decode, or run on the full object. The default
command is a no-decode plan. Synthetic fixtures exercise the complete build,
resume, tamper-detection, and verifier paths.

The source identity is frozen to EPIC-KITCHENS-100 v100 object
`P23/videos/P23_102.MP4`, official MD5
`4698fcbf13782f6396029761eb3bd5f2`, official duration 3569.52 seconds,
50 fps, and 1920x1080. Execution is fail-closed until the command-independent
exact acquisition manifest says `COMPLETE_VERIFIED_READY`, contains an exact
64-hex SHA-256, and the final media rehashes to that value.

## Governance boundary

The dataset evidence binds use to **CC BY-NC 4.0**. Attribution is required and
commercial use is not authorized. This pipeline is restricted local
noncommercial research infrastructure; it grants no redistribution, public
release, privacy, or participant-release clearance.

This source and every derived artifact are:

- development-only;
- ineligible for future test use;
- subject to fresh normal-mode regeneration if a later protocol creates a new
  test split;
- selected without opening or using EPIC action, narration, EPIC-SOUNDS,
  benchmark, or other semantic annotation bodies.

The pipeline makes no human-review, SES, H-tier, modality-necessity, Gate-A,
family, intervention, trajectory, evaluation, or metric claim. Whisper,
SigLIP2, and CLAP outputs are machine observations and retrieval features, not
human semantic annotations or gold.

## Timeline lattice

All persisted times are integer microseconds.

| Layer | Rule | P23_102 count |
|---|---|---:|
| Base cell | 4 s length/stride; retain positive terminal partial | 893 |
| Fine | 8 s length, 4 s stride; admit with at least 4 s remaining | 892 |
| Context | 32 s length, 16 s stride; admit with at least 16 s remaining | 223 |
| Fine + context | exact temporal-segment inventory | 1,115 |
| Speech | non-overlapping 30 s chunks; retain terminal partial | 119 |

One visual frame is sampled per base cell at
`min(cell_start + 2 seconds, duration - 1 microsecond)`.

## Observation and retrieval layers

### Speech

The frozen local `openai/whisper-tiny.en` revision
`87c7102498dcde7456f24cfd30239ca606ed9063` receives 16 kHz mono 30-second
chunks. Nonempty chunks that pass the frozen token-quality route are searchable
with deterministic BM25. Failed chunks remain in the inventory with reasons and
are not silently discarded.

### SigLIP2 visual retrieval

The frozen local `google/siglip2-base-patch16-224` revision
`75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2` produces one normalized 768-D
float16-persisted embedding per base cell. Fine/context vectors are normalized
means of their bound cells. The index exposes a retrieval hook: encode text
with the same pinned SigLIP2 text tower, then cosine-rank the stored segment
vectors. It does not generate or index captions.

### CLAP audio retrieval

The frozen local `laion/clap-htsat-unfused` revision
`8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a` receives exact 48 kHz mono fine
windows and produces normalized 512-D embeddings. Context vectors are
normalized means of overlapping fine vectors. The retrieval hook uses the same
pinned CLAP text tower and cosine ranking. Near-silence is retained as a quality
flag rather than converted into a semantic label.

## Checkpoints and deterministic resume

Exactly four source checkpoints are created:

1. `source_probe.json`
2. `speech_asr.json`
3. `siglip2_visual.json`
4. `clap_audio.json`

Each key binds exact source SHA-256, frozen layer/version, configuration hash,
and shard zero. A checkpoint is reusable only when its key, record count,
payload hash, file hash, byte count, path, and `0600` mode agree. Writes use a
restricted temporary file, file `fsync`, atomic rename, and directory `fsync`.
An invalid layer is deleted and rebuilt without invalidating valid independent
layers.

No decoded frame, waveform, media clip, thumbnail, or other media derivative is
persisted. Output directories are `0700`, files are `0600`, and the derived
hard cap is 128 MiB.

## Artifacts

The output root contains only:

- `segment_manifest.json`
- `observation_manifest.json`
- `full_timeline_index.json`
- `resource_manifest.json`
- `checkpoint_manifest.json`
- `build_manifest.json`
- the four JSON checkpoints beneath `checkpoints/P23_102/`

The verifier independently replays hashes, lattice counts and intervals,
checkpoint contracts, vector dimensions/norms, speech term frequencies,
governance booleans, source binding, permissions, artifact cap, and the absence
of media derivatives and prohibited claims.

## Resource estimate

The source is about 10.1 GiB and 0.992 hours. The required model payloads are
already local and total about 2.27 GB of weights.

- Speech stage: approximately 2-4 GiB peak RAM.
- SigLIP2 stage: approximately 4-8 GiB peak RAM.
- CLAP stage: approximately 5-10 GiB peak RAM.
- Derived index: approximately 15-35 MiB.
- CPU-only wall clock: approximately 3-10 hours depending on host load and
  decoder throughput.
- A later separately authorized GPU execution would likely take about
  20-90 minutes, but this v1 CLI is intentionally CPU-frozen.

There is one video decode pass. Speech and CLAP use separate audio decode passes
because they are independent resumable layers with different sample rates. On
resume, a valid completed layer avoids its decode and inference pass.

## Commands

### Plan now — safe while acquisition is absent

```bash
PYTHONPATH=src python scripts/build_epic_p23_102_full_timeline.py \
  --repo-root . --mode plan
```

This returns `EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY`, reports acquisition
pending if appropriate, and does not hash/open media, load models, decode, or
write restricted outputs.

### Validate after exact acquisition

```bash
PYTHONPATH=src python scripts/build_epic_p23_102_full_timeline.py \
  --repo-root . --mode validate
```

Validation rehashes the 10.8 GB media and the declared frozen weight files, but
does not decode media, load models, or write index outputs.

### Bounded smoke after validation

```bash
PYTHONPATH=src python scripts/build_epic_p23_102_full_timeline.py \
  --repo-root . --mode smoke --smoke-seconds 32 --resume --threads 8

PYTHONPATH=src python scripts/verify_epic_p23_102_full_timeline.py \
  --repo-root . --mode smoke --smoke-seconds 32
```

### Full build after validation

```bash
PYTHONPATH=src python scripts/build_epic_p23_102_full_timeline.py \
  --repo-root . --mode full --resume --threads 8

PYTHONPATH=src python scripts/verify_epic_p23_102_full_timeline.py \
  --repo-root . --mode full
```

For a fast manifest-only verifier replay after a successful prior source rehash,
`--no-rehash-source` may be used, but final acceptance should include the
default source rehash.

## Completion semantics

This task completes the executable pipeline, static plan, documentation,
synthetic tests, and independent verifier. It does not claim that the 10.8 GB
source was acquired or that a full index was built.

`EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY`
