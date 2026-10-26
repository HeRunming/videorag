# AV-TRACE Pilot-0 synthetic infrastructure

This repository contains a small Python reference implementation for the frozen
schema version `0.2.0`. It validates JSON structure, fail-closed rights gates,
episode-family semantics, deterministic family differences, actions, responses,
and trajectories. It also provides an in-memory synthetic replay backend for
`necessity_group_withholding` and `modality_channel_outage`.

The package never downloads, decodes, or processes media and never calls an
external model. Replay inputs are explicit synthetic JSON records supplied by a
test or caller.

## Setup and tests

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

`jsonschema` is the only runtime dependency. Tests use the standard-library
`unittest` runner.

## CLI

Run from the repository root (or pass `--repo-root`):

```bash
python -m av_trace schemas
python -m av_trace schema episode-family docs/spec/fixtures/positive_episode_family.json
python -m av_trace manifest docs/data/fixtures/positive_acquisition_manifest.json --gate public_release
python -m av_trace family docs/spec/fixtures/positive_episode_family.json \
  --manifest docs/data/fixtures/positive_acquisition_manifest.json
python -m av_trace action docs/spec/fixtures/positive_agent_action.json
python -m av_trace response docs/spec/fixtures/positive_tool_response.json
python -m av_trace trajectory docs/spec/fixtures/positive_trajectory.json
```

Every command emits deterministic JSON. Exit status is `0` for `PASS`, `1` for
a validation failure, and `2` for malformed input or CLI use.

## API shape

Validators return `ValidationReport`, with stable `ValidationIssue` entries:

```json
{
  "status": "FAIL",
  "issues": [
    {
      "code": "NEC-002",
      "pointer": "/claim_evidence_graph/necessity_groups/0",
      "message": "...",
      "severity": "error"
    }
  ]
}
```

No validator repairs inputs. Family validation requires the matching acquisition
manifest and fails closed when it is absent.

The synthetic backend accepts a structurally valid family, one state role, and
one synthetic record per evidence ID. Responses and hashes are canonical JSON
functions of that input and the action sequence.
