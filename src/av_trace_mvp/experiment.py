"""Experiment orchestration and report emission for deterministic MVP agents."""

from __future__ import annotations

import csv
import json
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from av_trace.trajectory import validate_trajectory
from av_trace.util import response_content_hash, sha256_json, trajectory_content_hash

from .agents import AgentSession, DeterministicAgent
from .metrics import aggregate_metrics, dashboard_rows, score_episode


class ToolBackend(Protocol):
    """Conservative adapter for the documented stateful tool contract."""

    def episode_start(self, *, reveal_state_role: bool = False) -> dict[str, Any]: ...

    def execute(self, action: dict[str, Any]) -> dict[str, Any] | None: ...


BackendFactory = Callable[[Mapping[str, Any], str], ToolBackend]
_ID_CHARS = re.compile(r"[^A-Za-z0-9._:-]+")


def _safe_id(value: str) -> str:
    cleaned = _ID_CHARS.sub("-", value).strip("-")
    if not cleaned or not cleaned[0].isalnum():
        cleaned = "agent-" + cleaned
    return cleaned[:80]


def _recorded_at(step_index: int, replay_seed: int) -> str:
    origin = datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=replay_seed)
    return (origin + timedelta(seconds=step_index)).isoformat().replace("+00:00", "Z")


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _map_registered_claims(
    final_answer: Mapping[str, Any],
    family: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply the frozen exact-text claim mapper at the evaluator boundary."""

    mapped = deepcopy(dict(final_answer))
    candidates: dict[str, str] = {}
    for claim in family["claim_evidence_graph"]["claims"]:
        texts = [claim["proposition"], *claim.get("accepted_aliases", ())]
        for text in texts:
            candidates[_normalized_text(text)] = claim["claim_id"]
    for claim in mapped.get("claims", ()):
        # Agent-supplied evaluator IDs are never trusted. The frozen mapper
        # determines the ID exclusively from the submitted claim text.
        claim["registered_claim_id"] = candidates.get(
            _normalized_text(claim.get("text", ""))
        )
    return mapped


class EpisodeSession(AgentSession):
    """Turn an adaptive agent/backend interaction into a normative trajectory."""

    def __init__(
        self,
        backend: ToolBackend,
        family: Mapping[str, Any],
        state_role: str,
        agent_name: str,
    ) -> None:
        self.backend = backend
        self.family = family
        self.state_role = state_role
        self.agent_name = agent_name
        self._trajectory_start = backend.episode_start(reveal_state_role=True)
        self.start = {
            key: deepcopy(value)
            for key, value in self._trajectory_start.items()
            if key
            in {
                "question",
                "available_tools",
                "video_duration_s",
                "budget",
                "tool_costs",
            }
        }
        self._events: list[dict[str, Any]] = []
        self._observations: list[Mapping[str, Any]] = []
        self._responses: list[Mapping[str, Any]] = []
        self._cost = 0.0
        self._finished = False
        self._replay_seed = next(
            item["replay"]["seed"]
            for item in family["episodes"]
            if item["state_role"] == state_role
        )

    @property
    def observations(self) -> Sequence[Mapping[str, Any]]:
        return tuple(self._observations)

    @property
    def responses(self) -> Sequence[Mapping[str, Any]]:
        return tuple(self._responses)

    def can_call(self, tool: str) -> bool:
        if self._finished:
            return False
        # Keep one action slot for mandatory finalization.
        if len(self._events) + 1 >= self.start["budget"]["max_steps"]:
            return False
        cost = self.start["tool_costs"].get(tool)
        return cost is not None and self._cost + cost <= self.start["budget"]["cost_limit"] + 1e-9

    def _action(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        belief_state: Mapping[str, Any],
    ) -> dict[str, Any]:
        step = len(self._events)
        return {
            "protocol_version": "0.2.0",
            "episode_id": self._trajectory_start["episode_id"],
            "request_id": f"{_safe_id(self.agent_name.lower())}.r{step:04d}",
            "step_index": step,
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
        response = self.backend.execute(action)
        if response is None:
            raise RuntimeError(f"Backend unexpectedly finalized during {tool}.")
        self._cost = float(response["cost_used_total"])
        agent_response = self._agent_response(response)
        self._responses.append(agent_response)
        self._observations.extend(
            result
            for result in agent_response["results"]
            if result.get("result_type") == "observation"
        )
        self._events.append(
            {
                "event_type": "tool_exchange",
                "action": action,
                "response": deepcopy(response),
                "active_hook_ids": list(
                    getattr(self.backend, "last_active_hook_ids", ())
                ),
                "recorded_at": _recorded_at(action["step_index"], self._replay_seed),
            }
        )
        return agent_response

    @staticmethod
    def _agent_response(response: Mapping[str, Any]) -> dict[str, Any]:
        """Return the documented response without evaluator identity fields.

        The full response remains in the trajectory for replay. Policies receive
        an opaque per-session view so episode IDs cannot disclose matched state.
        """

        visible = deepcopy(dict(response))
        visible["episode_id"] = "episode"
        for result in visible.get("results", ()):
            if result.get("result_type") == "observation":
                result.get("payload", {}).pop("_route_refs", None)
        visible["response_hash"] = response_content_hash(visible)
        return visible

    def finish(
        self,
        final_answer: Mapping[str, Any],
        belief_state: Mapping[str, Any],
    ) -> None:
        if self._finished:
            raise RuntimeError("Agent attempted to finalize twice.")
        if len(self._events) >= self.start["budget"]["max_steps"]:
            raise RuntimeError("No action slot remains for finalization.")
        action = self._action(
            "finalize",
            _map_registered_claims(final_answer, self.family),
            belief_state,
        )
        response = self.backend.execute(action)
        if response is not None:
            raise RuntimeError("A finalize action must not return a tool response.")
        self._events.append(
            {
                "event_type": "finalize",
                "action": action,
                "active_hook_ids": list(
                    getattr(self.backend, "last_active_hook_ids", ())
                ),
                "recorded_at": _recorded_at(action["step_index"], self._replay_seed),
            }
        )
        self._finished = True

    def trajectory(self) -> dict[str, Any]:
        if not self._finished:
            raise RuntimeError("Agent did not finalize.")
        episode = next(
            item
            for item in self.family["episodes"]
            if item["state_role"] == self.state_role
        )
        backend_version = getattr(
            self.backend,
            "backend_version",
            next(
                (
                    response["backend_version"]
                    for response in reversed(self._responses)
                    if response.get("backend_version")
                ),
                episode["backend"]["backend_version"],
            ),
        )
        backend_hash = getattr(
            self.backend,
            "backend_hash",
            sha256_json(
                {
                    "backend_version": backend_version,
                    "episode_start": self.start,
                    "adapter": "documented-tool-contract-v0.2.0",
                }
            ),
        )
        intervention_hash = getattr(
            self.backend,
            "intervention_manifest_hash",
            sha256_json(
                {
                    "family_id": self.family["family_id"],
                    "state_role": self.state_role,
                    "interventions": episode["interventions"],
                }
            ),
        )
        final_output = deepcopy(self._events[-1]["action"]["action"]["arguments"])
        trajectory = {
            "schema_version": "0.2.0",
            "trajectory_id": (
                f"traj.{_safe_id(self.agent_name.lower())}.{self._trajectory_start['episode_id']}"
            )[:128],
            "track": episode["backend"]["track"],
            "episode_start": deepcopy(dict(self._trajectory_start)),
            "events": deepcopy(self._events),
            "final_output": final_output,
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
                "total_cost": self._cost,
                "protocol_valid": True,
            },
            "replay": {
                "backend_version": backend_version,
                "backend_hash": backend_hash,
                "intervention_manifest_hash": intervention_hash,
                "trajectory_hash": "sha256:" + "0" * 64,
                "replay_seed": self._replay_seed,
            },
        }
        trajectory["replay"]["trajectory_hash"] = trajectory_content_hash(trajectory)
        registry = getattr(self.backend, "registry", None)
        report = validate_trajectory(trajectory, registry)
        if not report.ok:
            first = report.issues[0]
            raise RuntimeError(
                f"Agent trajectory invalid: {first.code} at {first.pointer}: {first.message}"
            )
        return trajectory


class BlindAgentSession:
    """Capability wrapper that exposes no evaluator family/state metadata."""

    __slots__ = ("_session", "start")

    def __init__(self, session: EpisodeSession) -> None:
        self._session = session
        self.start = deepcopy(session.start)

    @property
    def observations(self) -> Sequence[Mapping[str, Any]]:
        return self._session.observations

    @property
    def responses(self) -> Sequence[Mapping[str, Any]]:
        return self._session.responses

    def can_call(self, tool: str) -> bool:
        return self._session.can_call(tool)

    def call(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        belief_state: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        return self._session.call(tool, arguments, belief_state)

    def finish(
        self,
        final_answer: Mapping[str, Any],
        belief_state: Mapping[str, Any],
    ) -> None:
        self._session.finish(final_answer, belief_state)


def run_agent_episode(
    agent: DeterministicAgent,
    backend: ToolBackend,
    family: Mapping[str, Any],
    state_role: str,
) -> dict[str, Any]:
    session = EpisodeSession(backend, family, state_role, agent.name)
    agent.run(BlindAgentSession(session))
    return session.trajectory()


def run_experiment(
    families: Sequence[Mapping[str, Any]],
    agents: Sequence[DeterministicAgent],
    backend_factory: BackendFactory,
    *,
    output_dir: str | Path | None = None,
    bootstrap_samples: int = 1000,
    bootstrap_seed: int = 20260905,
) -> dict[str, Any]:
    """Run all matched triplets and optionally write JSON/CSV/Markdown reports."""

    trajectories: list[dict[str, Any]] = []
    episode_rows: list[dict[str, Any]] = []
    for agent in agents:
        for family in sorted(families, key=lambda item: item["family_id"]):
            for state_role in ("CLEAN", "BLOCKED", "RESTORED"):
                backend = backend_factory(family, state_role)
                trajectory = run_agent_episode(agent, backend, family, state_role)
                trajectories.append(
                    {
                        "agent": agent.name,
                        "family_id": family["family_id"],
                        "state_role": state_role,
                        "trajectory": trajectory,
                    }
                )
                episode_rows.append(
                    score_episode(agent.name, family, state_role, trajectory)
                )
    aggregates = aggregate_metrics(
        episode_rows,
        bootstrap_samples=bootstrap_samples,
        seed=bootstrap_seed,
    )
    report = {
        "report_version": "1.0.0",
        "protocol_version": "0.2.0",
        "bootstrap": {
            "unit": "source_video",
            "samples": bootstrap_samples,
            "seed": bootstrap_seed,
            "family_averaging_precedes_video_resampling": True,
        },
        "agents": [agent.name for agent in agents],
        "episode_metrics": episode_rows,
        "aggregates": aggregates,
        "dashboard": dashboard_rows(episode_rows, aggregates),
        "trajectories": trajectories,
    }
    report["result_hash"] = sha256_json(report)
    if output_dir is not None:
        write_reports(report, output_dir)
    return report


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _format(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _markdown(report: Mapping[str, Any]) -> str:
    columns = [
        ("agent", "System"),
        ("track", "Track"),
        ("clean_grounded_success", "CLEAN G"),
        ("blocked_grounded_success", "BLOCKED G"),
        ("blocked_false_sufficient_rate", "BLOCKED FSR ↓"),
        ("sufficiency_brier", "Suff. Brier ↓"),
        ("blocked_access_failure_diagnosis", "Access diagnosis"),
        ("blocked_premature_stop", "Premature stop ↓"),
        ("restored_grounded_success", "RESTORED G"),
        ("paired_restoration_gain", "Answer restore gain"),
        ("state_target_success_difference", "State-target Δ*"),
        ("triggered_supported_recovery", "Triggered supported recovery"),
        ("median_tool_cost", "Median cost"),
        ("replay_completion", "Completion"),
    ]
    lines = [
        "# AV-TRACE MVP experiment report",
        "",
        "Descriptive construct-validation results; this is not a leaderboard.",
        "",
        "| " + " | ".join(label for _, label in columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    for row in report["dashboard"]:
        lines.append(
            "| " + " | ".join(_format(row.get(key)) for key, _ in columns) + " |"
        )
    lines.extend(
        [
            "",
            "Confidence intervals in `summary.csv` use deterministic source-video",
            "cluster bootstrap resampling after averaging families within video.",
            "",
            "\\* `State-target Δ` is RESTORED grounded success minus BLOCKED grounded",
            "success, reproduced for normative compatibility. Because the two states",
            "score different targets, it is not interpreted as answer-recovery gain.",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(report: Mapping[str, Any], output_dir: str | Path) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_csv(destination / "episode_metrics.csv", report["episode_metrics"])
    _write_csv(
        destination / "summary.csv",
        list(report["aggregates"]["state"]) + list(report["aggregates"]["paired"]),
    )
    _write_csv(destination / "dashboard.csv", report["dashboard"])
    (destination / "report.md").write_text(_markdown(report), encoding="utf-8")
