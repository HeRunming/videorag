"""Public-fictional external strong-agent route through local tcodex.

Task 201 deliberately permits only public, source-free fictional packets.
The runner reuses the v2 factor validators and mechanical serializers, keeps
every gateway response byte-for-byte, and allows at most one schema-only
retry per factor. It never performs semantic repair or model substitution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from av_trace_strong_baselines.contracts import canonical_json_bytes
from av_trace_strong_baselines.errors import SchemaViolation
from av_trace_strong_baselines.security import assert_public_surface
from av_trace_strong_baselines_v2 import (
    AttemptKind,
    FactorSpec,
    FactorStatus,
    RawFactorAttempt,
    action_choice_spec,
    build_native_action_plan,
    evidence_state_spec,
    finalizer_factor_specs,
    parse_controller_factors,
    parse_factor_attempts,
    parse_finalizer_factors,
)
from av_trace_strong_baselines_v2.adapter import (
    _parse_action_choice,
    _parse_answer_text,
    _parse_citation_selections,
    _parse_claim_drafts,
    _parse_diagnosis,
    _parse_disposition,
    _parse_evidence_state,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path(
    "data/rehearsal_plan/external_gateway_strong_agent_registry_v1.json"
)
DEFAULT_OUTPUT_DIR = Path(
    "data/rehearsal_plan/external_gateway_strong_agent_smoke_run_v1"
)

READY = "EXTERNAL_GATEWAY_STRONG_AGENT_SMOKE_READY"
REPAIR = "EXTERNAL_GATEWAY_STRONG_AGENT_SMOKE_REPAIR"
NO_GO = "EXTERNAL_GATEWAY_STRONG_AGENT_SMOKE_NO_GO"

RUNNER_SCHEMA = "av-trace.external-gateway-strong-agent-run/1.0"
PACKET_SCHEMA = "av-trace.external-gateway-public-packet/1.0"
ATTEMPT_SCHEMA = "av-trace.external-gateway-factor-attempt/1.0"
MAX_CASES = 2

PROHIBITED_PACKET_KEYS = frozenset(
    {
        "accepted_ses_labels",
        "answer_key",
        "answer_keys",
        "assignment_arm",
        "evaluator_key",
        "evaluator_private",
        "expected_action_index",
        "expected_answer",
        "expected_evidence_state",
        "h2_label",
        "h2_labels",
        "hidden_route_availability",
        "intervention_id",
        "necessity_group_id",
        "private_labels",
        "private_support_map",
        "required_terms",
        "required_terms_by_claim",
        "restoration_trigger",
        "scoring_target",
        "ses",
        "sess",
        "ses_labels",
        "source_text",
        "state_role",
        "trigger",
        "trigger_enabled",
    }
)
PROHIBITED_PACKET_TERMS = (
    re.compile(r"\bH2\b", re.IGNORECASE),
    re.compile(r"\bSES(?:es)?\b", re.IGNORECASE),
    re.compile(r"\baccepted[_ -]?support\b", re.IGNORECASE),
    re.compile(r"\bevaluator[_ -]?key\b", re.IGNORECASE),
    re.compile(r"\brestoration[_ -]?trigger\b", re.IGNORECASE),
    re.compile(r"\bscientific[_ -]?(?:source|family|data)\b", re.IGNORECASE),
)
MEDIA_KEY_TERMS = (
    "audio",
    "image",
    "media",
    "source_file",
    "video",
    "waveform",
)
MEDIA_PATH_SUFFIXES = frozenset(
    {
        ".aac",
        ".avi",
        ".flac",
        ".gif",
        ".jpeg",
        ".jpg",
        ".m4a",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".ogg",
        ".png",
        ".wav",
        ".webm",
        ".webp",
    }
)
FICTIONAL_MARKERS = (
    "fictional",
    "closed-world",
    "source-free",
    "synthetic",
)
REAL_SOURCE_MARKERS = (
    "captaincook",
    "epic-kitchens",
    "noaa",
    "videomme",
)
FACTOR_ORDER = {
    "controller": ("action_choice", "evidence_state"),
    "finalizer": (
        "disposition",
        "answer_text",
        "claim_drafts",
        "citation_selections",
        "diagnosis",
    ),
}
DISABLED_FEATURES = (
    "apps",
    "browser_use",
    "computer_use",
    "goals",
    "image_generation",
    "multi_agent",
    "plugins",
    "shell_tool",
    "unified_exec",
)
WRAPPER_PROVIDER_ID = "tencent"
WRAPPER_PROVIDER_NAME = "Tencent Internal Gateway"
WRAPPER_WIRE_API = "responses"
PROVENANCE_WAIT_SECONDS = 30.0
PROVENANCE_POLL_SECONDS = 0.01
PROCESS_TERM_WAIT_SECONDS = 2.0
PROCESS_KILL_WAIT_SECONDS = 2.0
PROCESS_PIPE_DRAIN_SECONDS = 2.0
MODEL_CATALOG_CONFIG_RE = re.compile(
    r'^model_catalog_json="(?P<path>.*)"$'
)
MODEL_PROVIDER_CONFIG_RE = re.compile(
    r'^model_provider="(?P<provider>[^"]+)"$'
)
PROVIDER_BINDING_CONFIG_RE = re.compile(
    r"^model_providers\.(?P<provider>[^=]+)=\{\s*"
    r'name\s*=\s*"(?P<name>[^"]+)",\s*'
    r'base_url\s*=\s*"(?P<base_url>[^"]+)",\s*'
    r'wire_api\s*=\s*"(?P<wire_api>[^"]+)"\s*\}$'
)
MODEL_CONFIG_RE = re.compile(r'^model="(?P<model>.*)"$')


class ExternalGatewayError(RuntimeError):
    """Typed fail-closed Task-201 runner error."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExternalGatewayError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def atomic_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def atomic_json(path: Path, value: Any, *, mode: int = 0o600) -> None:
    atomic_write(
        path,
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n",
        mode=mode,
    )


def jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: jsonable(child) for key, child in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): jsonable(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(child) for child in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _walk(value: Any, path: str = "$") -> Sequence[tuple[str, str, Any]]:
    rows: list[tuple[str, str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            rows.append((child_path, str(key), child))
            rows.extend(_walk(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(_walk(child, f"{path}[{index}]"))
    return rows


def validate_public_packet(packet: Mapping[str, Any]) -> None:
    """Reject anything outside Task 201's public-fictional privacy boundary."""

    if packet.get("schema_version") != PACKET_SCHEMA:
        raise ExternalGatewayError("PUBLIC_PACKET_SCHEMA_MISMATCH")
    if packet.get("public_fictional") is not True:
        raise ExternalGatewayError("PUBLIC_PACKET_NOT_FICTIONAL")
    if packet.get("source_free") is not True:
        raise ExternalGatewayError("PUBLIC_PACKET_NOT_SOURCE_FREE")
    if packet.get("development_only") is not True:
        raise ExternalGatewayError("PUBLIC_PACKET_NOT_DEVELOPMENT_ONLY")
    case_type = packet.get("case_type")
    if case_type not in FACTOR_ORDER:
        raise ExternalGatewayError("PUBLIC_PACKET_CASE_TYPE_INVALID")
    public_input = packet.get("public_input")
    if not isinstance(public_input, Mapping):
        raise ExternalGatewayError("PUBLIC_PACKET_INPUT_INVALID")
    try:
        assert_public_surface(packet)
    except SchemaViolation as exc:
        raise ExternalGatewayError(exc.code) from exc
    serialized = json.dumps(
        packet,
        sort_keys=True,
        ensure_ascii=False,
    )
    if not any(marker in serialized.casefold() for marker in FICTIONAL_MARKERS):
        raise ExternalGatewayError("FICTIONAL_MARKER_REQUIRED")
    if any(marker in serialized.casefold() for marker in REAL_SOURCE_MARKERS):
        raise ExternalGatewayError("REAL_SOURCE_MARKER_FORBIDDEN")
    for pattern in PROHIBITED_PACKET_TERMS:
        if pattern.search(serialized):
            raise ExternalGatewayError("PROHIBITED_PACKET_TERM")
    for path, key, child in _walk(packet):
        folded = key.casefold()
        if folded in PROHIBITED_PACKET_KEYS:
            raise ExternalGatewayError(f"PROHIBITED_PACKET_KEY:{path}")
        if any(term in folded for term in MEDIA_KEY_TERMS):
            if key in {"missing_modalities", "modalities"}:
                continue
            raise ExternalGatewayError(f"MEDIA_FIELD_FORBIDDEN:{path}")
        if isinstance(child, str):
            lowered = child.casefold()
            if lowered.startswith(("data:", "file:", "http:", "https:")):
                raise ExternalGatewayError(f"EXTERNAL_OR_MEDIA_URI_FORBIDDEN:{path}")
            if any(lowered.endswith(suffix) for suffix in MEDIA_PATH_SUFFIXES):
                raise ExternalGatewayError(f"MEDIA_PATH_FORBIDDEN:{path}")


def public_smoke_packets() -> list[dict[str, Any]]:
    """Exactly two source-free development packets: one controller/finalizer."""

    packets = [
        {
            "schema_version": PACKET_SCHEMA,
            "case_id": 'PUBLIC_REDACTED_IDENTIFIER',
            "case_type": "controller",
            "public_fictional": True,
            "source_free": True,
            "development_only": True,
            "public_input": {
                "task": "choose_next_action",
                "policy": "evidence_sufficiency",
                "question": (
                    "In the fictional closed-world record, what color is "
                    "prism P1?"
                ),
                "public_claim_slots": [
                    {
                        "claim_handle": "public.slot.prism_color",
                        "description": "Visible fictional prism color.",
                    }
                ],
                "observed_evidence": [],
                "known_pointers": [],
                "recent_public_history": [],
                "remaining_budget": {
                    "actions_remaining": 6,
                    "cost_remaining": 8.0,
                },
                "action_menu": [
                    {
                        "tool": "search_visual",
                        "arguments": {
                            "query": "fictional prism P1 visible color",
                            "top_k": 5,
                            "time_range": {"start_s": 0.0, "end_s": 20.0},
                            "exclude_result_ids": [],
                        },
                    },
                    {
                        "tool": "search_speech",
                        "arguments": {
                            "query": "fictional spoken prism color",
                            "top_k": 5,
                            "time_range": {"start_s": 0.0, "end_s": 20.0},
                            "exclude_result_ids": [],
                            "speaker_hint": None,
                        },
                    },
                    {"tool": "finalize", "arguments": {}},
                ],
            },
        },
        {
            "schema_version": PACKET_SCHEMA,
            "case_id": 'PUBLIC_REDACTED_IDENTIFIER',
            "case_type": "finalizer",
            "public_fictional": True,
            "source_free": True,
            "development_only": True,
            "public_input": {
                "task": "grounded_finalization",
                "condition": "public_fictional_complete",
                "question": (
                    "What shape is the fictional closed-world badge B1?"
                ),
                "public_claim_slots": [
                    {
                        "claim_handle": "public.slot.badge_shape",
                        "description": "The fictional badge shape.",
                    }
                ],
                "observed_evidence": [
                    {
                        "observation_id": "public.obs.badge.1",
                        "interval": {"start_s": 0.0, "end_s": 1.0},
                        "modalities": ["vision"],
                        "payload": {
                            "text": "The fictional badge B1 is octagonal."
                        },
                    }
                ],
            },
        },
    ]
    if len(packets) != MAX_CASES:
        raise AssertionError("smoke packet count drift")
    for packet in packets:
        validate_public_packet(packet)
    return packets


def claim_handles(packet: Mapping[str, Any]) -> list[str]:
    return [
        str(item["claim_handle"])
        for item in packet["public_input"]["public_claim_slots"]
    ]


def factor_spec(packet: Mapping[str, Any], factor_name: str) -> FactorSpec:
    handles = claim_handles(packet)
    if packet["case_type"] == "controller":
        if factor_name == "action_choice":
            plan = build_native_action_plan(packet["public_input"]["action_menu"])
            return action_choice_spec(plan)
        if factor_name == "evidence_state":
            return evidence_state_spec(handles)
    if packet["case_type"] == "finalizer":
        observation_ids = [
            str(item["observation_id"])
            for item in packet["public_input"]["observed_evidence"]
        ]
        return finalizer_factor_specs(
            claim_handles=handles,
            observation_ids=observation_ids,
        )[factor_name]
    raise ExternalGatewayError(f"FACTOR_SPEC_UNSUPPORTED:{factor_name}")


def _factor_validator(packet: Mapping[str, Any], factor_name: str) -> Any:
    handles = claim_handles(packet)
    if packet["case_type"] == "controller":
        if factor_name == "action_choice":
            plan = build_native_action_plan(packet["public_input"]["action_menu"])
            return lambda value: _parse_action_choice(value, plan=plan)
        if factor_name == "evidence_state":
            return lambda value: _parse_evidence_state(
                value,
                claim_handles=handles,
            )
    if packet["case_type"] == "finalizer":
        observation_ids = [
            str(item["observation_id"])
            for item in packet["public_input"]["observed_evidence"]
        ]
        validators = {
            "disposition": _parse_disposition,
            "answer_text": _parse_answer_text,
            "claim_drafts": lambda value: _parse_claim_drafts(
                value,
                claim_handles=handles,
            ),
            "citation_selections": lambda value: _parse_citation_selections(
                value,
                claim_handles=handles,
                observation_ids=observation_ids,
            ),
            "diagnosis": _parse_diagnosis,
        }
        return validators[factor_name]
    raise ExternalGatewayError(f"FACTOR_VALIDATOR_UNSUPPORTED:{factor_name}")


def parse_factor_outcome(
    packet: Mapping[str, Any],
    factor_name: str,
    attempts: Sequence[RawFactorAttempt],
) -> Any:
    return parse_factor_attempts(
        factor_spec(packet, factor_name),
        attempts,
        _factor_validator(packet, factor_name),
    )


def model_catalog_record(
    catalog_path: Path,
    slug: str,
) -> tuple[dict[str, Any], str, str]:
    raw = catalog_path.read_bytes()
    catalog = json.loads(raw)
    if not isinstance(catalog, Mapping) or not isinstance(
        catalog.get("models"), list
    ):
        raise ExternalGatewayError("MODEL_CATALOG_INVALID")
    matches = [
        row
        for row in catalog["models"]
        if isinstance(row, Mapping) and row.get("slug") == slug
    ]
    if len(matches) != 1:
        raise ExternalGatewayError(f"MODEL_SLUG_NOT_UNIQUE:{slug}")
    row = dict(matches[0])
    return (
        row,
        sha256_bytes(raw),
        sha256_bytes(canonical_json_bytes(row)),
    )


def tcodex_version() -> dict[str, str]:
    completed = subprocess.run(
        ["tcodex", "--version"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=30,
    )
    text = completed.stdout.decode("utf-8", errors="replace")
    values: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("@tencent/tcodex "):
            values["tcodex_version"] = line.split()[1]
        elif line.strip().startswith("commit:"):
            values["tcodex_commit"] = line.split(":", 1)[1].strip()
        elif line.strip().startswith("built:"):
            values["tcodex_built"] = line.split(":", 1)[1].strip()
        elif line.startswith("@openai/codex "):
            values["upstream_codex_version"] = line.split()[1]
    required = {
        "tcodex_version",
        "tcodex_commit",
        "tcodex_built",
        "upstream_codex_version",
    }
    if set(values) != required:
        raise ExternalGatewayError("TCODEX_VERSION_PARSE_FAILED")
    return values


def _tcodex_package_paths() -> tuple[Path, Path]:
    executable = Path(shutil.which("tcodex") or "")
    if not executable:
        raise ExternalGatewayError("TCODEX_NOT_FOUND")
    resolved = executable.resolve()
    package_root = resolved.parents[1]
    wrapper = package_root / "dist/tcodex.js"
    native = (
        package_root
        / "node_modules/@openai/codex-linux-x64/vendor/"
        "x86_64-unknown-linux-musl/bin/codex"
    )
    if not wrapper.is_file() or not native.is_file():
        raise ExternalGatewayError("TCODEX_RUNTIME_FILES_NOT_FOUND")
    return wrapper, native


def runtime_binding(registry: Mapping[str, Any], slug: str) -> dict[str, Any]:
    allowed = registry["models"]["allowed_slugs"]
    if slug not in allowed:
        raise ExternalGatewayError("MODEL_SLUG_NOT_ALLOWED")
    versions = tcodex_version()
    wrapper, native = _tcodex_package_paths()
    binding = {
        "model_slug": slug,
        "catalog_capture_policy": (
            "WRAPPER_SELECTED_PER_INVOCATION_FAIL_CLOSED"
        ),
        "catalog_record_sha256": None,
        "catalog_file_sha256": None,
        "catalog_archive_path": None,
        "catalog_wrapper_path_observed": False,
        "catalog_selected_model_evidenced": False,
        "wrapper_binding_observed": False,
        "wrapper_model_provider": None,
        "wrapper_provider_name": None,
        "wrapper_wire_api": None,
        "wrapper_base_url_scheme": None,
        "wrapper_base_url_host": None,
        "wrapper_dynamic_port_observed": False,
        "wrapper_selected_model": None,
        "observed_invocations": [],
        "tcodex_path": str(Path(shutil.which("tcodex") or "").resolve()),
        "tcodex_wrapper_sha256": sha256_file(wrapper),
        "upstream_codex_binary_sha256": sha256_file(native),
        **versions,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }
    expected = registry["runtime_binding"]
    for key in (
        "tcodex_version",
        "tcodex_commit",
        "upstream_codex_version",
        "tcodex_wrapper_sha256",
        "upstream_codex_binary_sha256",
    ):
        if binding[key] != expected[key]:
            raise ExternalGatewayError(f"RUNTIME_BINDING_MISMATCH:{key}")
    return binding


def _config_values(argv: Sequence[str]) -> list[str]:
    values: list[str] = []
    index = 0
    while index < len(argv):
        if argv[index] == "-c":
            if index + 1 >= len(argv):
                raise ExternalGatewayError("TCODEX_CHILD_CONFIG_VALUE_MISSING")
            values.append(str(argv[index + 1]))
            index += 2
            continue
        index += 1
    return values


def _single_config_match(
    values: Sequence[str],
    pattern: re.Pattern[str],
    error_code: str,
) -> re.Match[str]:
    matches = [match for value in values if (match := pattern.fullmatch(value))]
    if len(matches) != 1:
        raise ExternalGatewayError(error_code)
    return matches[0]


def _selected_models(
    argv: Sequence[str],
    configs: Sequence[str],
) -> list[str]:
    models = [
        match.group("model")
        for value in configs
        if (match := MODEL_CONFIG_RE.fullmatch(value))
    ]
    index = 0
    while index < len(argv):
        value = argv[index]
        if value in {"--model", "-m"}:
            if index + 1 >= len(argv):
                raise ExternalGatewayError("TCODEX_SELECTED_MODEL_VALUE_MISSING")
            models.append(str(argv[index + 1]))
            index += 2
            continue
        if value.startswith("--model="):
            models.append(value.split("=", 1)[1])
        index += 1
    return models


def capture_wrapper_binding(
    *,
    child_argv: Sequence[str],
    expected_slug: str,
    catalog_archive_path: Path,
) -> dict[str, Any]:
    """Archive and validate tcodex's exact per-invocation child binding."""

    configs = _config_values(child_argv)
    catalog_match = _single_config_match(
        configs,
        MODEL_CATALOG_CONFIG_RE,
        "TCODEX_MODEL_CATALOG_BINDING_NOT_EVIDENCED",
    )
    provider_match = _single_config_match(
        configs,
        MODEL_PROVIDER_CONFIG_RE,
        "TCODEX_MODEL_PROVIDER_NOT_EVIDENCED",
    )
    provider_binding_match = _single_config_match(
        configs,
        PROVIDER_BINDING_CONFIG_RE,
        "TCODEX_PROVIDER_BINDING_NOT_EVIDENCED",
    )
    provider = provider_match.group("provider")
    if provider != provider_binding_match.group("provider"):
        raise ExternalGatewayError("TCODEX_MODEL_PROVIDER_BINDING_MISMATCH")
    if provider != WRAPPER_PROVIDER_ID:
        raise ExternalGatewayError("TCODEX_MODEL_PROVIDER_UNEXPECTED")
    if provider_binding_match.group("name") != WRAPPER_PROVIDER_NAME:
        raise ExternalGatewayError("TCODEX_PROVIDER_NAME_UNEXPECTED")
    if provider_binding_match.group("wire_api") != WRAPPER_WIRE_API:
        raise ExternalGatewayError("TCODEX_WIRE_API_UNEXPECTED")
    selected_models = _selected_models(child_argv, configs)
    if len(selected_models) != 1:
        raise ExternalGatewayError("TCODEX_SELECTED_MODEL_NOT_EVIDENCED")
    selected_model = selected_models[0]
    if selected_model != expected_slug:
        raise ExternalGatewayError("TCODEX_SELECTED_MODEL_MISMATCH")
    base_url = provider_binding_match.group("base_url")
    base_url_match = re.fullmatch(
        r"http://(?P<host>127\.0\.0\.1):(?P<port>[1-9][0-9]{0,4})",
        base_url,
    )
    if base_url_match is None or int(base_url_match.group("port")) > 65535:
        raise ExternalGatewayError("TCODEX_DYNAMIC_GATEWAY_BINDING_INVALID")
    catalog_path = Path(catalog_match.group("path"))
    if not catalog_path.is_file():
        raise ExternalGatewayError("TCODEX_SELECTED_CATALOG_NOT_OBSERVABLE")
    catalog_bytes = catalog_path.read_bytes()
    catalog_hash = sha256_bytes(catalog_bytes)
    atomic_write(catalog_archive_path, catalog_bytes)
    if sha256_file(catalog_archive_path) != catalog_hash:
        raise ExternalGatewayError("TCODEX_CATALOG_ARCHIVE_HASH_MISMATCH")
    try:
        catalog = json.loads(catalog_bytes)
    except json.JSONDecodeError as exc:
        raise ExternalGatewayError("MODEL_CATALOG_INVALID") from exc
    if not isinstance(catalog, Mapping) or not isinstance(
        catalog.get("models"), list
    ):
        raise ExternalGatewayError("MODEL_CATALOG_INVALID")
    matches = [
        item
        for item in catalog["models"]
        if isinstance(item, Mapping) and item.get("slug") == expected_slug
    ]
    if len(matches) != 1:
        raise ExternalGatewayError(f"MODEL_SLUG_NOT_UNIQUE:{expected_slug}")
    row = dict(matches[0])
    row_hash = sha256_bytes(canonical_json_bytes(row))
    recorded_archive_path = (
        str(catalog_archive_path.relative_to(ROOT))
        if catalog_archive_path.is_relative_to(ROOT)
        else str(catalog_archive_path)
    )
    return {
        "model_slug": expected_slug,
        "catalog_display_name": row.get("display_name"),
        "catalog_description": row.get("description"),
        "catalog_record_sha256": row_hash,
        "catalog_file_sha256": catalog_hash,
        "catalog_archive_path": recorded_archive_path,
        "catalog_wrapper_path_observed": True,
        "catalog_selected_model_evidenced": True,
        "wrapper_binding_observed": True,
        "wrapper_model_provider": provider,
        "wrapper_provider_name": provider_binding_match.group("name"),
        "wrapper_wire_api": provider_binding_match.group("wire_api"),
        "wrapper_base_url_scheme": "http",
        "wrapper_base_url_host": base_url_match.group("host"),
        "wrapper_dynamic_port_observed": True,
        "wrapper_selected_model": selected_model,
        "catalog_supported_in_api": row.get("supported_in_api"),
        "catalog_visibility": row.get("visibility"),
        "catalog_context_window": row.get("context_window"),
        "catalog_input_modalities": row.get("input_modalities"),
        "catalog_supported_reasoning_efforts": [
            item.get("effort")
            for item in row.get("supported_reasoning_levels", [])
            if isinstance(item, Mapping)
        ],
        "catalog_captured_at": utc_now(),
    }


def _factor_instruction(factor_name: str) -> str:
    if factor_name == "action_choice":
        return (
            "Return exactly one compact JSON object with keys "
            "\"function_name\" and \"arguments\". Choose the matching "
            "select_action_NN name for one exact listed action. arguments "
            "must be {}. Do not return prose or markdown."
        )
    return (
        "Return exactly one compact JSON object and no prose or markdown. "
        "Match the displayed schema exactly. Author only this factor and do "
        "not assume, fill, or repair another factor."
    )


def factor_prompt(
    packet: Mapping[str, Any],
    factor_name: str,
    *,
    previous_raw: str | None = None,
    previous_error: str | None = None,
) -> str:
    """Render a prompt containing only the validated public packet."""

    validate_public_packet(packet)
    spec = factor_spec(packet, factor_name)
    payload: dict[str, Any] = {
        "privacy_boundary": (
            "PUBLIC_FICTIONAL_SOURCE_FREE_DEVELOPMENT_PACKET_ONLY"
        ),
        "factor_id": factor_name,
        "factor_role": spec.role,
        "output_schema": spec.output_schema,
        "public_case": {
            "case_type": packet["case_type"],
            "public_input": packet["public_input"],
        },
    }
    instruction = _factor_instruction(factor_name)
    if previous_raw is not None:
        instruction += (
            " This is the sole schema-only retry. Preserve every semantic "
            "scalar from the prior attempt exactly and change only JSON or "
            "schema representation. Do not choose a different action, answer, "
            "claim, citation, diagnosis, enum, or probability. If a "
            "content-preserving schema repair is impossible, repeat the prior "
            "content rather than inventing substitute semantics."
        )
        payload["schema_only_retry"] = {
            "prior_error_code": previous_error,
            "prior_raw_output": previous_raw,
        }
    prompt = (
        "You are a schema-bound factor author for a fictional public "
        "development packet. You have no external tools. Use only the JSON "
        "shown below. Never infer hidden labels or external facts. "
        + instruction
        + "\n\n"
        + json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    if any(term in prompt for term in ("scoring_target", "private_labels")):
        raise ExternalGatewayError("PRIVATE_LABEL_PROMPT_EXPOSURE")
    return prompt


def tcodex_exec_command(
    *,
    model_slug: str,
    reasoning_effort: str,
    prompt_path: Path,
    output_path: Path,
    workspace: Path,
) -> list[str]:
    command = [
        "tcodex",
        "--",
        "-a",
        "never",
        "-s",
        "read-only",
        "-C",
        str(workspace),
        "exec",
        "--skip-git-repo-check",
        "--color",
        "never",
        "--model",
        model_slug,
        "-c",
        f'model_reasoning_effort="{reasoning_effort}"',
        "-c",
        'model_verbosity="low"',
        "-c",
        "check_for_update_on_startup=false",
        "-c",
        "analytics.enabled=false",
        "-o",
        str(output_path),
    ]
    for feature in DISABLED_FEATURES:
        command.extend(("-c", f"features.{feature}=false"))
    command.extend(("-",))
    if not prompt_path.is_file():
        raise ExternalGatewayError("PROMPT_FILE_NOT_WRITTEN")
    return command


def _process_parent_pid(path: Path) -> int | None:
    try:
        value = (path / "stat").read_text(encoding="utf-8")
        suffix = value[value.rfind(")") + 2 :].split()
        return int(suffix[1])
    except (OSError, ValueError, IndexError):
        return None


def _process_argv(path: Path) -> list[str] | None:
    try:
        raw = (path / "cmdline").read_bytes()
    except OSError:
        return None
    argv = [
        item.decode("utf-8", errors="surrogateescape")
        for item in raw.split(b"\0")
        if item
    ]
    return argv or None


def _tcodex_child_argv(wrapper_pid: int) -> list[str] | None:
    process_rows: dict[int, tuple[int, Path]] = {}
    try:
        process_paths = tuple(Path("/proc").iterdir())
    except OSError as exc:
        raise ExternalGatewayError("TCODEX_PROCESS_TREE_NOT_OBSERVABLE") from exc
    for path in process_paths:
        if not path.name.isdigit():
            continue
        parent_pid = _process_parent_pid(path)
        if parent_pid is not None:
            process_rows[int(path.name)] = (parent_pid, path)
    descendants = {wrapper_pid}
    changed = True
    while changed:
        changed = False
        for pid, (parent_pid, _) in process_rows.items():
            if parent_pid in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    candidates: list[list[str]] = []
    for pid in descendants - {wrapper_pid}:
        row = process_rows.get(pid)
        argv = _process_argv(row[1]) if row else None
        if not argv:
            continue
        configs = _config_values(argv)
        if any(MODEL_CATALOG_CONFIG_RE.fullmatch(item) for item in configs):
            candidates.append(argv)
    if len(candidates) > 1:
        raise ExternalGatewayError("TCODEX_CHILD_BINDING_AMBIGUOUS")
    return candidates[0] if candidates else None


def observe_tcodex_binding(
    *,
    process: subprocess.Popen[bytes],
    expected_slug: str,
    catalog_archive_path: Path,
    argv_archive_path: Path,
    timeout_seconds: float = PROVENANCE_WAIT_SECONDS,
) -> dict[str, Any]:
    """Observe tcodex's live native child before releasing the prompt."""

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        child_argv = _tcodex_child_argv(process.pid)
        if child_argv is not None:
            atomic_json(argv_archive_path, {"argv": child_argv})
            observed = capture_wrapper_binding(
                child_argv=child_argv,
                expected_slug=expected_slug,
                catalog_archive_path=catalog_archive_path,
            )
            observed["wrapper_child_argv_archive_path"] = (
                str(argv_archive_path.relative_to(ROOT))
                if argv_archive_path.is_relative_to(ROOT)
                else str(argv_archive_path)
            )
            return observed
        if process.poll() is not None:
            break
        time.sleep(PROVENANCE_POLL_SECONDS)
    raise ExternalGatewayError("TCODEX_CHILD_ARGV_NOT_OBSERVED")


def _attempt_record(
    *,
    packet: Mapping[str, Any],
    factor_name: str,
    attempt_index: int,
    command: Sequence[str],
    prompt: bytes,
    raw_output: bytes,
    stdout: bytes,
    stderr: bytes,
    returncode: int,
    elapsed_seconds: float,
    binding: Mapping[str, Any],
    transport_error_code: str | None = None,
    cleanup: Mapping[str, Any] | None = None,
    provenance_artifacts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    gateway_success = (
        transport_error_code is None
        and returncode == 0
        and bool(raw_output.strip())
    )
    return {
        "schema_version": ATTEMPT_SCHEMA,
        "attempt_id": (
            f"{packet['case_id']}::{factor_name}::{attempt_index}"
        ),
        "case_id": packet["case_id"],
        "case_type": packet["case_type"],
        "factor_name": factor_name,
        "attempt_index": attempt_index,
        "attempt_kind": (
            AttemptKind.INITIAL.value
            if attempt_index == 1
            else AttemptKind.SCHEMA_ONLY_RETRY.value
        ),
        "model_slug": binding["model_slug"],
        "catalog_record_sha256": binding["catalog_record_sha256"],
        "catalog_file_sha256": binding["catalog_file_sha256"],
        "catalog_archive_path": binding["catalog_archive_path"],
        "runtime": {
            "tcodex_version": binding["tcodex_version"],
            "tcodex_commit": binding["tcodex_commit"],
            "upstream_codex_version": binding["upstream_codex_version"],
            "tcodex_wrapper_sha256": binding["tcodex_wrapper_sha256"],
            "upstream_codex_binary_sha256": (
                binding["upstream_codex_binary_sha256"]
            ),
        },
        "command_argv": list(command),
        "prompt_sha256": sha256_bytes(prompt),
        "prompt_bytes": len(prompt),
        "raw_output": raw_output.decode("utf-8", errors="replace"),
        "raw_output_sha256": sha256_bytes(raw_output),
        "raw_output_bytes": len(raw_output),
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stdout_sha256": sha256_bytes(stdout),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "stderr_sha256": sha256_bytes(stderr),
        "returncode": returncode,
        "elapsed_seconds": elapsed_seconds,
        "gateway_success": gateway_success,
        "transport_failure": transport_error_code is not None,
        "transport_error_code": transport_error_code,
        "model_output_accepted": gateway_success,
        "cleanup": dict(cleanup or {}),
        "provenance_artifacts": dict(provenance_artifacts or {}),
    }


def _bytes_or_empty(value: bytes | str | None) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8", errors="replace")


def _prefer_complete_output(first: bytes, second: bytes) -> bytes:
    if not first:
        return second
    if not second:
        return first
    if second.startswith(first):
        return second
    if first.startswith(second):
        return first
    return first + second


def _close_pipe(pipe: Any) -> bool:
    if pipe is None:
        return False
    try:
        pipe.close()
    except OSError:
        return False
    return True


def _terminate_process_group(
    process: subprocess.Popen[bytes],
    *,
    initial_stdout: bytes = b"",
    initial_stderr: bytes = b"",
    terminate_wait_seconds: float = PROCESS_TERM_WAIT_SECONDS,
    kill_wait_seconds: float = PROCESS_KILL_WAIT_SECONDS,
    drain_wait_seconds: float = PROCESS_PIPE_DRAIN_SECONDS,
) -> tuple[bytes, bytes, dict[str, Any]]:
    """Bound cleanup of the invocation session, including pipe descendants."""

    stdout = initial_stdout
    stderr = initial_stderr
    cleanup: dict[str, Any] = {
        "process_group_id": process.pid,
        "terminate_group_sent": False,
        "terminate_wait_timed_out": False,
        "kill_group_sent": False,
        "kill_wait_timed_out": False,
        "pipe_drain_timed_out": False,
        "pipes_forcibly_closed": False,
    }
    _close_pipe(process.stdin)
    process.stdin = None
    try:
        os.killpg(process.pid, signal.SIGTERM)
        cleanup["terminate_group_sent"] = True
    except ProcessLookupError:
        cleanup["terminate_group_absent"] = True
    except OSError as exc:
        cleanup["terminate_group_error"] = type(exc).__name__
    try:
        process.wait(timeout=terminate_wait_seconds)
    except subprocess.TimeoutExpired:
        cleanup["terminate_wait_timed_out"] = True
    except OSError as exc:
        cleanup["terminate_wait_error"] = type(exc).__name__

    # Always address the whole group with SIGKILL after the grace period.
    # The wrapper may already have exited while a descendant still owns pipes.
    try:
        os.killpg(process.pid, signal.SIGKILL)
        cleanup["kill_group_sent"] = True
    except ProcessLookupError:
        cleanup["kill_group_absent"] = True
    except OSError as exc:
        cleanup["kill_group_error"] = type(exc).__name__
    try:
        process.wait(timeout=kill_wait_seconds)
    except subprocess.TimeoutExpired:
        cleanup["kill_wait_timed_out"] = True
    except OSError as exc:
        cleanup["kill_wait_error"] = type(exc).__name__

    try:
        drained_stdout, drained_stderr = process.communicate(
            timeout=drain_wait_seconds
        )
        stdout = _prefer_complete_output(
            stdout,
            _bytes_or_empty(drained_stdout),
        )
        stderr = _prefer_complete_output(
            stderr,
            _bytes_or_empty(drained_stderr),
        )
    except subprocess.TimeoutExpired as exc:
        cleanup["pipe_drain_timed_out"] = True
        stdout = _prefer_complete_output(
            stdout,
            _bytes_or_empty(exc.stdout),
        )
        stderr = _prefer_complete_output(
            stderr,
            _bytes_or_empty(exc.stderr),
        )
        closed_stdout = _close_pipe(process.stdout)
        closed_stderr = _close_pipe(process.stderr)
        cleanup["pipes_forcibly_closed"] = closed_stdout or closed_stderr
    except (OSError, ValueError) as exc:
        cleanup["pipe_drain_error"] = type(exc).__name__
        closed_stdout = _close_pipe(process.stdout)
        closed_stderr = _close_pipe(process.stderr)
        cleanup["pipes_forcibly_closed"] = closed_stdout or closed_stderr
    cleanup["returncode_after_cleanup"] = process.returncode
    return stdout, stderr, cleanup


def _artifact_record(path: Path) -> dict[str, Any]:
    recorded_path = (
        str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    )
    if not path.is_file():
        return {"path": recorded_path, "exists": False}
    return {
        "path": recorded_path,
        "exists": True,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def invoke_tcodex(
    *,
    packet: Mapping[str, Any],
    factor_name: str,
    attempt_index: int,
    prompt: str,
    binding: Mapping[str, Any],
    registry: Mapping[str, Any],
    run_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    factor_key = f"{packet['case_id']}__{factor_name}__{attempt_index}"
    prompt_path = run_dir / "prompts" / f"{factor_key}.txt"
    raw_path = run_dir / "raw" / f"{factor_key}.txt"
    catalog_archive_path = (
        run_dir / "provenance" / "catalogs" / f"{factor_key}.json"
    )
    argv_archive_path = (
        run_dir / "provenance" / "child_argv" / f"{factor_key}.json"
    )
    workspace = run_dir / "empty_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    prompt_bytes = prompt.encode("utf-8")
    atomic_write(prompt_path, prompt_bytes)
    command = tcodex_exec_command(
        model_slug=str(binding["model_slug"]),
        reasoning_effort=str(registry["execution"]["reasoning_effort"]),
        prompt_path=prompt_path,
        output_path=raw_path,
        workspace=workspace,
    )
    started = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    stdout = b""
    stderr = b""
    cleanup: dict[str, Any] = {}
    transport_error_code: str | None = None
    returncode = 125
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=ROOT,
            start_new_session=True,
        )
        observed = observe_tcodex_binding(
            process=process,
            expected_slug=str(binding["model_slug"]),
            catalog_archive_path=catalog_archive_path,
            argv_archive_path=argv_archive_path,
        )
        if isinstance(binding, dict):
            prior_hash = binding.get("catalog_file_sha256")
            if prior_hash is not None and prior_hash != observed[
                "catalog_file_sha256"
            ]:
                raise ExternalGatewayError("TCODEX_CATALOG_CHANGED_WITHIN_RUN")
            binding.update(observed)
            binding.setdefault("observed_invocations", []).append(
                {
                    "attempt_id": (
                        f"{packet['case_id']}::{factor_name}::{attempt_index}"
                    ),
                    "catalog_file_sha256": observed["catalog_file_sha256"],
                    "catalog_record_sha256": observed[
                        "catalog_record_sha256"
                    ],
                    "catalog_archive_path": observed["catalog_archive_path"],
                    "wrapper_child_argv_archive_path": observed[
                        "wrapper_child_argv_archive_path"
                    ],
                    "selected_model": observed["wrapper_selected_model"],
                }
            )
        else:
            raise ExternalGatewayError("RUNTIME_BINDING_NOT_MUTABLE")
        stdout, stderr = process.communicate(
            input=prompt_bytes,
            timeout=timeout_seconds,
        )
        returncode = process.returncode
    except subprocess.TimeoutExpired as exc:
        if process is not None:
            stdout, stderr, cleanup = _terminate_process_group(
                process,
                initial_stdout=_bytes_or_empty(exc.stdout),
                initial_stderr=_bytes_or_empty(exc.stderr),
            )
        returncode = 124
        transport_error_code = "TCODEX_TIMEOUT"
        stderr += b"\nTCODEX_TIMEOUT\n"
    except Exception as exc:  # noqa: BLE001 - preserve audit state on any failure
        if process is not None:
            stdout, stderr, cleanup = _terminate_process_group(process)
        transport_error_code = (
            str(exc)
            if isinstance(exc, ExternalGatewayError)
            else f"TCODEX_INVOCATION_ERROR:{type(exc).__name__}"
        )
        stderr += (
            f"\n{transport_error_code}\n".encode(
                "utf-8",
                errors="replace",
            )
        )
        returncode = 125
    if (
        transport_error_code is None
        and returncode is not None
        and returncode != 0
    ):
        transport_error_code = f"TCODEX_NONZERO_EXIT:{returncode}"
        if process is not None:
            extra_stdout, extra_stderr, cleanup = _terminate_process_group(
                process,
                initial_stdout=_bytes_or_empty(stdout),
                initial_stderr=_bytes_or_empty(stderr),
            )
            stdout, stderr = extra_stdout, extra_stderr
    if returncode is None:
        returncode = 125
        transport_error_code = "TCODEX_RETURN_CODE_UNAVAILABLE"
    elapsed = time.monotonic() - started
    raw = raw_path.read_bytes() if raw_path.exists() else b""
    provenance_artifacts = {
        "catalog": _artifact_record(catalog_archive_path),
        "child_argv": _artifact_record(argv_archive_path),
        "raw_output": _artifact_record(raw_path),
    }
    return _attempt_record(
        packet=packet,
        factor_name=factor_name,
        attempt_index=attempt_index,
        command=command,
        prompt=prompt_bytes,
        raw_output=raw,
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        elapsed_seconds=elapsed,
        binding=binding,
        transport_error_code=transport_error_code,
        cleanup=cleanup,
        provenance_artifacts=provenance_artifacts,
    )


def _record_to_attempt(record: Mapping[str, Any]) -> RawFactorAttempt:
    return RawFactorAttempt.from_text(
        str(record["raw_output"]),
        attempt_index=int(record["attempt_index"]),
        kind=(
            AttemptKind.INITIAL
            if int(record["attempt_index"]) == 1
            else AttemptKind.SCHEMA_ONLY_RETRY
        ),
    )


def _result_for_packet(
    packet: Mapping[str, Any],
    attempts: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Any:
    converted = {
        name: tuple(_record_to_attempt(item) for item in records)
        for name, records in attempts.items()
    }
    handles = claim_handles(packet)
    if packet["case_type"] == "controller":
        return parse_controller_factors(
            action_menu=packet["public_input"]["action_menu"],
            claim_handles=handles,
            observed_evidence=packet["public_input"]["observed_evidence"],
            action_attempts=converted["action_choice"],
            evidence_state_attempts=converted["evidence_state"],
        )
    return parse_finalizer_factors(
        claim_handles=handles,
        observations=packet["public_input"]["observed_evidence"],
        attempts_by_factor=converted,
    )


def _factor_status(result: Any, factor_name: str) -> Any:
    if factor_name == "action_choice":
        return result.action_factor
    if factor_name == "evidence_state":
        return result.evidence_state_factor
    return result.factors[factor_name]


def run_smoke(
    *,
    root: Path,
    registry: Mapping[str, Any],
    model_slug: str,
    output_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    packets = public_smoke_packets()
    if len(packets) != MAX_CASES:
        raise ExternalGatewayError("SMOKE_CASE_COUNT_MISMATCH")
    binding = runtime_binding(registry, model_slug)
    run_id = "task201-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / run_id
    if run_dir.exists():
        raise ExternalGatewayError("RUN_DIRECTORY_EXISTS")
    run_dir.mkdir(parents=True, mode=0o700)
    attempts_by_case: dict[str, dict[str, list[dict[str, Any]]]] = {}
    case_results: list[dict[str, Any]] = []
    all_attempts: list[dict[str, Any]] = []
    run_failures: list[dict[str, Any]] = []
    transport_halted = False

    for packet in packets:
        case_id = str(packet["case_id"])
        case_attempts: dict[str, list[dict[str, Any]]] = {}
        attempts_by_case[case_id] = case_attempts
        factor_names = FACTOR_ORDER[str(packet["case_type"])]
        factor_rows: dict[str, dict[str, Any]] = {}
        if transport_halted:
            for factor_name in factor_names:
                factor_rows[factor_name] = {
                    "status": "NOT_INVOKED_AFTER_TRANSPORT_FAILURE",
                    "error_code": "RUN_HALTED_AFTER_TRANSPORT_FAILURE",
                    "attempt_count": 0,
                    "schema_retries_used": 0,
                    "raw_output_sha256s": [],
                }
            case_results.append(
                {
                    "case_id": case_id,
                    "case_type": packet["case_type"],
                    "public_packet_sha256": sha256_bytes(
                        canonical_json_bytes(packet)
                    ),
                    "factors": factor_rows,
                    "projection_status": "NOT_COMPUTED",
                    "projection_error_code": (
                        "RUN_HALTED_AFTER_TRANSPORT_FAILURE"
                    ),
                    "canonical_output": None,
                }
            )
            continue
        for factor_index, factor_name in enumerate(factor_names):
            first_prompt = factor_prompt(packet, factor_name)
            try:
                first = invoke_tcodex(
                    packet=packet,
                    factor_name=factor_name,
                    attempt_index=1,
                    prompt=first_prompt,
                    binding=binding,
                    registry=registry,
                    run_dir=run_dir,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001 - emit fail-closed report
                error_code = (
                    str(exc)
                    if isinstance(exc, ExternalGatewayError)
                    else f"INVOCATION_RECORDING_ERROR:{type(exc).__name__}"
                )
                run_failures.append(
                    {
                        "case_id": case_id,
                        "factor_name": factor_name,
                        "attempt_index": 1,
                        "error_code": error_code,
                    }
                )
                factor_rows[factor_name] = {
                    "status": "TRANSPORT_FAILURE",
                    "error_code": error_code,
                    "attempt_count": 0,
                    "schema_retries_used": 0,
                    "raw_output_sha256s": [],
                }
                for remaining in factor_names[factor_index + 1 :]:
                    factor_rows[remaining] = {
                        "status": "NOT_INVOKED_AFTER_TRANSPORT_FAILURE",
                        "error_code": "RUN_HALTED_AFTER_TRANSPORT_FAILURE",
                        "attempt_count": 0,
                        "schema_retries_used": 0,
                        "raw_output_sha256s": [],
                    }
                transport_halted = True
                break
            case_attempts[factor_name] = [first]
            all_attempts.append(first)
            if first.get("transport_failure") is True:
                error_code = str(
                    first.get("transport_error_code")
                    or "TCODEX_TRANSPORT_FAILURE"
                )
                run_failures.append(
                    {
                        "case_id": case_id,
                        "factor_name": factor_name,
                        "attempt_index": 1,
                        "error_code": error_code,
                    }
                )
                factor_rows[factor_name] = {
                    "status": "TRANSPORT_FAILURE",
                    "error_code": error_code,
                    "attempt_count": 1,
                    "schema_retries_used": 0,
                    "raw_output_sha256s": [first["raw_output_sha256"]],
                }
                for remaining in factor_names[factor_index + 1 :]:
                    factor_rows[remaining] = {
                        "status": "NOT_INVOKED_AFTER_TRANSPORT_FAILURE",
                        "error_code": "RUN_HALTED_AFTER_TRANSPORT_FAILURE",
                        "attempt_count": 0,
                        "schema_retries_used": 0,
                        "raw_output_sha256s": [],
                    }
                transport_halted = True
                break
            outcome = parse_factor_outcome(
                packet,
                factor_name,
                (_record_to_attempt(first),),
            )
            if (
                first["gateway_success"]
                and outcome.status is FactorStatus.INVALID_OUTPUT
                and outcome.error_code
                in factor_spec(packet, factor_name).repairable_error_codes
            ):
                retry_prompt = factor_prompt(
                    packet,
                    factor_name,
                    previous_raw=str(first["raw_output"]),
                    previous_error=str(outcome.error_code),
                )
                try:
                    retry = invoke_tcodex(
                        packet=packet,
                        factor_name=factor_name,
                        attempt_index=2,
                        prompt=retry_prompt,
                        binding=binding,
                        registry=registry,
                        run_dir=run_dir,
                        timeout_seconds=timeout_seconds,
                    )
                except Exception as exc:  # noqa: BLE001 - preserve report
                    error_code = (
                        str(exc)
                        if isinstance(exc, ExternalGatewayError)
                        else (
                            "INVOCATION_RECORDING_ERROR:"
                            f"{type(exc).__name__}"
                        )
                    )
                    run_failures.append(
                        {
                            "case_id": case_id,
                            "factor_name": factor_name,
                            "attempt_index": 2,
                            "error_code": error_code,
                        }
                    )
                    factor_rows[factor_name] = {
                        "status": "TRANSPORT_FAILURE",
                        "error_code": error_code,
                        "attempt_count": 1,
                        "schema_retries_used": 0,
                        "raw_output_sha256s": [
                            first["raw_output_sha256"],
                        ],
                    }
                    for remaining in factor_names[factor_index + 1 :]:
                        factor_rows[remaining] = {
                            "status": (
                                "NOT_INVOKED_AFTER_TRANSPORT_FAILURE"
                            ),
                            "error_code": (
                                "RUN_HALTED_AFTER_TRANSPORT_FAILURE"
                            ),
                            "attempt_count": 0,
                            "schema_retries_used": 0,
                            "raw_output_sha256s": [],
                        }
                    transport_halted = True
                    break
                case_attempts[factor_name].append(retry)
                all_attempts.append(retry)
                if retry.get("transport_failure") is True:
                    error_code = str(
                        retry.get("transport_error_code")
                        or "TCODEX_TRANSPORT_FAILURE"
                    )
                    run_failures.append(
                        {
                            "case_id": case_id,
                            "factor_name": factor_name,
                            "attempt_index": 2,
                            "error_code": error_code,
                        }
                    )
                    factor_rows[factor_name] = {
                        "status": "TRANSPORT_FAILURE",
                        "error_code": error_code,
                        "attempt_count": 2,
                        "schema_retries_used": 1,
                        "raw_output_sha256s": [
                            first["raw_output_sha256"],
                            retry["raw_output_sha256"],
                        ],
                    }
                    for remaining in factor_names[factor_index + 1 :]:
                        factor_rows[remaining] = {
                            "status": (
                                "NOT_INVOKED_AFTER_TRANSPORT_FAILURE"
                            ),
                            "error_code": (
                                "RUN_HALTED_AFTER_TRANSPORT_FAILURE"
                            ),
                            "attempt_count": 0,
                            "schema_retries_used": 0,
                            "raw_output_sha256s": [],
                        }
                    transport_halted = True
                    break
                outcome = parse_factor_outcome(
                    packet,
                    factor_name,
                    tuple(
                        _record_to_attempt(item)
                        for item in case_attempts[factor_name]
                    ),
                )
            factor_rows[factor_name] = {
                "status": str(outcome.status),
                "error_code": outcome.error_code,
                "attempt_count": len(outcome.attempts),
                "schema_retries_used": outcome.schema_retries_used,
                "raw_output_sha256s": [
                    item.sha256 for item in outcome.attempts
                ],
            }

        if len(case_attempts) == len(factor_names) and not transport_halted:
            result = _result_for_packet(packet, case_attempts)
            for factor_name in factor_names:
                outcome = _factor_status(result, factor_name)
                factor_rows[factor_name] = {
                    "status": str(outcome.status),
                    "error_code": outcome.error_code,
                    "attempt_count": len(outcome.attempts),
                    "schema_retries_used": outcome.schema_retries_used,
                    "raw_output_sha256s": [
                        item.sha256 for item in outcome.attempts
                    ],
                }
            if packet["case_type"] == "controller":
                projection_status = str(result.state_projection.status)
                projection_error = result.state_projection.error_code
                canonical = result.canonical_decision
            else:
                projection_status = str(result.projection_status)
                projection_error = result.projection_error_code
                canonical = result.canonical_envelope
        else:
            projection_status = "NOT_COMPUTED"
            projection_error = (
                "TRANSPORT_FAILURE_PREVENTED_PROJECTION"
                if transport_halted
                else "INCOMPLETE_FACTOR_SET"
            )
            canonical = None
        case_results.append(
            {
                "case_id": case_id,
                "case_type": packet["case_type"],
                "public_packet_sha256": sha256_bytes(
                    canonical_json_bytes(packet)
                ),
                "factors": factor_rows,
                "projection_status": projection_status,
                "projection_error_code": projection_error,
                "canonical_output": jsonable(canonical),
            }
        )

    gateway_failures = sum(
        not bool(record["gateway_success"]) for record in all_attempts
    )
    transport_failures = sum(
        record.get("transport_failure") is True for record in all_attempts
    ) + sum(
        row["attempt_count"] == 0
        and row["status"] == "TRANSPORT_FAILURE"
        for case in case_results
        for row in case["factors"].values()
    )
    initial_attempts = sum(
        int(record["attempt_index"]) == 1 for record in all_attempts
    )
    schema_retries = len(all_attempts) - initial_attempts
    valid_factor_count = sum(
        row["status"] == str(FactorStatus.VALID)
        for case in case_results
        for row in case["factors"].values()
    )
    canonical_count = sum(
        case["canonical_output"] is not None for case in case_results
    )
    decision = (
        READY
        if gateway_failures == 0
        and not run_failures
        and all(
            len(case["factors"]) == len(FACTOR_ORDER[case["case_type"]])
            for case in case_results
        )
        else REPAIR
    )
    report = {
        "schema_version": RUNNER_SCHEMA,
        "task_id": 201,
        "run_id": run_id,
        "created_at": utc_now(),
        "decision_token": decision,
        "competence_claimed": False,
        "scientific_execution": False,
        "sealed_holdout_accessed": False,
        "case_count": len(packets),
        "case_ids": [packet["case_id"] for packet in packets],
        "case_types": [packet["case_type"] for packet in packets],
        "model_binding": binding,
        "execution": {
            "factorized_v2": True,
            "raw_output_preserved": True,
            "schema_only_retry_maximum_per_factor": 1,
            "schema_retries_used": schema_retries,
            "semantic_retries": 0,
            "semantic_repair": False,
            "semantic_substitution": False,
            "model_fallback_or_substitution": False,
            "tool_features_disabled": list(DISABLED_FEATURES),
            "transport_failures_are_model_outputs": False,
            "transport_failures_are_competence_claims": False,
        },
        "privacy_boundary": {
            "public_fictional_packets_only": True,
            "source_free": True,
            "development_only": True,
            "media_uploaded": False,
            "source_text_uploaded": False,
            "h2_labels_uploaded": False,
            "ses_uploaded": False,
            "triggers_uploaded": False,
            "evaluator_keys_uploaded": False,
            "scientific_data_uploaded": False,
        },
        "summary": {
            "gateway_failures": gateway_failures,
            "transport_failures": transport_failures,
            "run_failures": len(run_failures),
            "initial_attempts": initial_attempts,
            "schema_only_retries": schema_retries,
            "valid_factors": valid_factor_count,
            "total_factors": sum(
                len(case["factors"]) for case in case_results
            ),
            "canonical_outputs": canonical_count,
            "competence_metric_computed": False,
        },
        "cases": case_results,
        "failures": run_failures,
    }
    atomic_json(run_dir / "public_packets.json", {"packets": packets})
    atomic_json(run_dir / "raw_attempts.json", {"attempts": all_attempts})
    atomic_json(run_dir / "run_report.json", report)
    files = {
        name: {
            "sha256": sha256_file(run_dir / name),
            "bytes": (run_dir / name).stat().st_size,
        }
        for name in ("public_packets.json", "raw_attempts.json", "run_report.json")
    }
    manifest = {
        "schema_version": "av-trace.external-gateway-run-manifest/1.0",
        "run_id": run_id,
        "created_at": utc_now(),
        "files": files,
        "decision_token": decision,
    }
    atomic_json(run_dir / "manifest.json", manifest)
    for path in run_dir.rglob("*"):
        if path.is_file():
            os.chmod(path, 0o600)
        elif path.is_dir():
            os.chmod(path, 0o700)
    return report


def validate_registry(registry: Mapping[str, Any]) -> None:
    if registry.get("schema_version") != (
        "av-trace.external-gateway-strong-agent-registry/1.0"
    ):
        raise ExternalGatewayError("REGISTRY_SCHEMA_MISMATCH")
    if registry.get("task_id") not in {201, 202}:
        raise ExternalGatewayError("REGISTRY_TASK_MISMATCH")
    models = registry.get("models")
    if not isinstance(models, Mapping):
        raise ExternalGatewayError("REGISTRY_MODELS_INVALID")
    if models.get("primary", {}).get("slug") != "gpt-6-astra":
        raise ExternalGatewayError("PRIMARY_MODEL_MISMATCH")
    if models.get("backup", {}).get("slug") != "deepseek-v4-pro-ioa":
        raise ExternalGatewayError("BACKUP_MODEL_MISMATCH")
    if models.get("automatic_fallback") is not False:
        raise ExternalGatewayError("AUTOMATIC_FALLBACK_FORBIDDEN")
    privacy = registry.get("privacy_boundary")
    if not isinstance(privacy, Mapping):
        raise ExternalGatewayError("REGISTRY_PRIVACY_INVALID")
    if privacy.get("only_public_fictional_packets_until_approval") is not True:
        raise ExternalGatewayError("REGISTRY_PRIVACY_BOUNDARY_WEAK")
    forbidden = set(privacy.get("forbidden_uploads", []))
    required = {
        "media",
        "source_text",
        "H2_labels",
        "SESs",
        "triggers",
        "evaluator_keys",
        "scientific_or_restricted_source_data",
    }
    if not required.issubset(forbidden):
        raise ExternalGatewayError("REGISTRY_FORBIDDEN_UPLOADS_INCOMPLETE")
    execution = registry.get("execution")
    if not isinstance(execution, Mapping):
        raise ExternalGatewayError("REGISTRY_EXECUTION_INVALID")
    if execution.get("maximum_development_smoke_cases") != MAX_CASES:
        raise ExternalGatewayError("REGISTRY_SMOKE_COUNT_MISMATCH")
    if execution.get("sealed_holdout_authorized") is not False:
        raise ExternalGatewayError("SEALED_HOLDOUT_MUST_BE_UNAUTHORIZED")
    if execution.get("semantic_retries") != 0:
        raise ExternalGatewayError("SEMANTIC_RETRY_MUST_BE_ZERO")
    if execution.get("automatic_model_fallback") is not False:
        raise ExternalGatewayError("AUTOMATIC_MODEL_FALLBACK_FORBIDDEN")


def validate_delivered_smoke(
    root: Path,
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    smoke = registry.get("smoke")
    if not isinstance(smoke, Mapping):
        raise ExternalGatewayError("REGISTRY_SMOKE_INVALID")
    path_value = smoke.get("run_report_path")
    if not isinstance(path_value, str) or not path_value:
        raise ExternalGatewayError("SMOKE_RUN_REPORT_PATH_MISSING")
    path = root / path_value
    report = load_json(path)
    if report.get("case_count") != MAX_CASES:
        raise ExternalGatewayError("DELIVERED_SMOKE_CASE_COUNT_MISMATCH")
    if report.get("competence_claimed") is not False:
        raise ExternalGatewayError("COMPETENCE_CLAIM_FORBIDDEN")
    if report.get("sealed_holdout_accessed") is not False:
        raise ExternalGatewayError("SEALED_HOLDOUT_ACCESS_FORBIDDEN")
    privacy = report.get("privacy_boundary", {})
    if not isinstance(privacy, Mapping) or any(
        privacy.get(key) is not expected
        for key, expected in {
            "public_fictional_packets_only": True,
            "source_free": True,
            "development_only": True,
            "media_uploaded": False,
            "source_text_uploaded": False,
            "h2_labels_uploaded": False,
            "ses_uploaded": False,
            "triggers_uploaded": False,
            "evaluator_keys_uploaded": False,
            "scientific_data_uploaded": False,
        }.items()
    ):
        raise ExternalGatewayError("DELIVERED_SMOKE_PRIVACY_MISMATCH")
    if report.get("execution", {}).get("semantic_retries") != 0:
        raise ExternalGatewayError("DELIVERED_SMOKE_SEMANTIC_RETRY")
    if report.get("execution", {}).get("model_fallback_or_substitution") is not False:
        raise ExternalGatewayError("DELIVERED_SMOKE_MODEL_SUBSTITUTION")
    expected_hash = smoke.get("run_report_sha256")
    if expected_hash and sha256_file(path) != expected_hash:
        raise ExternalGatewayError("DELIVERED_SMOKE_HASH_MISMATCH")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run or validate the Task-201 public-fictional tcodex route."
        )
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--print-smoke-packets", action="store_true")
    modes.add_argument("--validate-registry", action="store_true")
    modes.add_argument("--run-smoke", action="store_true")
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--registry", default=str(REGISTRY))
    parser.add_argument("--model")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    registry_path = Path(args.registry)
    if not registry_path.is_absolute():
        registry_path = root / registry_path
    registry = load_json(registry_path)
    validate_registry(registry)
    if args.print_smoke_packets:
        print(json.dumps({"packets": public_smoke_packets()}, indent=2))
        return 0
    if args.validate_registry:
        validate_delivered_smoke(root, registry)
        print(registry["decision_token"])
        return 0
    if args.run_smoke:
        model = args.model or registry["models"]["primary"]["slug"]
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = root / output_dir
        report = run_smoke(
            root=root,
            registry=registry,
            model_slug=str(model),
            output_dir=output_dir,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
