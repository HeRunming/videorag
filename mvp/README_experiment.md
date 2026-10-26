# Deterministic MVP agents and metrics

This module is an offline construct-validation harness for the matched
`CLEAN`/`BLOCKED`/`RESTORED` protocol. It makes no model-performance claim and
does not call an LLM, network service, or external API.

## Baselines

- **AlwaysAnswer** makes one direct pass over one likely evidence route and
  answers even when an accepted sufficient evidence set (SES) has not been
  observed.
- **SingleShotRAG** makes one targeted retrieval pass over one registered SES,
  then answers or abstains. It does not check channel status, so a restoration
  whose trigger is `get_channel_status` is intentionally missed.
- **ReActHeuristic** iterates through lexical evidence routes and uses one status
  fallback after a typed channel outage.
- **EvidenceBeliefState** tracks sufficiency probability, missing modalities and
  hop types, missingness cause, and proactively checks status before retrying a
  missing route. This action triggers registered restoration where applicable.

The policies use graph evidence descriptions as deterministic synthetic search
templates. This is deliberate oracle-style scaffolding for testing protocol
behavior; results must not be presented as learned retrieval performance.
Claims still require citable observations returned by the backend.

## Backend interface

`run_experiment` accepts a factory returning a stateful backend with the
documented contract:

```python
backend.episode_start(reveal_state_role=True) -> dict
backend.execute(agent_action) -> tool_response | None
```

For normative trajectory metadata, a backend may additionally expose
`backend_version`, `backend_hash`, `intervention_manifest_hash`,
`last_active_hook_ids`, and `registry`. If absent, the orchestrator derives
stable adapter hashes from the episode start and family intervention. This is
the conservative integration assumption for non-reference backends.

Agents never branch on `state_role`; it is retained only in the evaluator log.

## Metrics

The report includes:

- grounded task success by state;
- stepwise and final sufficiency Brier score;
- BLOCKED false-sufficient and high-confidence false-sufficient rates;
- premature stop;
- final missing-modality F1/Brier, missing-hop F1, and cause accuracy/Brier;
- evidence coverage and supported-claim rate;
- tool calls, tool cost, and inspected duration;
- paired restoration gain on a common supported-answer endpoint;
- the literal `RESTORED - BLOCKED` state-target score difference, separately
  labeled as a heterogeneous-target contrast;
- triggered supported recovery;
- deterministic source-video cluster bootstrap intervals.

`triggered_supported_recovery` is supported RESTORED finalization within the
unchanged family budget **after the registered restoration trigger fires**. An
agent that answers without triggering restoration receives zero. It is not a
distinct timing metric and is not presented as `Recovery@Budget`.

Premature-stop requires validator-demonstrated route feasibility at the final
decision point. The synthetic artifacts do not link those validator
trajectories, so the MVP emits no eligible denominator rather than substituting
an agent-dependent status-call heuristic.

RESTORED diagnosis and missing-requirement labels follow action timing:
pre-trigger beliefs use blocked labels; after restoration but before an SES is
observed, the route is accessible-but-not-found; after an SES is observed, the
label is `not_missing`. A trajectory that never triggers restoration retains
blocked terminal labels.

The fixed backend remains metadata-backed: `inspect_clip` and transcript/audio
tools return frozen index payloads rather than decoding the generated MP4.

## Run

The generated root must contain the frozen backend manifest and index artifacts
described in `mvp/README_backend.md`.

```bash
PYTHONPATH=src python scripts/run_mvp_experiment.py \
  --generated-root mvp/generated/full \
  --output-dir mvp/results/experiment
```

Select a subset with:

```bash
--agents always-answer,evidence-belief-state
```

Outputs:

- `report.json`: metrics, aggregates, dashboard, and trajectories;
- `episode_metrics.csv`: one flat row per agent/family/state;
- `summary.csv`: state and paired estimates with bootstrap intervals;
- `dashboard.csv`: compact protocol dashboard;
- `report.md`: human-readable dashboard.

Public-core and compatibility tracks are grouped separately and never pooled.
