# Fixed tool API and deterministic restoration contract

**Version:** 0.2.0  
**Scope:** Pilot-0 protocol specification; no server implementation is included.

Normative JSON Schemas:

- `agent_action_schema.json`
- `tool_response_schema.json`
- `final_answer_schema.json`
- `trajectory_schema.json`

## 1. Principles

1. All primary-track systems use one frozen backend, indexes, decoder, ASR,
   result limits, error vocabulary, and cost schedule.
2. Outputs are deterministic functions of episode, request, backend version, and
   intervention manifest.
3. Times are source-video seconds and intervals are half-open.
4. Search results are non-citable pointers. `inspect_clip` and
   `read_transcript` return citable observations.
5. Every action includes a structured belief state; hidden chain-of-thought is
   neither requested nor scored.
6. The only channel-status tool is `get_channel_status`.
7. `finalize` uses the same action envelope as every other action.

## 2. Episode start

```json
{
  "protocol_version": "0.2.0",
  "episode_id": "syn_alarm_001.blocked",
  "family_id": "syn_alarm_001",
  "state_role": "BLOCKED",
  "question": "What caused the alarm?",
  "available_tools": [
    "search_visual",
    "search_speech",
    "search_ambient_audio",
    "inspect_clip",
    "read_transcript",
    "get_channel_status",
    "finalize"
  ],
  "video_duration_s": 1800.0,
  "budget": {"cost_limit": 12.0, "max_steps": 10},
  "tool_costs": {
    "search_visual": 1.0,
    "search_speech": 1.0,
    "search_ambient_audio": 1.0,
    "inspect_clip": 2.0,
    "read_transcript": 1.0,
    "get_channel_status": 0.25,
    "finalize": 0.0
  }
}
```

The hidden state role is not shown in blind primary execution; it appears in the
evaluator log.

## 3. Agent actions

### Valid search action

```json
{
  "protocol_version": "0.2.0",
  "episode_id": "syn_alarm_001.blocked",
  "request_id": "r-0001",
  "step_index": 0,
  "belief_state": {
    "p_sufficient": 0.2,
    "verdict": "insufficient",
    "missing_modality_probabilities": {
      "vision": 0.2,
      "speech": 0.9,
      "ambient": 0.1
    },
    "missing_hop_types": ["speech_content"],
    "missingness_cause_probabilities": {
      "source_evidence_absent": 0.05,
      "evidence_in_source_but_inaccessible": 0.65,
      "evidence_accessible_but_not_found": 0.2,
      "not_missing": 0.05,
      "uncertain": 0.05
    },
    "next_action_rationale": "Check whether speech access is available."
  },
  "action": {
    "tool": "get_channel_status",
    "arguments": {"channels": ["speech", "transcript"]}
  }
}
```

Missing-modality values are independent multilabel probabilities and need not
sum to one. Missingness-cause probabilities are categorical and must sum to one
within the semantic-validator tolerance.

### Invalid action fixture

This fails because `request_channel_status` is not a tool and the cause
distribution is absent:

```json
{
  "protocol_version": "0.2.0",
  "episode_id": "syn_alarm_001.blocked",
  "request_id": "r-0001",
  "step_index": 0,
  "belief_state": {
    "p_sufficient": 0.2,
    "verdict": "insufficient",
    "missing_modality_probabilities": {"vision": 0.2, "speech": 0.9, "ambient": 0.1},
    "missing_hop_types": ["speech_content"],
    "next_action_rationale": "Check speech."
  },
  "action": {
    "tool": "request_channel_status",
    "arguments": {"channels": ["speech"]}
  }
}
```

## 4. Tool responses

### Valid unavailable-channel response

