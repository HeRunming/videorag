# Mini-pilot full-timeline indexing final audit

**Date:** 2026-09-23  
**Scope:** Task 136 four-source, full-duration, indexing-only build and audit  
**Decision:** `MINI_PILOT_FULL_TIMELINE_READY`

## 1. Final decision

The canonical four-source mini-pilot full-timeline index is accepted.

The exact authorized build completed over all four Task-132 sources with the
locally frozen Whisper, AST, CLIP, and OpenCV routing assets on CPU. All 16
source-layer checkpoints completed. The repaired frozen verifier passed
**395 checks with zero failures**, and a separate recomputation of source
identity, lattice counts, checkpoint payloads, model gates, paths, modes,
privacy boundaries, storage, and resume determinism also returned zero
failures.

No candidate-family mining, family migration, negative construction,
intervention construction, controller or agent execution, trajectory
generation, evaluation, metric reporting, or human annotation was run.

## 2. Authorization and pre-build gates

### Task 132 acquisition gate

`orchestration/results/132_four_source_exact_acquisition.txt` records:

```text
MINI_PILOT_FOUR_SOURCE_ACQUISITION_READY
```

The source-plan loader independently revalidated the acquisition manifest,
four source manifests, four primary media objects, and five official
transcript/caption sidecars. The aggregate acquisition-manifest SHA-256
remains:

```text
36bdc5efd973189f14f1876d4bb753617c254f1f12267cbc83934be96d680e90
```

### Task 135 smoke gate

`orchestration/results/135_mini_pilot_index_smoke.txt` records:

```text
MINI_PILOT_INDEX_SMOKE_GO
```

### Canonical output state

Before execution, `data/restricted/mini_pilot_index_v1/` was absent, so the
requested `--resume` run began as a clean canonical build. The output root did
not overlap the source root and was not a symlink.

### Preflight, tests, and lint

Commands:

```bash
PYTHONPATH=src python scripts/build_mini_pilot_full_timeline.py --repo-root .
PYTHONPATH=src pytest -q tests_mini_pilot_index
python -m ruff check \
  scripts/build_mini_pilot_full_timeline.py \
  scripts/verify_mini_pilot_full_timeline.py \
  src/av_trace_mini_pilot_index \
  tests_mini_pilot_index
```

Results before the heavy build:

- offline technical preflight: `READY`;
- expected checkpoints: **16**;
- expected base cells: **3,208**;
- expected fine windows / AST calls: **3,204**;
- expected context windows: **800**;
- expected temporal segments: **4,004**;
- expected Whisper chunks: **430**;
- focused tests: **29 passed**;
- focused Ruff: **passed**;
- all four source and model gates: **passed**.

The mounted `.git` directory contains no repository metadata, so Git status
could not be inspected. Concurrent files were not reverted. Changes were
limited to the owned indexing implementation/verifier/tests and the requested
audit outputs.

## 3. Exact full build

Executed exactly:

```bash
PYTHONPATH=src python scripts/build_mini_pilot_full_timeline.py --execute --resume --threads 8 --device cpu
```

The uninterrupted CPU build completed successfully:

```text
status: complete
mode: full_build
source_count: 4
checkpoint_count: 16
routing_cells: 3208
clip_cells: 3208
ast_fine_calls: 3204
ambient_records: 4004
vision_records: 4004
whisper_chunks: 430
speech_records: 430
downstream_stages_triggered: false
no_persisted_media_derivatives: true
```

The runtime manifest binds execution to `device=cpu`,
`network_access=disabled`, `HF_HUB_OFFLINE=1`, and
`TRANSFORMERS_OFFLINE=1`.

## 4. Narrow owned repair

The first post-build frozen verifier passed **393 checks with zero failures**.
Independent audit then identified one narrow implementation/verifier defect:

1. The CLI constructed an `IndexConfig` rather than passing the source-plan
   object directly, so the frozen **512 MiB** derived-artifact cap was not
   copied into the build configuration. The verifier independently enforced
   the cap, but the persisted build manifest recorded the cap as `null`.
2. The builder's `derived_artifact_bytes_before_build_manifest` calculation
   could include an already-existing build manifest during resume, making
   that accounting field differ between the initial build and first resume.

The repair was limited to:

- `src/av_trace_mini_pilot_index/core.py`;
- `scripts/build_mini_pilot_full_timeline.py`;
- `scripts/verify_mini_pilot_full_timeline.py`;
- `tests_mini_pilot_index/test_core.py`;
- `tests_mini_pilot_index/test_cli.py`.

The repair:

- carries the frozen 512 MiB cap through both source-plan and CLI config paths;
- excludes `build_manifest.json` from the pre-build-manifest byte baseline;
- verifies the persisted cap and byte-accounting binding;
- adds regression coverage for cap propagation and byte-identical resume.

No source, plan, model, Scale-1A artifact, learned output, threshold, family,
intervention, controller/evaluator artifact, or human datum was changed. No
deterministic substitute was introduced and no contract was weakened.

Post-repair validation:

