# Mini-pilot full-timeline bounded-smoke audit

**Date:** 2026-09-23  
**Scope:** Task 135 real-model, four-source, 8-second bounded smoke  
**Decision:** `MINI_PILOT_INDEX_SMOKE_GO`

## 1. Decision

The bounded smoke is accepted. The exact requested build completed over all
four frozen Task-132 sources using the locally frozen Whisper, AST, CLIP, and
OpenCV routing assets on CPU. The explicit smoke verifier passed **393 checks**
with no failures after a narrow verifier-only repair that teaches the verifier
to derive smoke counts from the frozen 4/8/32-second lattice. No index contract
was weakened and no learned output was replaced with a deterministic stand-in.

This is a smoke decision only. It does not authorize or claim completion of the
unbounded full-timeline build, candidate-family work, interventions, agent or
controller execution, evaluation, metrics, annotation, or release.

## 2. Inputs and Workstreams A-C

- **Workstream A:** `docs/design/mini_pilot_full_timeline_index_v1.md` and
  `data/rehearsal_plan/mini_pilot_full_timeline_v1.json` freeze exactly four
  source identities, the 4/8/32-second lattice, 16 source-layer checkpoints,
  local model pins, search-record restrictions, and the downstream boundary.
- **Workstream B:** `src/av_trace_mini_pilot_index/sources.py` and
  `src/av_trace_mini_pilot_index/core.py` implement strict source loading,
  segmentation, frozen local inference, checkpointing, indexing, and terminal
  build manifests.
- **Workstream C:** `scripts/build_mini_pilot_full_timeline.py`,
  `scripts/verify_mini_pilot_full_timeline.py`, and their focused tests provide
  the execution/preflight and independent verification surfaces.

Repository Git status could not be inspected because the mounted `.git`
directory contains no repository metadata. File inspection showed concurrent
work in the tree; only the owned verifier/test files and the requested audit
outputs were changed. No protected input path had a write timestamp during the
smoke/audit interval.

## 3. Pre-execution checks

Commands:

```bash
PYTHONPATH=src pytest -q tests_mini_pilot_index
ruff check src/av_trace_mini_pilot_index \
  scripts/build_mini_pilot_full_timeline.py \
  scripts/verify_mini_pilot_full_timeline.py \
  tests_mini_pilot_index
```

Initial result: **27 focused tests passed; Ruff passed.**

The source-plan loader also rehashed and validated the acquisition manifest,
all four media files, all source manifests, and all official transcript or
caption sidecars. Source directories were `0700`; restricted acquisition,
manifest, media, and sidecar files were `0600`.

The frozen Scale-1A verifier was run after the smoke:

```bash
PYTHONPATH=src python scripts/verify_scale1a.py --repo-root .
```

Result: `SCALE1A_ENGINEERING_GO`, zero failures, trust anchor verified with 94
inventory entries. This confirms that the frozen Scale-1A artifacts remained
valid.

## 4. Exact smoke execution

Executed exactly:

```bash
PYTHONPATH=src python scripts/build_mini_pilot_full_timeline.py --execute --smoke-seconds 8 --output-root data/restricted/mini_pilot_index_v1_smoke --resume --threads 8 --device cpu
```

Result:

- status: `complete`
- mode: `bounded_smoke`
- source count: **4**
- checkpoint count: **16**
- base/routing cells: **8**
- CLIP cells: **8**
- fine AST calls: **8**
- temporal ambient records: **8**
- temporal vision records: **8**
- Whisper chunks / speech records: **4**
- downstream stages triggered: **false**
- persisted media derivatives: **false**

The exact command was run a second time with `--resume`. It completed without
model-loading or inference warnings, and all smoke artifact hashes remained
unchanged, demonstrating valid checkpoint reuse and deterministic persistence.

## 5. Narrow engineering repair

The first verification attempt used the existing full-build verifier against
the smoke output. It correctly validated hashes, modes, paths, source identity,
model pins, and boundaries, but returned `NO_GO` because it compared an
8-second smoke against the full-duration counts (4,004 temporal segments and
430 Whisper chunks).

