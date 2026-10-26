# AV-TRACE subprocess agent runtime

This directory documents the leakage-resistant execution path implemented in
`src/av_trace_agent_runtime/`.

## Boundary

The evaluator launches **one fresh process per episode**. The child receives
newline-delimited JSON on standard input and may write only protocol messages
as newline-delimited JSON on standard output.

The first message is:

```json
{
  "type": "episode_start",
  "payload": {
    "protocol_version": "0.2.0",
    "episode_id": "e7f5f2d198c80a0e5203b0ad",
    "question": "...",
    "available_tools": ["search_visual", "...", "finalize"],
    "video_duration_s": 1200.0,
    "budget": {"cost_limit": 12.0, "max_steps": 10},
    "tool_costs": {"search_visual": 1.0, "finalize": 0.0},
    "seed": 20260906,
    "config": {
      "wire_version": "av-trace-agent-jsonl-v1",
      "deterministic": true
    }
  }
}
```

It deliberately excludes real episode, family, state-role, intervention,
oracle, evidence, route, backend, and replay identifiers. The visible episode,
request, search-pointer, observation, and backend-version identifiers are
episode-local opaque deterministic handles. A different configured seed changes
the handle namespace.

The child emits normative agent-action envelopes:

```json
{"type":"action","payload":{...agent_action_schema.json...}}
```

For non-final actions, the evaluator returns:

```json
{"type":"tool_response","payload":{...tool_response_schema.json...}}
```

After `finalize`, the evaluator returns a small acknowledgement and expects the
process to exit:

```json
{"type":"finalized","payload":{"protocol_version":"0.2.0","episode_id":"...","request_id":"...","step_index":3}}
```

Actions and tool responses are validated against the frozen normative schemas
and semantic action/response checks. The evaluator privately translates opaque
IDs to backend IDs, retains private route references, ignores submitted
`registered_claim_id` values, applies the frozen exact-text claim mapper, and
reconstructs a normative trajectory with real evaluator IDs.

## Guarantees

The runtime enforces:

- one child process per episode;
- a total episode wall-clock timeout;
- per-message and cumulative child-output byte limits;
- one UTF-8 JSON object per line;
- failure on malformed, non-object, unexpected, duplicate, non-contiguous, or
  post-finalize messages;
- schema validation before backend execution and before sending a response;
- deterministic seed/config environment (`PYTHONHASHSEED`,
  `AV_TRACE_AGENT_SEED`, and wire version);
- removal of evaluator-private `_route_refs` from policy-visible observations;
- evaluator-only reconstruction of real IDs and normative trajectory metadata.

The wire protocol itself assumes no filesystem or network capability. No such
capability is needed by the bundled baseline subprocesses.

## Non-guarantees

This is **not an OS-level sandbox**. It prevents direct Python object references
to family/backend/evaluator state from crossing the serialization boundary, but
does not by itself stop a malicious process from reading files, opening network
connections, inspecting environment-visible resources, spawning processes, or
using system calls if the host permits them. Production evaluation must combine
this runtime with an external sandbox/container policy that removes those
capabilities.

Standard error is not part of the protocol, is discarded, and counts against
the cumulative output limit.

## Running a bundled baseline

```bash
PYTHONPATH=src python scripts/run_agent_subprocess.py \
  --generated-root mvp/generated/full \
  --family-id syn_f01_visual_order \
  --state-role RESTORED \
  --baseline EvidenceBeliefState \
  --output /tmp/trajectory.json
```

Available baseline names:

- `AlwaysAnswer`
- `SingleShotRAG`
- `ReActHeuristic`
- `EvidenceBeliefState`

The adapter imports the existing policies only inside the child process and
implements their `AgentSession` interface using JSONL messages. The child never
receives a family, oracle, intervention runtime, backend, index, or evaluator
session object.

## Running another agent

An executable that implements the protocol can be supplied directly:

```bash
PYTHONPATH=src python scripts/run_agent_subprocess.py \
  --generated-root mvp/generated/quick \
  --family-id syn_f01_visual_order \
  --state-role CLEAN \
  --agent-name MyAgent \
  --agent-command "python /path/to/my_agent.py" \
  --timeout-s 10 \
  --max-output-bytes 1000000 \
  --max-message-bytes 256000
```

The command string is split with POSIX shell-like quoting but is executed
without a shell.

## Tests

```bash
PYTHONPATH=src pytest -q tests_agent_runtime
```

The adversarial fixtures cover:

- attempts to infer state/family from the start message and IDs;
- submission of a gold registered claim ID;
- attempts to observe evaluator-private route references;
- malformed and oversized output;
- timeout;
- action after finalize;
- all four current baselines;
- CLI production of a trajectory accepted by the current validator.
