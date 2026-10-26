# EPIC Wave-1 full-timeline index final audit

**Date:** 2026-09-29  
**Task:** 164  
**Scope:** two-source restricted full-timeline index build and independent audit  
**Decision:** `EPIC_WAVE1_FULL_TIMELINE_READY`

## 1. Final decision

The canonical EPIC Wave-1 full-timeline index is complete and accepted.

The exact CPU build completed over both Task 162 sources with resume enabled
and eight threads. All eight source-layer checkpoints completed. After a
narrow verifier repair, the canonical verifier passed **336 checks with zero
failures**. A separate recomputation of source identity, timeline counts,
checkpoint keys and payload hashes, model bindings, output modes, storage,
artifact boundaries, and path safety passed **74,243 checks with zero
failures**.

The exact full build was then rerun from the validated checkpoints. All 13
canonical output-file hashes were byte-identical, and all eight checkpoint
modification times were unchanged.

No families, negatives, interventions, trajectories, controller or agent
runs, evaluation, metrics, or human semantic conclusions were generated.

## 2. Inputs and authorization

Reviewed:

- `docs/review/epic_wave1_exact_acquisition.md`;
- `docs/design/epic_wave1_full_timeline_index_v1.md`;
- `docs/review/epic_wave1_index_implementation_audit.md`;
- `orchestration/results/162_epic_wave1_exact_acquisition.txt`;
- `orchestration/results/163_epic_wave1_index_implementation.txt`;
- `data/rehearsal_plan/epic_wave1_full_timeline_index_v1.json`;
- the owned EPIC package, build/verifier scripts, and focused tests.

The Task 162 acquisition gate was independently reloaded and rehashed:

```text
decision: EPIC_WAVE1_ACQUISITION_READY
acquisition manifest SHA-256:
6658c99ccf807c83d9a0fce8509c2643ba13b1434a2309fcf13a4bd4c07b3aad
failed transfers: 0
incomplete transfers: 0
complete sources: 2
```

Exact source identities:

| Source | Bytes | MD5 | SHA-256 |
|---|---:|---|---|
| `P28_103` | 5,529,540,372 | `30258174e4ae5cee495170d2748efc4e` | `a2f1023ab698f790430ed126f9fddfd9b0de6258f57f6f89cdfb0ab131f9cf8e` |
| `P27_101` | 4,120,358,548 | `f3e40c9216ab5f05cddb762bd70278d5` | `3b843787ad5906fe48d6b440b305a4dd31346e9a1569211286b3705a3baa1c0d` |

Both media objects remained regular non-symlink files at the exact frozen
paths, with file mode `0600` and parent mode `0700`. Audio/video stream and
A/V-sync evidence remained present and passed.

## 3. Pre-build validation and narrow repairs

Initial syntax compilation and Ruff passed. The first focused test run found
three stale assertions that still expected Task 162's acquisition manifest to
be absent. The tests were updated, within the owned test directory, to assert
the now-current READY acquisition state and missing-output fail-closed
behavior.

The independent post-build audit also found a real verifier coverage gap. The
verifier checked checkpoint files, sizes, and file hashes, but did not itself
check all promised internal checkpoint bindings. The repair was limited to:

- `scripts/verify_epic_wave1_full_timeline.py`;
- `tests_epic_wave1_index/test_cli_and_verifier.py`;
- `tests_epic_wave1_index/test_sources.py`.

The repaired verifier now checks:

- exact checkpoint path inventory;
- source hash, layer version, scale, shard, and observation-config hash in
  every checkpoint key;
- internal checkpoint record count and payload hash;
- layer-specific payload cardinalities;
- source identity within checkpoint records;
- observation configuration hash and segment-manifest binding;
- frozen model file inventory, file hashes, snapshot hashes, weight pins,
  local-only flags, and CPU binding;
- acquisition/resource source bindings; and
- exact output file and directory inventory.

Final focused validation:

```text
focused Ruff: PASS
focused py_compile: PASS
focused pytest: 12 passed
```

No production inference behavior, source plan, model asset, threshold, or
learned output was changed.

## 4. Dry preflight and smoke gate

Canonical dry preflight returned:

```text
decision: EPIC_WAVE1_INDEX_IMPLEMENTATION_READY
status: READY
media_decoded: false
artifacts_written: false
staging_tree_read: false
threads: 8
device: cpu
```