The narrow repair was limited to:

- `scripts/verify_mini_pilot_full_timeline.py`
- `tests_mini_pilot_index/test_verifier.py`

The verifier now accepts an explicit `--smoke-seconds` mode and derives exact
per-source and aggregate counts from the unchanged frozen lattice. Full-build
verification remains the default and still rejects smoke-sized artifacts. The
smoke mode additionally checks structured evidence of actual inference:

- Whisper chunks contain decoded text, token counts, log-probability quality
  decisions, and source bindings;
- AST fine records contain 15 class IDs/names/probabilities per inference;
- CLIP records contain nonzero 512-dimensional float16 vectors;
- OpenCV routing records contain decoded-frame PTS/time-base and non-semantic
  routing features.

Post-repair checks:

```bash
PYTHONPATH=src pytest -q tests_mini_pilot_index
ruff check src/av_trace_mini_pilot_index \
  scripts/build_mini_pilot_full_timeline.py \
  scripts/verify_mini_pilot_full_timeline.py \
  tests_mini_pilot_index
```

Result: **29 focused tests passed; Ruff passed.**

## 6. Explicit smoke verification

Command:

```bash
PYTHONPATH=src python scripts/verify_mini_pilot_full_timeline.py \
  --repo-root . \
  --output-root data/restricted/mini_pilot_index_v1_smoke \
  --smoke-seconds 8
```

Result:

- verified: **true**
- decision: `MINI_PILOT_INDEX_SMOKE_VERIFIED`
- verification mode: `bounded_smoke`
- checks: **393**
- failures: **0**
- derived bytes: **176,743**

### Four-source coverage and expected smoke records

Each source is bound to its original full media hash and byte count while its
smoke timeline is clipped to exactly 8,000,000 microseconds:

| Source | Base cells | Fine windows | Context windows | Whisper chunks | Checkpoints |
|---|---:|---:|---:|---:|---:|
| `SG-OXFORD-QM-001` | 2 | 2 | 0 | 1 | 4 |
| `SG-OXFORD-DHL-CONSCIOUSNESS` | 2 | 2 | 0 | 1 | 4 |
| `SG-MIT-RES12-003-L01` | 2 | 2 | 0 | 1 | 4 |
| `SG-YALE-PHYS200-L01` | 2 | 2 | 0 | 1 | 4 |
| **Total** | **8** | **8** | **0** | **4** | **16** |

The 16 checkpoint files comprise speech, ambient, vision routing, and CLIP
vision for every source. All checkpoint keys, body counts, payload hashes,
file hashes, sizes, and modes passed verification.

### Actual frozen-model inference

The first run loaded the three local neural snapshots and performed CPU
inference. Persisted outputs demonstrate model-specific, non-placeholder
results:

- Whisper produced one transcript chunk per source. Yale produced a 20-token
  sentence that passed its quality gate; the three shorter opening snippets
  were retained but correctly marked non-searchable by the frozen quality
  gate.
- AST produced 15 scored AudioSet labels for every one of the eight fine
  windows, with source-dependent probabilities.
- CLIP produced two nonzero, normalized, 512-dimensional float16 cell vectors
  per source and pooled visual segment records.
- OpenCV routing persisted source-specific PTS/time-base and visual routing
  features for two sampled frames per source.

The resource and observation manifests bind the run to these exact frozen
snapshot identities:

| Layer | Frozen snapshot hash | Frozen weight/asset hash |
|---|---|---|
| Whisper | `sha256:1e098354f3cbd9f339ef8fbdcc0e82ff238786bffa25794493ebe32830f4518a` | `db59695928ded6043adaef491a53ef4e12da9611184d77c53baa691a60b958ad` |
| AST | `sha256:acb9247d5f2548c121e7fd213347586e1b781fd8dc329e27505dd269a69cccbc` | `ae0c1e2ad4e1381d851fa9bf298ba13ebc9c5a914cdee2dbe427a6583869924d` |
| CLIP | `sha256:2c29598276753a41d293ca65ef8fe60287ed62d8cd94b0ee77ec38ecb41a20f5` | `a63082132ba4f97a80bea76823f544493bffa8082296d62d71581a4feff1576f` |
| OpenCV Haar | `sha256:a9ee3c8bf4ab44314001ffa728bbfc388fcc579790b8b2909d71dd80306d2f40` | `0f7d4527844eb514d4a4948e822da90fbb16a34a0bbbbc6adc6498747a5aafb0` |

