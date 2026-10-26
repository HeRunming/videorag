"""Evaluator-side subprocess lifecycle and normative trajectory reconstruction."""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import sys
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from av_trace.schemas import SchemaRegistry
from av_trace.trajectory import validate_trajectory
from av_trace.util import trajectory_content_hash

from .errors import AgentRuntimeError
from .protocol import (
    OpaqueHandleMap,
    PolicyView,
    WIRE_VERSION,
    canonical_json_line,
    parse_json_line,
)


@dataclass(frozen=True)
class RuntimeConfig:
    """Frozen process and wire limits for one isolated episode."""

    timeout_s: float = 10.0
    max_output_bytes: int = 1_000_000
    max_message_bytes: int = 256_000
    seed: int = 20260906

    def __post_init__(self) -> None:
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        if self.max_message_bytes <= 0 or self.max_message_bytes > self.max_output_bytes:
            raise ValueError("max_message_bytes must be positive and no larger than max_output_bytes")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")


def _recorded_at(step_index: int, replay_seed: int) -> str:
    origin = datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=replay_seed)
    return (origin + timedelta(seconds=step_index)).isoformat().replace("+00:00", "Z")


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _map_registered_claims(
    final_answer: Mapping[str, Any],
    family: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluator-private exact-text mapping; submitted gold IDs are ignored."""

    mapped = deepcopy(dict(final_answer))
    candidates: dict[str, str] = {}
    for claim in family["claim_evidence_graph"]["claims"]:
        for text in [claim["proposition"], *claim.get("accepted_aliases", ())]:
            candidates[_normalized_text(text)] = claim["claim_id"]
    for claim in mapped.get("claims", ()):
        claim["registered_claim_id"] = candidates.get(
            _normalized_text(claim.get("text", ""))
        )
    return mapped


class _JsonlProcess:
    """Small fail-closed JSONL transport with one cumulative output budget."""

    def __init__(self, command: Sequence[str], config: RuntimeConfig) -> None:
        if not command:
            raise ValueError("command must not be empty")
        self.command = tuple(command)
        self.config = config
        self.deadline = time.monotonic() + config.timeout_s
        self.output_bytes = 0
        self._buffer = bytearray()
        env = {
            "PATH": os.environ.get("PATH", ""),
            # Preserve only Python's already-active import roots. This makes
            # the bundled module entrypoint work when the parent script added
            # ``src`` to sys.path without requiring an installed wheel.
            "PYTHONPATH": os.pathsep.join(str(item) for item in sys.path if item),
            "PYTHONHASHSEED": str(config.seed),
            "AV_TRACE_AGENT_SEED": str(config.seed),
            "AV_TRACE_AGENT_WIRE_VERSION": WIRE_VERSION,
        }
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                close_fds=True,
                start_new_session=True,
                env=env,
            )
        except OSError as exc:
            raise AgentRuntimeError("SPAWN_FAILED", str(exc)) from exc
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        assert self.process.stderr is not None
        os.set_blocking(self.process.stdout.fileno(), False)
        os.set_blocking(self.process.stderr.fileno(), False)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ, "stdout")
        self.selector.register(self.process.stderr, selectors.EVENT_READ, "stderr")

    def _remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise AgentRuntimeError("TIMEOUT", "Agent episode exceeded its wall-clock timeout.")
        return remaining

    def send(self, message: Mapping[str, Any]) -> None:
        raw = canonical_json_line(message)
        if len(raw) > self.config.max_message_bytes:
            raise AgentRuntimeError("INPUT_LIMIT", "Evaluator message exceeds max_message_bytes.")
        try:
            self.process.stdin.write(raw)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise AgentRuntimeError("AGENT_EXITED", "Agent closed stdin unexpectedly.") from exc

    def receive(self) -> dict[str, Any]:
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                raw = bytes(self._buffer[: newline + 1])
                del self._buffer[: newline + 1]
                return parse_json_line(
                    raw,
                    max_bytes=self.config.max_message_bytes,
                    source="agent",
                )
            if len(self._buffer) > self.config.max_message_bytes:
                raise AgentRuntimeError(
                    "OUTPUT_LIMIT",
                    "Agent emitted a line larger than max_message_bytes.",
                )
            events = self.selector.select(self._remaining())
            if not events:
                continue
            for key, _ in events:
                try:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    self.selector.unregister(key.fileobj)
                    if key.data == "stdout":
                        if self._buffer:
                            raise AgentRuntimeError(
                                "MALFORMED_MESSAGE",
                                "Agent closed stdout with a non-newline-terminated message.",
                            )
                        code = self.process.poll()
                        raise AgentRuntimeError(
                            "AGENT_EXITED",
                            f"Agent exited before the episode completed (return code {code}).",
                        )
                    continue
                self.output_bytes += len(chunk)
                if self.output_bytes > self.config.max_output_bytes:
                    raise AgentRuntimeError(
                        "OUTPUT_LIMIT",
                        f"Agent output exceeded {self.config.max_output_bytes} bytes.",
                    )
                if key.data == "stdout":
                    self._buffer.extend(chunk)
                # stderr is deliberately not protocol input and is discarded,
                # while still counting toward the child output limit.

    def close(self, *, expect_clean_exit: bool) -> None:
        try:
            if self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.close()
            if expect_clean_exit:
                try:
                    code = self.process.wait(timeout=max(0.01, self._remaining()))
                except subprocess.TimeoutExpired as exc:
                    raise AgentRuntimeError(
                        "TIMEOUT", "Agent did not exit after finalization."
                    ) from exc
                if code != 0:
                    raise AgentRuntimeError(
                        "AGENT_EXITED",
                        f"Agent exited with return code {code}.",
                    )
            elif self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=1)
        finally:
            self.selector.close()


class SubprocessEpisodeRuntime:
    """Run exactly one agent process for one backend episode."""

    def __init__(
        self,
        *,
        backend: Any,
        family: Mapping[str, Any],
        state_role: str,
        agent_name: str,
        command: Sequence[str],
        config: RuntimeConfig | None = None,
        registry: SchemaRegistry | None = None,
    ) -> None:
        self.backend = backend
        self.family = deepcopy(dict(family))
        self.state_role = state_role
        self.agent_name = agent_name
        self.command = tuple(command)
        self.config = config or RuntimeConfig()
        self.registry = registry or getattr(backend, "registry", None) or SchemaRegistry()
        self._normative_start = backend.episode_start(reveal_state_role=True)
        self._replay_seed = next(
            item["replay"]["seed"]
            for item in self.family["episodes"]
            if item["state_role"] == state_role
        )
        # The namespace seed is public configuration.  Do not derive it from
        # low-entropy evaluator identifiers, since a child that knows the
        # algorithm could enumerate candidate family/state IDs offline.
        self.handles = OpaqueHandleMap(self.config.seed)
        public_episode_id = self.handles.public(
            "episode", self._normative_start["episode_id"]
        )
        self.view = PolicyView(
            self.registry,
            self.handles,
            self._normative_start["episode_id"],
            public_episode_id,
        )
        self._events: list[dict[str, Any]] = []
        self._final_output: dict[str, Any] | None = None

    def _event(self, action: dict[str, Any], response: dict[str, Any] | None) -> None:
        event = {
            "event_type": "finalize" if response is None else "tool_exchange",
            "action": deepcopy(action),
            "active_hook_ids": list(
                getattr(self.backend, "last_active_hook_ids", ())
            ),
            "recorded_at": _recorded_at(action["step_index"], self._replay_seed),
        }
        if response is not None:
            event["response"] = deepcopy(response)
        self._events.append(event)

    def _trajectory(self) -> dict[str, Any]:
        if self._final_output is None:
            raise AgentRuntimeError("NO_FINALIZE", "Agent did not finalize.")
        episode = next(
            item
            for item in self.family["episodes"]
            if item["state_role"] == self.state_role
        )
        trajectory = {
            "schema_version": "0.2.0",
            "trajectory_id": self.handles.public(
                "episode",
                f"trajectory\0{self.agent_name}\0{self._normative_start['episode_id']}",
            ),
            "track": episode["backend"]["track"],
            "episode_start": deepcopy(self._normative_start),
            "events": deepcopy(self._events),
            "final_output": deepcopy(self._final_output),
            "completion": {
                "status": (
                    "forced_finalization"
                    if any(
                        event.get("response", {}).get("status") == "budget_exhausted"
                        for event in self._events
                    )
                    else "completed"
                ),
                "total_steps": len(self._events),
                "total_cost": float(getattr(self.backend, "cost_used", 0.0)),
                "protocol_valid": True,
            },
            "replay": {
                "backend_version": self.backend.backend_version,
                "backend_hash": self.backend.backend_hash,
                "intervention_manifest_hash": self.backend.intervention_manifest_hash,
                "trajectory_hash": "sha256:" + "0" * 64,
                "replay_seed": self._replay_seed,
            },
        }
        trajectory["replay"]["trajectory_hash"] = trajectory_content_hash(trajectory)
        report = validate_trajectory(trajectory, self.registry)
        if not report.ok:
            first = report.issues[0]
            raise AgentRuntimeError(
                "INVALID_TRAJECTORY",
                f"{first.code} at {first.pointer}: {first.message}",
            )
        return trajectory

    def run(self) -> dict[str, Any]:
        transport = _JsonlProcess(self.command, self.config)
        finished = False
        try:
            transport.send(
                {
                    "type": "episode_start",
                    "payload": self.view.episode_start(
                        self._normative_start,
                        seed=self.config.seed,
                    ),
                }
            )
            while True:
                message = transport.receive()
                if set(message) != {"type", "payload"} or message["type"] != "action":
                    raise AgentRuntimeError(
                        "MALFORMED_MESSAGE",
                        "Agent messages must be {'type':'action','payload':...}.",
                    )
                if not isinstance(message["payload"], dict):
                    raise AgentRuntimeError("MALFORMED_MESSAGE", "Action payload must be an object.")
                public_action = message["payload"]
                if public_action.get("episode_id") != self.view.public_episode_id:
                    raise AgentRuntimeError(
                        "EPISODE_MISMATCH",
                        "Action episode_id does not match the opaque episode handle.",
                    )
                if public_action.get("step_index") != len(self._events):
                    raise AgentRuntimeError(
                        "STEP_MISMATCH",
                        f"Expected step_index {len(self._events)}.",
                    )
                private_action = self.view.action_to_private(public_action)
                if private_action["action"]["tool"] == "finalize":
                    private_action["action"]["arguments"] = _map_registered_claims(
                        private_action["action"]["arguments"], self.family
                    )
                response = self.backend.execute(private_action)
                self._event(private_action, response)
                if response is None:
                    self._final_output = deepcopy(
                        private_action["action"]["arguments"]
                    )
                    transport.send(
                        {
                            "type": "finalized",
                            "payload": {
                                "protocol_version": "0.2.0",
                                "episode_id": self.view.public_episode_id,
                                "request_id": public_action["request_id"],
                                "step_index": public_action["step_index"],
                            },
                        }
                    )
                    # Any post-finalize stdout message is a protocol violation.
                    try:
                        extra = transport.receive()
                    except AgentRuntimeError as exc:
                        if exc.code == "AGENT_EXITED":
                            finished = True
                            break
                        raise
                    raise AgentRuntimeError(
                        "AFTER_FINALIZE",
                        f"Agent emitted a message after finalization: {extra.get('type')!r}.",
                    )
                public_response = self.view.response_to_public(response)
                transport.send({"type": "tool_response", "payload": public_response})
            trajectory = self._trajectory()
            return trajectory
        finally:
            transport.close(expect_clean_exit=finished)


def run_subprocess_episode(
    *,
    backend: Any,
    family: Mapping[str, Any],
    state_role: str,
    agent_name: str,
    command: Sequence[str],
    config: RuntimeConfig | None = None,
    registry: SchemaRegistry | None = None,
) -> dict[str, Any]:
    """Convenience wrapper for one-process-per-episode execution."""

    return SubprocessEpisodeRuntime(
        backend=backend,
        family=family,
        state_role=state_role,
        agent_name=agent_name,
        command=command,
        config=config,
        registry=registry,
    ).run()
