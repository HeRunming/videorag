"""JSONL wire protocol and policy-visible identifier translation."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

from av_trace.schemas import SchemaRegistry
from av_trace.trajectory import validate_action, validate_response
from av_trace.util import response_content_hash

from .errors import AgentRuntimeError

WIRE_VERSION = "av-trace-agent-jsonl-v1"
_HANDLE_RE = re.compile(r"^[a-z][a-z0-9]{23}$")


def canonical_json_line(message: Mapping[str, Any]) -> bytes:
    """Serialize one compact, deterministic UTF-8 JSONL message."""

    return (
        json.dumps(
            dict(message),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def parse_json_line(raw: bytes, *, max_bytes: int, source: str) -> dict[str, Any]:
    """Parse exactly one bounded JSON object from one protocol line."""

    if len(raw) > max_bytes:
        raise AgentRuntimeError(
            "OUTPUT_LIMIT",
            f"{source} message exceeded the {max_bytes}-byte limit.",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AgentRuntimeError("MALFORMED_MESSAGE", f"{source} emitted non-UTF-8 output.") from exc
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AgentRuntimeError("MALFORMED_MESSAGE", f"{source} emitted invalid JSON.") from exc
    if not isinstance(value, dict):
        raise AgentRuntimeError("MALFORMED_MESSAGE", f"{source} message must be a JSON object.")
    return value


def validate_episode_start_payload(payload: Mapping[str, Any]) -> None:
    """Validate the deliberately reduced, evaluator-ID-free start payload."""

    required = {
        "protocol_version",
        "episode_id",
        "question",
        "available_tools",
        "video_duration_s",
        "budget",
        "tool_costs",
        "seed",
        "config",
    }
    if set(payload) != required:
        raise AgentRuntimeError(
            "INVALID_START",
            f"Episode start fields must be exactly {sorted(required)}.",
        )
    if payload["protocol_version"] != "0.2.0":
        raise AgentRuntimeError("INVALID_START", "Unsupported normative protocol version.")
    if not isinstance(payload["episode_id"], str) or not _HANDLE_RE.fullmatch(payload["episode_id"]):
        raise AgentRuntimeError("INVALID_START", "episode_id must be an opaque runtime handle.")
    if not isinstance(payload["question"], str) or not payload["question"]:
        raise AgentRuntimeError("INVALID_START", "question must be a non-empty string.")
    if not isinstance(payload["available_tools"], list) or not payload["available_tools"]:
        raise AgentRuntimeError("INVALID_START", "available_tools must be a non-empty array.")
    if not isinstance(payload["video_duration_s"], (int, float)) or payload["video_duration_s"] <= 0:
        raise AgentRuntimeError("INVALID_START", "video_duration_s must be positive.")
    budget = payload["budget"]
    if not isinstance(budget, dict) or set(budget) != {"cost_limit", "max_steps"}:
        raise AgentRuntimeError("INVALID_START", "budget has an invalid shape.")
    if not isinstance(payload["tool_costs"], dict):
        raise AgentRuntimeError("INVALID_START", "tool_costs must be an object.")
    if not isinstance(payload["seed"], int) or payload["seed"] < 0:
        raise AgentRuntimeError("INVALID_START", "seed must be a non-negative integer.")
    config = payload["config"]
    if not isinstance(config, dict) or set(config) != {"wire_version", "deterministic"}:
        raise AgentRuntimeError("INVALID_START", "config has an invalid shape.")
    if config["wire_version"] != WIRE_VERSION or config["deterministic"] is not True:
        raise AgentRuntimeError("INVALID_START", "config must freeze this deterministic wire version.")


@dataclass
class OpaqueHandleMap:
    """Per-episode deterministic bijection between evaluator and policy IDs.

    Public handles are allocated by first-seen ordinal, not derived from the
    private identifier.  Hashing a low-entropy private ID (for example a known
    family/state episode ID) would still permit an offline dictionary attack
    when the algorithm and configured seed are visible to the child.
    """

    seed: int
    _private_to_public: dict[tuple[str, str], str] = field(default_factory=dict)
    _public_to_private: dict[tuple[str, str], str] = field(default_factory=dict)
    _next_ordinal: dict[str, int] = field(default_factory=dict)

    def _candidate(self, namespace: str, ordinal: int, counter: int) -> str:
        material = f"{self.seed}\0{namespace}\0{ordinal}\0{counter}".encode("utf-8")
        digest = hashlib.blake2s(material, digest_size=16).hexdigest()
        prefix = {
            "episode": "e",
            "request": "q",
            "pointer": "p",
            "observation": "o",
            "backend": "b",
        }[namespace]
        return prefix + digest[:23]

    def public(self, namespace: str, private_id: str) -> str:
        key = (namespace, private_id)
        existing = self._private_to_public.get(key)
        if existing is not None:
            return existing
        ordinal = self._next_ordinal.get(namespace, 0)
        counter = 0
        while True:
            handle = self._candidate(namespace, ordinal, counter)
            reverse_key = (namespace, handle)
            collision = self._public_to_private.get(reverse_key)
            if collision is None or collision == private_id:
                self._private_to_public[key] = handle
                self._public_to_private[reverse_key] = private_id
                self._next_ordinal[namespace] = ordinal + 1
                return handle
            counter += 1

    def private(self, namespace: str, public_id: str) -> str:
        try:
            return self._public_to_private[(namespace, public_id)]
        except KeyError as exc:
            raise AgentRuntimeError(
                "UNKNOWN_HANDLE",
                f"Unknown {namespace} handle {public_id!r}.",
            ) from exc

    def knows_public(self, namespace: str, public_id: str) -> bool:
        return (namespace, public_id) in self._public_to_private


@dataclass
class PolicyView:
    """Translate schema-valid normative messages at the process boundary."""

    registry: SchemaRegistry
    handles: OpaqueHandleMap
    real_episode_id: str
    public_episode_id: str
    private_request_ids: dict[str, str] = field(default_factory=dict)

    def episode_start(
        self,
        normative_start: Mapping[str, Any],
        *,
        seed: int,
    ) -> dict[str, Any]:
        payload = {
            "protocol_version": normative_start["protocol_version"],
            "episode_id": self.public_episode_id,
            "question": deepcopy(normative_start["question"]),
            "available_tools": deepcopy(normative_start["available_tools"]),
            "video_duration_s": normative_start["video_duration_s"],
            "budget": deepcopy(normative_start["budget"]),
            "tool_costs": deepcopy(normative_start["tool_costs"]),
            "seed": seed,
            "config": {
                "wire_version": WIRE_VERSION,
                "deterministic": True,
            },
        }
        validate_episode_start_payload(payload)
        return payload

    def action_to_private(self, public_action: Mapping[str, Any]) -> dict[str, Any]:
        action = deepcopy(dict(public_action))
        public_report = validate_action(action, self.registry)
        if not public_report.ok:
            first = public_report.issues[0]
            raise AgentRuntimeError(
                "INVALID_ACTION",
                f"{first.code} at {first.pointer}: {first.message}",
            )
        public_request_id = action.get("request_id")
        if not isinstance(public_request_id, str):
            raise AgentRuntimeError("INVALID_ACTION", "request_id must be a string.")
        if public_request_id in self.private_request_ids:
            raise AgentRuntimeError("DUPLICATE_REQUEST", "request_id must be unique.")
        # Request handles are also episode-scoped; the private backend never
        # receives a policy-chosen identifier verbatim.
        private_request_id = self.handles.public(
            "request", f"{self.real_episode_id}\0{public_request_id}"
        )
        self.private_request_ids[public_request_id] = private_request_id
        action["episode_id"] = self.real_episode_id
        action["request_id"] = private_request_id

        tool = action.get("action", {}).get("tool")
        arguments = action.get("action", {}).get("arguments")
        if tool in {"search_visual", "search_speech", "search_ambient_audio"} and isinstance(
            arguments, dict
        ):
            excluded = arguments.get("exclude_result_ids")
            if isinstance(excluded, list):
                arguments["exclude_result_ids"] = [
                    self.handles.private("pointer", item) for item in excluded
                ]
        if tool == "finalize" and isinstance(arguments, dict):
            for claim in arguments.get("claims", ()):
                # Evaluator IDs are never accepted from policy code.
                claim["registered_claim_id"] = None
                for citation in claim.get("citations", ()):
                    citation["observation_id"] = self.handles.private(
                        "observation", citation["observation_id"]
                    )

        report = validate_action(action, self.registry)
        if not report.ok:
            first = report.issues[0]
            raise AgentRuntimeError(
                "INVALID_ACTION",
                f"{first.code} at {first.pointer}: {first.message}",
            )
        return action

    def response_to_public(self, private_response: Mapping[str, Any]) -> dict[str, Any]:
        response = deepcopy(dict(private_response))
        report = validate_response(response, self.registry)
        if not report.ok:
            first = report.issues[0]
            raise AgentRuntimeError(
                "INVALID_BACKEND_RESPONSE",
                f"{first.code} at {first.pointer}: {first.message}",
            )
        private_request_id = response["request_id"]
        public_request_id = next(
            (
                public
                for public, private in self.private_request_ids.items()
                if private == private_request_id
            ),
            None,
        )
        if public_request_id is None:
            raise AgentRuntimeError("INVALID_BACKEND_RESPONSE", "Response request ID is unmapped.")
        response["episode_id"] = self.public_episode_id
        response["request_id"] = public_request_id
        response["backend_version"] = self.handles.public(
            "backend", response["backend_version"]
        )
        for result in response.get("results", ()):
            if result.get("result_type") == "search_pointer":
                result["result_id"] = self.handles.public("pointer", result["result_id"])
            elif result.get("result_type") == "observation":
                result["observation_id"] = self.handles.public(
                    "observation", result["observation_id"]
                )
                payload = result.get("payload")
                if isinstance(payload, dict):
                    payload.pop("_route_refs", None)
                # The public payload hash authenticates exactly the public payload.
                from av_trace.util import sha256_json

                result["payload_hash"] = sha256_json(result["payload"])
        response["response_hash"] = response_content_hash(response)
        public_report = validate_response(response, self.registry)
        if not public_report.ok:
            first = public_report.issues[0]
            raise AgentRuntimeError(
                "INVALID_PUBLIC_RESPONSE",
                f"{first.code} at {first.pointer}: {first.message}",
            )
        return response
