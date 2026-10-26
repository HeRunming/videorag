# CaptainCook4D Wave-0 Full-Timeline Index v1

**Date:** 2026-10-10  
**Task:** 189  
**Scope:** restricted three-source full-timeline indexing only  
**Final token:** `CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY`

## 1. Purpose and boundary

Task189 implements and executes a dedicated CaptainCook4D Wave-0 index over
the three exact sources accepted by Task188. The package and outputs are
isolated from the EPIC package while reusing the audited timeline/index engine
and frozen local model assets that Tasks163–164 validated.

Canonical output:

`data/restricted/captaincook4d_wave0_index_v1/`

The following are outside scope and prohibited:

- semantic or human annotations;
- candidate families, family migration, or hard negatives;
- interventions;
- trajectories, agents, or controllers;
- evaluation or metric artifacts;
- persisted audio, video, image, frame, or other media derivatives;
- public release or redistribution.

Task153's nine unlabeled source-prescreen intervals remain nonsemantic inputs
to the acquisition record only. No human form or eligibility decision is
joined to this index.

## 2. Exact Task188 source binding

The plan binds the exact Task188 acquisition manifest:

`data/restricted/captaincook4d_wave0_sources_v3/manifests/captaincook4d_wave0_acquisition_manifest.json`

SHA-256:

`ee50c9579b77f7ee4f45753adad1d5d1e09569c6b1be5308a82ccbcc9a05934a`

Required decision:

`CAPTAINCOOK4D_WAVE0_ACQUISITION_READY`

| Source | Person | Environment | Duration | Bytes | SHA-256 |
|---|---:|---:|---:|---:|---|
| `16_20` | 1 | 8 | 1930.90 s | 230,486,870 | `8082945db8c24cb40e3dd76eafc11cb2b3df5a0b8bdb2e5c22e1ada98ae82f12` |
| `15_29` | 2 | 2 | 1292.82 s | 181,454,428 | `f1f77f09d6ffd35531f4d23fb3d4bfe3eb350e71a7240ced9ac9b4f28b8b048d` |
| `26_22` | 3 | 3 | 1324.22 s | 131,633,528 | `3c4b69b4ad37c4318b24d034cf0fdd3fa2eb96b3e85136001b0ea531b5abbd7b` |

The gate also verifies:

- exact MD5, byte count, path, source-group, person, and environment;
- exact source-manifest path and SHA-256;
- three distinct people and three distinct environments;
- regular non-symlink media and manifest files;
- source root mode `0700` and file mode `0600`;
- audio/video stream evidence;
- beginning/middle/end decode and synchronization;
- full PyAV and OpenCV EOF/no-truncation evidence;
- Task188's no-annotation, no-human-review, no-H-tier, and
  no-public-release boundaries.

The plan hash is:

`9c86f22b8b0102491632aa5570d95c5553f8426d65b00e0e9af2771a26603431`

## 3. Frozen timeline lattice

All stored times are integer microseconds.

### 4-second base cells

- length: 4 seconds;
- stride: 4 seconds;
- retain a positive terminal partial cell;
- sample one frame at
  `min(cell_start + 2 seconds, source_duration - 1 microsecond)`.

### 8-second fine windows

- nominal length: 8 seconds;
- stride: 4 seconds;
- admit while at least 4 seconds remain;
- clip the terminal end to source duration.

### 32-second context windows

- nominal length: 32 seconds;
- stride: 16 seconds;
- admit while at least 16 seconds remain;
- clip the terminal end to source duration.

### 30-second speech lattice

- non-overlapping Whisper chunks;
- retain the positive terminal partial;
- citations remain bound to the truthful full ASR chunk interval.

Expected and observed full counts:

