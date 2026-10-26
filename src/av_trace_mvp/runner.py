"""Scripted deterministic episode execution and schema-valid trajectory emission."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from av_trace.trajectory import validate_trajectory
from av_trace.util import trajectory_content_hash

from .backend import FixedBackend


class EpisodeRunError(ValueError):
    """Raised when a script cannot produce a valid terminal trajectory."""


def _recorded_at(step_index: int, replay_seed: int) -> str:
    origin = datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=replay_seed)
    return (origin + timedelta(seconds=step_index)).isoformat().replace("+00:00", "Z")


def run_scripted_episode(
    backend: FixedBackend,
    actions: Iterable[dict[str, Any]],
    *,
    trajectory_id: str | None = None,
) -> dict[str, Any]:
    """Execute full action envelopes and return a frozen-schema trajectory.

    Timestamps are logical replay timestamps rather than wall time. Inspect duration
    is preserved exactly in each ``inspect_clip`` observation payload and is also
    available as ``backend.inspected_duration_s`` after execution.
    """
    events: list[dict[str, Any]] = []
    final_output: dict[str, Any] | None = None
    replay_seed = backend.episode["replay"]["seed"]
    for supplied in actions:
        action = deepcopy(supplied)
        response = backend.execute(action)
        event = {
            "event_type": "finalize" if response is None else "tool_exchange",
            "action": action,
            "active_hook_ids": list(backend.last_active_hook_ids),
            "recorded_at": _recorded_at(action["step_index"], replay_seed),
        }
        if response is None:
            final_output = deepcopy(action["action"]["arguments"])
        else:
            event["response"] = response
        events.append(event)

    if final_output is None:
        raise EpisodeRunError("A scripted episode must end with exactly one finalize action.")
    episode_id = backend.episode["episode_id"]
    trajectory = {
        "schema_version": "0.2.0",
        "trajectory_id": trajectory_id or f"traj.{episode_id}",
        "track": backend.episode["backend"]["track"],
        "episode_start": backend.episode_start(reveal_state_role=True),
        "events": events,
        "final_output": final_output,
        "completion": {
            "status": "forced_finalization" if any(
                event.get("response", {}).get("status") == "budget_exhausted" for event in events
            ) else "completed",
            "total_steps": len(events),
            "total_cost": backend.cost_used,
            "protocol_valid": True,
        },
        "replay": {
            "backend_version": backend.backend_version,
            "backend_hash": backend.backend_hash,
            "intervention_manifest_hash": backend.intervention_manifest_hash,
            "trajectory_hash": "sha256:" + "0" * 64,
            "replay_seed": replay_seed,
        },
    }
    trajectory["replay"]["trajectory_hash"] = trajectory_content_hash(trajectory)
    report = validate_trajectory(trajectory, backend.registry)
    if not report.ok:
        first = report.issues[0]
        raise EpisodeRunError(f"Generated trajectory is invalid: {first.code} at {first.pointer}: {first.message}")
    return trajectory


run_episode = run_scripted_episode