```text
PYTHONPATH=src pytest -q tests_mini_pilot_index: 30 passed
focused Ruff: passed
```

One intermediate verifier run correctly returned:

```text
MINI_PILOT_INDEX_NO_GO
failure: build_derived_bytes_binding
```

That exposed the stale-build-manifest accounting issue above. After excluding
the prior build manifest from the byte baseline, the exact resume and verifier
both passed.

## 5. Frozen verifier result

Command:

```bash
PYTHONPATH=src python scripts/verify_mini_pilot_full_timeline.py --repo-root .
```

Final result:

```text
verified: true
decision: MINI_PILOT_INDEX_VERIFIED
verification_mode: full_build
check_count: 395
failures: []
sources: 4
checkpoints: 16
base_cells: 3208
temporal_segments: 4004
derived_bytes: 68099838
```

## 6. Independent count recomputation

Counts were recomputed directly from the four frozen durations using the
4/8/32-second lattice and 30-second speech chunks, rather than trusting the
persisted count summaries.

| Source | Base cells | Fine | Context | Segments | Whisper chunks | Checkpoints |
|---|---:|---:|---:|---:|---:|---:|
| `SG-OXFORD-QM-001` | 662 | 661 | 165 | 826 | 89 | 4 |
| `SG-OXFORD-DHL-CONSCIOUSNESS` | 730 | 729 | 182 | 911 | 98 | 4 |
| `SG-MIT-RES12-003-L01` | 715 | 714 | 178 | 892 | 96 | 4 |
| `SG-YALE-PHYS200-L01` | 1,101 | 1,100 | 275 | 1,375 | 147 | 4 |
| **Total** | **3,208** | **3,204** | **800** | **4,004** | **430** | **16** |

Independent payload totals:

- routing cell records: **3,208**;
- CLIP cell vectors: **3,208**;
- fine AST records/calls: **3,204**;
- ambient temporal records: **4,004**;
- visual temporal records: **4,004**;
- Whisper chunks: **430**;
- speech records: **430**.

Every source has exactly one checkpoint for each of:

- `speech.json`;
- `ambient.json`;
- `vision_routing.json`;
- `vision_clip.json`.

Checkpoint keys, record counts, JSON payload hashes, file hashes, file sizes,
and modes all passed.

## 7. Frozen model gates

| Layer | Snapshot hash | Pinned weight/asset hash | Gate |
|---|---|---|---|
| Whisper | `sha256:1e098354f3cbd9f339ef8fbdcc0e82ff238786bffa25794493ebe32830f4518a` | `db59695928ded6043adaef491a53ef4e12da9611184d77c53baa691a60b958ad` | PASS |
| AST | `sha256:acb9247d5f2548c121e7fd213347586e1b781fd8dc329e27505dd269a69cccbc` | `ae0c1e2ad4e1381d851fa9bf298ba13ebc9c5a914cdee2dbe427a6583869924d` | PASS |
| CLIP | `sha256:2c29598276753a41d293ca65ef8fe60287ed62d8cd94b0ee77ec38ecb41a20f5` | `a63082132ba4f97a80bea76823f544493bffa8082296d62d71581a4feff1576f` | PASS |
| OpenCV Haar | `sha256:a9ee3c8bf4ab44314001ffa728bbfc388fcc579790b8b2909d71dd80306d2f40` | `0f7d4527844eb514d4a4948e822da90fbb16a34a0bbbbc6adc6498747a5aafb0` | PASS |

All model files were rehashed, all paths were repository-relative, every
model was marked frozen and local-only, and every runtime/model device was
CPU.

## 8. Paths, privacy, artifact boundary, modes, and storage

Independent audit results:

- all persisted paths are repository-relative, normalized, and non-escaping;
- no absolute `/jizhicfs/` or `file://` path leaked into artifacts;
- no forbidden evaluator/private/rights fields occur as searchable record
  fields;
- no decoded frames, audio, clips, or other media derivatives are persisted;
- no family, negative, intervention, trajectory, controller, agent-run,
  evaluation, or metric artifact exists under the output root;
- output/checkpoint directories are `0700`;
- all **21** JSON files are `0600`;
- derived output is **68,099,838 bytes** (**64.945066 MiB**);
- 256 MiB soft cap: **PASS**;
- 512 MiB hard cap: **PASS**;
- build-manifest hard-cap binding: **512 MiB**, PASS;
- pre-build-manifest byte binding: **68,098,074 bytes**, PASS.

The frozen Scale-1A verifier was also rerun after the build:

```text
SCALE1A_ENGINEERING_GO
failures: []
verified_inventory_count: 94
```

## 9. Deterministic resume

After the narrow repair, the exact build command was run twice from the 16
valid checkpoints. Neither run decoded media or reran learned inference.
Before/after SHA-256 listings for all 21 output files were byte-identical.

SHA-256 of the sorted 21-file SHA-256 listing on both sides:

```text
039db3b53fd852fa1b1031d1fd4ad921e3e67ec3cc8e4a2357a0fd1d22a33aff
```

The frozen verifier passed again after the deterministic resume.

## 10. Canonical top-level hashes