| Source | Base | Fine | Context | Segments | Whisper | Checkpoints |
|---|---:|---:|---:|---:|---:|---:|
| `16_20` | 483 | 482 | 120 | 602 | 65 | 4 |
| `15_29` | 324 | 323 | 80 | 403 | 44 | 4 |
| `26_22` | 332 | 331 | 82 | 413 | 45 | 4 |
| **Total** | **1,139** | **1,136** | **282** | **1,418** | **154** | **12** |

AST runs once per fine window. OpenCV routing and CLIP each run once per base
cell. Ambient and visual records cover all 1,418 temporal segments.

## 4. Frozen local assets and offline execution

The index is CPU-only and offline. It binds:

| Layer | Local asset | Frozen hash |
|---|---|---|
| Whisper tiny.en | `data/restricted/noaa01/models/whisper-tiny.en-87c7102` | `sha256:1e098354f3cbd9f339ef8fbdcc0e82ff238786bffa25794493ebe32830f4518a` |
| AST AudioSet | `data/restricted/noaa01/models/ast-audioset-f826b80` | `sha256:acb9247d5f2548c121e7fd213347586e1b781fd8dc329e27505dd269a69cccbc` |
| CLIP ViT-B/32 | `data/restricted/noaa01/models/clip-vit-base-patch32-3d74acf` | `sha256:2c29598276753a41d293ca65ef8fe60287ed62d8cd94b0ee77ec38ecb41a20f5` |
| OpenCV Haar | `data/restricted/noaa01/models/opencv-haarcascade-frontalface-default.xml` | `sha256:a9ee3c8bf4ab44314001ffa728bbfc388fcc579790b8b2909d71dd80306d2f40` |

Pinned weight or asset SHA-256 values are checked in addition to snapshot
hashes. Runtime records bind CPU, eight threads, network disabled,
`HF_HUB_OFFLINE=1`, and `TRANSFORMERS_OFFLINE=1`. Decoded media is memory-only.

## 5. Outputs and resume checkpoints

The canonical root contains exactly five top-level JSON files:

1. `segment_manifest.json`
2. `observation_manifest.json`
3. `full_timeline_index.json`
4. `resource_manifest.json`
5. `build_manifest.json`

Each source has:

- `speech.json`;
- `ambient.json`;
- `vision_routing.json`;
- `vision_clip.json`.

A checkpoint is reused only when its source SHA-256, layer version, scale,
shard, observation configuration, record count, payload hash, file hash, byte
count, and permissions match. Writes use restricted temporary files, `fsync`,
and atomic replacement. Canonical directories are `0700` and files are
`0600`.

## 6. Commands

Dry preflight:

```bash
PYTHONPATH=src python scripts/build_captaincook4d_wave0_full_timeline.py \
  --repo-root .
```

Bounded smoke:

```bash
PYTHONPATH=src python scripts/build_captaincook4d_wave0_full_timeline.py \
  --repo-root . --execute --mode smoke --smoke-seconds 32 \
  --resume --threads 8 --device cpu
```

Full build:

```bash
PYTHONPATH=src python scripts/build_captaincook4d_wave0_full_timeline.py \
  --repo-root . --execute --mode full \
  --resume --threads 8 --device cpu
```

Canonical verifier:

```bash
PYTHONPATH=src python scripts/verify_captaincook4d_wave0_full_timeline.py \
  --repo-root . --mode full
```

Independent structural audit:

```bash
PYTHONPATH=src python scripts/audit_captaincook4d_wave0_full_timeline.py \
  --repo-root .
```

For the deterministic-resume audit, record the 17 canonical file hashes,
sizes, and 12 checkpoint mtimes, rerun the exact full command, then pass the
snapshot with `--before-snapshot`.

## 7. Decision semantics

- `CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY`: all acquisition, source,
  model, index, checkpoint, storage, boundary, verifier, and deterministic
  resume conditions pass.
- `CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_REPAIR`: a remediable prerequisite or
  requested output is absent.
- `CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_NO_GO`: an identity, safety,
  determinism, or boundary invariant fails.

Final decision:

`CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY`
