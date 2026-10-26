"""Minimal deterministic synthetic replay backend for both Pilot-0 mechanisms."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .schemas import SchemaRegistry
from .semantic import validate_family
from .trajectory import validate_action
from .util import response_content_hash, sha256_json


class ReplayProtocolError(ValueError):
    """Stable exception for invalid synthetic replay usage."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SyntheticRecord:
    evidence_id: str
    interval: dict[str, float]
    modality: str
    payload: dict[str, Any]


class SyntheticReplayBackend:
    """Stateful deterministic backend over explicit synthetic records only."""

    def __init__(
        self,
        family: dict[str, Any],
        state_role: str,
        records: dict[str, dict[str, Any]],
        registry: SchemaRegistry | None = None,
    ) -> None:
        self.registry = registry or SchemaRegistry()
        structural = self.registry.validate("episode-family", family)
        if not structural.ok:
            first = structural.issues[0]
            raise ReplayProtocolError("REPLAY-INVALID-FAMILY", f"{first.code} at {first.pointer}: {first.message}")
        semantic = validate_family(family, None, self.registry)
        semantic_issues = [issue for issue in semantic.issues if issue.code not in {"PROV-000"}]
        if semantic_issues:
            first = semantic_issues[0]
            raise ReplayProtocolError("REPLAY-INVALID-FAMILY", f"{first.code} at {first.pointer}: {first.message}")
        episodes = {episode["state_role"]: episode for episode in family["episodes"]}
        if len(episodes) != 3:
            raise ReplayProtocolError("REPLAY-INVALID-FAMILY", "Family must contain exactly one episode for each state role.")
        if state_role not in episodes:
            raise ReplayProtocolError("REPLAY-001", f"Unknown state role {state_role}.")
        self.family = deepcopy(family)
        self.episode = deepcopy(episodes[state_role])
        self.records = deepcopy(records)
        evidence = {unit["evidence_id"]: unit for unit in family["claim_evidence_graph"]["evidence_units"]}
        if set(records) != set(evidence):
            raise ReplayProtocolError("REPLAY-002", "Synthetic records must exactly cover graph evidence IDs.")
        for evidence_id, record in records.items():
            if record.get("modality") != evidence[evidence_id]["modality"]:
                raise ReplayProtocolError("REPLAY-002", f"Record modality mismatch for {evidence_id}.")
            interval = record.get("interval")
            if (
                not isinstance(interval, dict)
                or not isinstance(interval.get("start_s"), (int, float))
                or not isinstance(interval.get("end_s"), (int, float))
                or interval["start_s"] < 0
                or interval["end_s"] <= interval["start_s"]
                or interval["end_s"] > family["source"]["duration_s"]
            ):
                raise ReplayProtocolError("REPLAY-002", f"Record interval is invalid for {evidence_id}.")
            if interval not in evidence[evidence_id]["intervals"]:
                raise ReplayProtocolError("REPLAY-002", f"Record interval does not match graph provenance for {evidence_id}.")
            if not isinstance(record.get("payload"), dict):
                raise ReplayProtocolError("REPLAY-002", f"Record payload must be an object for {evidence_id}.")
        self._all_evidence = evidence
        self._accessible = set(self.episode["initial_state"]["accessible_evidence_ids"])
        self._enabled_channels = set(self.episode["initial_state"]["enabled_channels"])
        self._cost_used = 0.0
        self._calls = 0
        self._finalized = False
        self._budget_exhausted = False
        self._request_ids: set[str] = set()
        self._restored = state_role != "RESTORED"
        self.last_active_hook_ids: tuple[str, ...] = ()
        self._restore = next((item for item in self.episode["interventions"] if item["phase"] == "restoration"), None)
        self._block = next((item for item in self.episode["interventions"] if item["phase"] == "blocked"), None)

    @property
    def state_hash(self) -> str:
        return sha256_json({
            "episode_id": self.episode["episode_id"],
            "backend": self.episode["backend"],
            "budget": self.episode["budget"],
            "replay": self.episode["replay"],
            "records_hash": sha256_json(self.records),
            "accessible": sorted(self._accessible),
            "enabled_channels": sorted(self._enabled_channels),
            "cost_used": self._cost_used,
            "calls": self._calls,
            "finalized": self._finalized,
            "budget_exhausted": self._budget_exhausted,
            "request_ids": sorted(self._request_ids),
            "active_hook_ids": list(self.last_active_hook_ids),
            "restored": self._restored,
        })

    def _restore_if_triggered(self, action: dict[str, Any]) -> list[str]:
        if self._restore is None or self._restored:
            return []
        spec = self._restore["restoration"]
        triggered = (
            spec["trigger_type"] == "get_channel_status" and action["action"]["tool"] == "get_channel_status"
        ) or (
            spec["trigger_type"] == "fixed_call_index" and self._calls == spec["trigger_value"]
        )
        if not triggered:
            return []
        self._accessible.update(self._restore["affected_evidence_ids"])
        channel = self._restore["affected_channel"]
        if channel is not None:
            self._enabled_channels.add(channel)
        self._restored = True
        return [self._restore["intervention_id"]]

    def execute(self, action: dict[str, Any]) -> dict[str, Any] | None:
        report = validate_action(action, self.registry)
        if not report.ok:
            first = report.issues[0]
            raise ReplayProtocolError("REPLAY-INVALID-ACTION", f"{first.code} at {first.pointer}: {first.message}")
        if self._finalized:
            raise ReplayProtocolError("REPLAY-AFTER-FINALIZE", "No action is permitted after finalize.")
        if action["episode_id"] != self.episode["episode_id"]:
            raise ReplayProtocolError("REPLAY-EPISODE-MISMATCH", "Action episode_id does not match backend episode.")
        if action["step_index"] != self._calls:
            raise ReplayProtocolError("REPLAY-STEP-MISMATCH", f"Expected step_index {self._calls}.")
        if action["request_id"] in self._request_ids:
            raise ReplayProtocolError("REPLAY-REQUEST-DUPLICATE", f"Duplicate request_id {action['request_id']}.")
        if self._calls >= self.episode["budget"]["max_steps"]:
            raise ReplayProtocolError("REPLAY-MAX-STEPS", "Episode max_steps has been reached.")
        tool = action["action"]["tool"]
        arguments = action["action"]["arguments"]
        requested_interval = arguments.get("time_range") or arguments.get("interval")
        if isinstance(requested_interval, dict) and (
            requested_interval["end_s"] <= requested_interval["start_s"]
            or requested_interval["end_s"] > self.family["source"]["duration_s"]
        ):
            raise ReplayProtocolError("REPLAY-INVALID-ACTION", "Requested interval must be non-empty and within source bounds.")
        if self._budget_exhausted and tool != "finalize":
            raise ReplayProtocolError("REPLAY-AFTER-BUDGET", "Only finalize is permitted after budget exhaustion.")
        self._request_ids.add(action["request_id"])
        if tool == "finalize":
            self._finalized = True
            self._calls += 1
            return None

        charge = self.episode["budget"]["tool_costs"][tool]
        limit = self.episode["budget"]["cost_limit"]
        if self._cost_used + charge > limit:
            self.last_active_hook_ids = ()
            self._budget_exhausted = True
            response = self._response(action, "budget_exhausted", 0.0, [], {
                "code": "BUDGET_EXHAUSTED", "retryable": False, "message": "The requested call would exceed the episode budget.", "retry_after_step": None
            })
        else:
            active_hooks = self._restore_if_triggered(action)
            self.last_active_hook_ids = tuple(active_hooks)
            self._cost_used += charge
            status, results, error = self._dispatch(action)
            response = self._response(action, status, charge, results, error)
        self._calls += 1
        return response

    def _dispatch(self, action: dict[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        tool = action["action"]["tool"]
        args = action["action"]["arguments"]
        required_channel = {
            "search_visual": "visual", "search_speech": "speech", "search_ambient_audio": "ambient",
            "read_transcript": "transcript", "inspect_clip": "clip",
        }.get(tool)
        if required_channel and required_channel not in self._enabled_channels:
            code = f"{required_channel.upper()}_CHANNEL_UNAVAILABLE"
            return "channel_unavailable", [], {"code": code, "retryable": True, "message": "The requested channel is unavailable.", "retry_after_step": None}
        if tool == "get_channel_status":
            channels = {
                channel: {"status": "available" if channel in self._enabled_channels else "unavailable", "retryable": channel not in self._enabled_channels}
                for channel in args["channels"]
            }
            return "ok", [{"result_type": "channel_status", "channels": channels}], None
        if tool.startswith("search_"):
            modality = {"search_visual": "vision", "search_speech": "speech", "search_ambient_audio": "ambient"}[tool]
            interval = args["time_range"]
            matches = []
            for evidence_id in sorted(self._accessible):
                record = self.records[evidence_id]
                if record["modality"] != modality or f"ptr.{evidence_id}" in args["exclude_result_ids"]:
                    continue
                if record["interval"]["end_s"] <= interval["start_s"] or record["interval"]["start_s"] >= interval["end_s"]:
                    continue
                matches.append({
                    "result_type": "search_pointer", "result_id": f"ptr.{evidence_id}",
                    "interval": deepcopy(record["interval"]), "score": 1.0,
                    "preview": f"Synthetic pointer for {evidence_id}",
                })
            return ("ok" if matches else "not_found"), matches[: args["top_k"]], None if matches else {"code": "NO_RESULTS", "retryable": False, "message": "No accessible synthetic result matched.", "retry_after_step": None}
        requested = args["interval"]
        if tool == "read_transcript":
            requested_source = args["source"]
            eligible_streams = {
                unit["stream_id"]
                for unit in self._all_evidence.values()
                if unit["modality"] == "speech"
                and (
                    (
                        requested_source == "asr"
                        and any("asr" in item.lower() for item in unit["provenance"]["transformation_ids"])
                    )
                    or (
                        requested_source == "subtitle"
                        and any("subtitle" in item.lower() for item in unit["provenance"]["transformation_ids"])
                    )
                )
            }
        else:
            eligible_streams = None
        modalities = {"speech"} if tool == "read_transcript" else ({"vision"} if args["include_video"] else set()) | ({"speech", "ambient"} if args["include_audio"] else set())
        results = []
        for evidence_id in sorted(self._accessible):
            record = self.records[evidence_id]
            interval = record["interval"]
            if eligible_streams is not None and self._all_evidence[evidence_id]["stream_id"] not in eligible_streams:
                continue
            if record["modality"] not in modalities or interval["end_s"] <= requested["start_s"] or interval["start_s"] >= requested["end_s"]:
                continue
            payload = deepcopy(record["payload"])
            if interval["start_s"] < requested["start_s"] or interval["end_s"] > requested["end_s"]:
                continue
            results.append({
                "result_type": "observation", "observation_id": f"obs.{evidence_id}",
                "interval": deepcopy(interval), "modalities": [record["modality"]],
                "payload": payload, "payload_hash": sha256_json(payload),
            })
        return ("ok" if results else "not_found"), results, None if results else {"code": "NO_RESULTS", "retryable": False, "message": "No accessible synthetic observation matched.", "retry_after_step": None}

    def _response(self, action: dict[str, Any], status: str, charge: float, results: list[dict[str, Any]], error: dict[str, Any] | None) -> dict[str, Any]:
        response = {
            "protocol_version": "0.2.0", "episode_id": action["episode_id"], "request_id": action["request_id"],
            "step_index": action["step_index"], "tool": action["action"]["tool"], "status": status,
            "cost_charged": charge, "cost_used_total": self._cost_used,
            "cost_remaining": max(0.0, self.episode["budget"]["cost_limit"] - self._cost_used),
            "backend_version": self.episode["backend"]["backend_version"], "results": results, "error": error,
        }
        response["response_hash"] = response_content_hash(response)
        return response