### File SHA-256

| Artifact | File SHA-256 |
|---|---|
| `segment_manifest.json` | `f73606374dfe2bf2904f634c124d27d9f4f002b60aec55e41b34c18847fb2114` |
| `observation_manifest.json` | `d60f930fd6909a0b8d57b82b31a4a82213c6209b6f06f135d35c3f3270cd52c5` |
| `full_timeline_index.json` | `6f8f7fb3e13a4a374901b79220f55b4e5b18d8923d2c78302b383793d3dd122a` |
| `resource_manifest.json` | `9b93576a8031683ca022e1b0fbc1b8976f610024970f2d824b9024e6303918c6` |
| `build_manifest.json` | `93aa3baf32f1edfbc68415f572616d510fd130a1db51f537838131f14fb60800` |

### Internal canonical self-hashes

| Artifact | Internal hash |
|---|---|
| segment manifest | `sha256:e0e9cc7f79c87e7d301aaae238e9835baebe603ca1e6ca0d36d4cd61358f42e8` |
| observation manifest | `sha256:cd31dc1f7a5d239f3872df9fe8fe4661b65c4e07dca38c70dce73b481b6e84ec` |
| full timeline index | `sha256:5b84f3629849b63bb567ec60d0e2a304fc4aae6758630672ff2036d8b08e12eb` |
| resource manifest | `sha256:8e4b9932a4c22699f70a3a1ce48ffb15726a94fd173808324928ba0481e656dd` |
| build manifest | `sha256:63d9e11f1d3a949d72f1a9aa148b24c79188bf4209eb46b68ff69a5136c344f6` |

## 11. Checkpoint file hashes

| Source/layer | File SHA-256 |
|---|---|
| `SG-OXFORD-QM-001/speech.json` | `aada110bd525d156fa493cf10e59783922275b76ddd3495a4ccd0830f7188914` |
| `SG-OXFORD-QM-001/ambient.json` | `222fdb630e1d452f1e6c37b8d8445f4c6f51424ec2cf1067e21514e91c2410d1` |
| `SG-OXFORD-QM-001/vision_routing.json` | `6d7e37e1a8f6676f3715b85268af16bac291b39d04c317a53042fb6ee091c751` |
| `SG-OXFORD-QM-001/vision_clip.json` | `79475ad4dcc45b3e94cdb02a9431299d03165967e64e5f8dcc0c90651db8fc78` |
| `SG-OXFORD-DHL-CONSCIOUSNESS/speech.json` | `07ec8c3550f16203fbed96658281b8fe5048191e1ae62ae0b8c169d21dcf8f9d` |
| `SG-OXFORD-DHL-CONSCIOUSNESS/ambient.json` | `5f404d5d13972c54ce4b5ec8d441ce12c1ae9bb1358236e45551ed0943bbeb33` |
| `SG-OXFORD-DHL-CONSCIOUSNESS/vision_routing.json` | `e9c3965ecc06353877fa40a726a6bb4e59601cf64463af050ae33123fd741690` |
| `SG-OXFORD-DHL-CONSCIOUSNESS/vision_clip.json` | `15e53265a36e61962667f528c9e5f989eface50cf7e2da0b39cd9ed3db4858db` |
| `SG-MIT-RES12-003-L01/speech.json` | `f63bbc780efa309c1ce2c2da149377a28bdeb51715e0c36eea089e36e036ab74` |
| `SG-MIT-RES12-003-L01/ambient.json` | `ee73962802a4fd726fcdf0600f96d506ab9ab21a42871fd52224977774587384` |
| `SG-MIT-RES12-003-L01/vision_routing.json` | `271ec709ed42c16062fdd487be614d4819fe13113593be1a32b44936b8040003` |
| `SG-MIT-RES12-003-L01/vision_clip.json` | `6831fee70be54f483ececb0d85d9d4b76370f3e525387c3f2a0583701828ea3e` |
| `SG-YALE-PHYS200-L01/speech.json` | `4382870de84415dab1ec56408f65fd01225daada54218bab683f637e9c3881ec` |
| `SG-YALE-PHYS200-L01/ambient.json` | `025d5cdc06e180460b93747198f9abace33c51d8c2ea8aa81f4a4c6595f39a7a` |
| `SG-YALE-PHYS200-L01/vision_routing.json` | `32fc7f26737534461ef463ce21b4c104fb81ba6dcbf9cb9f8d15ad77e68593d1` |
| `SG-YALE-PHYS200-L01/vision_clip.json` | `28fcd3e4cbcc1d794245bf5e62f6de5e5a255b77f16865155240d1f46c83ff16` |

## 12. Persisted outputs and boundary

Persisted:

- `data/restricted/mini_pilot_index_v1/`;
- `docs/review/mini_pilot_full_timeline_final_audit.md`;
- `orchestration/results/136_mini_pilot_full_timeline_build.txt`.

Final decision:

```text
MINI_PILOT_FULL_TIMELINE_READY
```

This decision covers the frozen four-source full-timeline index only. It does
not authorize family mining or any other downstream stage.
