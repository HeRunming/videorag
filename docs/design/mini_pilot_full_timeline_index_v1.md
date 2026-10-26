# Mini-pilot full-timeline index v1 — Workstream A

**Date:** 2026-09-23  
**Plan:** `AV-TRACE-MINI-PILOT-FULL-TIMELINE-V1`  
**Decision:** `READY_FOR_INDEX_IMPLEMENTATION`

## 1. Scope and boundary

Workstream A freezes the source-facing contract for a restricted full-timeline
index over exactly four Task132 acquisitions:

1. `SG-OXFORD-QM-001`
2. `SG-OXFORD-DHL-CONSCIOUSNESS`
3. `SG-MIT-RES12-003-L01`
4. `SG-YALE-PHYS200-L01`

The normative machine-readable contract is
`data/rehearsal_plan/mini_pilot_full_timeline_v1.json`. The loader in
`src/av_trace_mini_pilot_index/sources.py` verifies that contract against the
Task132 aggregate acquisition manifest, every source manifest, and every
retained media/transcript payload.

This workstream authorizes source verification, segmentation, speech,
ambient, and vision observation/index construction, checkpointing, index
freeze, and deterministic replay only. It does **not** authorize candidate
families, family migration, hard-negative labeling, interventions, agent or
controller runs, evaluation, metrics, human annotation, public release, or
redistribution.

The source media remain immutable under:

```text
data/restricted/mini_pilot_sources_v1/
```

All new outputs belong under:

```text
data/restricted/mini_pilot_index_v1/
```

No source media, Scale-1A artifact, or model snapshot is modified by this
workstream.

## 2. Exact source inventory

| Source | Media path | Bytes | SHA-256 | Duration (s) | A/V expectation |
|---|---|---:|---|---:|---|
| Oxford QM | `data/restricted/mini_pilot_sources_v1/SG-OXFORD-QM-001/binney01.mp4` | 302,443,579 | `c83b4e0ed82e20bfed1cab701057ac16c6c13872f1fae9f7e56b65ae17dd0bcc` | 2645.280000 | AAC stereo 48 kHz stream 0; H.264 640×360 at 25 fps stream 1 |
| Oxford DH Lawrence | `data/restricted/mini_pilot_sources_v1/SG-OXFORD-DHL-CONSCIOUSNESS/2012-01-18-01-great-writers-brown-lawrence.mp4` | 369,848,995 | `6748569f9e9ac6a49985fa5410461f60fadba4054a28a4cd8ede9785c217f33a` | 2918.760000 | AAC stereo 44.1 kHz stream 0; H.264 640×360 at 25 fps stream 1 |
| MIT Fluid Dynamics | `data/restricted/mini_pilot_sources_v1/SG-MIT-RES12-003-L01/mitres_12-003f25_lec1_1080p_360p_16_9.mp4` | 84,051,067 | `8fe1fd3c25cae687735aaecbcc5a6aa7bd9a668c310bd579622372ed05449889` | 2859.933333 | H.264 640×360 at 30 fps stream 0; AAC stereo 48 kHz stream 1 |
| Yale PHYS 200 | `data/restricted/mini_pilot_sources_v1/SG-YALE-PHYS200-L01/phys200_01_090606.m4v` | 377,169,329 | `fff84141b2791164b52847c35f988456699dd0f350b8853c8b1cb451f4430016` | 4400.900907 | H.264 320×180 at 29.97 fps stream 0; AAC stereo 44.1 kHz stream 1 |

Total primary media is **1,133,512,970 bytes** and **12,824.874240
seconds**. Every source must have exactly one manifest `video` role, exactly
one aggregate `primary_video` role, one video stream, and one audio stream.
Paths must be repository-relative descendants of the allowed restricted root;
symlinks, root escape, size drift, hash drift, duration drift, or mode drift
fail closed.

Source directories are required to be mode `0700`. The aggregate manifest,
source manifests, primary media, and official transcript/caption payloads are
required to be mode `0600`.

## 3. Frozen 4/8/32-second lattice

The lattice is copied semantically from the audited Scale-1A implementation:

```text
base cell: 4 s length, 4 s stride
fine:      8 s nominal length, 4 s stride, admit when >=4 s remains
context:   32 s nominal length, 16 s stride, admit when >=16 s remains
```

The final positive sub-four-second base cell is retained for coverage and
frame sampling. Fine and context terminal windows end exactly at the source
duration. Persisted boundaries use integer microseconds.

| Source | 4 s cells | Fine | Context | Segments | 30 s Whisper chunks |
|---|---:|---:|---:|---:|---:|
| Oxford QM | 662 | 661 | 165 | 826 | 89 |
| Oxford DH Lawrence | 730 | 729 | 182 | 911 | 98 |
| MIT Fluid Dynamics | 715 | 714 | 178 | 892 | 96 |
| Yale PHYS 200 | 1101 | 1100 | 275 | 1375 | 147 |
| **Total** | **3208** | **3204** | **800** | **4004** | **430** |

The index therefore performs 3,208 CLIP frame forwards, 3,204 AST fine-window
calls, and 430 Whisper chunk calls. There are 4,004 temporal segments and a
maximum of 12,012 modality-segment records.

Segment identifiers depend only on the immutable source hash, scale, and
lattice index. Questions, answers, family/evidence/review IDs, intervention
state, and evaluation labels are forbidden inputs.

