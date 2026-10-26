# EPIC Wave-1 Index Implementation Audit

**Date:** 2026-09-28  
**Task:** 163  
**Decision:** `EPIC_WAVE1_INDEX_IMPLEMENTATION_REPAIR`

## Executive finding

The isolated EPIC Wave-1 full-timeline indexing implementation is complete and
passes focused unit tests, syntax compilation, lint, static plan validation,
and dry preflight. It is not currently executable because Task 162 has not yet
published the required root acquisition manifest with decision
`EPIC_WAVE1_ACQUISITION_READY` and exact final-media SHA-256 values.

This is a remediable external gate, not an implementation defect. The correct
current token is therefore **REPAIR**, not READY and not NO_GO.

No full build was run. No incomplete media was decoded. The active `.staging`
chunk tree was neither traversed nor modified.

## Reviewed inputs

- Task 136 final mini-pilot full-timeline result and resume/audit boundary.
- Task 153 semantic A/V source-prescreen tooling boundary.
- Task 161 EPIC access preflight, registry, official duration metadata, and
  official v100 MD5 manifest.
- The current Task 162 root outside `.staging`: final media directories and
  manifest directory are present but empty; only logs and official metadata
  are currently available.
- `src/av_trace_mini_pilot_index`, reused as the frozen inference/index engine
  but not modified by this task.

## Implemented artifacts

- `src/av_trace_epic_wave1_index/__init__.py`
- `src/av_trace_epic_wave1_index/sources.py`
- `src/av_trace_epic_wave1_index/core.py`
- `scripts/build_epic_wave1_full_timeline.py`
- `scripts/verify_epic_wave1_full_timeline.py`
- `tests_epic_wave1_index/test_sources.py`
- `tests_epic_wave1_index/test_core.py`
- `tests_epic_wave1_index/test_cli_and_verifier.py`
- `data/rehearsal_plan/epic_wave1_full_timeline_index_v1.json`
- `docs/design/epic_wave1_full_timeline_index_v1.md`
- this audit and the Task 163 result record.

## Source and gate audit

The plan is fixed to exactly:

- `P28_103`, participant block `P28`, duration 1825.16 seconds, official MD5
  `30258174e4ae5cee495170d2748efc4e`, final path
  `data/restricted/epic_wave1_sources_v1/media/P28/P28_103.MP4`;
- `P27_101`, participant block `P27`, duration 1360.20 seconds, official MD5
  `f3e40c9216ab5f05cddb762bd70278d5`, final path
  `data/restricted/epic_wave1_sources_v1/media/P27/P27_101.MP4`.

The loader rejects:

- a missing or non-READY acquisition manifest;
- failed or incomplete transfer accounting;
- missing exact SHA-256;
- MD5, byte-count, media-version, participant, path, duration, stream, sync,
  mode, or recomputed-hash mismatch;
- symlinks, path escape, and every `.staging` path.

The exact SHA-256 values are deliberately not invented in the plan. Once Task
162 publishes them, the loader recomputes both SHA-256 and MD5 over the final
files before any decode.

## Index isolation and leakage audit

The implementation writes only to the configured EPIC index root. The build
and verifier prohibit media derivatives and names associated with families,
interventions, trajectories, evaluation, metrics, controllers, or agent runs.

Search records retain the mini-pilot allowlist and forbidden-key protection.
Rights, source paths, official annotations, evaluator-private fields, and
semantic labels are not copied into searchable records. EPIC action,
narration, and EPIC-SOUNDS annotations are sealed and unused.

## Lattice, model, and checkpoint audit

The frozen full-build counts are:

- 798 four-second base cells;
- 796 eight-second fine windows;
- 199 thirty-two-second context windows;
- 995 temporal segments;
- 107 thirty-second Whisper chunks;
- 796 AST calls;
- 798 CLIP image forwards;
- eight checkpoints.

Whisper tiny.en, AST AudioSet, CLIP ViT-B/32, and the OpenCV Haar routing asset
are bound to the already frozen local snapshot and weight hashes. Runtime is
CPU-only and offline.

Checkpoint writes are atomic and restricted. Resume requires exact key,
payload hash, file hash, size, record count, source hash, model binding, and
configuration binding. A fake-backend smoke test verified byte-identical
artifacts after checkpoint reuse.

## Validation performed

### Focused tests

```text
PYTHONPATH=src pytest -o addopts='' -q tests_epic_wave1_index
11 passed
```

Coverage includes:

- exact lattice counts;
- static plan validation while Task 162 is incomplete;
- successful loading of a synthetic READY acquisition with exact hashes;
- rejection of READY without SHA-256;
- rejection of a `.staging` media path;
- isolated smoke construction with fake media/models;
- deterministic resume;
- CLI controls and no-decode default;
- verifier fail-closed behavior;
- searchable-field leakage rejection.

### Focused Ruff

```text
ruff check src/av_trace_epic_wave1_index \
  scripts/build_epic_wave1_full_timeline.py \
  scripts/verify_epic_wave1_full_timeline.py \
  tests_epic_wave1_index
All checks passed!
```

### Focused syntax compilation

The new package and both scripts passed `python -m py_compile`.

### Dry preflight

The default build command returned exit code `2` with:

- decision `EPIC_WAVE1_INDEX_IMPLEMENTATION_REPAIR`;
- status `BLOCKED_BY_ACQUISITION_GATE`;
- `media_decoded: false`;
- `artifacts_written: false`;
- `staging_tree_read: false`;
- frozen model gates present and hash-valid;
- failure reason `ACQUISITION_MANIFEST_MISSING`.

### Verifier before Task 162 completion

The verifier returned exit code `2` and the same REPAIR decision because the
required acquisition manifest is absent. This is the intended fail-closed
behavior.

## Remaining action

After Task 162 finishes:

1. Confirm the acquisition manifest path and schema match the prepared
   contract.
2. Run dry preflight again.
3. If READY, run the bounded smoke build and smoke verifier.
4. Review smoke resource use and artifacts.
5. Only under a separate explicit authorization, run the full build and full
   verifier.

## Final decision

`EPIC_WAVE1_INDEX_IMPLEMENTATION_REPAIR`

Reason: implementation is ready for gated execution, but Task 162's exact
READY manifest and final-media SHA-256 bindings do not yet exist.
