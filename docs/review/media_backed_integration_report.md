# Media-backed MVP v2 integration report

**Date:** 2026-09-06  
**Scope:** offline synthetic media-backed construct-validation integration; not
scientific evidence for general audiovisual reasoning or model ranking.

## Result

The v2 integration implements the requested end-to-end path:

- search pointers are built from a frozen index whose searchable content is
  produced by decoding MP4 pixels/audio on a fixed temporal grid;
- every citable `inspect_clip`, transcript, and ambient observation is decoded
  again from registered MP4 bytes at runtime;
- all four existing agents run in a fresh process per episode over JSONL;
- every reconstructed trajectory is validated against the normative schema and
  semantic trajectory rules;
- the checked-in dataset certificate is validated before execution and bound to
  the live backend, family hashes, index hash, denominator hash, and fixed-call
  case;
- premature-stop eligibility is computed from certified route artifacts;
- both intervention mechanisms and both restoration trigger types execute;
- original-versus-mutated media checks exercise visual blanking, ambient
  muting, and a changed speech-codec symbol.

No normative document and no previous result directory was modified.

## Architecture

`src/av_trace_media_pipeline/` contains:

- `indexing.py`: deterministic 2-second decoded-media scan, adjacent proposal
  merge, final interval re-decode, media-derived text projection, and private
  interval-only evidence-route binding;
- `backend.py`: a `FixedBackend` subclass that retains budget, intervention,
  response, and replay semantics while replacing all citable content paths with
  `av_trace_media` decoding;
- `certification.py`: fail-closed certificate, artifact-index, denominator,
  live-backend, live-family, and fixed-call hash checks;
- `experiment.py`: the 96 main subprocess runs, four fixed-call canary runs,
  mutation pairs, metrics, calibration output, and deterministic reports.

The certified v1 backend/index remains the control-plane authority required by
existing family and validator hashes. The media-derived v2 index is an
additional search artifact. It does not replace or rewrite certified files.

## Important validator correction

The denominator adapter previously treated an explicitly infeasible,
zero-step `BLOCKED` alternative as executable. The adapter now excludes route
alternatives unless `feasible` is exactly true. A regression test verifies that
certified `BLOCKED` no-route records yield zero eligibility rather than false
premature stops. No validator rule or certificate was weakened.

## Experiment matrix

Main experiment:

- 8 certified families;
- 3 states (`CLEAN`, `BLOCKED`, `RESTORED`);
- 4 agents;
- 96 subprocess trajectories.

Additional integration fixtures:

- 4 subprocess trajectories on the separately certified fixed-call RESTORED
  family;
- 24 mutation trajectories: three mutations × affected/control family × four
  agents.

The fixed-call fixture is not scored with the canonical status-trigger
premature-stop denominator because it shares a family ID but has different
trigger semantics and no separate denominator artifact.

## Metrics

The v2 report recomputes and stores:

- state-specific grounded task success;
- episode and final sufficiency Brier scores plus five equal-count calibration
  bins per agent;
- triggered supported recovery;
- common-endpoint paired restoration gain, using supported-answer success in
  both BLOCKED and RESTORED;
- certified premature-stop numerator, denominator, and rate by agent/state;
- media consistency and mutation/tamper sensitivity.

The literal heterogeneous state-target difference is retained for transparency
but is not interpreted as answer recovery.

## Mutation contract

Each mutation is registered under its own MP4 hash. Runtime perception therefore
fails closed on an unregistered or mismatched file. The expected affected
observation must change or disappear, and supported-answer success must fall
from one to zero for every agent. A same-source unrelated family must retain its
semantic observations, answer, and support result.

Semantic stability is used rather than byte equality because the checked-in
mutation fixtures re-encode the whole container. Media hashes, payload hashes,
observation IDs, and irrelevant counter pixels may consequently differ.

## Remaining synthetic-specific outputs

The exact perception outputs that remain synthetic-specific are:

1. fixed-layout central-object shape and palette classification;
2. closed-vocabulary burned-in caption/counter recognition;
3. six-symbol tonal speech decoding (`synthetic_codec`, not ASR);
4. handcrafted pulse, motor-hum, and confirmation-chime classifications;
5. deterministic role/display wording projected from decoded symbols for the
   legacy answer parser.

The evaluator-private mapping from observation interval/modality to evidence ID
is also fixture-specific evaluation infrastructure, but it does not supply
runtime observation content.

## Interpretation boundary

This integration demonstrates that the intended protocol can now be exercised
with observations causally dependent on media bytes and with certified control
artifacts across a serialization boundary. It still does not establish
performance on natural speech, unconstrained video, real annotation workflows,
or independent learned agents. The existing synthetic-specific limitations and
small four-source sample prohibit leaderboard or general scientific claims.

Exact counts, metrics, mutation outcomes, and same-environment hashes are stored
in `mvp/results/media_backed_v2/` by the reproduction command above.

## Recorded v2 run

The checked-in run produced:

- 96/96 valid main subprocess trajectories;
- 4/4 fixed-call subprocess trajectories triggering at call index 0;
- 24 mutation trajectories;
- 17/17 registered evidence units covered by the decoded-media index;
- 3/3 mutation contracts passing, for tamper sensitivity 1.0.

Dashboard point estimates:

| Agent | CLEAN grounded | BLOCKED grounded | RESTORED grounded | Triggered supported recovery | Common-endpoint restoration gain | Sufficiency Brier |
|---|---:|---:|---:|---:|---:|---:|
| AlwaysAnswer | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.748 |
| SingleShotRAG | 1.00 | 0.50 | 0.00 | 0.00 | 0.00 | 0.024 |
| ReActHeuristic | 1.00 | 0.50 | 0.50 | 0.50 | 0.50 | 0.021 |
| EvidenceBeliefState | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.016 |

The certified premature-stop denominator has no eligible final decision points
for the main `BLOCKED` runs: those states have no restoration operation by
construction. In `RESTORED`, AlwaysAnswer and SingleShotRAG each stop
prematurely in 8/8 eligible runs, ReActHeuristic in 4/4 eligible runs, and
EvidenceBeliefState has no eligible final stops because it acquires sufficient
evidence.

Two same-environment complete runs were byte-identical at the report, run
manifest, and per-artifact hash-map levels. Frozen hashes:

| Artifact | Hash |
|---|---|
| v2 semantic result | `sha256:bcb3b5eb7458abd132a1939d53f043aef615a98c2f462bc3bc6b2573f2844a01` |
| media-derived index | `sha256:2de4b00530f924c4478d14ac2abc1686c6f45a7b47819f9b13c034460c654872` |
| media-index build record | `sha256:b1772ae45c518cb9430ee530575d8f21832d35137d6cd3fa07d506a5a7f73d32` |
| certified dataset certificate | `sha256:48a91b1e459b22048badf72d6142779f11045c1203213041a4867be60f030f24` |
| certified denominator | `sha256:d6322db5b4b8a6853183224e09a19bfea4f31c575fe277d41e6d7284d83e84ca` |

The explicitly enumerated full suite
`tests tests_mvp tests_media tests_agent_runtime tests_validation tests_media_pipeline`
passed.
