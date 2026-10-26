"""Small hostile JSONL agents used to exercise fail-closed runtime behavior."""

from __future__ import annotations

import argparse
import json
import sys
import time
from copy import deepcopy
from typing import Any


def read() -> dict[str, Any]:
    line = sys.stdin.buffer.readline()
    if not line:
        raise SystemExit(2)
    return json.loads(line)


def write(value: Any) -> None:
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def belief(*, sufficient: bool = False) -> dict[str, Any]:
    if sufficient:
        return {
            "p_sufficient": 0.9,
            "verdict": "sufficient",
            "missing_modality_probabilities": {
                "vision": 0.05,
                "speech": 0.05,
                "ambient": 0.05,
            },
            "missing_hop_types": [],
            "missingness_cause_probabilities": {
                "source_evidence_absent": 0.01,
                "evidence_in_source_but_inaccessible": 0.01,
                "evidence_accessible_but_not_found": 0.02,
                "not_missing": 0.95,
                "uncertain": 0.01,
            },
            "next_action_rationale": "Finalize.",
        }
    return {
        "p_sufficient": 0.1,
        "verdict": "insufficient",
        "missing_modality_probabilities": {
            "vision": 0.8,
            "speech": 0.8,
            "ambient": 0.8,
        },
        "missing_hop_types": ["other_registered"],
        "missingness_cause_probabilities": {
            "source_evidence_absent": 0.05,
            "evidence_in_source_but_inaccessible": 0.75,
            "evidence_accessible_but_not_found": 0.1,
            "not_missing": 0.02,
            "uncertain": 0.08,
        },
        "next_action_rationale": "Abstain.",
    }


def action(start: dict[str, Any], step: int, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": "0.2.0",
        "episode_id": start["episode_id"],
        "request_id": f"evil{step}",
        "step_index": step,
        "belief_state": belief(sufficient=tool == "finalize" and bool(arguments.get("claims"))),
        "action": {"tool": tool, "arguments": arguments},
    }


def abstain() -> dict[str, Any]:
    b = belief()
    return {
        "p_sufficient": b["p_sufficient"],
        "verdict": b["verdict"],
        "answer_mode": "abstain",
        "claims": [],
        "diagnosis": {
            "modality_probabilities": b["missing_modality_probabilities"],
            "hop_types": b["missing_hop_types"],
            "cause_probabilities": b["missingness_cause_probabilities"],
            "recovery_route_declared": False,
            "description": "No evidence used.",
        },
        "natural_language_answer": "",
        "termination_reason": "no_recovery_route",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=[
            "inspect_start",
            "gold_claim",
            "route_refs",
            "malformed",
            "oversized",
            "after_finalize",
            "timeout",
        ],
    )
    args = parser.parse_args()
    start_message = read()
    start = start_message["payload"]

    if args.mode == "inspect_start":
        forbidden = {
            "family_id",
            "state_role",
            "interventions",
            "oracle",
            "evidence_id",
            "episode_start",
        }
        if forbidden.intersection(start):
            raise SystemExit(9)
        handle = start["episode_id"]
        if any(token in handle.casefold() for token in ("clean", "blocked", "restored", "syn_f")):
            raise SystemExit(10)
        write({"type": "action", "payload": action(start, 0, "finalize", abstain())})
        read()
        return 0

    if args.mode == "gold_claim":
        final = abstain()
        b = belief(sufficient=True)
        final.update(
            {
                "p_sufficient": b["p_sufficient"],
                "verdict": b["verdict"],
                "answer_mode": "answer",
                "claims": [
                    {
                        "claim_id": "agent_claim",
                        "registered_claim_id": "c1",
                        "text": "Invented unsupported text.",
                        "confidence": 0.9,
                        "citations": [],
                    }
                ],
                "diagnosis": {
                    "modality_probabilities": b["missing_modality_probabilities"],
                    "hop_types": b["missing_hop_types"],
                    "cause_probabilities": b["missingness_cause_probabilities"],
                    "recovery_route_declared": False,
                    "description": "Attempted gold-ID injection.",
                },
                "natural_language_answer": "Invented unsupported text.",
                "termination_reason": "sufficient_evidence",
            }
        )
        write({"type": "action", "payload": action(start, 0, "finalize", final)})
        read()
        return 0

    if args.mode == "route_refs":
        write(
            {
                "type": "action",
                "payload": action(
                    start,
                    0,
                    "inspect_clip",
                    {
                        "interval": {
                            "start_s": 0.0,
                            "end_s": start["video_duration_s"],
                        },
                        "include_video": True,
                        "include_audio": True,
                    },
                ),
            }
        )
        response = read()["payload"]
        serialized = json.dumps(response)
        if "_route_refs" in serialized or "evidence_id" in serialized:
            raise SystemExit(11)
        write({"type": "action", "payload": action(start, 1, "finalize", abstain())})
        read()
        return 0

    if args.mode == "malformed":
        sys.stdout.write("{definitely-not-json\n")
        sys.stdout.flush()
        time.sleep(5)
        return 0

    if args.mode == "oversized":
        sys.stdout.write("x" * 200_000)
        sys.stdout.flush()
        time.sleep(5)
        return 0

    if args.mode == "after_finalize":
        final_action = action(start, 0, "finalize", abstain())
        write({"type": "action", "payload": final_action})
        read()
        extra = deepcopy(final_action)
        extra["request_id"] = "evil1"
        extra["step_index"] = 1
        write({"type": "action", "payload": extra})
        time.sleep(1)
        return 0

    time.sleep(10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
