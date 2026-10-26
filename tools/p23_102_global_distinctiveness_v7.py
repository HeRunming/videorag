"""Fail-closed, model-free R23-B v7 integrity contract.

V7 is an isolated hardening layer over the inherited v6/v5 semantic
implementation.  It closes duplicate typed-key ambiguity, validates every
typed-audit scalar exactly, makes adjudication presence conflict-dependent,
and binds the complete executable/semantic dependency closure in the external
commitment request.

The tool runs no model, consumes no authorization, and does not modify the
historical authoring, Canary, marker, or capsule surfaces.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT_DATE = "2026-10-23"
DECISION_TOKEN = "R23_B_V7_DESIGN_READY"
SCHEMA_VERSION = "av-trace.p23-102-r23b-global-distinctiveness/7.0"
ANALYSIS_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-global-distinctiveness-analysis/7.0"
)
RAW_AUDIT_ENCODING_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-canonical-typed-raw-audit/4.0"
)
REVIEW_PACKET_SCHEMA_VERSION = "av-trace.p23-102-r23b-review-packet/7.0"
REVIEW_RECEIPT_SCHEMA_VERSION = "av-trace.p23-102-r23b-review-receipt/4.0"
PLAN_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-global-distinctiveness-plan/7.0"
)
COMMITMENT_REQUEST_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-external-commitment-request/5.0"
)
DEPENDENCY_MANIFEST_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-dependency-manifest/1.0"
)
INTEGRITY_CLAIM = (
    "CURRENT_IMPLEMENTATION_RECOMPUTED_INTEGRITY_NOT_EXTERNAL_AUTHORIZATION"
)

V6_TOOL = Path("tools/p23_102_global_distinctiveness_v6.py")
V5_TOOL = Path("tools/p23_102_global_distinctiveness_v5.py")
PARENT_AMBIENT_TOOL = Path("tools/p23_102_query_authoring_v2.py")
TEST_FILE = Path("tooling/tests/test_p23_102_global_distinctiveness_v7.py")
V6_TEST_FILE = Path("tooling/tests/test_p23_102_global_distinctiveness_v6.py")
DESIGN_DOC = Path("docs/design/p23_102_global_distinctiveness_v7.md")
DEFAULT_PLAN = Path(
    "data/rehearsal_plan/p23_102_global_distinctiveness_v7_plan.json"
)
DEFAULT_COMMITMENT_REQUEST = Path(
    "data/rehearsal_plan/"
    "p23_102_global_distinctiveness_v7_external_commitment_request.json"
)

UNKNOWN_PUBLIC_KEY = "unknown"
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
CANONICAL_INT_RE = re.compile(r"(?:0|-[1-9][0-9]*|[1-9][0-9]*)\Z")
FLOAT_SPECIALS = frozenset({"NaN", "+Infinity", "-Infinity"})
REVIEW_QUESTIONS = [
    "Is the blinded action claim correct for the exact evidence interval?",
    "Are all blinded object claims correct for the exact evidence interval?",
]


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V6 = _load_module(V6_TOOL, "r23b_v6_for_v7")
V5 = V6.V5
ContractError = V6.ContractError


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def semantic_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _strict_dict(value: Any, fields: set[str], code: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise ContractError(code, disposition="REJECT")
    return value


def _valid_hash(value: Any) -> bool:
    return type(value) is str and SHA256_RE.fullmatch(value) is not None


def _validate_state(row: dict[str, Any]) -> None:
    status = row.get("state_status")
    if status not in {
        "NO_SAFE_STATE",
        "SAFE_TYPED_STATE",
        "STATE_ENCODING_FAILED",
    }:
        raise ContractError("R23B_AUDIT_STATE_INVALID", disposition="REJECT")
    failures = row.get("state_failures")
    if type(failures) is not list or any(type(item) is not str for item in failures):
        raise ContractError("R23B_AUDIT_STATE_INVALID", disposition="REJECT")
    if status == "SAFE_TYPED_STATE":
        if set(row) & {"state", "state_sha256"} != {"state", "state_sha256"}:
            raise ContractError("R23B_AUDIT_STATE_INVALID", disposition="REJECT")
        _validate_audit_tree(row["state"])
        if not _valid_hash(row["state_sha256"]):
            raise ContractError("R23B_AUDIT_STATE_INVALID", disposition="REJECT")
        if row["state_sha256"] != semantic_hash(row["state"]):
            raise ContractError("R23B_AUDIT_STATE_INVALID", disposition="REJECT")
    elif "state" in row or "state_sha256" in row:
        raise ContractError("R23B_AUDIT_STATE_INVALID", disposition="REJECT")


def _validate_type_fields(row: dict[str, Any]) -> None:
    for field in ("type_label", "module", "qualname"):
        if type(row.get(field)) is not str or not row[field]:
            raise ContractError("R23B_AUDIT_TYPE_LABEL_INVALID", disposition="REJECT")
    if row["type_label"] != f"{row['module']}.{row['qualname']}":
        raise ContractError("R23B_AUDIT_TYPE_LABEL_INVALID", disposition="REJECT")


def _validate_float_text(value: Any) -> None:
    if type(value) is not str:
        raise ContractError("R23B_AUDIT_FLOAT_INVALID", disposition="REJECT")
    if value in FLOAT_SPECIALS:
        return
    try:
        parsed = float.fromhex(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContractError("R23B_AUDIT_FLOAT_INVALID", disposition="REJECT") from exc
    if not math.isfinite(parsed) or parsed.hex() != value:
        raise ContractError("R23B_AUDIT_FLOAT_INVALID", disposition="REJECT")


def _validate_audit_tree_inner(value: Any) -> None:
    if type(value) is not dict or type(value.get("tag")) is not str:
        raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")
    tag = value["tag"]
    if tag == "null":
        _strict_dict(value, {"tag"}, "R23B_AUDIT_ENCODING_INVALID")
        return
    if tag == "bool":
        _strict_dict(value, {"tag", "value"}, "R23B_AUDIT_ENCODING_INVALID")
        if type(value["value"]) is not bool:
            raise ContractError("R23B_AUDIT_BOOL_INVALID", disposition="REJECT")
        return
    if tag == "str":
        _strict_dict(value, {"tag", "value"}, "R23B_AUDIT_ENCODING_INVALID")
        if type(value["value"]) is not str:
            raise ContractError("R23B_AUDIT_STRING_INVALID", disposition="REJECT")
        return
    if tag == "int":
        _strict_dict(value, {"tag", "value"}, "R23B_AUDIT_ENCODING_INVALID")
        if (
            type(value["value"]) is not str
            or CANONICAL_INT_RE.fullmatch(value["value"]) is None
        ):
            raise ContractError("R23B_AUDIT_INT_INVALID", disposition="REJECT")
        return
    if tag == "float":
        _strict_dict(value, {"tag", "value"}, "R23B_AUDIT_ENCODING_INVALID")
        _validate_float_text(value["value"])
        return
    if tag == "bytes":
        _strict_dict(value, {"tag", "base64"}, "R23B_AUDIT_ENCODING_INVALID")
        encoded = value["base64"]
        if type(encoded) is not str:
            raise ContractError("R23B_AUDIT_BASE64_INVALID", disposition="REJECT")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise ContractError("R23B_AUDIT_BASE64_INVALID", disposition="REJECT") from exc
        if base64.b64encode(decoded).decode("ascii") != encoded:
            raise ContractError("R23B_AUDIT_BASE64_INVALID", disposition="REJECT")
        return
    if tag in {"list", "tuple", "set", "frozenset"}:
        _strict_dict(value, {"tag", "items"}, "R23B_AUDIT_ENCODING_INVALID")
        if type(value["items"]) is not list:
            raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")
        previous: bytes | None = None
        for item in value["items"]:
            _validate_audit_tree_inner(item)
            current = canonical_bytes(item)
            if tag in {"set", "frozenset"}:
                if previous is not None and current <= previous:
                    raise ContractError(
                        "R23B_AUDIT_SET_ORDER_INVALID", disposition="REJECT"
                    )
                previous = current
        return

    state_fields = {"state_status", "state_failures", "state", "state_sha256"}
    if tag == "mapping":
        allowed = {
            "tag",
            "type_label",
            "module",
            "qualname",
            "entries",
            *state_fields,
        }
        required = {
            "tag",
            "type_label",
            "module",
            "qualname",
            "entries",
            "state_status",
            "state_failures",
        }
        if not required <= set(value) or not set(value) <= allowed:
            raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")
        _validate_type_fields(value)
        _validate_state(value)
        if type(value["entries"]) is not list:
            raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")
        previous = None
        for pair in value["entries"]:
            _strict_dict(pair, {"key", "value"}, "R23B_AUDIT_ENCODING_INVALID")
            _validate_audit_tree_inner(pair["key"])
            _validate_audit_tree_inner(pair["value"])
            current = canonical_bytes(pair)
            if previous is not None and current < previous:
                raise ContractError(
                    "R23B_AUDIT_MAPPING_ORDER_INVALID", disposition="REJECT"
                )
            previous = current
        return
    if tag == "UNSUPPORTED_TYPE":
        allowed = {
            "tag",
            "type_label",
            "module",
            "qualname",
            "failure",
            "capture_error_type",
            *state_fields,
        }
        required = {
            "tag",
            "type_label",
            "module",
            "qualname",
            "failure",
            "state_status",
            "state_failures",
        }
        if not required <= set(value) or not set(value) <= allowed:
            raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")
        _validate_type_fields(value)
        if type(value["failure"]) is not str or not value["failure"]:
            raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")
        if "capture_error_type" in value and (
            type(value["capture_error_type"]) is not str
            or not value["capture_error_type"]
        ):
            raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")
        _validate_state(value)
        return
    raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")


def _validate_audit_tree(value: Any) -> None:
    """Validate a typed audit tree without leaking native exceptions."""

    try:
        _validate_audit_tree_inner(value)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT") from exc


def _json_scalar_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContractError("R23B_CANONICAL_AUDIT_INVALID", disposition="REJECT") from exc


def _canonical_json_bytes_from_audit_inner(value: dict[str, Any]) -> bytes:
    tag = value["tag"]
    if tag == "null":
        return b"null"
    if tag == "bool":
        return b"true" if value["value"] else b"false"
    if tag == "str":
        return _json_scalar_bytes(value["value"])
    if tag == "int":
        return value["value"].encode("ascii")
    if tag == "float":
        encoded = value["value"]
        if encoded in FLOAT_SPECIALS:
            raise ContractError("R23B_CANONICAL_AUDIT_NON_JSON", disposition="REJECT")
        return _json_scalar_bytes(float.fromhex(encoded))
    if tag == "list":
        return b"[" + b",".join(
            _canonical_json_bytes_from_audit_inner(item) for item in value["items"]
        ) + b"]"
    if tag == "mapping":
        rendered: list[tuple[str, bytes, bytes]] = []
        seen: set[str] = set()
        for pair in value["entries"]:
            key = pair["key"]
            if key["tag"] != "str":
                raise ContractError(
                    "R23B_CANONICAL_AUDIT_NON_JSON", disposition="REJECT"
                )
            key_text = key["value"]
            if key_text in seen:
                raise ContractError(
                    "R23B_CANONICAL_AUDIT_DUPLICATE_KEY", disposition="REJECT"
                )
            seen.add(key_text)
            rendered.append(
                (
                    key_text,
                    _json_scalar_bytes(key_text),
                    _canonical_json_bytes_from_audit_inner(pair["value"]),
                )
            )
        rendered.sort(key=lambda row: row[0])
        return b"{" + b",".join(
            key_bytes + b":" + item_bytes
            for _, key_bytes, item_bytes in rendered
        ) + b"}"
    raise ContractError("R23B_CANONICAL_AUDIT_NON_JSON", disposition="REJECT")


def _canonical_json_bytes_from_audit(value: Any) -> bytes:
    """Total ContractError boundary for malformed typed-audit trees."""

    try:
        _validate_audit_tree(value)
        return _canonical_json_bytes_from_audit_inner(value)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError("R23B_CANONICAL_AUDIT_INVALID", disposition="REJECT") from exc


def _typed_payload(audit_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": RAW_AUDIT_ENCODING_SCHEMA_VERSION,
        "version": 4,
        "value": audit_input,
    }


def _capture_raw(value: Any) -> dict[str, Any]:
    audit_input = V6._audit_encode_safely(value)
    _validate_audit_tree(audit_input)
    typed = _typed_payload(audit_input)
    try:
        raw_bytes = canonical_bytes(value)
        if raw_bytes != _canonical_json_bytes_from_audit(audit_input):
            raise ContractError("R23B_CANONICAL_AUDIT_BYTES_DIVERGE")
        status = "CANONICAL"
        encoding = "CANONICAL_JSON_UTF8"
        reasons: list[str] = []
    except Exception:  # noqa: BLE001 - typed fallback is the contract
        raw_bytes = canonical_bytes(typed)
        status = "CANONICALIZATION_FAILED"
        encoding = "CANONICAL_TYPED_AUDIT_JSON_UTF8"
        reasons = ["CANONICALIZATION_FAILED"]
    return {
        "raw_encoding": encoding,
        "raw_encoding_schema": RAW_AUDIT_ENCODING_SCHEMA_VERSION,
        "raw_encoding_version": 4,
        "raw_encoding_payload_sha256": semantic_hash(typed),
        "raw_bytes_base64": base64.b64encode(raw_bytes).decode("ascii"),
        "raw_bytes_sha256": bytes_hash(raw_bytes),
        "canonicalization_status": status,
        "capture_reasons": reasons,
        "audit_input": audit_input,
    }


def _audit_to_safe_value_inner(value: dict[str, Any]) -> Any:
    tag = value["tag"]
    if tag == "null":
        return None
    if tag in {"bool", "str"}:
        return value["value"]
    if tag == "int":
        return int(value["value"])
    if tag == "float":
        special = {"NaN": math.nan, "+Infinity": math.inf, "-Infinity": -math.inf}
        return special[value["value"]] if value["value"] in special else float.fromhex(
            value["value"]
        )
    if tag == "list":
        return [_audit_to_safe_value_inner(item) for item in value["items"]]
    if tag == "mapping":
        pairs: list[tuple[str, Any]] = []
        for pair in value["entries"]:
            key = _audit_to_safe_value_inner(pair["key"])
            if type(key) is not str:
                raise ContractError("R23B_AUDIT_NOT_SAFE_SEMANTIC_MAPPING")
            pairs.append((key, _audit_to_safe_value_inner(pair["value"])))
        if len({key for key, _ in pairs}) != len(pairs):
            raise ContractError("R23B_AUDIT_DUPLICATE_SEMANTIC_KEY")
        return dict(pairs)
    raise ContractError("R23B_AUDIT_NOT_SAFE_SEMANTIC_VALUE")


def _audit_to_safe_value(value: Any) -> Any:
    try:
        _validate_audit_tree(value)
        return _audit_to_safe_value_inner(value)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(
            "R23B_AUDIT_SEMANTIC_DECODE_INVALID", disposition="REJECT"
        ) from exc


def _typed_mapping_extraction(
    mapping: Any,
    key: str,
    *,
    require_nonempty_string: bool = False,
) -> dict[str, Any]:
    """Return UNIQUE, MISSING, or DUPLICATE_OR_INVALID with all pair positions."""

    if type(mapping) is not dict or mapping.get("tag") != "mapping":
        return {
            "key": key,
            "status": "DUPLICATE_OR_INVALID",
            "reason": "NOT_TYPED_MAPPING",
            "matches": [],
            "unique_value": None,
            "unique_string": None,
        }
    matches: list[dict[str, Any]] = []
    for position, pair in enumerate(mapping["entries"]):
        encoded_key = pair["key"]
        if (
            type(encoded_key) is dict
            and encoded_key.get("tag") == "str"
            and encoded_key.get("value") == key
        ):
            encoded_value = copy.deepcopy(pair["value"])
            valid_string = (
                type(encoded_value) is dict
                and encoded_value.get("tag") == "str"
                and type(encoded_value.get("value")) is str
                and bool(encoded_value["value"])
            )
            matches.append(
                {
                    "audit_pair_position": position,
                    "value_audit": encoded_value,
                    "value_status": "VALID_NONEMPTY_STRING"
                    if valid_string
                    else "INVALID_PUBLIC_KEY_VALUE",
                    "string_value": encoded_value.get("value")
                    if valid_string
                    else None,
                }
            )
    if not matches:
        status = "MISSING"
        reason = "KEY_ABSENT"
        unique_value = None
    elif len(matches) == 1 and (
        not require_nonempty_string
        or matches[0]["value_status"] == "VALID_NONEMPTY_STRING"
    ):
        status = "UNIQUE"
        reason = (
            "UNIQUE_VALID_PUBLIC_KEY"
            if require_nonempty_string
            else "UNIQUE_TYPED_VALUE"
        )
        unique_value = copy.deepcopy(matches[0]["value_audit"])
    else:
        status = "DUPLICATE_OR_INVALID"
        reason = "DUPLICATE_KEY" if len(matches) > 1 else "INVALID_VALUE"
        unique_value = None
    return {
        "key": key,
        "status": status,
        "reason": reason,
        "matches": matches,
        "unique_value": unique_value,
        "unique_string": (
            matches[0]["string_value"]
            if status == "UNIQUE"
            and matches[0]["value_status"] == "VALID_NONEMPTY_STRING"
            else None
        ),
    }


def _mapping_value(mapping: dict[str, Any], key: str) -> dict[str, Any] | None:
    extraction = _typed_mapping_extraction(mapping, key)
    if extraction["status"] != "UNIQUE":
        return None
    return copy.deepcopy(extraction["unique_value"])


def _safe_public_key(mapping: dict[str, Any], key: str) -> str:
    extraction = _typed_mapping_extraction(
        mapping, key, require_nonempty_string=True
    )
    return (
        extraction["unique_string"]
        if extraction["status"] == "UNIQUE"
        else UNKNOWN_PUBLIC_KEY
    )


def _component_envelopes(audit_input: dict[str, Any]) -> list[dict[str, Any]]:
    extraction = _typed_mapping_extraction(audit_input, "components")
    if extraction["status"] != "UNIQUE":
        return []
    components = extraction["unique_value"]
    if components.get("tag") != "list":
        return []
    return list(components["items"])


def _derive_sealed_identity(
    raw_capture: Mapping[str, Any],
    slot: Mapping[str, Any],
    slot_manifest_sha256: str,
) -> dict[str, Any]:
    audit_input = copy.deepcopy(raw_capture["audit_input"])
    exact_input_sha256 = str(raw_capture["raw_bytes_sha256"])
    sample_key_extraction = _typed_mapping_extraction(
        audit_input, "sample_key", require_nonempty_string=True
    )
    content_envelope = V6._strip_public_keys(audit_input)
    content_input_sha256 = semantic_hash(
        {"kind": "audited_content_v7", "audit": content_envelope}
    )
    components = []
    for ordinal, component in enumerate(_component_envelopes(audit_input), 1):
        key_extraction = _typed_mapping_extraction(
            component, "component_key", require_nonempty_string=True
        )
        component_content = V6._strip_public_keys(component)
        component_content_sha256 = semantic_hash(
            {"kind": "audited_component_content_v7", "audit": component_content}
        )
        components.append(
            {
                "component_ordinal": ordinal,
                "component_key": (
                    key_extraction["unique_string"]
                    if key_extraction["status"] == "UNIQUE"
                    else UNKNOWN_PUBLIC_KEY
                ),
                "component_key_extraction": key_extraction,
                "exact_component_input_sha256": semantic_hash(
                    {"kind": "audited_component_exact_v7", "audit": component}
                ),
                "component_content_sha256": component_content_sha256,
                "component_identity_sha256": semantic_hash(
                    {
                        "kind": "audited_component_slot_identity_v7",
                        "slot_manifest_sha256": slot_manifest_sha256,
                        "slot_index": slot["slot_index"],
                        "external_slot_id": slot["external_slot_id"],
                        "component_ordinal": ordinal,
                        "component_content_sha256": component_content_sha256,
                    }
                ),
            }
        )
    return {
        "slot_index": slot["slot_index"],
        "external_slot_id": slot["external_slot_id"],
        "slot_manifest_sha256": slot_manifest_sha256,
        "slot_identity_sha256": semantic_hash(
            {
                "kind": "external_manifest_bound_slot_v7",
                "slot_manifest_sha256": slot_manifest_sha256,
                "slot_index": slot["slot_index"],
                "external_slot_id": slot["external_slot_id"],
            }
        ),
        "sample_key": (
            sample_key_extraction["unique_string"]
            if sample_key_extraction["status"] == "UNIQUE"
            else UNKNOWN_PUBLIC_KEY
        ),
        "sample_key_extraction": sample_key_extraction,
        "exact_input_sha256": exact_input_sha256,
        "content_input_sha256": content_input_sha256,
        "sample_identity_sha256": semantic_hash(
            {
                "kind": "audited_sample_slot_identity_v7",
                "slot_manifest_sha256": slot_manifest_sha256,
                "slot_index": slot["slot_index"],
                "external_slot_id": slot["external_slot_id"],
                "content_input_sha256": content_input_sha256,
            }
        ),
        "component_identities": components,
        **copy.deepcopy(dict(raw_capture)),
    }


def _validate_raw_capture(sealed: Mapping[str, Any]) -> dict[str, Any]:
    _strict_dict(
        sealed, V6.SEALED_INPUT_FIELDS, "R23B_SEALED_INPUT_FIELD_SET_INVALID"
    )
    encoded = sealed["raw_bytes_base64"]
    if type(encoded) is not str:
        raise ContractError("R23B_RAW_BYTES_ENCODING_INVALID", disposition="REJECT")
    try:
        raw_bytes = base64.b64decode(encoded, validate=True)
    except (TypeError, ValueError) as exc:
        raise ContractError(
            "R23B_RAW_BYTES_ENCODING_INVALID", disposition="REJECT"
        ) from exc
    if base64.b64encode(raw_bytes).decode("ascii") != encoded:
        raise ContractError("R23B_RAW_BYTES_ENCODING_INVALID", disposition="REJECT")
    if bytes_hash(raw_bytes) != sealed["raw_bytes_sha256"]:
        raise ContractError("R23B_RAW_BYTES_HASH_MISMATCH", disposition="REJECT")
    if sealed["exact_input_sha256"] != sealed["raw_bytes_sha256"]:
        raise ContractError(
            "R23B_EXACT_INPUT_RAW_BYTES_MISMATCH", disposition="REJECT"
        )
    _validate_audit_tree(sealed["audit_input"])
    typed = _typed_payload(sealed["audit_input"])
    if (
        sealed["raw_encoding_schema"] != RAW_AUDIT_ENCODING_SCHEMA_VERSION
        or sealed["raw_encoding_version"] != 4
        or sealed["raw_encoding_payload_sha256"] != semantic_hash(typed)
    ):
        raise ContractError(
            "R23B_RAW_AUDIT_ENCODING_BINDING_MISMATCH", disposition="REJECT"
        )
    if type(sealed["capture_reasons"]) is not list or any(
        type(item) is not str for item in sealed["capture_reasons"]
    ):
        raise ContractError("R23B_RAW_CAPTURE_REASONS_INVALID", disposition="REJECT")
    status = sealed["canonicalization_status"]
    if status == "CANONICALIZATION_FAILED":
        if sealed["raw_encoding"] != "CANONICAL_TYPED_AUDIT_JSON_UTF8":
            raise ContractError(
                "R23B_RAW_ENCODING_STATUS_MISMATCH", disposition="REJECT"
            )
        if raw_bytes != canonical_bytes(typed):
            raise ContractError(
                "R23B_RAW_AUDIT_BYTES_MISMATCH", disposition="REJECT"
            )
    elif status == "CANONICAL":
        if sealed["raw_encoding"] != "CANONICAL_JSON_UTF8":
            raise ContractError(
                "R23B_RAW_ENCODING_STATUS_MISMATCH", disposition="REJECT"
            )
        try:
            expected = _canonical_json_bytes_from_audit(sealed["audit_input"])
        except ContractError as exc:
            raise ContractError(
                "R23B_CANONICAL_RAW_AUDIT_INVALID", disposition="REJECT"
            ) from exc
        if raw_bytes != expected:
            raise ContractError(
                "R23B_CANONICAL_RAW_BYTES_MISMATCH", disposition="REJECT"
            )
    else:
        raise ContractError(
            "R23B_CANONICALIZATION_STATUS_INVALID", disposition="REJECT"
        )
    return {
        "raw_encoding": sealed["raw_encoding"],
        "raw_encoding_schema": sealed["raw_encoding_schema"],
        "raw_encoding_version": sealed["raw_encoding_version"],
        "raw_encoding_payload_sha256": sealed["raw_encoding_payload_sha256"],
        "raw_bytes_base64": sealed["raw_bytes_base64"],
        "raw_bytes_sha256": sealed["raw_bytes_sha256"],
        "canonicalization_status": status,
        "capture_reasons": copy.deepcopy(sealed["capture_reasons"]),
        "audit_input": copy.deepcopy(sealed["audit_input"]),
    }


def _identity_analysis(
    sealed_inputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    inherited = V6_ORIGINAL_IDENTITY_ANALYSIS(sealed_inputs)
    failures: list[dict[str, Any]] = []
    for sealed in sealed_inputs:
        sample_extraction = sealed["sample_key_extraction"]
        if sample_extraction["status"] == "DUPLICATE_OR_INVALID":
            failures.append(
                {
                    "scope": "sample",
                    "slot_index": sealed["slot_index"],
                    "public_key_field": "sample_key",
                    "extraction": copy.deepcopy(sample_extraction),
                }
            )
        for component in sealed["component_identities"]:
            extraction = component["component_key_extraction"]
            if extraction["status"] == "DUPLICATE_OR_INVALID":
                failures.append(
                    {
                        "scope": "component",
                        "slot_index": sealed["slot_index"],
                        "component_ordinal": component["component_ordinal"],
                        "public_key_field": "component_key",
                        "extraction": copy.deepcopy(extraction),
                    }
                )
    findings = inherited["gates"]["global_identity_and_content_duplicate_policy"][
        "findings"
    ]
    findings["invalid_or_duplicate_public_keys"] = copy.deepcopy(failures)
    if failures:
        inherited["hard_global_identity_failures"].append(
            {
                "identity_class": "invalid_or_duplicate_public_keys",
                "failures": copy.deepcopy(failures),
            }
        )
        inherited["status"] = "FAIL_CLOSED"
        inherited["blocking_gates"] = [
            "global_identity_and_content_duplicate_policy"
        ]
        inherited["gates"]["global_identity_and_content_duplicate_policy"][
            "status"
        ] = "FAIL_CLOSED"
    inherited["schema_version"] = ANALYSIS_SCHEMA_VERSION
    inherited["typed_public_key_extraction_contract"] = (
        "UNIQUE | MISSING | DUPLICATE_OR_INVALID; duplicate/invalid is hard"
    )
    return inherited


V6_ORIGINAL_IDENTITY_ANALYSIS = V6._identity_analysis
V6_ORIGINAL_BUILD_AUTHORING_BUNDLE = V6.build_authoring_bundle


def build_authoring_bundle(
    samples: Sequence[Any],
    slot_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    bundle = V6_ORIGINAL_BUILD_AUTHORING_BUNDLE(samples, slot_manifest)
    bundle["provenance"] = {
        "tool_source_sha256": file_sha256(Path(__file__).resolve()),
        "v6_inherited_tool_source_sha256": file_sha256(ROOT / V6_TOOL),
        "v5_semantic_parent_source_sha256": file_sha256(ROOT / V5_TOOL),
        "parent_ambient_tool_source_sha256": file_sha256(ROOT / PARENT_AMBIENT_TOOL),
        "slot_manifest_payload_sha256": bundle["slot_manifest_binding"][
            "slot_manifest_payload_sha256"
        ],
        "sealed_input_set_sha256": semantic_hash(bundle["sealed_inputs"]),
        "principal_registry_schema_sha256": semantic_hash(
            V6.principal_registry_schema_manifest()
        ),
    }
    payload = copy.deepcopy(bundle)
    payload.pop("bundle_payload_sha256", None)
    bundle["bundle_payload_sha256"] = semantic_hash(payload)
    return bundle


def build_review_packet(
    component_record: Mapping[str, Any],
    media_evidence_binding: Mapping[str, Any],
    stratum: str,
) -> dict[str, Any]:
    trusted = V6.verify_component_record(component_record)
    record = trusted["component_record"]
    expected_binding = V6._expected_media_evidence_binding(trusted)
    if type(media_evidence_binding) is not dict or media_evidence_binding != expected_binding:
        raise ContractError(
            "R23B_REVIEW_PACKET_SOURCE_BINDING_MISMATCH", disposition="REJECT"
        )
    if stratum != V6._expected_stratum(record["family_role"]):
        raise ContractError("R23B_REVIEW_PACKET_STRATUM_MISMATCH", disposition="REJECT")
    visual = V5.validate_visual_atoms(record["visual_atoms"])
    payload = {
        "component_record_sha256": trusted["component_record_sha256"],
        "slot_identity_sha256": record["slot_identity_sha256"],
        "sample_key": record["sample_key"],
        "sample_identity_sha256": record["sample_identity_sha256"],
        "exact_input_sha256": record["exact_input_sha256"],
        "component_key": record["component_key"],
        "component_identity_sha256": record["component_identity_sha256"],
        "component_ordinal": record["component_ordinal"],
        "stratum": stratum,
        "content_sha256": record["content_sha256"],
        "media_evidence_binding": expected_binding,
        "media_binding_sha256": semantic_hash(expected_binding["media_binding"]),
        "evidence_binding_sha256": semantic_hash(
            expected_binding["evidence_binding"]
        ),
        "blind_atoms": {
            "action_claim": visual["action"],
            "object_claims": list(visual["objects"]),
        },
        "questions": copy.deepcopy(REVIEW_QUESTIONS),
    }
    payload_hash = semantic_hash(payload)
    return {
        "schema_version": REVIEW_PACKET_SCHEMA_VERSION,
        "packet_payload": payload,
        "packet_payload_sha256": payload_hash,
        "review_packet_key": semantic_hash(
            {
                "schema": REVIEW_PACKET_SCHEMA_VERSION,
                "version": 7,
                "trusted_component_record_sha256": trusted[
                    "component_record_sha256"
                ],
                "packet_payload_sha256": payload_hash,
            }
        ),
        "reviewer_1": None,
        "reviewer_2": None,
        "adjudication": None,
        "decision": None,
    }


def verify_review_packet(
    packet: Mapping[str, Any],
    trusted_component_record: Mapping[str, Any],
) -> dict[str, Any]:
    row = _strict_dict(
        packet, V6.REVIEW_PACKET_FIELDS, "R23B_REVIEW_PACKET_FIELD_SET_INVALID"
    )
    if row["schema_version"] != REVIEW_PACKET_SCHEMA_VERSION:
        raise ContractError("R23B_REVIEW_PACKET_SCHEMA_INVALID", disposition="REJECT")
    if any(
        row[field] is not None
        for field in ("reviewer_1", "reviewer_2", "adjudication", "decision")
    ):
        raise ContractError("R23B_REVIEW_PACKET_NOT_UNFILLED", disposition="REJECT")
    payload = row["packet_payload"]
    if type(payload) is not dict:
        raise ContractError("R23B_REVIEW_PACKET_PAYLOAD_INVALID", disposition="REJECT")
    try:
        expected = build_review_packet(
            trusted_component_record,
            payload["media_evidence_binding"],
            payload["stratum"],
        )
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(
            "R23B_REVIEW_PACKET_PAYLOAD_INVALID", disposition="REJECT"
        ) from exc
    if canonical_bytes(expected) != canonical_bytes(row):
        raise ContractError(
            "R23B_REVIEW_PACKET_TRUSTED_RECORD_MISMATCH", disposition="REJECT"
        )
    return copy.deepcopy(row)


def evaluate_review_result(
    review_packet: Mapping[str, Any],
    trusted_component_record: Mapping[str, Any],
    reviewer_1: Any,
    reviewer_2: Any,
    adjudication: Any,
    principal_registry: Mapping[str, Any],
) -> dict[str, Any]:
    packet = verify_review_packet(review_packet, trusted_component_record)
    registry = V6.verify_principal_registry(principal_registry)
    binding = V6._packet_binding(packet)
    if reviewer_1 is None or reviewer_2 is None:
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "MISSING_REQUIRED_REVIEWER",
        }
    left = V6._validate_review_submission(reviewer_1, registry)
    right = V6._validate_review_submission(reviewer_2, registry)
    for index, row in enumerate((left, right), 1):
        if any(row[field] != binding[field] for field in V6.REVIEW_BINDING_FIELDS):
            return {
                "status": "FAIL_CLOSED",
                "decision": "REJECT_SAMPLE",
                "reason": f"REVIEWER_{index}_PACKET_BINDING_MISMATCH",
            }
    left_principal = V6._principal(registry, left["principal_id"], "reviewer")
    right_principal = V6._principal(registry, right["principal_id"], "reviewer")
    if (
        left["principal_id"] == right["principal_id"]
        or left_principal["subject_commitment"]
        == right_principal["subject_commitment"]
    ):
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "REVIEWERS_NOT_INDEPENDENT",
        }

    conflict = left["decision"] != right["decision"]
    resolved = None
    if adjudication is not None:
        resolved = V6._validate_adjudication(adjudication, registry)
        if any(
            resolved[field] != binding[field] for field in V6.REVIEW_BINDING_FIELDS
        ):
            return {
                "status": "FAIL_CLOSED",
                "decision": "REJECT_SAMPLE",
                "reason": "ADJUDICATION_PACKET_BINDING_MISMATCH",
            }
        adjudicator = V6._principal(
            registry, resolved["principal_id"], "adjudicator"
        )
        if adjudicator["subject_commitment"] in {
            left_principal["subject_commitment"],
            right_principal["subject_commitment"],
        }:
            return {
                "status": "FAIL_CLOSED",
                "decision": "REJECT_SAMPLE",
                "reason": "ADJUDICATOR_NOT_INDEPENDENT",
            }

    if not conflict:
        if resolved is not None:
            return {
                "status": "FAIL_CLOSED",
                "decision": "REJECT_SAMPLE",
                "reason": "UNEXPECTED_ADJUDICATION_WITHOUT_CONFLICT",
            }
        return {
            "status": "COMPLETE",
            "decision": (
                "PASS_REVIEW" if left["decision"] == "PASS" else "REJECT_SAMPLE"
            ),
            "reason": "REVIEWERS_AGREE",
        }
    if resolved is None:
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "CONFLICT_REQUIRES_ADJUDICATION",
        }
    return {
        "status": "COMPLETE",
        "decision": (
            "PASS_REVIEW" if resolved["decision"] == "PASS" else "REJECT_SAMPLE"
        ),
        "reason": "ADJUDICATED_CONFLICT",
    }


def build_review_receipt(
    review_packet: Mapping[str, Any],
    trusted_component_record: Mapping[str, Any],
    reviewer_1: Mapping[str, Any],
    reviewer_2: Mapping[str, Any],
    adjudication: Mapping[str, Any] | None,
    principal_registry: Mapping[str, Any],
) -> dict[str, Any]:
    registry = V6.verify_principal_registry(principal_registry)
    packet = verify_review_packet(review_packet, trusted_component_record)
    left = V6._validate_review_submission(reviewer_1, registry)
    right = V6._validate_review_submission(reviewer_2, registry)
    resolved = (
        V6._validate_adjudication(adjudication, registry)
        if adjudication is not None
        else None
    )
    decision = evaluate_review_result(
        packet,
        trusted_component_record,
        left,
        right,
        resolved,
        registry,
    )
    if decision["reason"] == "UNEXPECTED_ADJUDICATION_WITHOUT_CONFLICT":
        raise ContractError(
            "R23B_UNEXPECTED_ADJUDICATION_WITHOUT_CONFLICT",
            disposition="REJECT",
        )
    if decision["reason"] == "CONFLICT_REQUIRES_ADJUDICATION":
        raise ContractError(
            "R23B_CONFLICT_REQUIRES_ADJUDICATION", disposition="REJECT"
        )
    if decision["reason"] in {
        "ADJUDICATION_PACKET_BINDING_MISMATCH",
        "ADJUDICATOR_NOT_INDEPENDENT",
    }:
        raise ContractError(f"R23B_{decision['reason']}", disposition="REJECT")
    conflict = left["decision"] != right["decision"]
    canonical_adjudication = resolved if conflict else None
    payload = {
        "schema_version": REVIEW_RECEIPT_SCHEMA_VERSION,
        "integrity_claim": INTEGRITY_CLAIM,
        "external_signature_verified": False,
        "component_record_sha256": trusted_component_record[
            "component_record_sha256"
        ],
        "principal_registry_schema_version": registry["schema_version"],
        "principal_registry_payload_sha256": registry[
            "registry_payload_sha256"
        ],
        "review_packet": packet,
        "reviewer_1": left,
        "reviewer_2": right,
        "adjudication": canonical_adjudication,
        "decision": decision,
    }
    payload["receipt_payload_sha256"] = semantic_hash(payload)
    return payload


def verify_review_receipt(
    receipt: Mapping[str, Any],
    trusted_component_record: Mapping[str, Any],
    principal_registry: Mapping[str, Any],
) -> dict[str, Any]:
    row = _strict_dict(
        receipt, V6.REVIEW_RECEIPT_FIELDS, "R23B_REVIEW_RECEIPT_FIELD_SET_INVALID"
    )
    payload = copy.deepcopy(row)
    observed = payload.pop("receipt_payload_sha256")
    if not _valid_hash(observed) or observed != semantic_hash(payload):
        raise ContractError("R23B_REVIEW_RECEIPT_HASH_MISMATCH", disposition="REJECT")
    expected = build_review_receipt(
        row["review_packet"],
        trusted_component_record,
        row["reviewer_1"],
        row["reviewer_2"],
        row["adjudication"],
        principal_registry,
    )
    if canonical_bytes(expected) != canonical_bytes(row):
        raise ContractError(
            "R23B_REVIEW_RECEIPT_TRUSTED_BINDING_MISMATCH",
            disposition="REJECT",
        )
    return {
        "status": "PASS",
        "integrity_claim": INTEGRITY_CLAIM,
        "external_signature_verified": False,
        "review_packet_key": row["review_packet"]["review_packet_key"],
        "receipt_payload_sha256": observed,
        "decision": copy.deepcopy(row["decision"]),
    }


def runtime_constants() -> dict[str, Any]:
    return {
        "raw_audit_encoding_version": 4,
        "human_review_rate": V6.HUMAN_REVIEW_RATE,
        "unknown_public_key": UNKNOWN_PUBLIC_KEY,
        "review_packet_version": 7,
        "typed_mapping_extraction_states": [
            "UNIQUE",
            "MISSING",
            "DUPLICATE_OR_INVALID",
        ],
    }


def typed_audit_schema_manifest() -> dict[str, Any]:
    return {
        "$id": RAW_AUDIT_ENCODING_SCHEMA_VERSION,
        "scalar_contract": {
            "null": "tag only",
            "bool": "exact Python bool",
            "str": "exact Python string",
            "int": "canonical decimal; no leading zero or negative zero",
            "float": "exact float.hex() or NaN/+Infinity/-Infinity",
            "bytes": "canonical RFC4648 base64",
        },
        "mapping_contract": "sorted typed pair-list; duplicates preserved",
        "malformed_boundary": "ContractError only",
    }


def review_receipt_schema_manifest() -> dict[str, Any]:
    return {
        "$id": REVIEW_RECEIPT_SCHEMA_VERSION,
        "agreement_adjudication": "canonical null; any supplied record is rejected",
        "conflict_adjudication": "required and fully validated",
        "builder_material": "validated canonical records only",
    }


def _semantic_dependencies() -> dict[str, Any]:
    return {
        "v5_schema_manifest": V5.schema_manifest(),
        "v5_gate_manifest": V5.GATE_MANIFEST,
        "v5_visual_registry_manifest": V5.VISUAL_REGISTRY_MANIFEST,
        "v5_family_registry_manifest": V5.FAMILY_REGISTRY_MANIFEST,
        "v5_generator_manifest": V5.GENERATOR_MANIFEST,
        "parent_ambient_output_schema": V5.PARENT.AMBIENT_OUTPUT_SCHEMA,
        "v7_typed_audit_schema": typed_audit_schema_manifest(),
        "v7_review_receipt_schema": review_receipt_schema_manifest(),
        "review_principal_registry_schema": V6.principal_registry_schema_manifest(),
        "review_principal_registry_manifest": V6.build_synthetic_principal_registry(),
        "synthetic_fixture": V6.synthetic_samples(),
        "runtime_constants": runtime_constants(),
    }


DEPENDENCY_FILES = {
    "v7_tool": Path("tools/p23_102_global_distinctiveness_v7.py"),
    "v6_inherited_tool": V6_TOOL,
    "v5_inherited_tool": V5_TOOL,
    "parent_ambient_tool": PARENT_AMBIENT_TOOL,
    "v7_tests": TEST_FILE,
    "v6_inherited_tests": V6_TEST_FILE,
    "v7_design_doc": DESIGN_DOC,
}


def build_dependency_manifest() -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for dependency_id, path in sorted(DEPENDENCY_FILES.items()):
        entries.append(
            {
                "dependency_id": dependency_id,
                "kind": "file",
                "path": path.as_posix(),
                "sha256": file_sha256(ROOT / path),
            }
        )
    for dependency_id, value in sorted(_semantic_dependencies().items()):
        entries.append(
            {
                "dependency_id": dependency_id,
                "kind": "semantic_manifest",
                "sha256": semantic_hash(value),
            }
        )
    payload = {
        "schema_version": DEPENDENCY_MANIFEST_SCHEMA_VERSION,
        "entries": entries,
    }
    payload["dependency_manifest_payload_sha256"] = semantic_hash(payload)
    return payload


def verify_dependency_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    row = _strict_dict(
        manifest,
        {
            "schema_version",
            "entries",
            "dependency_manifest_payload_sha256",
        },
        "R23B_DEPENDENCY_MANIFEST_FIELD_SET_INVALID",
    )
    if row["schema_version"] != DEPENDENCY_MANIFEST_SCHEMA_VERSION:
        raise ContractError("R23B_DEPENDENCY_MANIFEST_SCHEMA_INVALID", disposition="REJECT")
    if type(row["entries"]) is not list:
        raise ContractError("R23B_DEPENDENCY_MANIFEST_ENTRIES_INVALID", disposition="REJECT")
    payload = copy.deepcopy(row)
    observed = payload.pop("dependency_manifest_payload_sha256")
    if not _valid_hash(observed) or observed != semantic_hash(payload):
        raise ContractError("R23B_DEPENDENCY_MANIFEST_HASH_MISMATCH", disposition="REJECT")
    expected = build_dependency_manifest()
    if canonical_bytes(expected) != canonical_bytes(row):
        raise ContractError(
            "R23B_DEPENDENCY_CLOSURE_CURRENT_BINDING_MISMATCH",
            disposition="REJECT",
        )
    return {
        "status": "PASS",
        "dependency_count": len(row["entries"]),
        "dependency_manifest_payload_sha256": observed,
    }


def execution_scope() -> dict[str, Any]:
    scope = V6.execution_scope()
    scope["model_calls"] = 0
    scope["authorization_calls"] = 0
    return scope


def build_plan() -> dict[str, Any]:
    dependency_manifest = build_dependency_manifest()
    registry = V6.build_synthetic_principal_registry()
    payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "date": CURRENT_DATE,
        "decision": DECISION_TOKEN,
        "experiment": "R23-B-v7",
        "complete_scientific_go": False,
        "integrity_claim": INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
        "runtime_constants": runtime_constants(),
        "typed_audit_contract": typed_audit_schema_manifest(),
        "public_key_contract": {
            "states": ["UNIQUE", "MISSING", "DUPLICATE_OR_INVALID"],
            "duplicate_or_invalid": "hard_global_identity_failure",
            "audit_pair_values_and_positions_preserved": True,
        },
        "review_contract": review_receipt_schema_manifest(),
        "dependency_manifest_payload_sha256": dependency_manifest[
            "dependency_manifest_payload_sha256"
        ],
        "dependency_count": len(dependency_manifest["entries"]),
        "synthetic_principal_registry": registry,
        "synthetic_principal_registry_payload_sha256": registry[
            "registry_payload_sha256"
        ],
        "scope": execution_scope(),
        "tool": DEPENDENCY_FILES["v7_tool"].as_posix(),
        "tests": DEPENDENCY_FILES["v7_tests"].as_posix(),
        "inherited_tests": DEPENDENCY_FILES["v6_inherited_tests"].as_posix(),
        "design_doc": DEPENDENCY_FILES["v7_design_doc"].as_posix(),
    }
    payload["plan_payload_sha256"] = semantic_hash(payload)
    return payload


def verify_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    expected = build_plan()
    if canonical_bytes(expected) != canonical_bytes(plan):
        raise ContractError("R23B_PLAN_RUNTIME_CONTRACT_MISMATCH", disposition="REJECT")
    return {
        "status": "PASS",
        "integrity_claim": INTEGRITY_CLAIM,
        "external_attested": False,
        "plan_payload_sha256": plan["plan_payload_sha256"],
    }


def build_external_commitment_request(
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    trusted_plan = build_plan() if plan is None else copy.deepcopy(dict(plan))
    verify_plan(trusted_plan)
    dependencies = build_dependency_manifest()
    verify_dependency_manifest(dependencies)
    payload = {
        "schema_version": COMMITMENT_REQUEST_SCHEMA_VERSION,
        "date": CURRENT_DATE,
        "decision": DECISION_TOKEN,
        "request_purpose": (
            "REQUEST_FUTURE_INDEPENDENT_EXTERNAL_AUTHORIZATION_BINDING"
        ),
        "integrity_claim": INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
        "bindings": {
            "plan_payload_sha256": trusted_plan["plan_payload_sha256"],
            "plan_file_expected_canonical_sha256": bytes_hash(
                json.dumps(
                    trusted_plan, indent=2, sort_keys=True
                ).encode("utf-8")
                + b"\n"
            ),
            "dependency_manifest": dependencies,
            "dependency_manifest_payload_sha256": dependencies[
                "dependency_manifest_payload_sha256"
            ],
        },
        "identity_disclaimer": (
            "principal registry consistency is not proof of real-human identity"
        ),
    }
    payload["commitment_request_payload_sha256"] = semantic_hash(payload)
    return payload


def verify_external_commitment_request(
    request: Mapping[str, Any],
) -> dict[str, Any]:
    row = _strict_dict(
        request,
        {
            "schema_version",
            "date",
            "decision",
            "request_purpose",
            "integrity_claim",
            "execution",
            "external_attested",
            "bindings",
            "identity_disclaimer",
            "commitment_request_payload_sha256",
        },
        "R23B_COMMITMENT_REQUEST_FIELD_SET_INVALID",
    )
    payload = copy.deepcopy(row)
    observed = payload.pop("commitment_request_payload_sha256")
    if not _valid_hash(observed) or observed != semantic_hash(payload):
        raise ContractError(
            "R23B_COMMITMENT_REQUEST_HASH_MISMATCH", disposition="REJECT"
        )
    bindings = _strict_dict(
        row["bindings"],
        {
            "plan_payload_sha256",
            "plan_file_expected_canonical_sha256",
            "dependency_manifest",
            "dependency_manifest_payload_sha256",
        },
        "R23B_COMMITMENT_BINDINGS_INVALID",
    )
    verified_dependencies = verify_dependency_manifest(
        bindings["dependency_manifest"]
    )
    if (
        bindings["dependency_manifest_payload_sha256"]
        != verified_dependencies["dependency_manifest_payload_sha256"]
    ):
        raise ContractError(
            "R23B_DEPENDENCY_MANIFEST_BINDING_MISMATCH", disposition="REJECT"
        )
    expected = build_external_commitment_request()
    if canonical_bytes(expected) != canonical_bytes(row):
        raise ContractError(
            "R23B_COMMITMENT_REQUEST_CURRENT_BINDING_MISMATCH",
            disposition="REJECT",
        )
    return {
        "status": "PASS",
        "integrity_claim": INTEGRITY_CLAIM,
        "external_attested": False,
        "dependency_count": verified_dependencies["dependency_count"],
        "dependency_manifest_payload_sha256": verified_dependencies[
            "dependency_manifest_payload_sha256"
        ],
        "commitment_request_payload_sha256": observed,
    }


def write_json(path: Path, value: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return file_sha256(path)


def _review_fixture() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    samples = V6.synthetic_samples()
    manifest = V6.build_slot_manifest(len(samples), manifest_id="synthetic-r23b-v7")
    bundle = build_authoring_bundle(samples, manifest)
    record = bundle["successful_component_records"][0]
    packet = build_review_packet(
        record,
        record["component_record"]["source_binding"],
        V6._expected_stratum(record["component_record"]["family_role"]),
    )
    registry = V6.build_synthetic_principal_registry()
    binding = V6._packet_binding(packet)
    left = {
        **binding,
        "principal_id": "opaque-reviewer-a",
        "action_correct": True,
        "object_tokens_correct": True,
        "decision": "PASS",
        "reasons": [],
    }
    right = {
        **binding,
        "principal_id": "opaque-reviewer-b",
        "action_correct": True,
        "object_tokens_correct": True,
        "decision": "PASS",
        "reasons": [],
    }
    return record, packet, registry, left, right, binding


def run_self_test() -> dict[str, Any]:
    class DuplicateMapping(Mapping):
        def __init__(self, pairs: list[tuple[Any, Any]]) -> None:
            self.pairs = pairs

        def __iter__(self):
            return (key for key, _ in self.pairs)

        def __len__(self):
            return len(self.pairs)

        def __getitem__(self, key):
            raise KeyError(key)

        def items(self):
            return iter(self.pairs)

    malformed = DuplicateMapping(
        [
            ("sample_key", "same-id"),
            ("sample_key", "same-id"),
            ("family_role", "bad"),
            ("components", []),
        ]
    )
    manifest = V6.build_slot_manifest(2, manifest_id="v7-duplicate-key-self-test")
    bundle = build_authoring_bundle(
        [{"sample_key": "same-id", "family_role": "bad", "components": []}, malformed],
        manifest,
    )
    V6.verify_bundle(bundle, manifest)
    if bundle["decision"] != "REJECT_SAMPLE_SET":
        raise ContractError("R23B_SELF_TEST_DUPLICATE_TYPED_KEY_NOT_REJECTED")

    for malformed_scalar in (
        {"tag": "bool", "value": 1},
        {"tag": "int", "value": "01"},
        {"tag": "float", "value": "1.0"},
        {"tag": "str", "value": 7},
        {"tag": "bytes", "base64": "==="},
    ):
        try:
            _canonical_json_bytes_from_audit(malformed_scalar)
        except ContractError:
            pass
        else:
            raise ContractError("R23B_SELF_TEST_MALFORMED_SCALAR_ACCEPTED")

    record, packet, registry, left, right, binding = _review_fixture()
    receipt = build_review_receipt(packet, record, left, right, None, registry)
    verify_review_receipt(receipt, record, registry)
    unexpected = {
        **binding,
        "principal_id": "opaque-adjudicator-c",
        "decision": "PASS",
        "reasons": [],
    }
    try:
        build_review_receipt(
            packet, record, left, right, unexpected, registry
        )
    except ContractError as exc:
        if exc.code != "R23B_UNEXPECTED_ADJUDICATION_WITHOUT_CONFLICT":
            raise
    else:
        raise ContractError("R23B_SELF_TEST_UNEXPECTED_ADJUDICATION_ACCEPTED")

    request = build_external_commitment_request()
    verify_external_commitment_request(request)
    return {
        "status": "PASS",
        "decision": DECISION_TOKEN,
        "integrity_claim": INTEGRITY_CLAIM,
        "checks": [
            "duplicate_typed_public_key_is_hard_global_failure",
            "typed_audit_scalar_validation_is_exact",
            "canonical_audit_boundary_contract_error_only",
            "agreement_requires_null_adjudication",
            "receipt_builder_uses_validated_records_only",
            "commitment_rehashes_transitive_dependency_manifest",
        ],
        "bundle_payload_sha256": bundle["bundle_payload_sha256"],
        "dependency_manifest_payload_sha256": request["bindings"][
            "dependency_manifest_payload_sha256"
        ],
        "model_calls": 0,
        "authorization_calls": 0,
    }


def run_preflight() -> dict[str, Any]:
    samples = V6.synthetic_samples()
    manifest = V6.build_slot_manifest(len(samples), manifest_id="synthetic-r23b-v7")
    bundle = build_authoring_bundle(samples, manifest)
    bundle_verification = V6.verify_bundle(bundle, manifest)
    plan = build_plan()
    plan_verification = verify_plan(plan)
    request = build_external_commitment_request(plan)
    request_verification = verify_external_commitment_request(request)
    if bundle["decision"] != "DESIGN_PREFLIGHT_PASS":
        raise ContractError("R23B_SYNTHETIC_PREFLIGHT_FAILED", disposition="REJECT")
    return {
        "status": "PASS",
        "decision": DECISION_TOKEN,
        "integrity_claim": INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
        "bundle_payload_sha256": bundle["bundle_payload_sha256"],
        "slot_manifest_payload_sha256": manifest[
            "slot_manifest_payload_sha256"
        ],
        "plan_payload_sha256": plan["plan_payload_sha256"],
        "commitment_request_payload_sha256": request[
            "commitment_request_payload_sha256"
        ],
        "dependency_manifest_payload_sha256": request["bindings"][
            "dependency_manifest_payload_sha256"
        ],
        "bundle_verifier": bundle_verification,
        "plan_verifier": plan_verification,
        "commitment_request_verifier": request_verification,
        "sample_count": len(samples),
        "component_record_count": len(bundle["successful_component_records"]),
        "primary_query_count": len(bundle["primary_queries"]),
        "model_calls": 0,
        "authorization_calls": 0,
        "real_families_selected": 0,
    }


def _install_v7_runtime() -> None:
    """Patch only the private, separately loaded v6 module instance."""

    V6.CURRENT_DATE = CURRENT_DATE
    V6.DECISION_TOKEN = DECISION_TOKEN
    V6.SCHEMA_VERSION = SCHEMA_VERSION
    V6.ANALYSIS_SCHEMA_VERSION = ANALYSIS_SCHEMA_VERSION
    V6.RAW_AUDIT_ENCODING_SCHEMA_VERSION = RAW_AUDIT_ENCODING_SCHEMA_VERSION
    V6.REVIEW_PACKET_SCHEMA_VERSION = REVIEW_PACKET_SCHEMA_VERSION
    V6.REVIEW_RECEIPT_SCHEMA_VERSION = REVIEW_RECEIPT_SCHEMA_VERSION
    V6.UNKNOWN_PUBLIC_KEY = UNKNOWN_PUBLIC_KEY
    V6._validate_audit_tree = _validate_audit_tree
    V6._canonical_json_bytes_from_audit = _canonical_json_bytes_from_audit
    V6._typed_payload = _typed_payload
    V6._capture_raw = _capture_raw
    V6._validate_raw_capture = _validate_raw_capture
    V6._audit_to_safe_value = _audit_to_safe_value
    V6._mapping_value = _mapping_value
    V6._safe_public_key = _safe_public_key
    V6._component_envelopes = _component_envelopes
    V6._derive_sealed_identity = _derive_sealed_identity
    V6._identity_analysis = _identity_analysis
    V6.SEALED_INPUT_FIELDS = {
        *V6.SEALED_INPUT_FIELDS,
        "sample_key_extraction",
    }
    V6.build_authoring_bundle = build_authoring_bundle
    V6.build_review_packet = build_review_packet
    V6.verify_review_packet = verify_review_packet
    V6.evaluate_review_result = evaluate_review_result
    V6.build_review_receipt = build_review_receipt
    V6.verify_review_receipt = verify_review_receipt


_install_v7_runtime()

# Public inherited operations use the patched, private v6 module instance.
build_slot_manifest = V6.build_slot_manifest
verify_slot_manifest = V6.verify_slot_manifest
verify_bundle = V6.verify_bundle
verify_component_record = V6.verify_component_record
build_synthetic_principal_registry = V6.build_synthetic_principal_registry
verify_principal_registry = V6.verify_principal_registry
principal_registry_schema_manifest = V6.principal_registry_schema_manifest
synthetic_samples = V6.synthetic_samples
_packet_binding = V6._packet_binding
_expected_stratum = V6._expected_stratum
normalize_principal_id = V6.normalize_principal_id


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("self-test")
    commands.add_parser("preflight")
    commands.add_parser("preflight0")
    plan = commands.add_parser("plan")
    plan.add_argument("--output", type=Path, default=DEFAULT_PLAN)
    commitment = commands.add_parser("commitment-request")
    commitment.add_argument(
        "--output", type=Path, default=DEFAULT_COMMITMENT_REQUEST
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "self-test":
            result = run_self_test()
        elif args.command in {"preflight", "preflight0"}:
            result = run_preflight()
        elif args.command == "plan":
            plan = build_plan()
            verification = verify_plan(plan)
            output = args.output if args.output.is_absolute() else ROOT / args.output
            result = {
                "status": "PASS",
                "decision": DECISION_TOKEN,
                "plan_path": output.relative_to(ROOT).as_posix(),
                "plan_file_sha256": write_json(output, plan),
                "plan_payload_sha256": plan["plan_payload_sha256"],
                "verification": verification,
                "model_calls": 0,
                "authorization_calls": 0,
            }
        elif args.command == "commitment-request":
            request = build_external_commitment_request()
            verification = verify_external_commitment_request(request)
            output = args.output if args.output.is_absolute() else ROOT / args.output
            result = {
                "status": "PASS",
                "decision": DECISION_TOKEN,
                "commitment_request_path": output.relative_to(ROOT).as_posix(),
                "commitment_request_file_sha256": write_json(output, request),
                "commitment_request_payload_sha256": request[
                    "commitment_request_payload_sha256"
                ],
                "dependency_manifest_payload_sha256": request["bindings"][
                    "dependency_manifest_payload_sha256"
                ],
                "verification": verification,
                "model_calls": 0,
                "authorization_calls": 0,
            }
        else:  # pragma: no cover
            raise ContractError("R23B_COMMAND_INVALID")
    except ContractError as exc:
        print(
            json.dumps(
                {"status": "FAIL_CLOSED", "error": exc.code},
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def __getattr__(name: str) -> Any:
    """Expose unchanged inherited helpers for regression compatibility."""

    return getattr(V6, name)


if __name__ == "__main__":
    raise SystemExit(main())