The exact bounded smoke command was run:

```bash
PYTHONPATH=src python scripts/build_epic_wave1_full_timeline.py \
  --repo-root . --execute --mode smoke --smoke-seconds 32 \
  --resume --threads 8 --device cpu
```

Smoke output:

- 16 base cells;
- 16 fine windows;
- 4 context windows;
- 20 temporal segments;
- 4 Whisper chunks;
- 16 AST calls;
- 16 routing records;
- 16 CLIP cell vectors;
- eight checkpoints.

The repaired smoke verifier passed **336 checks with zero failures**. This
satisfied the GO condition for the full build.

## 5. Exact full build

Executed exactly:

```bash
PYTHONPATH=src python scripts/build_epic_wave1_full_timeline.py \
  --repo-root . --execute --mode full \
  --resume --threads 8 --device cpu
```

Result:

```text
status: COMPLETE
mode: full
output_root: data/restricted/epic_wave1_index_v1
checkpoint_count: 8
build_manifest_hash:
sha256:a3abb46c9f5e71a08078671db1763cecf0f576427197049e31d6b7e77430615c
```

The runtime manifests bind execution to CPU, eight threads,
`network_access=disabled`, `HF_HUB_OFFLINE=1`, and
`TRANSFORMERS_OFFLINE=1`.

## 6. Exact timeline and observation counts

Counts were independently recomputed from the frozen source durations.

| Source | Base cells | Fine | Context | Segments | Whisper chunks | Checkpoints |
|---|---:|---:|---:|---:|---:|---:|
| `P28_103` | 457 | 456 | 114 | 570 | 61 | 4 |
| `P27_101` | 341 | 340 | 85 | 425 | 46 | 4 |
| **Total** | **798** | **796** | **199** | **995** | **107** | **8** |

Exact learned-observation inventory:

- routing cells: **798**;
- CLIP cell vectors: **798**;
- AST fine-window calls: **796**;
- ambient temporal records: **995**;
- visual temporal records: **995**;
- Whisper chunks: **107**;
- speech records: **107**;
- maximum modality/segment records: **2,985**.

The segment intervals themselves matched the frozen 4-second, 8-second,
32-second, and 30-second lattices, including terminal partials.

## 7. Checkpoints

Exactly one checkpoint exists for each source and each required layer:

| Source/layer | Records | File SHA-256 |
|---|---:|---|
| `P27_101/ambient.json` | 340 AST fine calls | `a72e82d68bd1dfa2198b0b6b6328925c2180688469d1a6175cfcf6f0df46717a` |
| `P27_101/speech.json` | 46 chunks | `d55fba6d6c19fad99e0d09b4f083e531b925b5f96d4f653417b0dc60e44e7464` |
| `P27_101/vision_clip.json` | 341 cells | `e29590224e857eef806884c529bd88debe25e79c3dc90e33a04ed165c07464d2` |
| `P27_101/vision_routing.json` | 341 cells | `906e5c80693d245988a9343bfe23e82fa8cb26ef3eab9070cf9a513a6f860ad3` |
| `P28_103/ambient.json` | 456 AST fine calls | `a55b96afb96841d6572908f2575b1385133928cee0872b59b0bcac84a61fac6b` |
| `P28_103/speech.json` | 61 chunks | `849c2296df2810af167511e4dea56045e13325e0c3784e5115d473f3a130f40f` |
| `P28_103/vision_clip.json` | 457 cells | `c76f33e6bad37219269a10b0bfccda02fec9bcc0d7779f88d3969ee21c4ef25c` |
| `P28_103/vision_routing.json` | 457 cells | `d6abefae1515a15133a4923cc5b64f03374c89801e6e1f703044aa3b57eb182e` |

All checkpoint keys, payload hashes, file hashes, byte counts, source hashes,
layer/scale bindings, configuration bindings, record counts, and modes
passed.

## 8. Frozen model binding