## 4. Frozen observation snapshots

Workstream A reuses the exact locally frozen Scale-1A snapshots:

| Layer | Model/revision | Snapshot identity |
|---|---|---|
| Speech | `openai/whisper-tiny.en` at `87c7102498dcde7456f24cfd30239ca606ed9063` | `sha256:1e098354f3cbd9f339ef8fbdcc0e82ff238786bffa25794493ebe32830f4518a` |
| Ambient | `MIT/ast-finetuned-audioset-10-10-0.4593` at `f826b80d28226b62986cc218e5cec390b1096902` | `sha256:acb9247d5f2548c121e7fd213347586e1b781fd8dc329e27505dd269a69cccbc` |
| Semantic vision | `openai/clip-vit-base-patch32` at `3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268` | `sha256:2c29598276753a41d293ca65ef8fe60287ed62d8cd94b0ee77ec38ecb41a20f5` |
| Vision routing | `opencv-routing/1.0`, revision `2.0` | Haar asset SHA-256 `0f7d4527844eb514d4a4948e822da90fbb16a34a0bbbbc6adc6498747a5aafb0` |

All model inference is local-only. Model rights and redistribution metadata
stay in their model manifests; they are not search features.

Each source has four atomic checkpoints: speech, ambient, vision routing, and
CLIP vision. The total is therefore exactly **16 checkpoints**. A checkpoint
is reusable only when its source hash, model/layer revision, configuration,
record count, byte count, and content hash all match. Checkpoints never retain
decoded audio, frames, or clips.

## 5. Search policy

### Speech

Speech search is BM25 over quality-gated, timestamped Whisper output.
Non-overlapping 30-second chunks are the truthful acoustic inference unit.
The final short chunk is retained in provenance and admitted to postings only
if it passes the frozen quality gate.

### Ambient

AST runs once per fine window and stores the top 15 canonical AudioSet
classes/scores after the frozen generic-label discount. Context observations
are deterministic max/mean aggregates over child fine windows; context
windows do not trigger additional AST calls. These are provisional model
observations, not human audible-event gold.

### Vision

One frame is sampled per four-second cell at
`min(cell_start + 2 s, duration - one video time-base tick)`. CLIP cell
vectors are pooled deterministically into fine and context vectors.
Embeddings are stored as float16 and similarity is computed in float32.
OpenCV routing features remain non-semantic. Generated captions are not
searchable.

### Search-record privacy and rights boundary

Search records use a strict allowlist. They may contain opaque IDs,
source/hash bindings, intervals, modality, scale, binding-cell IDs, a
modality-specific search payload, and searchable/exclusion state. They must
not contain filenames, paths, URLs, titles, rights/license/attribution/privacy
flags, questions, answers, family/evidence/review/claim IDs, intervention
state, evaluator labels, or gold fields.

Rights, attribution, component, privacy, commercial-use, and release flags
remain in the Task132 source/acquisition manifests. They are deliberately
kept out of search records so that retrieval cannot exploit administrative
metadata and so that sensitive policy data does not spread into index shards.

## 6. Official transcript sidecars

All Task132 official transcript/caption payloads are mandatory source
sidecars:

- Oxford QM SRT;
- Oxford DH Lawrence SRT;
- MIT WebVTT captions and PDF transcript;
- Yale HTML transcript.

The loader verifies each sidecar's repository-relative path, role, bytes,
SHA-256, source-manifest binding, aggregate-manifest binding, mode, and source
directory confinement.

Sidecars are **verification-only** in index v1. They are not searchable, not
citable, not training labels, and not inputs to ranking, query expansion,
answer generation, candidate-family generation, or evaluation. Permitted uses
are source-identity/syntax checks and a separate post-freeze ASR
coverage/error audit. This prevents publisher text from silently replacing
the frozen Whisper observation layer.

## 7. Storage and execution caps

- Derived-artifact soft cap: **256 MiB**.
- Derived-artifact hard fail: **512 MiB**.
- Existing frozen model-snapshot cap: **1 GiB**.
- Exact source-media cap: **1,133,512,970 bytes**.
- Exact official-sidecar cap: **343,544 bytes**.
- Source media and existing model snapshots are excluded from the derived cap.
- Persisted decoded frames, audio, and clips are forbidden.

Writes use temporary files, fsync, hash verification, and atomic rename.
Partial shards are deleted. The output root must not overlap the source root.

## 8. Loader fail-closed contract

`load_source_plan(repo_root)` performs strict validation before returning any
source:

1. exact plan schema and readiness decision;
2. exact Task132 acquisition-manifest path, SHA-256, mode, READY decision,
   four complete sources, zero failed/incomplete transfers, and zero partials;
3. exactly four unique planned sources;
4. exact source-manifest hashes, IDs, completion states, paths, and modes;
5. one and only one primary video role in both source and aggregate manifests;
6. media/sidecar confinement to the allowed restricted root with no symlinks;
7. exact file bytes and SHA-256 by default;
8. exact durations and audio/video stream expectations from both manifests;
9. exact per-source and aggregate lattice, call, segment, and checkpoint
   counts; and
10. absence of evaluator-private fields from indexing configuration.

The optional `hash_files=False` switch exists only to keep mutation-focused
unit tests fast. Production callers use the default full hashing behavior.
