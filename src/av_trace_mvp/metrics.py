"""Core AV-TRACE MVP metrics, aggregation, and deterministic uncertainty."""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from typing import Any, Mapping, Sequence

from av_trace.util import sha256_json

from .agents import CAUSES, MODALITIES


def evidence_ids_from_observations(
    family: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
) -> set[str]:
    """Evaluator-only mapping from observations to registered evidence units."""

    matched: set[str] = set()
    for observation in observations:
        route_refs = set(observation.get("payload", {}).get("_route_refs", ()))
        if route_refs:
            matched.update(
                evidence["evidence_id"]
                for evidence in family["claim_evidence_graph"]["evidence_units"]
                if sha256_json({"evidence_id": evidence["evidence_id"]}) in route_refs
            )
            continue
        observed_interval = observation.get("interval", {})
        observed_modalities = set(observation.get("modalities", ()))
        for evidence in family["claim_evidence_graph"]["evidence_units"]:
            if evidence["modality"] not in observed_modalities:
                continue
            if any(
                observed_interval.get("start_s", float("inf")) <= interval["start_s"]
                and observed_interval.get("end_s", float("-inf")) >= interval["end_s"]
                for interval in evidence["intervals"]
            ):
                matched.add(evidence["evidence_id"])
    return matched


def _episode(family: Mapping[str, Any], state_role: str) -> Mapping[str, Any]:
    return next(item for item in family["episodes"] if item["state_role"] == state_role)


def _observations(trajectory: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        result
        for event in trajectory["events"]
        for result in event.get("response", {}).get("results", ())
        if result.get("result_type") == "observation"
    ]


