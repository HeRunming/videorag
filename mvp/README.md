# AV-TRACE offline MVP

This directory contains the integrated, deterministic construct-validation
demonstration for the synthetic corpus, frozen backend, four baseline agents,
trajectory validation, and core metrics.

## Fresh-workspace run

Install the package and local media dependencies, then run:

```bash
python -m pip install -e .
python scripts/run_mvp.py all --probe
PYTHONPATH=src pytest -q tests tests_mvp
```

`all` performs, in order:

1. generation of the four-source, eight-family synthetic corpus;
2. construction and verification of `backend_index.json` and
   `backend_manifest.json`;
3. manifest and family validation;
4. 96 agent episodes: four agents × eight families × three states;
5. validation of all 96 emitted trajectories;
6. metric aggregation and deterministic video-cluster bootstrap;
7. JSON, CSV, Markdown, validation, artifact-inventory, and run-manifest output.

Default locations:

- generated corpus and frozen backend: `mvp/generated/full/`;
- reports: `mvp/results/latest/`.

## Commands

```bash
# Generate the full corpus and freeze its backend.
python scripts/run_mvp.py generate --probe

# Validate generated artifacts and, if present, result trajectories.
python scripts/run_mvp.py validate

# Load the persisted backend and run all four agents.
python scripts/run_mvp.py run

# Complete pipeline.
python scripts/run_mvp.py all --probe
```

Useful deterministic options:

```bash
python scripts/run_mvp.py all \
  --seed 20260905 \
  --bootstrap-seed 20260905 \
  --bootstrap-samples 1000
```

## Integration guarantees

- The generated backend is persisted and loaded through its manifest; experiment
  execution does not reconstruct an in-memory oracle index from family
  observation text.
- Search payloads, intervals, modalities, and text come from generated corpus
  artifacts (`timelines/`, `transcripts/`, `audio_events/`, and `evidence/`).
- Family data binds route IDs and validates intervention closure, but is not
  exposed to agent policies.
- Bundled policies receive only the question, tool/budget description, redacted
  tool responses, and prior observations. State-bearing episode IDs are removed
  from the policy-visible response. This is an in-process engineering wrapper,
  not a security boundary for untrusted agent code.
- Search uses one source-level candidate universe for every family on a source;
  intervention routes may be masked, but family membership no longer removes
  unrelated same-source events.
- The evaluator applies a frozen exact-text mapper to attach registered claim
  IDs because the synthetic policies emit display text.
- Every trajectory is validated with the normative schema and semantic
  trajectory validator. Invalid output fails the run.

## Result files

`mvp/results/latest/` contains:

- `report.json` — complete metrics and trajectories;
- `episode_metrics.csv` — one row per agent/family/state;
- `summary.csv` — aggregate estimates and intervals;
- `dashboard.csv` and `report.md` — concise dashboard;
- `validation.json` — schema, manifest, family, and trajectory validation;
- `run_manifest.json` — commands, runtime, hashes, counts, interpretation, and
  limitations;
- `artifacts.json` — output file hashes and sizes.

The current full-run interpretation is recorded in
`docs/review/mvp_integration_report.md`.

## Limitations

- These are 4–8 minute engineering fixtures on
  `EXTERNAL_COMPATIBILITY_UNPOOLED`, not the 20–90 minute public core.
- The four agents are symbolic deterministic protocol probes, not learned
  systems.
- They share fixture-oriented extraction logic, so equal CLEAN accuracy and
  baseline separation are constructed smoke-test behavior, not scientific model
  evidence.
- The exact-text claim mapper is a declared evaluator-side simplification.
- Agent-supplied registered claim IDs are overwritten by the evaluator mapper.
- The runtime is metadata-backed. MP4/audio files are generated, hashed, and
  playability-probed, but retrieval tools do not decode their content.
- The report labels the literal `RESTORED - BLOCKED` state-specific grounded
  scores as a heterogeneous state-target difference. `paired_restoration_gain`
  instead compares supported-answer success in both states. The normative
  formula requires future revision because its two success targets differ.
- Premature-stop is reported unavailable until validator-demonstrated
  final-decision route-feasibility records exist.
- MP4 bytes are reproducible under the same pinned codec stack but are not
  promised identical across different FFmpeg/PyAV/codec builds.