```json
{
  "protocol_version": "0.2.0",
  "episode_id": "syn_alarm_001.blocked",
  "request_id": "r-0001",
  "step_index": 0,
  "tool": "get_channel_status",
  "status": "channel_unavailable",
  "cost_charged": 0.25,
  "cost_used_total": 0.25,
  "cost_remaining": 11.75,
  "backend_version": "fixed-v0.2",
  "results": [],
  "error": {
    "code": "SPEECH_CHANNEL_UNAVAILABLE",
    "retryable": true,
    "message": "The requested channel is unavailable.",
    "retry_after_step": 3
  },
  "response_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

`status` is one of `ok`, `partial`, `channel_unavailable`, `timeout`,
`invalid_request`, `budget_exhausted`, `rate_limited`, or `not_found`.

Successful search results contain pointers. Successful inspection/transcript
results contain immutable observation IDs, payloads, modalities, intervals, and
payload hashes.

## 5. Tool definitions

| Tool | Purpose | Citable output? |
|---|---|---|
| `search_visual` | Query the frozen visual index. | No |
| `search_speech` | Query the frozen ASR/subtitle index. | No |
| `search_ambient_audio` | Query the frozen non-speech audio index. | No |
| `inspect_clip` | Inspect a bounded source-time clip with declared video/audio channels. | Yes |
| `read_transcript` | Read bounded ASR or subtitle text. | Yes |
| `get_channel_status` | Query operational status and, only when registered, trigger restoration. | No |
| `finalize` | Submit the final belief, answer, citations, and diagnosis. | Terminates |

Detailed argument shapes are normative in `agent_action_schema.json`.

## 6. Finalize

The final belief state in the envelope is timed after the last tool response.
`action.arguments` is the scored final answer:

```json
{
  "protocol_version": "0.2.0",
  "episode_id": "syn_alarm_001.blocked",
  "request_id": "r-final",
  "step_index": 3,
  "belief_state": {
    "p_sufficient": 0.1,
    "verdict": "insufficient",
    "missing_modality_probabilities": {
      "vision": 0.1,
      "speech": 0.95,
      "ambient": 0.05
    },
    "missing_hop_types": ["speech_content"],
    "missingness_cause_probabilities": {
      "source_evidence_absent": 0.02,
      "evidence_in_source_but_inaccessible": 0.9,
      "evidence_accessible_but_not_found": 0.03,
      "not_missing": 0.01,
      "uncertain": 0.04
    },
    "next_action_rationale": "No supported answer is available in the blocked state."
  },
  "action": {
    "tool": "finalize",
    "arguments": {
      "p_sufficient": 0.1,
      "verdict": "insufficient",
      "answer_mode": "abstain",
      "claims": [],
      "diagnosis": {
        "modality_probabilities": {
          "vision": 0.1,
          "speech": 0.95,
          "ambient": 0.05
        },
        "hop_types": ["speech_content"],
        "cause_probabilities": {
          "source_evidence_absent": 0.02,
          "evidence_in_source_but_inaccessible": 0.9,
          "evidence_accessible_but_not_found": 0.03,
          "not_missing": 0.01,
          "uncertain": 0.04
        },
        "recovery_route_declared": false,
        "description": "The speech route is unavailable."
      },
      "natural_language_answer": "",
      "termination_reason": "no_recovery_route"
    }
  }
}
```

The semantic validator requires final belief and final-answer probability fields
to agree.

## 7. Intervention and restoration

Pilot-0 supports only:

- withholding all evidence in one registered necessity group; or
- disabling one registered modality/channel route.

`RESTORED` starts byte/state-identically to `BLOCKED`. A fixed call index or a
registered `get_channel_status` action reverses exactly the block. No result may
depend on model identity, correctness, or rationale.

ASR corruption, injected distractors, answer replacement, generic wrong results,
and budget mutation are invalid in Pilot-0.

## 8. Cost and failure semantics

- Backend-reaching calls are charged the frozen advertised cost, including
  injected typed failures.
- Schema-invalid requests receive one configured repair opportunity; the policy
  is frozen before runs.
- A call that would exceed budget returns `budget_exhausted` and permits one
  zero-cost finalization.
- Cost, result IDs, ordering, errors, and payload hashes must replay exactly.

## 9. Protocol violations

An episode is invalid for a submission after the allowed repair if it includes:

- malformed action or final output;
- citation to an unreturned observation;
- citation outside the observation interval;
- an undisclosed external tool in the fixed-backend track;
- action after `finalize`;
- access to sealed manifests or source bytes;
- non-monotone or mismatched request/step IDs.