The OpenCV snapshot hash is the canonical manifest hash of the one-file
snapshot; the second value is the pinned XML file hash.

### Offline/local-only and CPU boundary

The manifests record:

- `HF_HUB_OFFLINE=1`
- `TRANSFORMERS_OFFLINE=1`
- `HF_HUB_DISABLE_TELEMETRY=1`
- `HF_HUB_DISABLE_IMPLICIT_TOKEN=1`
- `network_access=disabled`
- `local_files_only=true` for every model
- `device=cpu` for runtime and every model

The implementation calls all Transformers `from_pretrained` loaders with
`local_files_only=True`. No network access was requested or used.

### Paths, modes, hashes, leakage, and artifact boundaries

- All persisted paths passed the repository-relative/no-parent-escape audit.
- Output and checkpoint directories are `0700`.
- All 21 JSON artifacts (five top-level manifests plus 16 checkpoints) are
  `0600`.
- Every top-level self-hash, build inventory hash/size, checkpoint payload
  hash, checkpoint file hash/size, and frozen model file hash/size passed.
- Search records use the frozen allowlist shape. The verifier found no
  forbidden evaluator/private, rights, source-path, title, question/answer,
  family, evidence, intervention, label, or gold fields in the searchable
  index. An independent recursive private-key scan over all smoke JSON also
  found zero matches.
- No image, audio, or video derivative exists below the smoke output root.
- No family, negative, intervention, trajectory, controller, agent-run,
  evaluation, or metric artifact exists below the smoke output root.
- The build terminal boundary is `resource_manifest`, with every downstream
  generation flag false.
- Derived output is 176,743 bytes, far below the 512 MiB hard cap.

## 7. Frozen input identities

The four primary media hashes revalidated exactly:

- Oxford QM: `c83b4e0ed82e20bfed1cab701057ac16c6c13872f1fae9f7e56b65ae17dd0bcc`
- Oxford DH Lawrence: `6748569f9e9ac6a49985fa5410461f60fadba4054a28a4cd8ede9785c217f33a`
- MIT Fluid Dynamics: `8fe1fd3c25cae687735aaecbcc5a6aa7bd9a668c310bd579622372ed05449889`
- Yale PHYS 200: `fff84141b2791164b52847c35f988456699dd0f350b8853c8b1cb451f4430016`

The Task-132 acquisition manifest remained
`36bdc5efd973189f14f1876d4bb753617c254f1f12267cbc83934be96d680e90`.

## 8. Smoke artifact hashes

| Artifact | SHA-256 |
|---|---|
| `segment_manifest.json` | `39898c8757d5bc9146323440c2582261a4bc6b012036235d2abe3b3a73e58162` |
| `observation_manifest.json` | `b48fe8c51e563daf1ce3787395580f8bb8bffb02e3fac09b88058d1af66014ee` |
| `full_timeline_index.json` | `93607572081ee9abbe8a879def6f75bf08f69c66e08835b85a4c97a8c487bfa0` |
| `resource_manifest.json` | `9b93576a8031683ca022e1b0fbc1b8976f610024970f2d824b9024e6303918c6` |
| `build_manifest.json` | `a543cd4ea0328fe83a287ea3b8a2f375218e70c600769ec60553f42d23835faa` |

## 9. Final boundary

`MINI_PILOT_INDEX_SMOKE_GO`

This GO means the bounded 8-second-per-source real-model indexing path,
checkpoint/resume path, and smoke verification path are ready. It is not a GO
for the full build or any downstream scientific/evaluation stage.
