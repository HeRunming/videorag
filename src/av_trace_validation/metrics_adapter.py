"""Adapter from certified route artifacts to the existing MVP metric rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from av_trace_mvp.metrics import score_episode

from .graph import reachable_ses_ids
from .trajectory import evidence_ids_from_observations


@dataclass(frozen=True)
class PrematureStopResult:
    eligible: int
    premature_stop: int
    feasible_route_ids: tuple[str, ...]
    remaining_steps: int
    remaining_cost: float


def _observations(trajectory: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        result
        for event in trajectory["events"]
        for result in event.get("response", {}).get("results", ())
        if result.get("result_type") == "observation"
    ]


def _final_cost_before_finalize(trajectory: Mapping[str, Any]) -> float:
    values = [
        float(event["response"]["cost_used_total"])
        for event in trajectory["events"]
        if event.get("response") is not None
    ]
    return values[-1] if values else 0.0


def _route_templates(
    denominator: Mapping[str, Any],
    family_id: str,
    state_role: str,
) -> dict[str, Mapping[str, Any]]:
    """Return consensus route templates, preferring the earliest decision record."""

    candidates = [
        item
        for item in denominator.get("records", ())
        if item.get("family_id") == family_id
        and item.get("state_role") == state_role
        and item.get("decision_index") == 0
    ]
    routes: dict[str, Mapping[str, Any]] = {}
    for record in candidates:
        for route in record.get("route_alternatives", ()):
            # The denominator records both feasible templates and explicit
            # proofs that no route exists.  Only the former are executable
            # route templates.  Treating an infeasible, zero-step alternative
            # as a route would invert the certified BLOCKED denominator.
            if route.get("feasible") is not True:
                continue
            previous = routes.get(route["route_id"])
            if previous is not None and previous != route:
                raise ValueError(
                    f"Certified validators disagree on route {route['route_id']}."
                )
            routes[route["route_id"]] = route
    return routes


def evaluate_premature_stop(
    family: Mapping[str, Any],
    state_role: str,
    trajectory: Mapping[str, Any],
    denominator: Mapping[str, Any],
) -> PrematureStopResult:
    """Apply the normative stop rule using only pre-certified route templates."""

    if denominator.get("system_independent") is not True:
        raise ValueError("Premature-stop denominator is not system-independent.")
    routes = _route_templates(denominator, family["family_id"], state_role)
    has_certified_decision = any(
        item.get("family_id") == family["family_id"]
        and item.get("state_role") == state_role
        and item.get("decision_index") == 0
        for item in denominator.get("records", ())
    )
    if not has_certified_decision:
        raise ValueError(
            f"No certified decision record for {family['family_id']} {state_role}."
        )
    observations = _observations(trajectory)
    observed = evidence_ids_from_observations(family, observations)
    observed_sufficient = bool(
        reachable_ses_ids(family["claim_evidence_graph"], observed)
    )
    episode_start = trajectory["episode_start"]
    remaining_steps = (
        int(episode_start["budget"]["max_steps"]) - (len(trajectory["events"]) - 1)
    )
    remaining_cost = (
        float(episode_start["budget"]["cost_limit"])
        - _final_cost_before_finalize(trajectory)
    )
    feasible = []
    restoration_triggered = any(
        event.get("active_hook_ids") for event in trajectory["events"]
    )
    for route_id, route in sorted(routes.items()):
        steps = []
        for step in route["steps"]:
            if step["tool"] == "get_channel_status" and restoration_triggered:
                continue
            expected = set(step["expected_evidence_ids"])
            if expected and expected <= observed:
                continue
            steps.append(step)
        required_steps = len(steps)
        required_cost = sum(float(step["cost"]) for step in steps)
        if required_steps <= remaining_steps and required_cost <= remaining_cost + 1e-9:
            feasible.append(route_id)
    final = trajectory["final_output"]
    stop_mode = final["answer_mode"] == "answer" or (
        final["answer_mode"] in {"partial_answer", "abstain"}
        and final["diagnosis"]["recovery_route_declared"] is False
    )
    valid_budget_guard = (
        final["termination_reason"] == "budget_guard"
        and not feasible
    )
    eligible = int(not observed_sufficient and bool(feasible))
    premature = int(eligible and stop_mode and not valid_budget_guard)
    return PrematureStopResult(
        eligible=eligible,
        premature_stop=premature,
        feasible_route_ids=tuple(feasible),
        remaining_steps=remaining_steps,
        remaining_cost=round(remaining_cost, 6),
    )


def adapt_episode_metrics(
    agent_name: str,
    family: Mapping[str, Any],
    state_role: str,
    trajectory: Mapping[str, Any],
    denominator: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the existing metric row with certified premature-stop fields."""

    row = score_episode(agent_name, family, state_role, trajectory)
    result = evaluate_premature_stop(
        family, state_role, trajectory, denominator
    )
    row.update(
        {
            "premature_stop": result.premature_stop,
            "premature_stop_eligible": result.eligible,
            "certified_feasible_route_ids": list(result.feasible_route_ids),
            "final_remaining_steps": result.remaining_steps,
            "final_remaining_cost": result.remaining_cost,
            "premature_stop_denominator_source": denominator["artifact_id"],
        }
    )
    return row
