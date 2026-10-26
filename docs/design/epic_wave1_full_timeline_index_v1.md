# EPIC Wave-1 Full-Timeline Index v1

**Date:** 2026-09-28  
**Scope:** restricted indexing implementation only  
**Current execution token:** `EPIC_WAVE1_INDEX_IMPLEMENTATION_REPAIR`

## 1. Purpose and governing boundary

This design prepares an isolated full-timeline index for the two EPIC-KITCHENS-100
Wave-1 sources selected by Task 161:

| Source | Participant block | Official duration | Official v100 MD5 | Expected final path |
|---|---|---:|---|---|
| `P28_103` | `P28` | 1825.16 s | `30258174e4ae5cee495170d2748efc4e` | `data/restricted/epic_wave1_sources_v1/media/P28/P28_103.MP4` |
| `P27_101` | `P27` | 1360.20 s | `f3e40c9216ab5f05cddb762bd70278d5` | `data/restricted/epic_wave1_sources_v1/media/P27/P27_101.MP4` |

The implementation reuses the frozen local Whisper tiny.en, AST, CLIP, and
OpenCV routing assets already validated by the mini-pilot work. It does not
reuse mini-pilot outputs. Every EPIC artifact is written under:

`data/restricted/epic_wave1_index_v1/`

The implementation does **not** create or authorize:

- candidate families or family migration;
- hard negatives;
- CLEAN/BLOCKED/RESTORED interventions;
- trajectories, controller or agent runs;
- evaluation or metric artifacts;
- human semantic annotations;
- public release or redistribution.

Task 153's semantic-prescreen protocol remains separate. No EPIC action,
narration, sound-class, benchmark-split, or label-derived annotation is read
or copied into the index.

## 2. Required acquisition gate

The build is fail-closed. Before any media decode or output creation it must
load:

`data/restricted/epic_wave1_sources_v1/manifests/epic_wave1_acquisition_manifest.json`

That Task 162 manifest must satisfy all of the following:

1. `decision` is exactly `EPIC_WAVE1_ACQUISITION_READY`.
2. It contains exactly `P28_103` and `P27_101`.
3. Failed and incomplete transfer counts are zero.
4. Each source has a final, non-symlink media path equal to the path frozen
   in the v1 plan. Paths containing `.staging` are rejected.
5. Each source records a 64-hex exact SHA-256, the official v100 MD5, exact
   byte count, duration, audio and video stream evidence, and A/V-sync
   verification.
6. The final file is mode `0600`, its parent is mode `0700`, and recomputed
   SHA-256 and MD5 values match the manifest.

The plan intentionally does not guess or synthesize the final SHA-256 values.
They are bound at execution time to the completed Task 162 acquisition
manifest and persisted into `resource_manifest.json` and
`build_manifest.json`. A READY token without exact SHA-256 values is rejected.

As of 2026-09-28, Task 162 has not published that root manifest. The media
downloads remain active, so only dry preflight is permitted. The implementation
does not traverse or read `data/restricted/epic_wave1_sources_v1/.staging/`.

## 3. Frozen official metadata

The v1 plan binds the source identities to:

- Task 161 video metadata:
  `data/restricted/epic_wave1_sources_v1/logs/task161_video_info.csv`
  (`sha256:75fd040f6662cb407b4ca2eed4811ca94df280a1aba00b6bf8a5cd286deff382`);
- Task 161 checksum metadata:
  `data/restricted/epic_wave1_sources_v1/logs/task161_md5.csv`
  (`sha256:3f9c31899ff5807c8f0fed5d26a8fe62300f3f4c40dc3eea767345212c2e83c7`);
- Task 161 registry:
  `data/rehearsal_plan/assembly_epic_access_registry_v2.json`
  (`sha256:22f1c3a5a59f60e94e5b8d61b3ded4f71558805502f25ac9295e8007204ef9b1`).

The plan verifies the exact duration, FPS, resolution, remote path, media
version, and official MD5 rows for both source IDs before checking Task 162.

## 4. Timeline lattice

All stored times are integer microseconds.

### Base cells

- length: 4 seconds;
- stride: 4 seconds;
- terminal positive partial cell retained;
- one visual sample at `min(cell_start + 2 seconds, duration - 1 microsecond)`.

### Fine windows

- nominal length: 8 seconds;
- stride: 4 seconds;
- admitted while at least 4 seconds remain;
- terminal window clipped to source duration.

### Context windows

- nominal length: 32 seconds;
- stride: 16 seconds;
- admitted while at least 16 seconds remain;
- terminal window clipped to source duration.

