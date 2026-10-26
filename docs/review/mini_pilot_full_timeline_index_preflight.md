# Mini-pilot full-timeline index technical preflight

**Date:** 2026-09-23  
**Scope:** Workstream C CLI, verifier, and bounded execution controls  
**Decision:** `READY_FOR_BOUNDED_SMOKE`; full heavy build not run

## Frozen inputs and outputs

The build command defaults to the Workstream-A plan and its frozen restricted
output root:

- plan: `data/rehearsal_plan/mini_pilot_full_timeline_v1.json`
- output: `data/restricted/mini_pilot_index_v1/`
- sources: exactly four Task-132 source groups
- checkpoints: exactly four layers per source, 16 total
- device: CPU only
- network: disabled/local model snapshots only

The CLI accepts `--plan`, `--output-root`, `--resume`/`--no-resume`,
`--threads`, `--device`, and `--smoke-seconds`. Execution is additionally
protected by `--execute`; omitting it runs an offline technical preflight and
writes no index artifacts.

## Offline preflight performed

Command:

```bash
PYTHONPATH=src python scripts/build_mini_pilot_full_timeline.py --repo-root .
```

Result: `READY`.

The preflight fully validates the frozen source plan, including the acquisition
manifest and all four source/media/sidecar hashes and modes. It imports the
required local runtime packages without loading the model weights or decoding
media. It also validates the four model gates against the plan:

- Whisper snapshot and pinned weight: PASS
- AST snapshot and pinned weight: PASS
- CLIP snapshot and pinned weight: PASS
- OpenCV Haar asset: PASS

Frozen expected totals are 3,208 base cells, 3,204 fine windows, 800 context
windows, 4,004 temporal segments, 430 Whisper chunks, 3,204 AST calls, 3,208
CLIP frame forwards, and 16 checkpoints.

## Bounded smoke

A smoke run uses the core `smoke_seconds` path and a bounded PyAV audio reader,
so every source is clipped to the requested duration before lattice creation
and audio decoding. Unless an explicit `--output-root` is supplied, smoke
artifacts go to `data/restricted/mini_pilot_index_v1_smoke/`, keeping them
separate from the canonical full build.

Recommended first smoke:

```bash
PYTHONPATH=src python scripts/build_mini_pilot_full_timeline.py \
  --execute --smoke-seconds 8 --output-root data/restricted/mini_pilot_index_v1_smoke \
  --resume --threads 8 --device cpu
```

This smoke was intentionally **not** run in Workstream C because it loads the
three frozen neural models and performs media inference. The CLI refuses to
silently replace a requested smoke with an unbounded full build if the core
API lacks smoke support.

## Verification contract

After a full build, run:

```bash
PYTHONPATH=src python scripts/verify_mini_pilot_full_timeline.py --repo-root .
```

The verifier fails closed on:

- any source count other than four;
- any source byte/hash/count mismatch;
- any checkpoint count other than 16 or a missing/duplicate source-layer pair;
- checkpoint key, payload hash, file hash, byte count, or mode mismatch;
- top-level manifest self-hash or inventory mismatch;
- wrong frozen model path/snapshot hash/weight hash, nonlocal model use, or a
  non-CPU runtime;
- absolute, escaping, or non-repository-relative persisted paths;
- forbidden question/answer/family/evidence/intervention/evaluation/rights
  fields in searchable index records;
- persisted decoded media derivatives;
- downstream family, negative, intervention, trajectory, controller,
  evaluation, or metric artifacts; or
- violation of the 512 MiB derived-artifact hard cap.

## Downstream isolation

The build entry point invokes only `av_trace_mini_pilot_index` construction.
It does not import or invoke family generation, migration, hard-negative,
intervention, agent/controller, evaluation, metric, annotation, or release
stages. Both post-build boundary checking and the independent verifier reject
such artifacts if they appear under the output root.

## Exact full-build command

Do not run until the bounded smoke is accepted:

```bash
PYTHONPATH=src python scripts/build_mini_pilot_full_timeline.py \
  --execute --resume --threads 8 --device cpu
```

Then verify with:

```bash
PYTHONPATH=src python scripts/verify_mini_pilot_full_timeline.py --repo-root .
```
