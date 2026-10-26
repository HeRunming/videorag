"""Subprocess entrypoint adapting the four existing deterministic baselines."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from typing import Any, Mapping, Sequence

from av_trace_mvp.agents import (
    AlwaysAnswerAgent,
    EvidenceBeliefStateAgent,
    ReActHeuristicAgent,
    SingleShotRAGAgent,
)

from .protocol import WIRE_VERSION, canonical_json_line, validate_episode_start_payload

AGENTS = {
    "AlwaysAnswer": AlwaysAnswerAgent,
    "SingleShotRAG": SingleShotRAGAgent,
    "ReActHeuristic": ReActHeuristicAgent,
    "EvidenceBeliefState": EvidenceBeliefStateAgent,
}


def _read_message() -> dict[str, Any]:
    line = sys.stdin.buffer.readline()
    if not line:
        raise RuntimeError("Evaluator closed stdin.")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise RuntimeError("Protocol message must be an object.")
    return value


def _write_message(message: Mapping[str, Any]) -> None:
    sys.stdout.buffer.write(canonical_json_line(message))
    sys.stdout.buffer.flush()


class JsonlAgentSession:
    """Agent-side implementation of the existing ``AgentSession`` protocol."""

    def __init__(self, start: Mapping[str, Any]) -> None:
        validate_episode_start_payload(start)
        if start["config"]["wire_version"] != WIRE_VERSION:
            raise RuntimeError("Wire version mismatch.")
        self.start = deepcopy(dict(start))
        self._responses: list[dict[str, Any]] = []
        self._observations: list[dict[str, Any]] = []
        self._finished = False
        self._cost = 0.0
        self._step = 0

    @property
    def observations(self) -> Sequence[Mapping[str, Any]]:
        return tuple(self._observations)

    @property
    def responses(self) -> Sequence[Mapping[str, Any]]:
        return tuple(self._responses)

    def can_call(self, tool: str) -> bool:
        if self._finished:
            return False
        if self._step + 1 >= self.start["budget"]["max_steps"]:
            return False
        cost = self.start["tool_costs"].get(tool)
        return (
            cost is not None
            and self._cost + cost <= self.start["budget"]["cost_limit"] + 1e-9
        )

    def _action(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        belief_state: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "protocol_version": "0.2.0",
            "episode_id": self.start["episode_id"],
            "request_id": f"r{self._step:04d}",
            "step_index": self._step,
            "belief_state": deepcopy(dict(belief_state)),
            "action": {"tool": tool, "arguments": deepcopy(dict(arguments))},
        }

    def call(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        belief_state: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        if not self.can_call(tool):
            return None
        action = self._action(tool, arguments, belief_state)
        _write_message({"type": "action", "payload": action})
        message = _read_message()
        if message.get("type") != "tool_response":
            raise RuntimeError("Expected tool_response.")
        response = message["payload"]
        if response["request_id"] != action["request_id"]:
            raise RuntimeError("Response request mismatch.")
        self._cost = float(response["cost_used_total"])
        self._responses.append(response)
        self._observations.extend(
            result
            for result in response["results"]
            if result.get("result_type") == "observation"
        )
        self._step += 1
        return response

    def finish(
        self,
        final_answer: Mapping[str, Any],
        belief_state: Mapping[str, Any],
    ) -> None:
        if self._finished:
            raise RuntimeError("Agent attempted to finalize twice.")
        action = self._action("finalize", final_answer, belief_state)
        _write_message({"type": "action", "payload": action})
        message = _read_message()
        if message.get("type") != "finalized":
            raise RuntimeError("Expected finalized acknowledgement.")
        self._finished = True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=sorted(AGENTS), required=True)
    args = parser.parse_args(argv)
    message = _read_message()
    if set(message) != {"type", "payload"} or message["type"] != "episode_start":
        raise RuntimeError("First message must be episode_start.")
    session = JsonlAgentSession(message["payload"])
    AGENTS[args.agent]().run(session)
    if not session._finished:
        raise RuntimeError("Baseline returned without finalizing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
