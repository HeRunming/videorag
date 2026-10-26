# CaptainCook4D Wave-0 full-timeline final audit

**Date:** 2026-10-10  
**Task:** 189  
**Scope:** three-source restricted full-timeline index and deterministic resume  
**Decision:** `CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY`

## 1. Final decision

The canonical CaptainCook4D Wave-0 full-timeline index is complete and
accepted at:

`data/restricted/captaincook4d_wave0_index_v1/`

The exact Task188 source identities, source manifests, durations, stream and
EOF evidence, local model assets, 4/8/32-second timeline lattice, 30-second
speech lattice, learned-observation cardinalities, checkpoint identities,
output inventory, modes, storage limit, and stage boundary passed.

The canonical verifier passed **410 checks with zero failures**. A separate
independent audit recomputed timeline intervals and bindings, checkpoint
payloads, index records, model/source/artifact bindings, and output safety,
passing **217,335 checks with zero failures** before resume.

After recording all 17 canonical file hashes/sizes and all 12 checkpoint
mtimes, the exact full build command was rerun. The resume-aware independent
audit passed **217,338 checks with zero failures**:

- file inventory identical;
- all 17 file hashes and sizes identical;
- all 12 checkpoint mtimes unchanged;
- sorted canonical file-hash-list SHA-256:
  `c300c10bdb458fb4cbe07c4cf2ad97ebc551349ef335102694d7777e1e3c5071`.

## 2. Input gate

Task188 acquisition manifest:

```text
decision: CAPTAINCOOK4D_WAVE0_ACQUISITION_READY
SHA-256:
ee50c9579b77f7ee4f45753adad1d5d1e09569c6b1be5308a82ccbcc9a05934a
source count: 3
replacement events: 0
distinct people: 3
distinct environments: 3
```

Exact sources:

| Source | Person/environment | Duration | Bytes | MD5 | SHA-256 |
|---|---|---:|---:|---|---|
| `16_20` | 1 / 8 | 1930.90 s | 230,486,870 | `74defe8b6b9eca32e05a386cb31296ea` | `8082945db8c24cb40e3dd76eafc11cb2b3df5a0b8bdb2e5c22e1ada98ae82f12` |
| `15_29` | 2 / 2 | 1292.82 s | 181,454,428 | `22bede9e345d59406959a98f012393c3` | `f1f77f09d6ffd35531f4d23fb3d4bfe3eb350e71a7240ced9ac9b4f28b8b048d` |
| `26_22` | 3 / 3 | 1324.22 s | 131,633,528 | `ab63a75fe9bc333c1a87515ede58d0a2` | `3c4b69b4ad37c4318b24d034cf0fdd3fa2eb96b3e85136001b0ea531b5abbd7b` |

All source files and source manifests remained regular non-symlink files,
mode `0600`, under a mode-`0700` restricted source root. Task188 technical
evidence continued to show audio/video streams, synchronized
beginning/middle/end decode, complete PyAV/OpenCV EOF, and no truncation.

## 3. Implementation and validation

Owned implementation:

- `src/av_trace_captaincook4d_wave0_index/`;
- `scripts/build_captaincook4d_wave0_full_timeline.py`;
- `scripts/verify_captaincook4d_wave0_full_timeline.py`;
- `scripts/audit_captaincook4d_wave0_full_timeline.py`;
- `tests_captaincook4d_wave0_index/`;
- the Task189 plan, design, audit, result, smoke output, and canonical output.

Focused validation:

```text
pytest: 13 passed
Ruff: PASS
py_compile: PASS
plan JSON parse: PASS
```

Dry preflight passed with:

```text
media_decoded: false
artifacts_written: false
staging_tree_read: false
network_access: disabled
device: cpu
threads: 8
```

## 4. Smoke gate

The exact 32-second-per-source smoke build completed with:

- 24 base cells;
- 24 fine windows;
- 6 context windows;
- 30 temporal segments;
- 6 Whisper chunks and speech records;
- 24 AST calls;
- 24 routing cells;
- 24 CLIP cell vectors;
- 12 checkpoints.

The smoke verifier passed **410 checks with zero failures**. Smoke bytes were
527,643.

## 5. Exact full build

Executed:

```bash
PYTHONPATH=src python scripts/build_captaincook4d_wave0_full_timeline.py \
  --repo-root . --execute --mode full \
  --resume --threads 8 --device cpu
```

Final build-manifest internal hash:

`sha256:460f14f4b37de8024745fe4709732fd6d15d6da6042097de062006b30e707ebe`

Final plan SHA-256:

`9c86f22b8b0102491632aa5570d95c5553f8426d65b00e0e9af2771a26603431`

## 6. Full counts

| Source | Base | Fine | Context | Segments | Whisper | Checkpoints |
|---|---:|---:|---:|---:|---:|---:|
| `16_20` | 483 | 482 | 120 | 602 | 65 | 4 |
| `15_29` | 324 | 323 | 80 | 403 | 44 | 4 |
| `26_22` | 332 | 331 | 82 | 413 | 45 | 4 |
| **Total** | **1,139** | **1,136** | **282** | **1,418** | **154** | **12** |

Learned-observation inventory:

- AST fine calls: 1,136;
- routing cells: 1,139;
- CLIP cell vectors: 1,139;
- speech records: 154;
- ambient records: 1,418;
- visual records: 1,418.

## 7. Checkpoint identities

