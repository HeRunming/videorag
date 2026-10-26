#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time


def read():
    return json.loads(sys.stdin.readline())


def write(value):
    print(json.dumps(value), flush=True)


mode = sys.argv[1]
write({"type": "ready"})
calls = 0
while True:
    request = read()
    if request["type"] == "shutdown":
        write({"type": "shutdown_ack"})
        break
    calls += 1
    if mode == "crash":
        raise SystemExit(17)
    if mode == "timeout":
        time.sleep(30)
    if mode == "oom":
        write({"type": "error", "code": "OOM", "message": "synthetic OOM"})
        continue
    if mode == "always_invalid":
        parsed = {"bad": True}
    elif mode == "environment":
        parsed = {
            "restricted_environment_present": any(
                os.environ.get(key)
                for key in (
                    "HF_TOKEN",
                    "HUGGING_FACE_HUB_TOKEN",
                    "http_proxy",
                    "https_proxy",
                    "HTTP_PROXY",
                    "HTTPS_PROXY",
                    "ALL_PROXY",
                )
            )
        }
    elif mode == "repair":
        parsed = (
            {"bad": True}
            if calls == 1
            else {
                "verdict": "answer",
                "answer_text": "A supported answer.",
                "asserted_claims": [
                    {
                        "claim_handle": "slot.c01",
                        "text": "A supported answer.",
                        "citations": ["obs.a"],
                    }
                ],
                "claim_to_citations": {"slot.c01": ["obs.a"]},
                "missing_modalities": [],
                "missing_hops": [],
                "missingness_cause": "not_missing",
                "p_sufficient": 0.9,
                "recovery_intent": "",
                "stop_rationale": "Evidence is cited.",
            }
        )
    elif mode == "agent":
        if request["payload"].get("task") == "grounded_finalization":
            parsed = {
                "verdict": "answer",
                "answer_text": "A supported answer.",
                "asserted_claims": [
                    {
                        "claim_handle": "slot.c01",
                        "text": "A supported answer.",
                        "citations": ["obs.a"],
                    }
                ],
                "claim_to_citations": {"slot.c01": ["obs.a"]},
                "missing_modalities": [],
                "missing_hops": [],
                "missingness_cause": "not_missing",
                "p_sufficient": 0.9,
                "recovery_intent": "",
                "stop_rationale": "Evidence is cited.",
            }
            write(
                {
                    "type": "generation",
                    "raw_text": json.dumps(parsed),
                    "parsed": parsed,
                    "parse_error": None,
                    "prompt_tokens": 1,
                    "generated_tokens": 1,
                    "latency_seconds": 0.0,
                }
            )
            continue
        if request["payload"].get("task") != "choose_next_action":
            menu = request["payload"]["output_schema"][
                "action_menu"
            ]
            parsed = {
                "public_state": {
                    "p_sufficient": 0.1,
                    "covered_claim_handles": [],
                    "missing_modalities": ["vision"],
                    "missing_hops": ["event_detection"],
                    "missingness_cause": "evidence_accessible_but_not_found",
                    "recovery_intent": "Follow a visible action.",
                },
                "action_index": 0,
            }
            write(
                {
                    "type": "generation",
                    "raw_text": json.dumps(parsed),
                    "parsed": parsed,
                    "parse_error": None,
                    "prompt_tokens": 1,
                    "generated_tokens": 1,
                    "latency_seconds": 0.0,
                }
            )
            continue
        turn = request["payload"]["turn"]
        menu = request["payload"]["output_schema"]["action_menu"]
        common = {
            "p_sufficient": 0.9 if turn == 2 else 0.1,
            "covered_claim_handles": ["slot.c01"] if turn == 2 else [],
            "missing_modalities": [] if turn == 2 else ["vision"],
            "missing_hops": [] if turn == 2 else ["event_detection"],
            "missingness_cause": (
                "not_missing" if turn == 2 else "evidence_accessible_but_not_found"
            ),
            "recovery_intent": "" if turn == 2 else "Search and inspect.",
        }
        actions = [item["action"] for item in menu]
        desired = "search" if turn == 0 else "observe" if turn == 1 else "finalize"
        action_index = next(
            index for index, action in enumerate(actions)
            if action["type"] == desired
        )
        parsed = {"public_state": common, "action_index": action_index}
    elif mode == "controller_context_repair":
        if calls == 1:
            parsed = {"bad": True}
        else:
            payload = request["payload"]
            assert payload["question"] == "Which word is spoken?"
            assert payload["public_claim_slots"][0]["claim_handle"] == "devslot.word"
            parsed = {
                "public_state": {
                    "p_sufficient": 0.1,
                    "covered_claim_handles": [],
                    "missing_modalities": ["speech"],
                    "missing_hops": ["speech_content"],
                    "missingness_cause": "evidence_accessible_but_not_found",
                    "recovery_intent": "Search speech.",
                },
                "action_index": 0,
            }
    else:
        parsed = {}
    write(
        {
            "type": "generation",
            "raw_text": json.dumps(parsed),
            "parsed": parsed,
            "parse_error": None,
            "prompt_tokens": 1,
            "generated_tokens": 1,
            "latency_seconds": 0.0,
        }
    )