def _observation_index(trajectory: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {item["observation_id"]: item for item in _observations(trajectory)}


def _observation_evidence_map(
    family: Mapping[str, Any],
    trajectory: Mapping[str, Any],
) -> dict[str, set[str]]:
    return {
        observation["observation_id"]: evidence_ids_from_observations(family, [observation])
        for observation in _observations(trajectory)
    }


def _accepted_sets(family: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    return family["claim_evidence_graph"]["accepted_sufficient_sets"]


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _claim_text_matches(
    family: Mapping[str, Any],
    claim_id: str | None,
    text: str,
) -> bool:
    if claim_id is None:
        return False
    for claim in family["claim_evidence_graph"]["claims"]:
        if claim["claim_id"] != claim_id:
            continue
        accepted = [claim["proposition"], *claim.get("accepted_aliases", ())]
        return _normalized_text(text) in {_normalized_text(item) for item in accepted}
    return False


def _is_sufficient(family: Mapping[str, Any], evidence_ids: set[str]) -> bool:
    return any(set(item["evidence_ids"]) <= evidence_ids for item in _accepted_sets(family))


def _final_observed_sufficient(
    family: Mapping[str, Any],
    trajectory: Mapping[str, Any],
) -> bool:
    return _is_sufficient(
        family,
        evidence_ids_from_observations(family, _observations(trajectory)),
    )


def _claim_support(
    family: Mapping[str, Any],
    trajectory: Mapping[str, Any],
) -> list[bool]:
    evidence_by_observation = _observation_evidence_map(family, trajectory)
    valid_observations = _observation_index(trajectory)
    support: list[bool] = []
    for claim in trajectory["final_output"]["claims"]:
        claim_id = claim.get("registered_claim_id")
        cited_evidence: set[str] = set()
        citations_valid = True
        for citation in claim["citations"]:
            observation = valid_observations.get(citation["observation_id"])
            if observation is None:
                citations_valid = False
                continue
            if not set(citation["modalities"]) <= set(observation["modalities"]):
                citations_valid = False
            interval = citation["interval"]
            observed_interval = observation["interval"]
            if (
                interval["start_s"] < observed_interval["start_s"]
                or interval["end_s"] > observed_interval["end_s"]
            ):
                citations_valid = False
            cited_evidence.update(evidence_by_observation[citation["observation_id"]])
        supported = (
            citations_valid
            and _claim_text_matches(family, claim_id, claim.get("text", ""))
            and any(
            claim_id in sufficient_set["claim_ids"]
            and set(sufficient_set["evidence_ids"]) <= cited_evidence
            for sufficient_set in _accepted_sets(family)
            )
        )
        support.append(supported)
    return support


def grounded_task_success(
    family: Mapping[str, Any],
    state_role: str,
    trajectory: Mapping[str, Any],
) -> int:
    """Score the state-specific grounded success contract."""

    completion = trajectory["completion"]
    if not completion.get("protocol_valid") or completion.get("status") not in {
        "completed",
        "forced_finalization",
    }:
        return 0
    final = trajectory["final_output"]
    asserted = [claim.get("registered_claim_id") for claim in final["claims"]]
    required = set(family["answer_spec"]["required_claim_ids"])
    forbidden = set(family["answer_spec"]["forbidden_claim_ids"])
    graph_claims = {
        item["claim_id"]: item for item in family["claim_evidence_graph"]["claims"]
    }
    contradictory = {
        contradiction
        for claim_id in required
        for contradiction in graph_claims.get(claim_id, {}).get(
            "contradiction_claim_ids", ()
        )
    }
    support = _claim_support(family, trajectory)
    no_forbidden = not (forbidden | contradictory).intersection(
        item for item in asserted if item
    )
    all_asserted_supported = all(support)

    if state_role in {"CLEAN", "RESTORED"}:
        return int(
            final["verdict"] == "sufficient"
            and required <= set(item for item in asserted if item)
            and no_forbidden
            and all_asserted_supported
        )

    acceptable_stop = final["verdict"] == "insufficient" or (
        final["verdict"] == "uncertain" and final["p_sufficient"] < 0.5
    )
    cause = final["diagnosis"]["cause_probabilities"]
    diagnosed_access = max(cause, key=lambda key: (cause[key], key)) == (
        "evidence_in_source_but_inaccessible"
    )
    return int(
        acceptable_stop
        and no_forbidden
        and all_asserted_supported
        and diagnosed_access
    )


def supported_answer_success(
    family: Mapping[str, Any],
    trajectory: Mapping[str, Any],
) -> int:
    """Score the supported-answer endpoint identically in every state."""

    completion = trajectory["completion"]
    if not completion.get("protocol_valid") or completion.get("status") not in {
        "completed",
        "forced_finalization",
    }:
        return 0
    final = trajectory["final_output"]
    asserted = {
        claim.get("registered_claim_id")
        for claim in final["claims"]
        if claim.get("registered_claim_id")
    }
    required = set(family["answer_spec"]["required_claim_ids"])
    forbidden = set(family["answer_spec"]["forbidden_claim_ids"])
    graph_claims = {
        item["claim_id"]: item for item in family["claim_evidence_graph"]["claims"]
    }
    contradictory = {
        contradiction
        for claim_id in required
        for contradiction in graph_claims.get(claim_id, {}).get(
            "contradiction_claim_ids", ()
        )
    }
    return int(
        final["verdict"] == "sufficient"
        and required <= asserted
        and not (forbidden | contradictory).intersection(asserted)
        and all(_claim_support(family, trajectory))
    )


def _belief_labels(
    family: Mapping[str, Any],
    trajectory: Mapping[str, Any],
) -> list[tuple[float, int]]:
    observed: list[Mapping[str, Any]] = []
    scored: list[tuple[float, int]] = []
    for event in trajectory["events"]:
        evidence_ids = evidence_ids_from_observations(family, observed)
        y = int(_is_sufficient(family, evidence_ids))
        scored.append((event["action"]["belief_state"]["p_sufficient"], y))
        observed.extend(
            result
            for result in event.get("response", {}).get("results", ())
            if result.get("result_type") == "observation"
        )
    return scored


def sufficiency_brier(
    family: Mapping[str, Any],
    trajectory: Mapping[str, Any],
) -> float:
    values = _belief_labels(family, trajectory)
    return sum((probability - label) ** 2 for probability, label in values) / len(values)


def _f1(predicted: set[str], gold: set[str]) -> float:
    if not predicted and not gold:
        return 1.0
    if not predicted or not gold:
        return 0.0
    true_positive = len(predicted & gold)
    return 2 * true_positive / (len(predicted) + len(gold))


def _gold_modalities(
    family: Mapping[str, Any],
    state_role: str,
    *,
    restored_terminal: bool = True,
) -> list[set[str]]:
    if state_role == "CLEAN" or (state_role == "RESTORED" and restored_terminal):
        return [set()]
    sets = _episode(family, state_role)["oracle"]["gold_missing_modality_sets"]
    return [set(item) for item in sets] or [set()]


def _observed_missing_modality_sets(
    family: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
) -> list[set[str]]:
    observed = evidence_ids_from_observations(family, observations)
    modality_by_evidence = {
        item["evidence_id"]: item["modality"]
        for item in family["claim_evidence_graph"]["evidence_units"]
    }
    missing_sets = [
        {
            modality_by_evidence[evidence_id]
            for evidence_id in set(sufficient_set["evidence_ids"]) - observed
        }
        for sufficient_set in _accepted_sets(family)
    ]
    unique = {
        tuple(sorted(item))
        for item in missing_sets
    }
    return [set(item) for item in sorted(unique, key=lambda item: (len(item), item))]


def _modality_scores(
    family: Mapping[str, Any],
    state_role: str,
    trajectory: Mapping[str, Any],
) -> tuple[float, float]:
    probabilities = trajectory["final_output"]["diagnosis"]["modality_probabilities"]
    predicted = {key for key, value in probabilities.items() if value >= 0.5}
    gold_sets = _observed_missing_modality_sets(family, _observations(trajectory))
    f1 = max(_f1(predicted, gold) for gold in gold_sets)
    brier = min(
        sum((probabilities[modality] - int(modality in gold)) ** 2 for modality in MODALITIES)
        / len(MODALITIES)
        for gold in gold_sets
    )
    return f1, brier


def _gold_hops(
    family: Mapping[str, Any],
    state_role: str,
    *,
    restored_terminal: bool = True,
) -> set[str]:
    if state_role == "CLEAN" or (state_role == "RESTORED" and restored_terminal):
        return set()
    return set(_episode(family, state_role)["oracle"]["gold_missing_hop_types"])


def _gold_cause(state_role: str) -> str:
    return (
        "evidence_in_source_but_inaccessible"
        if state_role == "BLOCKED"
        else "not_missing"
    )


def _stepwise_gold_cause(
    state_role: str,
    sufficient: bool,
) -> str:
    if sufficient:
        return "not_missing"
    if state_role in {"BLOCKED", "RESTORED"}:
        return "evidence_in_source_but_inaccessible"
    return "evidence_accessible_but_not_found"


def _cause_scores(
    family: Mapping[str, Any],
    state_role: str,
    trajectory: Mapping[str, Any],
) -> tuple[int, float]:
    probabilities = trajectory["final_output"]["diagnosis"]["cause_probabilities"]
    if _final_observed_sufficient(family, trajectory):
        gold = "not_missing"
    elif state_role == "RESTORED" and _restoration_triggered(trajectory):
        gold = "evidence_accessible_but_not_found"
    elif state_role in {"BLOCKED", "RESTORED"}:
        gold = "evidence_in_source_but_inaccessible"
    else:
        gold = "evidence_accessible_but_not_found"
    prediction = max(probabilities, key=lambda key: (probabilities[key], key))
    brier = sum((probabilities[cause] - int(cause == gold)) ** 2 for cause in CAUSES) / len(CAUSES)
    return int(prediction == gold), brier


def _stepwise_cause_scores(
    family: Mapping[str, Any],
    state_role: str,
    trajectory: Mapping[str, Any],
) -> tuple[float, float]:
    accuracies: list[float] = []
    briers: list[float] = []
    beliefs = _belief_labels(family, trajectory)
    restored = state_role != "RESTORED"
    for event, (_probability, sufficient) in zip(trajectory["events"], beliefs):
        if sufficient:
            gold = "not_missing"
        elif state_role == "RESTORED" and restored:
            gold = "evidence_accessible_but_not_found"
        else:
            gold = _stepwise_gold_cause(state_role, False)
        probabilities = event["action"]["belief_state"][
            "missingness_cause_probabilities"
        ]
        prediction = max(probabilities, key=lambda key: (probabilities[key], key))
        accuracies.append(float(prediction == gold))
        briers.append(
            sum(
                (probabilities[cause] - int(cause == gold)) ** 2
                for cause in CAUSES
            )
            / len(CAUSES)
        )
        if event.get("active_hook_ids"):
            restored = True
    return _mean(accuracies), _mean(briers)


def _stepwise_modality_brier(
    family: Mapping[str, Any],
    state_role: str,
    trajectory: Mapping[str, Any],
) -> float:
    losses = []
    beliefs = _belief_labels(family, trajectory)
    observed: list[Mapping[str, Any]] = []
    for event, (_probability, _sufficient) in zip(trajectory["events"], beliefs):
        gold_sets = _observed_missing_modality_sets(family, observed)
        probabilities = event["action"]["belief_state"][
            "missing_modality_probabilities"
        ]
        losses.append(
            min(
                sum(
                    (probabilities[modality] - int(modality in gold)) ** 2
                    for modality in MODALITIES
                )
                / len(MODALITIES)
                for gold in gold_sets
            )
        )
        observed.extend(
            result
            for result in event.get("response", {}).get("results", ())
            if result.get("result_type") == "observation"
        )
    return _mean(losses)


def _evidence_coverage(
    family: Mapping[str, Any],
    trajectory: Mapping[str, Any],
) -> float:
    observed = evidence_ids_from_observations(family, _observations(trajectory))
    return max(
        len(observed.intersection(item["evidence_ids"])) / len(item["evidence_ids"])
        for item in _accepted_sets(family)
    )


def _inspected_duration(trajectory: Mapping[str, Any]) -> float:
    return sum(
        event["action"]["action"]["arguments"]["interval"]["end_s"]
        - event["action"]["action"]["arguments"]["interval"]["start_s"]
        for event in trajectory["events"]
        if event["event_type"] == "tool_exchange"
        and event["action"]["action"]["tool"] == "inspect_clip"
    )


def _search_route_fraction(
    trajectory: Mapping[str, Any],
    *,
    start_index: int = 0,
) -> float:
    calls = [
        event["action"]["action"]["tool"]
        for event in trajectory["events"][start_index:]
        if event["event_type"] == "tool_exchange"
    ]
    if not calls:
        return 0.0
    route_tools = {
        "search_visual",
        "search_speech",
        "search_ambient_audio",
        "inspect_clip",
        "read_transcript",
    }
    return sum(tool in route_tools for tool in calls) / len(calls)


def _restoration_triggered(trajectory: Mapping[str, Any]) -> bool:
    return any(event.get("active_hook_ids") for event in trajectory["events"])


def _premature_stop(
    family: Mapping[str, Any],
    state_role: str,
    trajectory: Mapping[str, Any],
) -> tuple[int, int]:
    # The denominator requires a validator-demonstrated feasible route at the
    # final decision point. The synthetic artifacts do not link validator
    # trajectories, so eligibility cannot be established from agent behavior.
    return 0, 0


def _recovery_details(
    family: Mapping[str, Any],
    state_role: str,
    trajectory: Mapping[str, Any],
) -> dict[str, Any]:
    if state_role != "RESTORED":
        return {
            "restoration_triggered": None,
            "triggered_supported_recovery": None,
            "actions_trigger_to_first_ses": None,
            "cost_trigger_to_first_ses": None,
            "actions_trigger_to_supported_finalize": None,
            "cost_trigger_to_supported_finalize": None,
            "recovery_inspected_duration_s": None,
            "post_trigger_search_route_fraction": None,
        }
    trigger_index: int | None = None
    trigger_cost = 0.0
    for index, event in enumerate(trajectory["events"]):
        if event.get("active_hook_ids"):
            trigger_index = index
            trigger_cost = event.get("response", {}).get("cost_used_total", 0.0)
            break
    grounded = grounded_task_success(family, state_role, trajectory)
    if trigger_index is None:
        return {
            "restoration_triggered": 0,
            "triggered_supported_recovery": 0,
            "actions_trigger_to_first_ses": None,
            "cost_trigger_to_first_ses": None,
            "actions_trigger_to_supported_finalize": None,
            "cost_trigger_to_supported_finalize": None,
            "recovery_inspected_duration_s": None,
            "post_trigger_search_route_fraction": None,
        }
    post_events = trajectory["events"][trigger_index + 1 :]
    observed = [
        result
        for event in trajectory["events"][: trigger_index + 1]
        for result in event.get("response", {}).get("results", ())
        if result.get("result_type") == "observation"
    ]
    actions_to_first_ses: int | None = None
    cost_to_first_ses: float | None = None
    for offset, event in enumerate(post_events, start=1):
        observed.extend(
            result
            for result in event.get("response", {}).get("results", ())
            if result.get("result_type") == "observation"
        )
        if actions_to_first_ses is None and _is_sufficient(
            family,
            evidence_ids_from_observations(family, observed),
        ):
            actions_to_first_ses = offset
            cost_to_first_ses = (
                event.get("response", {}).get(
                    "cost_used_total",
                    trajectory["completion"]["total_cost"],
                )
                - trigger_cost
            )
    inspected = sum(
        event["action"]["action"]["arguments"]["interval"]["end_s"]
        - event["action"]["action"]["arguments"]["interval"]["start_s"]
        for event in post_events
        if event["event_type"] == "tool_exchange"
        and event["action"]["action"]["tool"] == "inspect_clip"
    )
    return {
        "restoration_triggered": 1,
        "triggered_supported_recovery": grounded,
        "actions_trigger_to_first_ses": actions_to_first_ses,
        "cost_trigger_to_first_ses": cost_to_first_ses,
        "actions_trigger_to_supported_finalize": (
            len(post_events) if grounded else None
        ),
        "cost_trigger_to_supported_finalize": (
            trajectory["completion"]["total_cost"] - trigger_cost
            if grounded
            else None
        ),
        "recovery_inspected_duration_s": inspected,
        "post_trigger_search_route_fraction": _search_route_fraction(
            trajectory,
            start_index=trigger_index + 1,
        ),
    }


def score_episode(
    agent_name: str,
    family: Mapping[str, Any],
    state_role: str,
    trajectory: Mapping[str, Any],
) -> dict[str, Any]:
    """Return one flat, report-friendly metrics row."""

    beliefs = _belief_labels(family, trajectory)
    final_p, final_label = beliefs[-1]
    final = trajectory["final_output"]
    modality_f1, modality_brier = _modality_scores(family, state_role, trajectory)
    cause_accuracy, cause_brier = _cause_scores(family, state_role, trajectory)
    stepwise_cause_accuracy, stepwise_cause_brier = _stepwise_cause_scores(
        family, state_role, trajectory
    )
    support = _claim_support(family, trajectory)
    false_sufficient = int(
        state_role == "BLOCKED"
        and final_label == 0
        and (final["verdict"] == "sufficient" or final["p_sufficient"] >= 0.5)
    )
    premature, premature_eligible = _premature_stop(family, state_role, trajectory)
    row = {
        "agent": agent_name,
        "family_id": family["family_id"],
        "video_id": family["source"]["asset_id"],
        "track": _episode(family, state_role)["backend"]["track"],
        "state_role": state_role,
        "intervention_mechanism": family["intervention_mechanism"],
        "modality_stratum": (
            "cross_modal"
            if len(
                {
                    item["modality"]
                    for item in family["claim_evidence_graph"]["evidence_units"]
                }
            )
            > 1
            else family["claim_evidence_graph"]["evidence_units"][0]["modality"]
        ),
        "grounded_task_success": grounded_task_success(family, state_role, trajectory),
        "supported_answer_success": supported_answer_success(family, trajectory),
        "sufficiency_brier": sufficiency_brier(family, trajectory),
        "final_sufficiency_brier": (final_p - final_label) ** 2,
        "false_sufficient": false_sufficient,
        "high_confidence_false_sufficient": int(
            state_role == "BLOCKED" and final_label == 0 and final["p_sufficient"] >= 0.8
        ),
        "premature_stop": premature,
        "premature_stop_eligible": premature_eligible,
        "modality_f1": modality_f1,
        "modality_brier": modality_brier,
        "stepwise_modality_brier": _stepwise_modality_brier(
            family, state_role, trajectory
        ),
        "hop_f1": _f1(
            set(final["diagnosis"]["hop_types"]),
            _gold_hops(
                family,
                state_role,
                restored_terminal=_final_observed_sufficient(family, trajectory),
            ),
        ),
        "cause_accuracy": cause_accuracy,
        "cause_brier": cause_brier,
        "stepwise_cause_accuracy": stepwise_cause_accuracy,
        "stepwise_cause_brier": stepwise_cause_brier,
        "evidence_coverage": _evidence_coverage(family, trajectory),
        "supported_claim_rate": (
            sum(support) / len(support) if support else None
        ),
        "tool_cost": trajectory["completion"]["total_cost"],
        "tool_calls": sum(
            event["event_type"] == "tool_exchange" for event in trajectory["events"]
        ),
        "inspected_duration_s": _inspected_duration(trajectory),
        "completion": int(
            trajectory["completion"]["status"] in {"completed", "forced_finalization"}
        ),
        "protocol_valid": int(trajectory["completion"]["protocol_valid"]),
        "final_p_sufficient": final["p_sufficient"],
        "access_failure_probability": final["diagnosis"]["cause_probabilities"][
            "evidence_in_source_but_inaccessible"
        ],
        "search_route_fraction": _search_route_fraction(trajectory),
        "observed_sufficient": final_label,
    }
    row.update(_recovery_details(family, state_role, trajectory))
    return row


def paired_restoration_rows(
    episode_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in episode_rows:
        grouped[(row["agent"], row["track"], row["family_id"])][row["state_role"]] = row
    paired: list[dict[str, Any]] = []
    for (agent, track, family_id), states in sorted(grouped.items()):
        if "BLOCKED" not in states or "RESTORED" not in states:
            continue
        blocked, restored = states["BLOCKED"], states["RESTORED"]
        paired.append(
            {
                "agent": agent,
                "track": track,
                "family_id": family_id,
                "video_id": blocked["video_id"],
                # Retained only as a transparent reproduction of normative
                # D-012. BLOCKED and RESTORED use different success targets, so
                # this difference is not interpreted as an answer-recovery
                # effect in MVP reports.
                "state_target_success_difference": (
                    restored["grounded_task_success"] - blocked["grounded_task_success"]
                ),
                "paired_restoration_gain": (
                    restored["supported_answer_success"]
                    - blocked["supported_answer_success"]
                ),
                "restoration_response": int(
                    restored["restoration_triggered"] == 1
                    and restored["grounded_task_success"] == 1
                ),
                "restoration_p_sufficient_change": (
                    restored["final_p_sufficient"] - blocked["final_p_sufficient"]
                ),
                "restoration_access_failure_change": (
                    restored["access_failure_probability"]
                    - blocked["access_failure_probability"]
                ),
                "restoration_search_allocation_change": (
                    None
                    if restored["post_trigger_search_route_fraction"] is None
                    else restored["post_trigger_search_route_fraction"]
                    - blocked["search_route_fraction"]
                ),
                "triggered_supported_recovery": restored[
                    "triggered_supported_recovery"
                ],
            }
        )
    return paired


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def video_cluster_bootstrap(
    rows: Sequence[Mapping[str, Any]],
    metric: str,
    *,
    samples: int = 1000,
    seed: int = 20260905,
) -> dict[str, Any]:
    """Average families within videos, then bootstrap source-video clusters."""

    by_family: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        value = row.get(metric)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            by_family[(str(row["video_id"]), str(row["family_id"]))].append(float(value))
    family_means = {
        key: _mean(values)
        for key, values in by_family.items()
        if values
    }
    by_video: dict[str, list[float]] = defaultdict(list)
    for (video_id, _family_id), value in family_means.items():
        by_video[video_id].append(value)
    video_means = {
        video: _mean(values)
        for video, values in by_video.items()
        if values
    }
    if not video_means:
        return {
            "estimate": None,
            "ci_low": None,
            "ci_high": None,
            "n_families": 0,
            "n_videos": 0,
        }
    values = [video_means[key] for key in sorted(video_means)]
    estimate = _mean(values)
    if len(values) == 1 or samples <= 0:
        low = high = estimate
    else:
        rng = random.Random(seed)
        draws = sorted(
            _mean([values[rng.randrange(len(values))] for _ in values])
            for _ in range(samples)
        )
        low = draws[int(0.025 * (len(draws) - 1))]
        high = draws[int(0.975 * (len(draws) - 1))]
    return {
        "estimate": estimate,
        "ci_low": low,
        "ci_high": high,
        "n_families": len(family_means),
        "n_videos": len(values),
    }


EPISODE_METRICS = (
    "grounded_task_success",
    "supported_answer_success",
    "sufficiency_brier",
    "final_sufficiency_brier",
    "false_sufficient",
    "high_confidence_false_sufficient",
    "premature_stop",
    "modality_f1",
    "modality_brier",
    "stepwise_modality_brier",
    "hop_f1",
    "cause_accuracy",
    "cause_brier",
    "stepwise_cause_accuracy",
    "stepwise_cause_brier",
    "evidence_coverage",
    "supported_claim_rate",
    "tool_cost",
    "tool_calls",
    "inspected_duration_s",
    "completion",
    "protocol_valid",
    "final_p_sufficient",
    "access_failure_probability",
    "search_route_fraction",
    "post_trigger_search_route_fraction",
)

PAIRED_METRICS = (
    "paired_restoration_gain",
    "state_target_success_difference",
    "restoration_response",
    "restoration_p_sufficient_change",
    "restoration_access_failure_change",
    "restoration_search_allocation_change",
    "triggered_supported_recovery",
)


def aggregate_metrics(
    episode_rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap_samples: int = 1000,
    seed: int = 20260905,
) -> dict[str, Any]:
    """Produce state-specific and paired video-cluster summaries."""

    state_summaries: list[dict[str, Any]] = []
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in episode_rows:
        groups[(row["agent"], row["track"], row["state_role"])].append(row)
    for (agent, track, state), rows in sorted(groups.items()):
        for metric in EPISODE_METRICS:
            metric_rows = rows
            if metric == "premature_stop":
                metric_rows = [
                    row for row in rows if row.get("premature_stop_eligible") == 1
                ]
            summary = video_cluster_bootstrap(
                metric_rows,
                metric,
                samples=bootstrap_samples,
                seed=seed,
            )
            state_summaries.append(
                {
                    "agent": agent,
                    "track": track,
                    "scope": "state",
                    "state_role": state,
                    "metric": metric,
                    **summary,
                }
            )

    paired_rows = paired_restoration_rows(episode_rows)
    paired_summaries: list[dict[str, Any]] = []
    paired_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in paired_rows:
        paired_groups[(row["agent"], row["track"])].append(row)
    for (agent, track), rows in sorted(paired_groups.items()):
        for metric in PAIRED_METRICS:
            paired_summaries.append(
                {
                    "agent": agent,
                    "track": track,
                    "scope": "paired",
                    "state_role": "BLOCKED_TO_RESTORED",
                    "metric": metric,
                    **video_cluster_bootstrap(
                        rows,
                        metric,
                        samples=bootstrap_samples,
                        seed=seed,
                    ),
                }
            )
    return {
        "state": state_summaries,
        "paired": paired_summaries,
        "paired_family_rows": paired_rows,
    }


def dashboard_rows(
    episode_rows: Sequence[Mapping[str, Any]],
    aggregates: Mapping[str, Any],
) -> list[dict[str, Any]]:
    lookup = {
        (row["agent"], row["track"], row["state_role"], row["metric"]): row["estimate"]
        for row in aggregates["state"]
    }
    paired = {
        (row["agent"], row["track"], row["metric"]): row["estimate"]
        for row in aggregates["paired"]
    }
    agents_tracks = sorted({(row["agent"], row["track"]) for row in episode_rows})
    dashboard = []
    for agent, track in agents_tracks:
        costs = [
            float(row["tool_cost"])
            for row in episode_rows
            if row["agent"] == agent and row["track"] == track
        ]
        dashboard.append(
            {
                "agent": agent,
                "track": track,
                "clean_grounded_success": lookup.get(
                    (agent, track, "CLEAN", "grounded_task_success")
                ),
                "blocked_grounded_success": lookup.get(
                    (agent, track, "BLOCKED", "grounded_task_success")
                ),
                "blocked_false_sufficient_rate": lookup.get(
                    (agent, track, "BLOCKED", "false_sufficient")
                ),
                "sufficiency_brier": _mean(
                    [
                        lookup[(agent, track, state, "sufficiency_brier")]
                        for state in ("CLEAN", "BLOCKED", "RESTORED")
                        if (agent, track, state, "sufficiency_brier") in lookup
                    ]
                ),
                "blocked_access_failure_diagnosis": lookup.get(
                    (agent, track, "BLOCKED", "cause_accuracy")
                ),
                "blocked_premature_stop": lookup.get(
                    (agent, track, "BLOCKED", "premature_stop")
                ),
                "restored_grounded_success": lookup.get(
                    (agent, track, "RESTORED", "grounded_task_success")
                ),
                "state_target_success_difference": paired.get(
                    (agent, track, "state_target_success_difference")
                ),
                "paired_restoration_gain": paired.get(
                    (agent, track, "paired_restoration_gain")
                ),
                "triggered_supported_recovery": paired.get(
                    (agent, track, "triggered_supported_recovery")
                ),
                "median_tool_cost": statistics.median(costs) if costs else None,
                "replay_completion": _mean(
                    [
                        float(row["completion"])
                        for row in episode_rows
                        if row["agent"] == agent and row["track"] == track
                    ]
                ),
            }
        )
    return dashboard