### Speech lattice

- non-overlapping 30-second Whisper chunks;
- terminal positive partial chunk retained;
- a speech citation points to its truthful whole ASR chunk interval.

Expected full-build counts:

| Source | 4 s cells | 8 s fine | 32 s context | Temporal segments | Whisper chunks |
|---|---:|---:|---:|---:|---:|
| `P28_103` | 457 | 456 | 114 | 570 | 61 |
| `P27_101` | 341 | 340 | 85 | 425 | 46 |
| **Total** | **798** | **796** | **199** | **995** | **107** |

The maximum modality-segment inventory is 2,985 records. Vision routing and
CLIP each have 798 base-cell calls. AST has 796 fine-window calls.

## 5. Frozen local model routing

The implementation verifies local snapshot and weight hashes before the
acquisition gate can pass:

- Whisper: `openai/whisper-tiny.en`, revision
  `87c7102498dcde7456f24cfd30239ca606ed9063`;
- AST: `MIT/ast-finetuned-audioset-10-10-0.4593`, revision
  `f826b80d28226b62986cc218e5cec390b1096902`;
- CLIP: `openai/clip-vit-base-patch32`, revision
  `3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268`;
- OpenCV Haar routing asset:
  `opencv-haarcascade-frontalface-default.xml`.

Runtime is CPU-only and offline. Hugging Face tokens are removed from the
process environment, offline flags are set, and no model download is allowed.
Decoded frames and audio remain memory-only.

## 6. Outputs and checkpoint resume

The only top-level output artifacts are:

1. `segment_manifest.json`
2. `observation_manifest.json`
3. `full_timeline_index.json`
4. `resource_manifest.json`
5. `build_manifest.json`

Each source has four resumable checkpoints:

- `checkpoints/<source>/speech.json`
- `checkpoints/<source>/ambient.json`
- `checkpoints/<source>/vision_routing.json`
- `checkpoints/<source>/vision_clip.json`

The expected total is eight checkpoints. A checkpoint is reused only when its
source hash, model/layer version, scale, shard, config hash, record count,
payload hash, file hash, byte count, and permissions all match. Invalid partial
or stale checkpoints are rejected and rebuilt. Writes use a restricted
temporary file, `fsync`, hash metadata, and atomic rename.

All output directories are mode `0700`; all output and checkpoint files are
mode `0600`. The hard derived-artifact cap is 512 MiB. Source media and frozen
model snapshots are excluded from that cap.

## 7. Modes and commands

### Dry preflight — currently permitted

```bash
PYTHONPATH=src python scripts/build_epic_wave1_full_timeline.py \
  --repo-root .
```

This checks the static plan, official metadata, dependencies, frozen model
hashes, and acquisition gate. It does not decode media or write index outputs.
Until Task 162 is complete, the expected exit code is `2` and the expected
token is `EPIC_WAVE1_INDEX_IMPLEMENTATION_REPAIR`.

### Bounded smoke — only after the gate passes

```bash
PYTHONPATH=src python scripts/build_epic_wave1_full_timeline.py \
  --execute --mode smoke --smoke-seconds 32 --resume --threads 8 --device cpu
```

The default smoke output is
`data/restricted/epic_wave1_index_v1_smoke/`. It samples only the leading
bounded interval of each complete source.

### Full build — prepared but not run

```bash
PYTHONPATH=src python scripts/build_epic_wave1_full_timeline.py \
  --execute --mode full --resume --threads 8 --device cpu
```

The full command is not authorized by this implementation task and was not
run.

### Verification

```bash
PYTHONPATH=src python scripts/verify_epic_wave1_full_timeline.py \
  --repo-root . --mode full
```

For a smoke output, pass `--mode smoke --smoke-seconds 32` and its explicit
output root.

## 8. Decision semantics

- `EPIC_WAVE1_INDEX_IMPLEMENTATION_READY`: the acquisition gate passes and
  the requested implementation or produced index verifies exactly.
- `EPIC_WAVE1_INDEX_IMPLEMENTATION_REPAIR`: the implementation is prepared,
  but a remediable prerequisite such as the Task 162 manifest or exact hashes
  is absent.
- `EPIC_WAVE1_INDEX_IMPLEMENTATION_NO_GO`: an invariant is violated, an
  unsafe path is requested, verified artifacts are corrupt, or a build fails
  after authorization.

Current decision: **`EPIC_WAVE1_INDEX_IMPLEMENTATION_REPAIR`**.