| Layer | Snapshot hash | Pinned weight/asset hash | Result |
|---|---|---|---|
| Whisper tiny.en | `sha256:1e098354f3cbd9f339ef8fbdcc0e82ff238786bffa25794493ebe32830f4518a` | `db59695928ded6043adaef491a53ef4e12da9611184d77c53baa691a60b958ad` | PASS |
| AST AudioSet | `sha256:acb9247d5f2548c121e7fd213347586e1b781fd8dc329e27505dd269a69cccbc` | `ae0c1e2ad4e1381d851fa9bf298ba13ebc9c5a914cdee2dbe427a6583869924d` | PASS |
| CLIP ViT-B/32 | `sha256:2c29598276753a41d293ca65ef8fe60287ed62d8cd94b0ee77ec38ecb41a20f5` | `a63082132ba4f97a80bea76823f544493bffa8082296d62d71581a4feff1576f` | PASS |
| OpenCV Haar | `sha256:a9ee3c8bf4ab44314001ffa728bbfc388fcc579790b8b2909d71dd80306d2f40` | `0f7d4527844eb514d4a4948e822da90fbb16a34a0bbbbc6adc6498747a5aafb0` | PASS |

Every model file listed in `resource_manifest.json` was rehashed. Model file
inventory, snapshot hash, pinned weight/asset hash, local-only status, and CPU
device binding passed.

## 9. Modes, storage, paths, and stage boundary

The canonical root contains exactly:

- five top-level JSON artifacts;
- eight checkpoint JSON files;
- one `checkpoints/` directory and two source checkpoint directories.

Results:

- all 13 files are mode `0600`;
- all four output directories, including the root, are mode `0700`;
- derived bytes before `build_manifest.json`: **16,492,520**;
- total canonical bytes including `build_manifest.json`: **16,494,988**;
- 256 MiB soft cap: PASS;
- 512 MiB hard cap and persisted binding: PASS;
- no symlinks: PASS;
- no absolute, escaping, or `.staging` paths in output artifacts: PASS;
- no persisted audio, video, image, frame, or clip derivatives: PASS;
- no family, negative, intervention, trajectory, controller, agent-run,
  evaluation, or metric artifact: PASS;
- no forbidden private, rights, evaluator, or label fields in searchable
  records: PASS.

The source and output path loaders reject every `.staging` path. The plan and
all canonical outputs contain no staging path. The acquisition staging
directory retains only `fetch_range.sh` and `run_parallel_ranges.sh`; no
`.part` or `chunk-*.bin` transfer object remains. No syscall-level tracing
claim is made; a supplementary `strace` attempt was not used. The no-staging
finding is based on the fail-closed path implementation, canonical preflight,
artifact/path audit, and staging custody inspection.

## 10. Deterministic resume

Before resume, SHA-256 values and checkpoint modification times were recorded
for all 13 canonical files. The exact full command was rerun with all eight
checkpoints valid.

Results:

- all 13 before/after file SHA-256 values were byte-identical;
- all eight checkpoint modification times were unchanged;
- the five top-level JSON files were deterministically rewritten with
  byte-identical content;
- sorted 13-file hash-list SHA-256 before and after:

```text
9c5658749e92f8f5e9bd9d3fabe14aaee804569dba76dc097405527151c32ae6
```

The repaired canonical verifier passed **336/336** again after resume.

## 11. Canonical top-level file hashes

| Artifact | Bytes | File SHA-256 |
|---|---:|---|
| `segment_manifest.json` | 680,916 | `bd3764894ec50003344c488da24f7de6e7336100b737c68fa672afdaee809bf5` |
| `observation_manifest.json` | 6,413 | `b38b1c0ae7395e0247f0a580b728c52b02e5a8d71b5f79f957f92de5e44417d8` |
| `full_timeline_index.json` | 7,778,033 | `8b0ac50910ae6c1383bce2c3602485728450ac9dc0797d647ce27f496c8934b9` |
| `resource_manifest.json` | 9,309 | `66408dfe71fd0444d0ac20e8225a2bbeaa7f3cc85440b1905af417122fda71d9` |
| `build_manifest.json` | 2,468 | `e029c126e22c2cd6b28133baad08f4327fad5b8c06ebaaeff5d663707874a9cb` |

## 12. Boundary and decision

This acceptance covers only the restricted EPIC Wave-1 full-timeline index.
It does not authorize semantic source conclusions, candidate-family
generation, hard negatives, interventions, trajectories, controller or agent
runs, evaluation, metrics, public release, or redistribution.

Final decision:

```text
EPIC_WAVE1_FULL_TIMELINE_READY
```
