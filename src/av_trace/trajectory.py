"""Action, response, and complete trajectory semantic validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .errors import ValidationIssue, ValidationReport, make_report
from .schemas import SchemaRegistry
from .util import is_finite_number, response_content_hash, safe_sha256_json, sha256_json, trajectory_content_hash

TOLERANCE = 1e-6


def _cause_sum_issue(obj: dict[str, Any], pointer: str) -> ValidationIssue | None:
    total = sum(obj.values())
    if not is_finite_number(total) or abs(total - 1.0) > TOLERANCE:
        return ValidationIssue("TRJ-006", pointer, f"Cause probabilities must sum to 1 within 1e-6; found {total:.12g}.")
    return None


def validate_action(action: dict[str, Any], registry: SchemaRegistry | None = None) -> ValidationReport:
    registry = registry or SchemaRegistry()
    issues = list(registry.validate("agent-action", action).issues)
    if not issues:
        issue = _cause_sum_issue(action["belief_state"]["missingness_cause_probabilities"], "/belief_state/missingness_cause_probabilities")
        if issue:
            issues.append(issue)
        final = action["action"]
        arguments = final["arguments"]
        interval = arguments.get("time_range") or arguments.get("interval")
        if isinstance(interval, dict):
            start = interval["start_s"]
            end = interval["end_s"]
            if not is_finite_number(start) or not is_finite_number(end) or end <= start:
                issues.append(ValidationIssue("TIME-001", "/action/arguments", "Requested interval values must be finite and end_s must be greater than start_s."))
        if final["tool"] == "finalize":
            args = final["arguments"]
            belief = action["belief_state"]
            if args["p_sufficient"] != belief["p_sufficient"]:
                issues.append(ValidationIssue("TRJ-007", "/action/arguments/p_sufficient", "Finalize p_sufficient must equal the envelope belief state."))
            if args["verdict"] != belief["verdict"]:
                issues.append(ValidationIssue("TRJ-007", "/action/arguments/verdict", "Finalize verdict must equal the envelope belief state."))
            if args["diagnosis"]["modality_probabilities"] != belief["missing_modality_probabilities"]:
                issues.append(ValidationIssue("TRJ-007", "/action/arguments/diagnosis/modality_probabilities", "Finalize modality probabilities must equal the envelope belief state."))
            if args["diagnosis"]["hop_types"] != belief["missing_hop_types"]:
                issues.append(ValidationIssue("TRJ-007", "/action/arguments/diagnosis/hop_types", "Finalize hop types must equal the envelope belief state."))
            if args["diagnosis"]["cause_probabilities"] != belief["missingness_cause_probabilities"]:
                issues.append(ValidationIssue("TRJ-007", "/action/arguments/diagnosis/cause_probabilities", "Finalize cause probabilities must equal the envelope belief state."))
    return make_report(issues, object="agent-action")


def validate_response(response: dict[str, Any], registry: SchemaRegistry | None = None) -> ValidationReport:
    registry = registry or SchemaRegistry()
    issues = list(registry.validate("tool-response", response).issues)
    if not issues:
        successful = response["status"] in {"ok", "partial"}
        if successful and not response["results"]:
            issues.append(ValidationIssue("TRJ-001", "/results", "Successful responses must contain at least one result."))
        if not successful and response["results"]:
            issues.append(ValidationIssue("TRJ-001", "/results", "Failed responses may not contain results."))
        for index, result in enumerate(response["results"]):
            interval = result.get("interval")
            if interval and interval["end_s"] <= interval["start_s"]:
                issues.append(ValidationIssue("TIME-001", f"/results/{index}/interval", "Result interval end_s must be greater than start_s."))
            if result["result_type"] == "observation" and result["payload_hash"] != sha256_json(result["payload"]):
                issues.append(ValidationIssue("TRJ-003", f"/results/{index}/payload_hash", "Observation payload_hash does not match the canonical payload."))
        if response["response_hash"] != response_content_hash(response):
            issues.append(ValidationIssue("TRJ-003", "/response_hash", "response_hash does not match the canonical response content."))
    return make_report(issues, object="tool-response")


def validate_trajectory(trajectory: dict[str, Any], registry: SchemaRegistry | None = None) -> ValidationReport:
    registry = registry or SchemaRegistry()
    structural = registry.validate("trajectory", trajectory)
    issues = list(structural.issues)
    if not structural.ok:
        return make_report(issues, trajectory_hash=safe_sha256_json(trajectory))

    start = trajectory["episode_start"]
    episode_id = start["episode_id"]
    duration = start["video_duration_s"]
    budget = start["budget"]
    schedule = start["tool_costs"]
    request_ids: set[str] = set()
    observations: dict[str, dict[str, Any]] = {}
    previous_total = 0.0
    finalize_count = 0
    budget_exhausted_at: int | None = None
    previous_recorded_at: datetime | None = None

    missing_costs = set(start["available_tools"]) - set(schedule)
    if missing_costs:
        issues.append(ValidationIssue("TRJ-004", "/episode_start/tool_costs", f"Missing costs for available tools: {sorted(missing_costs)}."))
    if schedule.get("finalize") != 0:
        issues.append(ValidationIssue("TRJ-004", "/episode_start/tool_costs/finalize", "finalize must have zero cost."))

    for index, event in enumerate(trajectory["events"]):
        recorded_at = datetime.fromisoformat(event["recorded_at"].replace("Z", "+00:00"))
        if previous_recorded_at is not None and recorded_at < previous_recorded_at:
            issues.append(ValidationIssue("TRJ-002", f"/events/{index}/recorded_at", "Event timestamps must be nondecreasing in action order."))
        previous_recorded_at = recorded_at
        action = event["action"]
        issues.extend(validate_action(action, registry).issues)
        expected_step = index
        if action["step_index"] != expected_step:
            issues.append(ValidationIssue("TRJ-001", f"/events/{index}/action/step_index", f"Step index must be contiguous; expected {expected_step}."))
        if action["request_id"] in request_ids:
            issues.append(ValidationIssue("TRJ-001", f"/events/{index}/action/request_id", f"Duplicate request ID {action['request_id']}."))
        request_ids.add(action["request_id"])
        if action["episode_id"] != episode_id:
            issues.append(ValidationIssue("TRJ-001", f"/events/{index}/action/episode_id", "Action episode ID must match episode_start."))
        tool = action["action"]["tool"]
        if tool not in start["available_tools"]:
            issues.append(ValidationIssue("TRJ-001", f"/events/{index}/action/action/tool", f"Tool {tool} is not available in this episode."))
        arguments = action["action"]["arguments"]
        requested_interval = arguments.get("time_range") or arguments.get("interval")
        if isinstance(requested_interval, dict):
            if requested_interval["end_s"] <= requested_interval["start_s"]:
                issues.append(ValidationIssue("TIME-001", f"/events/{index}/action/action/arguments", "Requested interval end_s must be greater than start_s."))
            elif requested_interval["end_s"] > duration:
                issues.append(ValidationIssue("TIME-002", f"/events/{index}/action/action/arguments", "Requested interval must lie within source bounds."))

        if event["event_type"] == "tool_exchange":
            if budget_exhausted_at is not None:
                issues.append(ValidationIssue("TRJ-004", f"/events/{index}", "Only zero-cost finalization is permitted after budget_exhausted."))
            response = event["response"]
            issues.extend(validate_response(response, registry).issues)
            if response["episode_id"] != action["episode_id"] or response["request_id"] != action["request_id"] or response["step_index"] != action["step_index"] or response["tool"] != tool:
                issues.append(ValidationIssue("TRJ-001", f"/events/{index}/response", "Action and response episode, request, step, and tool fields must agree."))
            allowed_result_types = {
                "search_visual": {"search_pointer"},
                "search_speech": {"search_pointer"},
                "search_ambient_audio": {"search_pointer"},
                "inspect_clip": {"observation"},
                "read_transcript": {"observation"},
                "get_channel_status": {"channel_status"},
            }[tool]
            if any(result["result_type"] not in allowed_result_types for result in response["results"]):
                issues.append(ValidationIssue("TRJ-001", f"/events/{index}/response/results", "Response result types must match the invoked tool."))
            if tool == "get_channel_status":
                for result_index, result in enumerate(response["results"]):
                    if result["result_type"] == "channel_status" and set(result["channels"]) != set(arguments["channels"]):
                        issues.append(ValidationIssue("TRJ-001", f"/events/{index}/response/results/{result_index}/channels", "Channel-status results must exactly match requested channels."))
            expected_charge = 0.0 if response["status"] == "budget_exhausted" else schedule.get(tool)
            if expected_charge is None or abs(response["cost_charged"] - expected_charge) > TOLERANCE:
                issues.append(ValidationIssue("TRJ-004", f"/events/{index}/response/cost_charged", f"Cost must equal frozen schedule value {expected_charge}."))
            expected_total = previous_total + response["cost_charged"]
            if abs(response["cost_used_total"] - expected_total) > TOLERANCE:
                issues.append(ValidationIssue("TRJ-004", f"/events/{index}/response/cost_used_total", f"Cumulative cost must be {expected_total}."))
            expected_remaining = max(0.0, budget["cost_limit"] - response["cost_used_total"])
            if abs(response["cost_remaining"] - expected_remaining) > TOLERANCE:
                issues.append(ValidationIssue("TRJ-004", f"/events/{index}/response/cost_remaining", f"Remaining cost must be {expected_remaining}."))
            if response["cost_used_total"] + TOLERANCE < previous_total:
                issues.append(ValidationIssue("TRJ-004", f"/events/{index}/response/cost_used_total", "Cumulative cost must be monotone."))
            if response["cost_used_total"] > budget["cost_limit"] + TOLERANCE:
                issues.append(ValidationIssue("TRJ-004", f"/events/{index}/response/cost_used_total", "Cumulative cost may not exceed the budget."))
            if response["backend_version"] != trajectory["replay"]["backend_version"]:
                issues.append(ValidationIssue("TRJ-001", f"/events/{index}/response/backend_version", "Response backend_version must match replay.backend_version."))
            if response["status"] == "budget_exhausted":
                scheduled_charge = schedule.get(tool)
                if scheduled_charge is None or previous_total + scheduled_charge <= budget["cost_limit"] + TOLERANCE:
                    issues.append(ValidationIssue("TRJ-004", f"/events/{index}/response/status", "budget_exhausted is valid only when the scheduled call would exceed remaining budget."))
                if response["error"]["code"] != "BUDGET_EXHAUSTED" or response["error"]["retryable"]:
                    issues.append(ValidationIssue("TRJ-004", f"/events/{index}/response/error", "budget_exhausted requires non-retryable BUDGET_EXHAUSTED error semantics."))
                budget_exhausted_at = index
            previous_total = response["cost_used_total"]
            for result_index, result in enumerate(response["results"]):
                interval = result.get("interval")
                if interval is not None and (interval["start_s"] < 0 or interval["end_s"] > duration):
                    issues.append(ValidationIssue("TRJ-003", f"/events/{index}/response/results/{result_index}/interval", "Result interval must lie within source bounds."))
                if interval is not None and isinstance(requested_interval, dict):
                    if tool in {"inspect_clip", "read_transcript"} and (
                        interval["start_s"] < requested_interval["start_s"]
                        or interval["end_s"] > requested_interval["end_s"]
                    ):
                        issues.append(ValidationIssue("TRJ-003", f"/events/{index}/response/results/{result_index}/interval", "Citable observation interval must be contained in the requested interval."))
                    if tool.startswith("search_") and (
                        interval["end_s"] <= requested_interval["start_s"]
                        or interval["start_s"] >= requested_interval["end_s"]
                    ):
                        issues.append(ValidationIssue("TRJ-003", f"/events/{index}/response/results/{result_index}/interval", "Search result interval must overlap the requested time range."))
                if result["result_type"] == "observation":
                    observation_id = result["observation_id"]
                    previous = observations.get(observation_id)
                    if previous is not None and previous != result:
                        issues.append(ValidationIssue("TRJ-003", f"/events/{index}/response/results/{result_index}/observation_id", "An observation ID must identify immutable content throughout a trajectory."))
                    observations[observation_id] = result
                    expected_modalities = {"speech"} if tool == "read_transcript" else (
                        ({"vision"} if arguments["include_video"] else set())
                        | ({"speech", "ambient"} if arguments["include_audio"] else set())
                    )
                    if not set(result["modalities"]) <= expected_modalities:
                        issues.append(ValidationIssue("TRJ-001", f"/events/{index}/response/results/{result_index}/modalities", "Observation modalities must be enabled by the request."))
        else:
            finalize_count += 1
            if tool != "finalize":
                issues.append(ValidationIssue("TRJ-005", f"/events/{index}/action/action/tool", "A finalize event must use the finalize tool."))
            if index != len(trajectory["events"]) - 1:
                issues.append(ValidationIssue("TRJ-005", f"/events/{index}", "Finalize must be the last agent action."))
            if budget_exhausted_at is not None and index != budget_exhausted_at + 1:
                issues.append(ValidationIssue("TRJ-004", f"/events/{index}", "budget_exhausted must be followed immediately by finalization."))
            final = action["action"]["arguments"]
            if budget_exhausted_at is not None and final["termination_reason"] != "budget_guard":
                issues.append(ValidationIssue("TRJ-004", "/final_output/termination_reason", "Finalization after budget_exhausted must use budget_guard."))
            if final != trajectory["final_output"]:
                issues.append(ValidationIssue("TRJ-005", "/final_output", "final_output must exactly equal finalize.arguments."))
            issue = _cause_sum_issue(final["diagnosis"]["cause_probabilities"], "/final_output/diagnosis/cause_probabilities")
            if issue:
                issues.append(issue)
            for claim_index, claim in enumerate(final["claims"]):
                for citation_index, citation in enumerate(claim["citations"]):
                    pointer = f"/final_output/claims/{claim_index}/citations/{citation_index}"
                    observation = observations.get(citation["observation_id"])
                    if observation is None:
                        issues.append(ValidationIssue("TRJ-003", pointer + "/observation_id", "Citation must resolve to a previously returned citable observation."))
                        continue
                    if not set(citation["modalities"]) <= set(observation["modalities"]):
                        issues.append(ValidationIssue("TRJ-003", pointer + "/modalities", "Citation modalities must be present in the observation."))
                    cited = citation["interval"]
                    observed = observation["interval"]
                    if cited["start_s"] < observed["start_s"] or cited["end_s"] > observed["end_s"] or cited["end_s"] <= cited["start_s"]:
                        issues.append(ValidationIssue("TRJ-003", pointer + "/interval", "Citation interval must be non-empty and contained in the observation interval."))

    if finalize_count != 1:
        issues.append(ValidationIssue("TRJ-005", "/events", "Trajectory must contain exactly one finalize event."))
    if len(trajectory["events"]) > budget["max_steps"]:
        issues.append(ValidationIssue("TRJ-004", "/events", "Trajectory exceeds max_steps."))
    if trajectory["completion"]["total_steps"] != len(trajectory["events"]):
        issues.append(ValidationIssue("TRJ-001", "/completion/total_steps", "completion.total_steps must equal the event count."))
    if abs(trajectory["completion"]["total_cost"] - previous_total) > TOLERANCE:
        issues.append(ValidationIssue("TRJ-004", "/completion/total_cost", "completion.total_cost must equal final cumulative tool cost."))
    if not trajectory["completion"]["protocol_valid"] or trajectory["completion"]["status"] not in {"completed", "forced_finalization"}:
        issues.append(ValidationIssue("TRJ-005", "/completion", "A passing trajectory must report a protocol-valid completed or forced-finalization status."))
    if trajectory["replay"]["trajectory_hash"] != trajectory_content_hash(trajectory):
        issues.append(ValidationIssue("TRJ-003", "/replay/trajectory_hash", "trajectory_hash does not match the canonical trajectory content."))
    return make_report(issues, trajectory_hash=safe_sha256_json(trajectory))
