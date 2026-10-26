"""Deterministic fixed backend exposing the frozen Pilot-0 tool surface."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from av_trace.schemas import SchemaRegistry
from av_trace.semantic import validate_family
from av_trace.trajectory import validate_action
from av_trace.util import response_content_hash, sha256_json

from .index import BackendManifest, FixedIndex, IndexRecord
from .interventions import InterventionRuntime

AVAILABLE_TOOLS = (
    "search_visual",
    "search_speech",
    "search_ambient_audio",
    "inspect_clip",
    "read_transcript",
    "get_channel_status",
    "finalize",
)


class BackendProtocolError(ValueError):
    """Stable protocol error for calls rejected before reaching a tool."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class FixedBackend:
    """One stateful, replayable episode over an immutable index and manifest."""

    def __init__(
        self,
        family: dict[str, Any],
        state_role: str,
        index: FixedIndex,
        manifest: BackendManifest,
        registry: SchemaRegistry | None = None,
    ) -> None:
        self.registry = registry or SchemaRegistry()
        structural = self.registry.validate("episode-family", family)
        if not structural.ok:
            first = structural.issues[0]
            raise BackendProtocolError("BACKEND_INVALID_FAMILY", f"{first.pointer}: {first.message}")
        semantic = validate_family(family, None, self.registry)
        semantic_issues = [issue for issue in semantic.issues if issue.code != "PROV-000"]
        if semantic_issues:
            first = semantic_issues[0]
            raise BackendProtocolError(
                "BACKEND_INVALID_FAMILY",
                f"{first.code} at {first.pointer}: {first.message}",
            )
        manifest.verify()
        episodes = {item["state_role"]: item for item in family["episodes"]}
        if state_role not in episodes:
            raise BackendProtocolError("BACKEND_STATE", f"Unknown state role {state_role}.")
        self.family = deepcopy(family)
        self.episode = deepcopy(episodes[state_role])
        self.index = index
        self.manifest = manifest
        if manifest.index_hash != index.index_hash:
            raise BackendProtocolError("BACKEND_INDEX_HASH", "Manifest index_hash does not match the loaded index.")
        if self.episode["backend"]["index_hash"] != index.index_hash:
            raise BackendProtocolError("BACKEND_INDEX_HASH", "Episode index_hash does not match the loaded index.")
        if self.episode["backend"]["backend_version"] != manifest.backend_version:
            raise BackendProtocolError("BACKEND_VERSION", "Episode backend_version does not match the manifest.")
        if self.episode["backend"]["tool_api_version"] != manifest.document["tool_api_version"]:
            raise BackendProtocolError("BACKEND_VERSION", "Episode tool_api_version does not match the manifest.")
        if self.episode["budget"]["tool_costs"] != manifest.tool_costs:
            raise BackendProtocolError("BACKEND_COSTS", "Episode tool costs do not match the backend manifest.")
        if self.episode["budget"]["tool_costs"]["finalize"] != 0:
            raise BackendProtocolError("BACKEND_COSTS", "finalize must be zero cost.")

        self.interventions = InterventionRuntime(family, state_role, index)
        # All questions over one source search the same source-level candidate
        # universe. Family annotations may mask registered intervention routes,
        # but must not pre-filter retrieval to answer-bearing records.
        self._records = index.for_asset(family["source"]["asset_id"])
        self._cost_used = 0.0
        self._call_index = 0
        self._request_ids: set[str] = set()
        self._finalized = False
        self._budget_exhausted = False
        self._inspected_duration_s = 0.0
        self.last_active_hook_ids: tuple[str, ...] = ()
        self.final_output: dict[str, Any] | None = None

    @property
    def backend_version(self) -> str:
        return self.manifest.backend_version

    @property
    def index_version(self) -> str:
        return self.manifest.index_version

    @property
    def backend_hash(self) -> str:
        return self.manifest.manifest_hash

    @property
    def intervention_manifest_hash(self) -> str:
        return self.interventions.manifest_hash

    @property
    def cost_used(self) -> float:
        return self._cost_used

    @property
    def inspected_duration_s(self) -> float:
        return self._inspected_duration_s

    @property
    def state_hash(self) -> str:
        return sha256_json(
            {
                "backend_hash": self.backend_hash,
                "index_hash": self.index.index_hash,
                "index_version": self.index_version,
                "episode_id": self.episode["episode_id"],
                "intervention_state": self.interventions.snapshot.state_hash,
                "cost_used": self._cost_used,
                "call_index": self._call_index,
                "request_ids": sorted(self._request_ids),
                "finalized": self._finalized,
                "budget_exhausted": self._budget_exhausted,
                "inspected_duration_s": self._inspected_duration_s,
                "final_output": self.final_output,
            }
        )

    def episode_start(self, *, reveal_state_role: bool = False) -> dict[str, Any]:
        return {
            "protocol_version": "0.2.0",
            "episode_id": self.episode["episode_id"],
            "family_id": self.family["family_id"],
            # The normative trajectory schema retains state_role for evaluator
            # replay. Blind agents receive an opaque placeholder and must infer
            # operational state only from tool responses.
            "state_role": self.episode["state_role"] if reveal_state_role else "CLEAN",
            "question": self.family["question"]["text"],
            "available_tools": list(AVAILABLE_TOOLS),
            "video_duration_s": self.family["source"]["duration_s"],
            "budget": {
                "cost_limit": self.episode["budget"]["cost_limit"],
                "max_steps": self.episode["budget"]["max_steps"],
            },
            "tool_costs": deepcopy(self.episode["budget"]["tool_costs"]),
        }

    def execute(self, action: dict[str, Any]) -> dict[str, Any] | None:
        report = validate_action(action, self.registry)
        if not report.ok:
            first = report.issues[0]
            raise BackendProtocolError("BACKEND_INVALID_ACTION", f"{first.code} at {first.pointer}: {first.message}")
        if self._finalized:
            raise BackendProtocolError("BACKEND_AFTER_FINALIZE", "No action is allowed after finalize.")
        if action["episode_id"] != self.episode["episode_id"]:
            raise BackendProtocolError("BACKEND_EPISODE_MISMATCH", "Action episode_id does not match.")
        if action["step_index"] != self._call_index:
            raise BackendProtocolError("BACKEND_STEP_MISMATCH", f"Expected step_index {self._call_index}.")
        if action["request_id"] in self._request_ids:
            raise BackendProtocolError("BACKEND_REQUEST_DUPLICATE", "request_id must be unique.")
        if self._call_index >= self.episode["budget"]["max_steps"]:
            raise BackendProtocolError("BACKEND_MAX_STEPS", "Episode max_steps has been reached.")
        tool = action["action"]["tool"]
        arguments = action["action"]["arguments"]
        interval = arguments.get("time_range") or arguments.get("interval")
        if isinstance(interval, dict) and interval["end_s"] > self.family["source"]["duration_s"]:
            raise BackendProtocolError("BACKEND_INVALID_INTERVAL", "Requested interval exceeds source duration.")
        if self._budget_exhausted and tool != "finalize":
            raise BackendProtocolError("BACKEND_AFTER_BUDGET", "Only finalize is allowed after budget exhaustion.")

        self._request_ids.add(action["request_id"])
        self.last_active_hook_ids = ()
        if tool == "finalize":
            self.final_output = deepcopy(arguments)
            self._finalized = True
            self._call_index += 1
            return None

        charge = self.episode["budget"]["tool_costs"][tool]
        limit = self.episode["budget"]["cost_limit"]
        if self._cost_used + charge > limit:
            self._budget_exhausted = True
            response = self._response(
                action,
                "budget_exhausted",
                0.0,
                [],
                self._error(
                    "BUDGET_EXHAUSTED",
                    False,
                    "The requested call would exceed the episode budget.",
                ),
            )
            self._call_index += 1
            return response

        self.last_active_hook_ids = self.interventions.maybe_restore(tool, self._call_index)
        self._cost_used += charge
        status, results, error = self._dispatch(tool, arguments)
        response = self._response(action, status, charge, results, error)
        self._call_index += 1
        return response

    @staticmethod
    def _error(code: str, retryable: bool, message: str, retry_after_step: int | None = None) -> dict[str, Any]:
        return {
            "code": code,
            "retryable": retryable,
            "message": message,
            "retry_after_step": retry_after_step,
        }

    def _unavailable(self, channel: str) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        return (
            "channel_unavailable",
            [],
            self._error(
                f"{channel.upper()}_CHANNEL_UNAVAILABLE",
                True,
                "The requested channel is unavailable.",
            ),
        )

    def _visible(self) -> tuple[IndexRecord, ...]:
        return self.interventions.visible_records(self._records)

    def _dispatch(
        self, tool: str, arguments: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        if tool == "get_channel_status":
            return self.get_channel_status(arguments)
        if tool == "search_visual":
            return self.search_visual(arguments)
        if tool == "search_speech":
            return self.search_speech(arguments)
        if tool == "search_ambient_audio":
            return self.search_ambient_audio(arguments)
        if tool == "read_transcript":
            return self.read_transcript(arguments)
        if tool == "inspect_clip":
            return self.inspect_clip(arguments)
        raise BackendProtocolError("BACKEND_UNKNOWN_TOOL", f"Unsupported tool {tool}.")

    # These methods are the public, frozen tool implementations. Normal callers
    # should still use execute() so request identity, cost, budget, and hashes are
    # applied to the returned result.
    def search_visual(
        self, arguments: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        return self._search("search_visual", "visual", "vision", arguments)

    def search_speech(
        self, arguments: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        return self._search("search_speech", "speech", "speech", arguments)

    def search_ambient_audio(
        self, arguments: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        return self._search("search_ambient_audio", "ambient", "ambient", arguments)

    def inspect_clip(
        self, arguments: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        return self._inspect_clip(arguments)

    def read_transcript(
        self, arguments: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        if not self.interventions.channel_available("transcript"):
            missing = "speech" if not self.interventions.channel_available("speech") else "transcript"
            return self._unavailable(missing)
        return self._read_transcript(arguments)

    def get_channel_status(
        self, arguments: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        channels = {
            channel: {
                "status": self.interventions.channel_status(channel),
                "retryable": not self.interventions.channel_available(channel),
            }
            for channel in arguments["channels"]
        }
        return "ok", [{"result_type": "channel_status", "channels": channels}], None

    def finalize(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Return an immutable copy of a final answer; execute() performs termination."""
        return deepcopy(arguments)

    def _search(
        self,
        tool: str,
        channel: str,
        modality: str,
        arguments: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        if not self.interventions.channel_available(channel):
            return self._unavailable(channel)
        ranked = self.index.search(
            records=self._visible(),
            modality=modality,
            query=arguments["query"],
            interval=arguments["time_range"],
            top_k=arguments["top_k"],
            excluded_result_ids=arguments["exclude_result_ids"],
            speaker_hint=arguments.get("speaker_hint"),
        )
        results = [
            {
                "result_type": "search_pointer",
                "result_id": record.result_id,
                "interval": deepcopy(record.interval),
                "score": score,
                "preview": record.preview,
            }
            for record, score in ranked
        ]
        if not results:
            return "not_found", [], self._error("NO_RESULTS", False, "No accessible indexed result matched.")
        return "ok", results, None

    @staticmethod
    def _contained(record: IndexRecord, interval: dict[str, float]) -> bool:
        return (
            record.interval["start_s"] >= interval["start_s"]
            and record.interval["end_s"] <= interval["end_s"]
        )

    @staticmethod
    def _observation(
        *,
        prefix: str,
        record: IndexRecord,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        payload = deepcopy(payload)
        payload["_route_refs"] = [
            sha256_json({"evidence_id": evidence_id})
            for evidence_id in record.route_evidence_ids
        ]
        identity = sha256_json(
            {
                "prefix": prefix,
                "record_id": record.record_id,
                "interval": record.interval,
                "modalities": [record.modality],
                "payload": payload,
            }
        ).split(":", 1)[1]
        return {
            "result_type": "observation",
            "observation_id": f"obs.{prefix}.{identity}",
            "interval": deepcopy(record.interval),
            "modalities": [record.modality],
            "payload": payload,
            "payload_hash": sha256_json(payload),
        }

    def _read_transcript(
        self, arguments: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        interval = arguments["interval"]
        source = arguments["source"]
        results = []
        for record in self._visible():
            if record.modality != "speech" or source not in record.transcript_sources:
                continue
            if not self._contained(record, interval):
                continue
            payload = deepcopy(record.payload)
            if not arguments["include_word_timestamps"]:
                payload.pop("words", None)
            payload["transcript_source"] = source
            results.append(self._observation(prefix=f"transcript.{source}", record=record, payload=payload))
        results.sort(key=lambda item: (item["interval"]["start_s"], item["observation_id"]))
        if not results:
            return "not_found", [], self._error("NO_RESULTS", False, "No accessible transcript observation matched.")
        return "ok", results, None

    def _inspect_clip(
        self, arguments: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        if not self.interventions.channel_available("clip"):
            return self._unavailable("clip")
        requested_modalities: set[str] = set()
        unavailable_requested = False
        if arguments["include_video"]:
            if self.interventions.channel_available("visual"):
                requested_modalities.add("vision")
            else:
                unavailable_requested = True
        if arguments["include_audio"]:
            present_audio = {record.modality for record in self._records if record.modality in {"speech", "ambient"}}
            enabled_audio = {
                modality
                for channel, modality in (("speech", "speech"), ("ambient", "ambient"))
                if modality in present_audio and self.interventions.channel_available(channel)
            }
            requested_modalities.update(enabled_audio)
            unavailable_requested = unavailable_requested or bool(present_audio - enabled_audio)
        if not requested_modalities:
            channel = "visual" if arguments["include_video"] else "speech"
            return self._unavailable(channel)

        interval = arguments["interval"]
        inspected = round(interval["end_s"] - interval["start_s"], 6)
        self._inspected_duration_s = round(self._inspected_duration_s + inspected, 6)
        results = []
        for record in self._visible():
            if record.modality not in requested_modalities or not self._contained(record, interval):
                continue
            payload = deepcopy(record.payload)
            payload["inspection"] = {
                "requested_interval": deepcopy(interval),
                "include_video": arguments["include_video"],
                "include_audio": arguments["include_audio"],
                "inspected_duration_s": inspected,
            }
            results.append(self._observation(prefix="clip", record=record, payload=payload))
        results.sort(key=lambda item: (item["interval"]["start_s"], item["modalities"], item["observation_id"]))
        if not results:
            return "not_found", [], self._error("NO_RESULTS", False, "No accessible clip observation matched.")
        return ("partial" if unavailable_requested else "ok"), results, None

    def _response(
        self,
        action: dict[str, Any],
        status: str,
        charge: float,
        results: list[dict[str, Any]],
        error: dict[str, Any] | None,
    ) -> dict[str, Any]:
        response = {
            "protocol_version": "0.2.0",
            "episode_id": action["episode_id"],
            "request_id": action["request_id"],
            "step_index": action["step_index"],
            "tool": action["action"]["tool"],
            "status": status,
            "cost_charged": charge,
            "cost_used_total": self._cost_used,
            "cost_remaining": max(0.0, self.episode["budget"]["cost_limit"] - self._cost_used),
            "backend_version": self.backend_version,
            "results": results,
            "error": error,
        }
        response["response_hash"] = response_content_hash(response)
        return response


MVPBackend = FixedBackend
DeterministicBackend = FixedBackend