| Checkpoint | Input records | File SHA-256 |
|---|---:|---|
| `15_29/ambient.json` | 323 | `91c0fe89ec22991a3e08ac30f239492bd3db209b6e6fe74449cca2b6463e26f8` |
| `15_29/speech.json` | 44 | `48f04991fbb8b6ad79d8df3811420de3954a798512daaadeee9f86660f3de963` |
| `15_29/vision_clip.json` | 324 | `48d55bff00a04a059c8c77c426a6b56f5a4b2020c3667e3db55017a1b63a3f26` |
| `15_29/vision_routing.json` | 324 | `88d99b56c82a408db52336268b41027f0866e0a3c20216f49bdcca2cab9a5987` |
| `16_20/ambient.json` | 482 | `84b58a24e24d87c59e00ef65091ee9980df30b205df22af825cfd71159f1c38d` |
| `16_20/speech.json` | 65 | `289e0e97e542978abd74286ae2535885c614aaebb52507c31d8a06ef9fc19528` |
| `16_20/vision_clip.json` | 483 | `d949b98a51cd2d14efc1ccdabb37e4e79904edb882a00e9800d1a163eb0169c4` |
| `16_20/vision_routing.json` | 483 | `5afd2d3dba064d2d14b96a8477aee86dfc3667634d9a467fc01823ecf2f3b884` |
| `26_22/ambient.json` | 331 | `652fcfc4c5def18ece3db13e58009be2b744cd55e81c75cf9cc495ed6723373c` |
| `26_22/speech.json` | 45 | `bb5924f01d9d92d59ffb9e9d06d27eb9d16b63bd8aad490ca9cabebcee96514d` |
| `26_22/vision_clip.json` | 332 | `6201ff63c79e7f9d228a6ec4fe7df8b19bf058a862e4b7a4d42c3d90a3d5aa77` |
| `26_22/vision_routing.json` | 332 | `419c52dadbf79357bdc6ec3ef240e9679aab0e6667cad2c1c467091c7e399ea6` |

Every key, layer, scale, source hash, configuration hash, record count,
payload hash, file hash, byte count, source binding, and mode passed.

## 8. Frozen model binding

| Layer | Snapshot hash | Pinned weight/asset SHA-256 |
|---|---|---|
| Whisper tiny.en | `sha256:1e098354f3cbd9f339ef8fbdcc0e82ff238786bffa25794493ebe32830f4518a` | `db59695928ded6043adaef491a53ef4e12da9611184d77c53baa691a60b958ad` |
| AST AudioSet | `sha256:acb9247d5f2548c121e7fd213347586e1b781fd8dc329e27505dd269a69cccbc` | `ae0c1e2ad4e1381d851fa9bf298ba13ebc9c5a914cdee2dbe427a6583869924d` |
| CLIP ViT-B/32 | `sha256:2c29598276753a41d293ca65ef8fe60287ed62d8cd94b0ee77ec38ecb41a20f5` | `a63082132ba4f97a80bea76823f544493bffa8082296d62d71581a4feff1576f` |
| OpenCV Haar | `sha256:a9ee3c8bf4ab44314001ffa728bbfc388fcc579790b8b2909d71dd80306d2f40` | `0f7d4527844eb514d4a4948e822da90fbb16a34a0bbbbc6adc6498747a5aafb0` |

## 9. Canonical artifact hashes and storage

| Artifact | Bytes | File SHA-256 |
|---|---:|---|
| `segment_manifest.json` | 965,198 | `3332e295d363e7f19573efb6f823d4b592377a204eb275989e6daed95445c36b` |
| `observation_manifest.json` | 8,634 | `edd92f0647fcebaa7ae2e0388e996fc1c3326a583e80d79da3a741a570d3ee45` |
| `full_timeline_index.json` | 11,018,977 | `c15c49fbac62ed103d4fa2298da72a3c9848e86c59031151da609e0334d0b878` |
| `resource_manifest.json` | 9,816 | `c0fdb0fdb353eabd664083b2ee96fb3474ab8dbf767fce471ab976ae5f13118d` |
| `build_manifest.json` | 3,019 | `28ba18a2388a7e077716422eeecb0816f7a37411507ee1dd527fbc085553318f` |

Storage and inventory:

- exactly 17 canonical JSON files;
- exactly 5 canonical directories including the root;
- all files mode `0600`;
- all directories mode `0700`;
- derived bytes before build manifest: 23,421,024;
- total canonical bytes: 23,424,043;
- 256 MiB soft cap: PASS;
- 512 MiB hard cap: PASS;
- no symlinks, absolute paths, path escape, or `.staging` path;
- no persisted media derivatives;
- no annotation, family, negative, intervention, trajectory, agent,
  controller, evaluation, or metric artifact.

## 10. Deterministic resume

The final plan was frozen first. A snapshot then recorded:

- all 17 canonical file paths, SHA-256 values, sizes, and mtimes;
- all 12 checkpoint mtimes.

The exact full command was rerun from all 12 valid checkpoints. Results:

```text
file inventory equal: true
all file hashes and sizes equal: true
all checkpoint mtimes equal: true
before files: 17
after files: 17
checkpoints: 12
sorted file-hash-list SHA-256:
c300c10bdb458fb4cbe07c4cf2ad97ebc551349ef335102694d7777e1e3c5071
```

The canonical verifier then passed 410/410 again.

## 11. Boundary and decision

This acceptance covers indexing only. It does not establish human semantic
eligibility, H tiers, modality necessity, candidate families, interventions,
trajectories, evaluation readiness, or release authorization.

Final:

`CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY`
