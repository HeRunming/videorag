#!/usr/bin/env python3
"""Fail-closed, model-free R23-B v6 integrity contract.

V6 closes four boundaries left open by v5:

* sealed identities are always rederived from raw bytes, the typed audit
  envelope, and an independently supplied slot manifest;
* review packets are rebuilt from a trusted sealed component/source record;
* hostile type/mapping/state introspection cannot leak native exceptions; and
* reviewer/adjudicator submissions resolve exact opaque principals through a
  separately provisioned registry.

All verification remains current-implementation integrity.  This tool neither
proves a real human identity nor supplies an external signature/authorization.
It runs no model and does not modify older authoring/canary/marker/capsule
surfaces.
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
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT_DATE = "2026-10-23"
DECISION_TOKEN = "R23_B_V6_DESIGN_READY"
SCHEMA_VERSION = "av-trace.p23-102-r23b-global-distinctiveness/6.0"
ANALYSIS_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-global-distinctiveness-analysis/6.0"
)
RAW_AUDIT_ENCODING_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-canonical-typed-raw-audit/3.0"
)
SLOT_MANIFEST_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-external-sealed-slot-manifest/1.0"
)
COMPONENT_RECORD_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-sealed-component-source-record/1.0"
)
REVIEW_PACKET_SCHEMA_VERSION = "av-trace.p23-102-r23b-review-packet/6.0"
REVIEW_RECEIPT_SCHEMA_VERSION = "av-trace.p23-102-r23b-review-receipt/3.0"
PRINCIPAL_REGISTRY_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-principal-registry/1.0"
)
PLAN_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-global-distinctiveness-plan/6.0"
)
COMMITMENT_REQUEST_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-external-commitment-request/4.0"
)
INTEGRITY_CLAIM = (
    "CURRENT_IMPLEMENTATION_RECOMPUTED_INTEGRITY_NOT_EXTERNAL_AUTHORIZATION"
)

V5_TOOL = Path("tools/p23_102_global_distinctiveness_v5.py")
TEST_FILE = Path("tooling/tests/test_p23_102_global_distinctiveness_v6.py")
DESIGN_DOC = Path("docs/design/p23_102_global_distinctiveness_v6.md")
DEFAULT_PLAN = Path(
    "data/rehearsal_plan/p23_102_global_distinctiveness_v6_plan.json"
)
DEFAULT_COMMITMENT_REQUEST = Path(
    "data/rehearsal_plan/"
    "p23_102_global_distinctiveness_v6_external_commitment_request.json"
)

SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
HUMAN_REVIEW_RATE = 0.20
REVIEW_QUESTIONS = [
    "Is the blinded action claim correct for the exact evidence interval?",
    "Are all blinded object claims correct for the exact evidence interval?",
]
UNKNOWN_PUBLIC_KEY = "unknown"


class ContractError(RuntimeError):
    """A normalized fail-closed contract error."""

    def __init__(self, code: str, *, disposition: str = "ABSTAIN") -> None:
        super().__init__(code)
        self.code = code
        self.disposition = disposition


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


def _load_v5() -> Any:
    path = ROOT / V5_TOOL
    spec = importlib.util.spec_from_file_location("r23b_v5_for_v6", path)
    if spec is None or spec.loader is None:
        raise ContractError("R23B_V5_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ContractError("R23B_V5_IMPORT_FAILED") from exc
    return module


V5 = _load_v5()


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _strict_dict(value: Any, fields: set[str], code: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise ContractError(code, disposition="REJECT")
    return value


def _native_exception_label(exc: BaseException) -> str:
    try:
        cls = type(exc)
        module = type.__getattribute__(cls, "__module__")
        qualname = type.__getattribute__(cls, "__qualname__")
        if isinstance(module, str) and isinstance(qualname, str):
            return f"{module}.{qualname}"
    except Exception:  # noqa: BLE001 - hostile metaclass/type metadata
        return "unknown.exception"
    return "unknown.exception"


def _safe_type_parts(value: Any) -> dict[str, str]:
    """Read type/module/qualname without allowing hostile metadata to escape."""

    module = "unknown"
    qualname = "unknown"
    try:
        value_type = type(value)
    except Exception:  # noqa: BLE001  # pragma: no cover
        value_type = None
    if value_type is not None:
        try:
            candidate = type.__getattribute__(value_type, "__module__")
            if isinstance(candidate, str) and candidate:
                module = candidate
        except Exception:  # noqa: BLE001 - hostile metaclass
            module = "unknown"
        try:
            candidate = type.__getattribute__(value_type, "__qualname__")
            if isinstance(candidate, str) and candidate:
                qualname = candidate
        except Exception:  # noqa: BLE001 - hostile metaclass
            qualname = "unknown"
    return {
        "type_label": f"{module}.{qualname}",
        "module": module,
        "qualname": qualname,
    }


def _safe_isinstance(value: Any, cls: Any) -> bool:
    try:
        return isinstance(value, cls)
    except Exception:  # noqa: BLE001 - ABC/metaclass checks are untrusted
        return False


def _safe_state_payload(value: Any, seen: set[int]) -> dict[str, Any]:
    """Capture safely encodable ``__dict__`` and slots state."""

    raw_state: dict[str, Any] = {}
    failures: list[str] = []
    try:
        state = object.__getattribute__(value, "__dict__")
    except AttributeError:
        state = None
    except Exception as exc:  # noqa: BLE001 - hostile state
        state = None
        failures.append(f"dict:{_native_exception_label(exc)}")
    if type(state) is dict:
        raw_state["dict"] = state

    slot_names: set[str] = set()
    try:
        value_type = type(value)
        mro = object.__getattribute__(value_type, "__mro__")
        for cls in mro:
            try:
                namespace = object.__getattribute__(cls, "__dict__")
                declared = namespace.get("__slots__", ())
            except Exception as exc:  # noqa: BLE001
                failures.append(f"slots_meta:{_native_exception_label(exc)}")
                continue
            if isinstance(declared, str):
                declared = (declared,)
            if isinstance(declared, (tuple, list)):
                slot_names.update(
                    item
                    for item in declared
                    if isinstance(item, str)
                    and item not in {"__dict__", "__weakref__"}
                )
    except Exception as exc:  # noqa: BLE001 - hostile metaclass
        failures.append(f"mro:{_native_exception_label(exc)}")

    slots: dict[str, Any] = {}
    for name in sorted(slot_names):
        try:
            slots[name] = object.__getattribute__(value, name)
        except AttributeError:
            continue
        except Exception as exc:  # noqa: BLE001 - hostile slot descriptor
            failures.append(f"slot:{name}:{_native_exception_label(exc)}")
    if slots:
        raw_state["slots"] = slots

    result: dict[str, Any] = {
        "state_status": "NO_SAFE_STATE",
        "state_failures": failures,
    }
    if not raw_state:
        return result
    try:
        state = _audit_encode(raw_state, seen=seen)
        result.update(
            {
                "state_status": "SAFE_TYPED_STATE",
                "state": state,
                "state_sha256": semantic_hash(state),
            }
        )
    except Exception as exc:  # noqa: BLE001 - downgrade, never leak
        result.update(
            {
                "state_status": "STATE_ENCODING_FAILED",
                "state_failures": [
                    *failures,
                    f"encode:{_native_exception_label(exc)}",
                ],
            }
        )
    return result


def _unsupported_envelope(
    value: Any,
    *,
    failure: str,
    seen: set[int] | None = None,
    capture_error: BaseException | None = None,
) -> dict[str, Any]:
    seen = seen if seen is not None else set()
    envelope = {
        "tag": "UNSUPPORTED_TYPE",
        **_safe_type_parts(value),
        "failure": failure,
        **_safe_state_payload(value, seen),
    }
    if capture_error is not None:
        envelope["capture_error_type"] = _native_exception_label(capture_error)
    return envelope


def _audit_encode(value: Any, *, seen: set[int] | None = None) -> dict[str, Any]:
    """Canonical typed encoding with hostile introspection containment."""

    seen = seen if seen is not None else set()
    if value is None:
        return {"tag": "null"}
    if type(value) is bool:
        return {"tag": "bool", "value": value}
    if type(value) is str:
        return {"tag": "str", "value": value}
    if type(value) is int:
        return {"tag": "int", "value": str(value)}
    if type(value) is float:
        if math.isnan(value):
            encoded = "NaN"
        elif math.isinf(value):
            encoded = "+Infinity" if value > 0 else "-Infinity"
        else:
            encoded = value.hex()
        return {"tag": "float", "value": encoded}
    if type(value) is bytes:
        return {
            "tag": "bytes",
            "base64": base64.b64encode(value).decode("ascii"),
        }
    if type(value) in {list, tuple, set, frozenset}:
        marker = id(value)
        if marker in seen:
            raise ContractError("R23B_AUDIT_RECURSION_UNSUPPORTED")
        seen.add(marker)
        try:
            items = [_audit_encode(item, seen=seen) for item in value]
        finally:
            seen.remove(marker)
        if type(value) in {set, frozenset}:
            items.sort(key=canonical_bytes)
        return {
            "tag": {
                list: "list",
                tuple: "tuple",
                set: "set",
                frozenset: "frozenset",
            }[type(value)],
            "items": items,
        }

    if _safe_isinstance(value, Mapping):
        marker = id(value)
        if marker in seen:
            raise ContractError("R23B_AUDIT_RECURSION_UNSUPPORTED")
        seen.add(marker)
        try:
            try:
                iterator = value.items()
                entries = [
                    {
                        "key": _audit_encode(key, seen=seen),
                        "value": _audit_encode(item, seen=seen),
                    }
                    for key, item in iterator
                ]
            except Exception as exc:  # noqa: BLE001 - hostile Mapping
                return _unsupported_envelope(
                    value,
                    failure="MAPPING_ITEMS_FAILED",
                    seen=seen,
                    capture_error=exc,
                )
            entries.sort(
                key=lambda entry: (
                    canonical_bytes(entry["key"]),
                    canonical_bytes(entry["value"]),
                )
            )
            return {
                "tag": "mapping",
                **_safe_type_parts(value),
                "entries": entries,
                **_safe_state_payload(value, seen),
            }
        finally:
            seen.remove(marker)
    return _unsupported_envelope(value, failure="UNSUPPORTED_OBJECT_TYPE", seen=seen)


def _audit_encode_safely(value: Any) -> dict[str, Any]:
    try:
        return _audit_encode(value)
    except ContractError:
        return _unsupported_envelope(
            value, failure="AUDIT_CONTRACT_FAILURE", capture_error=None
        )
    except Exception as exc:  # noqa: BLE001 - last-resort normalization
        return _unsupported_envelope(
            value,
            failure="AUDIT_CAPTURE_FAILED",
            capture_error=exc,
        )


def _validate_state(row: dict[str, Any]) -> None:
    status = row.get("state_status")
    if status not in {
        "NO_SAFE_STATE",
        "SAFE_TYPED_STATE",
        "STATE_ENCODING_FAILED",
    }:
        raise ContractError("R23B_AUDIT_STATE_INVALID", disposition="REJECT")
    if type(row.get("state_failures")) is not list or any(
        not isinstance(item, str) for item in row["state_failures"]
    ):
        raise ContractError("R23B_AUDIT_STATE_INVALID", disposition="REJECT")
    if status == "SAFE_TYPED_STATE":
        if "state" not in row or row.get("state_sha256") != semantic_hash(
            row["state"]
        ):
            raise ContractError("R23B_AUDIT_STATE_INVALID", disposition="REJECT")
        _validate_audit_tree(row["state"])
    elif "state" in row or "state_sha256" in row:
        raise ContractError("R23B_AUDIT_STATE_INVALID", disposition="REJECT")


def _validate_type_fields(row: dict[str, Any]) -> None:
    for field in ("type_label", "module", "qualname"):
        if not isinstance(row.get(field), str) or not row[field]:
            raise ContractError("R23B_AUDIT_TYPE_LABEL_INVALID", disposition="REJECT")
    if row["type_label"] != f"{row['module']}.{row['qualname']}":
        raise ContractError("R23B_AUDIT_TYPE_LABEL_INVALID", disposition="REJECT")


def _validate_audit_tree(value: Any) -> None:
    if type(value) is not dict or not isinstance(value.get("tag"), str):
        raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")
    tag = value["tag"]
    if tag == "null":
        _strict_dict(value, {"tag"}, "R23B_AUDIT_ENCODING_INVALID")
        return
    if tag in {"bool", "str", "int", "float"}:
        _strict_dict(value, {"tag", "value"}, "R23B_AUDIT_ENCODING_INVALID")
        return
    if tag == "bytes":
        _strict_dict(value, {"tag", "base64"}, "R23B_AUDIT_ENCODING_INVALID")
        try:
            base64.b64decode(value["base64"], validate=True)
        except Exception as exc:
            raise ContractError(
                "R23B_AUDIT_ENCODING_INVALID", disposition="REJECT"
            ) from exc
        return
    if tag in {"list", "tuple", "set", "frozenset"}:
        _strict_dict(value, {"tag", "items"}, "R23B_AUDIT_ENCODING_INVALID")
        if type(value["items"]) is not list:
            raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")
        for item in value["items"]:
            _validate_audit_tree(item)
        return
    state_fields = {
        "state_status",
        "state_failures",
        "state",
        "state_sha256",
    }
    if tag == "mapping":
        allowed = {
            "tag",
            "type_label",
            "module",
            "qualname",
            "entries",
            *state_fields,
        }
        if not set(value) <= allowed or not {
            "tag",
            "type_label",
            "module",
            "qualname",
            "entries",
            "state_status",
            "state_failures",
        } <= set(value):
            raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")
        _validate_type_fields(value)
        _validate_state(value)
        if type(value["entries"]) is not list:
            raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")
        previous: bytes | None = None
        for pair in value["entries"]:
            _strict_dict(pair, {"key", "value"}, "R23B_AUDIT_ENCODING_INVALID")
            _validate_audit_tree(pair["key"])
            _validate_audit_tree(pair["value"])
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
        _validate_state(value)
        return
    raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")


def _typed_payload(audit_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": RAW_AUDIT_ENCODING_SCHEMA_VERSION,
        "version": 3,
        "value": audit_input,
    }


def _json_scalar_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_json_bytes_from_audit(value: dict[str, Any]) -> bytes:
    """Render canonical JSON from pair lists without rebuilding a Python dict."""

    tag = value["tag"]
    if tag == "null":
        return b"null"
    if tag == "bool":
        return b"true" if value["value"] else b"false"
    if tag == "str":
        return _json_scalar_bytes(value["value"])
    if tag == "int":
        return str(int(value["value"])).encode("ascii")
    if tag == "float":
        encoded = value["value"]
        if encoded in {"NaN", "+Infinity", "-Infinity"}:
            raise ContractError("R23B_CANONICAL_AUDIT_NON_JSON")
        return _json_scalar_bytes(float.fromhex(encoded))
    if tag == "list":
        return b"[" + b",".join(
            _canonical_json_bytes_from_audit(item) for item in value["items"]
        ) + b"]"
    if tag == "mapping":
        rendered: list[tuple[str, bytes, bytes]] = []
        seen: set[str] = set()
        for pair in value["entries"]:
            key = pair["key"]
            if key.get("tag") != "str" or not isinstance(key.get("value"), str):
                raise ContractError("R23B_CANONICAL_AUDIT_NON_JSON")
            key_text = key["value"]
            if key_text in seen:
                raise ContractError("R23B_CANONICAL_AUDIT_DUPLICATE_KEY")
            seen.add(key_text)
            rendered.append(
                (
                    key_text,
                    _json_scalar_bytes(key_text),
                    _canonical_json_bytes_from_audit(pair["value"]),
                )
            )
        rendered.sort(key=lambda row: row[0])
        return b"{" + b",".join(
            key_bytes + b":" + item_bytes
            for _, key_bytes, item_bytes in rendered
        ) + b"}"
    raise ContractError("R23B_CANONICAL_AUDIT_NON_JSON")


def _capture_raw(value: Any) -> dict[str, Any]:
    audit_input = _audit_encode_safely(value)
    _validate_audit_tree(audit_input)
    typed = _typed_payload(audit_input)
    try:
        raw_bytes = canonical_bytes(value)
        if raw_bytes != _canonical_json_bytes_from_audit(audit_input):
            raise ContractError("R23B_CANONICAL_AUDIT_BYTES_DIVERGE")
        status = "CANONICAL"
        encoding = "CANONICAL_JSON_UTF8"
        reasons: list[str] = []
    except Exception:  # noqa: BLE001 - fallback is the contract
        raw_bytes = canonical_bytes(typed)
        status = "CANONICALIZATION_FAILED"
        encoding = "CANONICAL_TYPED_AUDIT_JSON_UTF8"
        reasons = ["CANONICALIZATION_FAILED"]
    return {
        "raw_encoding": encoding,
        "raw_encoding_schema": RAW_AUDIT_ENCODING_SCHEMA_VERSION,
        "raw_encoding_version": 3,
        "raw_encoding_payload_sha256": semantic_hash(typed),
        "raw_bytes_base64": base64.b64encode(raw_bytes).decode("ascii"),
        "raw_bytes_sha256": bytes_hash(raw_bytes),
        "canonicalization_status": status,
        "capture_reasons": reasons,
        "audit_input": audit_input,
    }


def _mapping_value(mapping: dict[str, Any], key: str) -> dict[str, Any] | None:
    if mapping.get("tag") != "mapping":
        return None
    found: list[dict[str, Any]] = []
    for pair in mapping["entries"]:
        encoded_key = pair["key"]
        if encoded_key.get("tag") == "str" and encoded_key.get("value") == key:
            found.append(pair["value"])
    return found[0] if len(found) == 1 else None


def _safe_public_key(mapping: dict[str, Any], key: str) -> str:
    encoded = _mapping_value(mapping, key)
    if (
        encoded is not None
        and encoded.get("tag") == "str"
        and isinstance(encoded.get("value"), str)
        and encoded["value"]
    ):
        return encoded["value"]
    return UNKNOWN_PUBLIC_KEY


def _strip_public_keys(value: dict[str, Any]) -> dict[str, Any]:
    stripped = copy.deepcopy(value)
    if stripped.get("tag") == "mapping":
        stripped["entries"] = [
            {
                "key": _strip_public_keys(pair["key"]),
                "value": _strip_public_keys(pair["value"]),
            }
            for pair in stripped["entries"]
            if not (
                pair["key"].get("tag") == "str"
                and pair["key"].get("value")
                in {"sample_key", "component_key"}
            )
        ]
        if stripped.get("state_status") == "SAFE_TYPED_STATE":
            stripped["state"] = _strip_public_keys(stripped["state"])
            stripped["state_sha256"] = semantic_hash(stripped["state"])
    elif stripped.get("tag") in {"list", "tuple", "set", "frozenset"}:
        stripped["items"] = [
            _strip_public_keys(item) for item in stripped["items"]
        ]
    elif (
        stripped.get("tag") == "UNSUPPORTED_TYPE"
        and stripped.get("state_status") == "SAFE_TYPED_STATE"
    ):
        stripped["state"] = _strip_public_keys(stripped["state"])
        stripped["state_sha256"] = semantic_hash(stripped["state"])
    return stripped


def build_slot_manifest(
    input_count: int,
    *,
    manifest_id: str = "synthetic-r23b-v6-slot-manifest",
    external_seal: str = "UNSIGNED_SYNTHETIC_CURRENT_INTEGRITY_ONLY",
) -> dict[str, Any]:
    if type(input_count) is not int or input_count < 0:
        raise ContractError("R23B_SLOT_MANIFEST_COUNT_INVALID", disposition="REJECT")
    payload = {
        "schema_version": SLOT_MANIFEST_SCHEMA_VERSION,
        "manifest_id": manifest_id,
        "external_seal": external_seal,
        "input_count": input_count,
        "slots": [
            {
                "slot_index": index,
                "external_slot_id": f"{manifest_id}:slot:{index:06d}",
            }
            for index in range(1, input_count + 1)
        ],
    }
    payload["slot_manifest_payload_sha256"] = semantic_hash(payload)
    return payload


SLOT_MANIFEST_FIELDS = {
    "schema_version",
    "manifest_id",
    "external_seal",
    "input_count",
    "slots",
    "slot_manifest_payload_sha256",
}


def verify_slot_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    row = _strict_dict(
        manifest, SLOT_MANIFEST_FIELDS, "R23B_SLOT_MANIFEST_FIELD_SET_INVALID"
    )
    payload = copy.deepcopy(row)
    observed = payload.pop("slot_manifest_payload_sha256")
    if observed != semantic_hash(payload):
        raise ContractError("R23B_SLOT_MANIFEST_HASH_MISMATCH", disposition="REJECT")
    if row["schema_version"] != SLOT_MANIFEST_SCHEMA_VERSION:
        raise ContractError("R23B_SLOT_MANIFEST_SCHEMA_INVALID", disposition="REJECT")
    if (
        type(row["input_count"]) is not int
        or row["input_count"] < 0
        or type(row["slots"]) is not list
        or len(row["slots"]) != row["input_count"]
    ):
        raise ContractError("R23B_SLOT_MANIFEST_COUNT_INVALID", disposition="REJECT")
    ids: set[str] = set()
    for expected, slot in enumerate(row["slots"], 1):
        _strict_dict(
            slot,
            {"slot_index", "external_slot_id"},
            "R23B_SLOT_MANIFEST_SLOT_INVALID",
        )
        if slot["slot_index"] != expected or not isinstance(
            slot["external_slot_id"], str
        ):
            raise ContractError(
                "R23B_SLOT_MANIFEST_SLOT_INVALID", disposition="REJECT"
            )
        if slot["external_slot_id"] in ids:
            raise ContractError(
                "R23B_SLOT_MANIFEST_SLOT_DUPLICATE", disposition="REJECT"
            )
        ids.add(slot["external_slot_id"])
    return copy.deepcopy(row)


def _component_envelopes(audit_input: dict[str, Any]) -> list[dict[str, Any]]:
    components = _mapping_value(audit_input, "components")
    if components is None or components.get("tag") != "list":
        return []
    return list(components["items"])


def _derive_sealed_identity(
    raw_capture: Mapping[str, Any],
    slot: Mapping[str, Any],
    slot_manifest_sha256: str,
) -> dict[str, Any]:
    audit_input = copy.deepcopy(raw_capture["audit_input"])
    exact_input_sha256 = str(raw_capture["raw_bytes_sha256"])
    content_envelope = _strip_public_keys(audit_input)
    content_input_sha256 = semantic_hash(
        {"kind": "audited_content_v6", "audit": content_envelope}
    )
    components = []
    for ordinal, component in enumerate(_component_envelopes(audit_input), 1):
        component_content = _strip_public_keys(component)
        component_content_sha256 = semantic_hash(
            {"kind": "audited_component_content_v6", "audit": component_content}
        )
        components.append(
            {
                "component_ordinal": ordinal,
                "component_key": _safe_public_key(component, "component_key"),
                "exact_component_input_sha256": semantic_hash(
                    {"kind": "audited_component_exact_v6", "audit": component}
                ),
                "component_content_sha256": component_content_sha256,
                "component_identity_sha256": semantic_hash(
                    {
                        "kind": "audited_component_slot_identity_v6",
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
                "kind": "external_manifest_bound_slot_v6",
                "slot_manifest_sha256": slot_manifest_sha256,
                "slot_index": slot["slot_index"],
                "external_slot_id": slot["external_slot_id"],
            }
        ),
        "sample_key": _safe_public_key(audit_input, "sample_key"),
        "exact_input_sha256": exact_input_sha256,
        "content_input_sha256": content_input_sha256,
        "sample_identity_sha256": semantic_hash(
            {
                "kind": "audited_sample_slot_identity_v6",
                "slot_manifest_sha256": slot_manifest_sha256,
                "slot_index": slot["slot_index"],
                "external_slot_id": slot["external_slot_id"],
                "content_input_sha256": content_input_sha256,
            }
        ),
        "component_identities": components,
        **copy.deepcopy(dict(raw_capture)),
    }


def _capture_input_identity(
    value: Any,
    slot: Mapping[str, Any],
    slot_manifest_sha256: str,
) -> dict[str, Any]:
    return _derive_sealed_identity(
        _capture_raw(value), slot, slot_manifest_sha256
    )


SEALED_INPUT_FIELDS = {
    "slot_index",
    "external_slot_id",
    "slot_manifest_sha256",
    "slot_identity_sha256",
    "sample_key",
    "exact_input_sha256",
    "content_input_sha256",
    "sample_identity_sha256",
    "component_identities",
    "raw_encoding",
    "raw_encoding_schema",
    "raw_encoding_version",
    "raw_encoding_payload_sha256",
    "raw_bytes_base64",
    "raw_bytes_sha256",
    "canonicalization_status",
    "capture_reasons",
    "audit_input",
}


def _validate_raw_capture(sealed: Mapping[str, Any]) -> dict[str, Any]:
    _strict_dict(
        sealed, SEALED_INPUT_FIELDS, "R23B_SEALED_INPUT_FIELD_SET_INVALID"
    )
    try:
        raw_bytes = base64.b64decode(sealed["raw_bytes_base64"], validate=True)
    except Exception as exc:
        raise ContractError(
            "R23B_RAW_BYTES_ENCODING_INVALID", disposition="REJECT"
        ) from exc
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
        or sealed["raw_encoding_version"] != 3
        or sealed["raw_encoding_payload_sha256"] != semantic_hash(typed)
    ):
        raise ContractError(
            "R23B_RAW_AUDIT_ENCODING_BINDING_MISMATCH", disposition="REJECT"
        )
    status = sealed["canonicalization_status"]
    if status == "CANONICALIZATION_FAILED":
        if raw_bytes != canonical_bytes(typed):
            raise ContractError(
                "R23B_RAW_AUDIT_BYTES_MISMATCH", disposition="REJECT"
            )
    elif status == "CANONICAL":
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
        "raw_encoding_payload_sha256": sealed[
            "raw_encoding_payload_sha256"
        ],
        "raw_bytes_base64": sealed["raw_bytes_base64"],
        "raw_bytes_sha256": sealed["raw_bytes_sha256"],
        "canonicalization_status": status,
        "capture_reasons": copy.deepcopy(sealed["capture_reasons"]),
        "audit_input": copy.deepcopy(sealed["audit_input"]),
    }


def _audit_to_safe_value(value: dict[str, Any]) -> Any:
    """Decode only ordinary JSON-safe typed data for semantic validation."""

    tag = value["tag"]
    if tag == "null":
        return None
    if tag in {"bool", "str"}:
        return value["value"]
    if tag == "int":
        return int(value["value"])
    if tag == "float":
        names = {"NaN": math.nan, "+Infinity": math.inf, "-Infinity": -math.inf}
        return names.get(value["value"], float.fromhex(value["value"]))
    if tag == "list":
        return [_audit_to_safe_value(item) for item in value["items"]]
    if tag == "mapping":
        pairs = []
        for pair in value["entries"]:
            key = _audit_to_safe_value(pair["key"])
            if not isinstance(key, str):
                raise ContractError("R23B_AUDIT_NOT_SAFE_SEMANTIC_MAPPING")
            pairs.append((key, _audit_to_safe_value(pair["value"])))
        if len({key for key, _ in pairs}) != len(pairs):
            raise ContractError("R23B_AUDIT_DUPLICATE_SEMANTIC_KEY")
        return {key: item for key, item in pairs}
    raise ContractError("R23B_AUDIT_NOT_SAFE_SEMANTIC_VALUE")


def _duplicate_values(values: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for value, location in values:
        grouped[value].append(location)
    return [
        {"value": value, "value_sha256": semantic_hash(value), "locations": locations}
        for value, locations in sorted(grouped.items())
        if len(locations) > 1
    ]


def _identity_analysis(
    sealed_inputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    classes: dict[str, list[tuple[str, str]]] = {
        "sample_key_duplicates": [],
        "component_key_duplicates": [],
        "sample_identity_sha256_duplicates": [],
        "component_identity_sha256_duplicates": [],
        "content_input_sha256_duplicates": [],
        "component_content_sha256_duplicates": [],
        "exact_input_sha256_duplicates": [],
    }
    for sealed in sealed_inputs:
        slot = f"slot:{sealed['slot_index']}"
        if sealed["sample_key"] != UNKNOWN_PUBLIC_KEY:
            classes["sample_key_duplicates"].append((sealed["sample_key"], slot))
        classes["sample_identity_sha256_duplicates"].append(
            (sealed["sample_identity_sha256"], slot)
        )
        classes["content_input_sha256_duplicates"].append(
            (sealed["content_input_sha256"], slot)
        )
        classes["exact_input_sha256_duplicates"].append(
            (sealed["exact_input_sha256"], slot)
        )
        for component in sealed["component_identities"]:
            location = f"{slot}:component:{component['component_ordinal']}"
            if component["component_key"] != UNKNOWN_PUBLIC_KEY:
                classes["component_key_duplicates"].append(
                    (component["component_key"], location)
                )
            classes["component_identity_sha256_duplicates"].append(
                (component["component_identity_sha256"], location)
            )
            classes["component_content_sha256_duplicates"].append(
                (component["component_content_sha256"], location)
            )
    findings = {
        name: _duplicate_values(values) for name, values in classes.items()
    }
    hard_classes = {
        "sample_key_duplicates",
        "component_key_duplicates",
        "sample_identity_sha256_duplicates",
        "component_identity_sha256_duplicates",
        "content_input_sha256_duplicates",
        "component_content_sha256_duplicates",
    }
    hard = [
        {"identity_class": name, "duplicates": copy.deepcopy(rows)}
        for name, rows in findings.items()
        if name in hard_classes and rows
    ]
    content_duplicates = [
        {"identity_class": name, "duplicates": copy.deepcopy(rows)}
        for name, rows in findings.items()
        if name in {
            "content_input_sha256_duplicates",
            "component_content_sha256_duplicates",
            "exact_input_sha256_duplicates",
        }
        and rows
    ]
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "status": "FAIL_CLOSED" if hard else "PASS",
        "blocking_gates": (
            ["global_identity_and_content_duplicate_policy"] if hard else []
        ),
        "hard_global_identity_failures": hard,
        "content_duplicates": content_duplicates,
        "gates": {
            "global_identity_and_content_duplicate_policy": {
                "status": "FAIL_CLOSED" if hard else "PASS",
                "findings": findings,
                "same_content_different_slots_are_not_exempt": True,
            }
        },
    }


def _record_payload(
    sample: Mapping[str, Any],
    identity: Mapping[str, Any],
    ordinal: int,
) -> dict[str, Any]:
    component = sample["components"][ordinal - 1]
    component_identity = identity["component_identities"][ordinal - 1]
    media = V5.validate_media_binding(component["media_binding"])
    evidence = {
        "evidence_sha256": media["evidence_sha256"],
        "evidence_start_ms": media["evidence_start_ms"],
        "evidence_end_ms": media["evidence_end_ms"],
    }
    source_binding = {
        "media_binding": media,
        "evidence_binding": evidence,
    }
    return {
        "schema_version": COMPONENT_RECORD_SCHEMA_VERSION,
        "record_status": "SEALED_SUCCESSFUL_COMPONENT_SOURCE",
        "slot_index": identity["slot_index"],
        "slot_identity_sha256": identity["slot_identity_sha256"],
        "sample_key": sample["sample_key"],
        "sample_identity_sha256": identity["sample_identity_sha256"],
        "exact_input_sha256": identity["exact_input_sha256"],
        "family_role": sample["family_role"],
        "component_key": component["component_key"],
        "component_ordinal": ordinal,
        "component_identity_sha256": component_identity[
            "component_identity_sha256"
        ],
        "visual_atoms": copy.deepcopy(component["visual_atoms"]),
        "ambient_tuple": copy.deepcopy(component["ambient_tuple"]),
        "content_sha256": semantic_hash(
            {
                "visual_atoms": component["visual_atoms"],
                "ambient_tuple": component["ambient_tuple"],
            }
        ),
        "source_binding": source_binding,
        "source_binding_sha256": semantic_hash(source_binding),
    }


def build_component_record(
    sample: Mapping[str, Any],
    identity: Mapping[str, Any],
    ordinal: int,
) -> dict[str, Any]:
    payload = _record_payload(sample, identity, ordinal)
    return {
        "component_record": payload,
        "component_record_sha256": semantic_hash(payload),
    }


def verify_component_record(record: Mapping[str, Any]) -> dict[str, Any]:
    row = _strict_dict(
        record,
        {"component_record", "component_record_sha256"},
        "R23B_COMPONENT_RECORD_FIELD_SET_INVALID",
    )
    payload = row["component_record"]
    required = {
        "schema_version",
        "record_status",
        "slot_index",
        "slot_identity_sha256",
        "sample_key",
        "sample_identity_sha256",
        "exact_input_sha256",
        "family_role",
        "component_key",
        "component_ordinal",
        "component_identity_sha256",
        "visual_atoms",
        "ambient_tuple",
        "content_sha256",
        "source_binding",
        "source_binding_sha256",
    }
    _strict_dict(payload, required, "R23B_COMPONENT_RECORD_PAYLOAD_INVALID")
    if (
        payload["schema_version"] != COMPONENT_RECORD_SCHEMA_VERSION
        or payload["record_status"] != "SEALED_SUCCESSFUL_COMPONENT_SOURCE"
    ):
        raise ContractError("R23B_COMPONENT_RECORD_STATUS_INVALID", disposition="REJECT")
    if row["component_record_sha256"] != semantic_hash(payload):
        raise ContractError("R23B_COMPONENT_RECORD_HASH_MISMATCH", disposition="REJECT")
    if payload["content_sha256"] != semantic_hash(
        {
            "visual_atoms": payload["visual_atoms"],
            "ambient_tuple": payload["ambient_tuple"],
        }
    ):
        raise ContractError(
            "R23B_COMPONENT_RECORD_CONTENT_HASH_MISMATCH", disposition="REJECT"
        )
    source = payload["source_binding"]
    _strict_dict(
        source,
        {"media_binding", "evidence_binding"},
        "R23B_COMPONENT_RECORD_SOURCE_BINDING_INVALID",
    )
    media = V5.validate_media_binding(source["media_binding"])
    evidence = {
        "evidence_sha256": media["evidence_sha256"],
        "evidence_start_ms": media["evidence_start_ms"],
        "evidence_end_ms": media["evidence_end_ms"],
    }
    if source["evidence_binding"] != evidence:
        raise ContractError(
            "R23B_COMPONENT_RECORD_EVIDENCE_BINDING_MISMATCH",
            disposition="REJECT",
        )
    if payload["source_binding_sha256"] != semantic_hash(source):
        raise ContractError(
            "R23B_COMPONENT_RECORD_SOURCE_HASH_MISMATCH", disposition="REJECT"
        )
    return copy.deepcopy(row)


def _expected_stratum(family_role: str) -> str:
    role_class = "far" if family_role in V5.FAR_FAMILY_ROLES else "local"
    return f"{role_class}:{family_role}"


def _expected_media_evidence_binding(
    component_record: Mapping[str, Any],
) -> dict[str, Any]:
    trusted = verify_component_record(component_record)
    return copy.deepcopy(trusted["component_record"]["source_binding"])


def build_review_packet(
    component_record: Mapping[str, Any],
    media_evidence_binding: Mapping[str, Any],
    stratum: str,
) -> dict[str, Any]:
    """Mechanically derive an unfilled packet from one trusted sealed record."""

    trusted = verify_component_record(component_record)
    record = trusted["component_record"]
    expected_binding = _expected_media_evidence_binding(trusted)
    if dict(media_evidence_binding) != expected_binding:
        raise ContractError(
            "R23B_REVIEW_PACKET_SOURCE_BINDING_MISMATCH", disposition="REJECT"
        )
    if stratum != _expected_stratum(record["family_role"]):
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
                "version": 6,
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


REVIEW_PACKET_FIELDS = {
    "schema_version",
    "packet_payload",
    "packet_payload_sha256",
    "review_packet_key",
    "reviewer_1",
    "reviewer_2",
    "adjudication",
    "decision",
}


def verify_review_packet(
    packet: Mapping[str, Any],
    trusted_component_record: Mapping[str, Any],
) -> dict[str, Any]:
    row = _strict_dict(
        packet, REVIEW_PACKET_FIELDS, "R23B_REVIEW_PACKET_FIELD_SET_INVALID"
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
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError(
            "R23B_REVIEW_PACKET_PAYLOAD_INVALID", disposition="REJECT"
        ) from exc
    if canonical_bytes(expected) != canonical_bytes(row):
        raise ContractError(
            "R23B_REVIEW_PACKET_TRUSTED_RECORD_MISMATCH", disposition="REJECT"
        )
    return copy.deepcopy(row)


def _packet_binding(packet: Mapping[str, Any]) -> dict[str, str]:
    payload = packet["packet_payload"]
    binding = {
        "review_packet_key": packet["review_packet_key"],
        "packet_payload_sha256": packet["packet_payload_sha256"],
        "component_record_sha256": payload["component_record_sha256"],
        "content_sha256": payload["content_sha256"],
        "media_binding_sha256": payload["media_binding_sha256"],
        "evidence_binding_sha256": payload["evidence_binding_sha256"],
    }
    if any(not _valid_hash(value) for value in binding.values()):
        raise ContractError("R23B_REVIEW_PACKET_BINDING_INVALID", disposition="REJECT")
    return binding


def normalize_principal_id(value: Any) -> str:
    if not isinstance(value, str):
        raise ContractError("R23B_PRINCIPAL_ID_INVALID", disposition="REJECT")
    return " ".join(value.strip().casefold().split())


def build_synthetic_principal_registry() -> dict[str, Any]:
    principals = [
        {
            "principal_id": "opaque-reviewer-a",
            "role": "reviewer",
            "subject_commitment": semantic_hash(
                {"opaque_subject": "synthetic-reviewer-a"}
            ),
        },
        {
            "principal_id": "opaque-reviewer-b",
            "role": "reviewer",
            "subject_commitment": semantic_hash(
                {"opaque_subject": "synthetic-reviewer-b"}
            ),
        },
        {
            "principal_id": "opaque-adjudicator-c",
            "role": "adjudicator",
            "subject_commitment": semantic_hash(
                {"opaque_subject": "synthetic-adjudicator-c"}
            ),
        },
    ]
    payload = {
        "schema_version": PRINCIPAL_REGISTRY_SCHEMA_VERSION,
        "registry_id": "synthetic-opaque-r23b-v6-principals",
        "provisioning_status": "SYNTHETIC_OPAQUE_CURRENT_INTEGRITY_ONLY",
        "real_human_identity_proven": False,
        "principals": principals,
    }
    payload["registry_payload_sha256"] = semantic_hash(payload)
    return payload


PRINCIPAL_REGISTRY_FIELDS = {
    "schema_version",
    "registry_id",
    "provisioning_status",
    "real_human_identity_proven",
    "principals",
    "registry_payload_sha256",
}


def verify_principal_registry(registry: Mapping[str, Any]) -> dict[str, Any]:
    row = _strict_dict(
        registry,
        PRINCIPAL_REGISTRY_FIELDS,
        "R23B_PRINCIPAL_REGISTRY_FIELD_SET_INVALID",
    )
    payload = copy.deepcopy(row)
    observed = payload.pop("registry_payload_sha256")
    if observed != semantic_hash(payload):
        raise ContractError(
            "R23B_PRINCIPAL_REGISTRY_HASH_MISMATCH", disposition="REJECT"
        )
    if row["schema_version"] != PRINCIPAL_REGISTRY_SCHEMA_VERSION:
        raise ContractError(
            "R23B_PRINCIPAL_REGISTRY_SCHEMA_INVALID", disposition="REJECT"
        )
    if type(row["principals"]) is not list or not row["principals"]:
        raise ContractError(
            "R23B_PRINCIPAL_REGISTRY_EMPTY", disposition="REJECT"
        )
    ids: set[str] = set()
    subjects: set[str] = set()
    roles: set[str] = set()
    for principal in row["principals"]:
        _strict_dict(
            principal,
            {"principal_id", "role", "subject_commitment"},
            "R23B_PRINCIPAL_REGISTRY_ENTRY_INVALID",
        )
        normalized = normalize_principal_id(principal["principal_id"])
        if principal["principal_id"] != normalized or not normalized:
            raise ContractError(
                "R23B_PRINCIPAL_REGISTRY_ID_NOT_CANONICAL",
                disposition="REJECT",
            )
        if normalized in ids:
            raise ContractError(
                "R23B_PRINCIPAL_REGISTRY_ID_DUPLICATE", disposition="REJECT"
            )
        if principal["role"] not in {"reviewer", "adjudicator"}:
            raise ContractError(
                "R23B_PRINCIPAL_REGISTRY_ROLE_INVALID", disposition="REJECT"
            )
        if not _valid_hash(principal["subject_commitment"]):
            raise ContractError(
                "R23B_PRINCIPAL_SUBJECT_COMMITMENT_INVALID",
                disposition="REJECT",
            )
        if principal["subject_commitment"] in subjects:
            raise ContractError(
                "R23B_PRINCIPAL_SUBJECT_COMMITMENT_DUPLICATE",
                disposition="REJECT",
            )
        ids.add(normalized)
        subjects.add(principal["subject_commitment"])
        roles.add(principal["role"])
    if roles != {"reviewer", "adjudicator"}:
        raise ContractError(
            "R23B_PRINCIPAL_REGISTRY_ROLE_COVERAGE_INVALID",
            disposition="REJECT",
        )
    return copy.deepcopy(row)


def _principal(
    registry: Mapping[str, Any],
    supplied_id: Any,
    expected_role: str,
) -> dict[str, Any]:
    trusted = verify_principal_registry(registry)
    normalized = normalize_principal_id(supplied_id)
    if supplied_id != normalized:
        raise ContractError(
            "R23B_PRINCIPAL_ID_NOT_CANONICAL_EXACT", disposition="REJECT"
        )
    matches = [
        row for row in trusted["principals"] if row["principal_id"] == supplied_id
    ]
    if len(matches) != 1:
        raise ContractError("R23B_PRINCIPAL_NOT_REGISTERED", disposition="REJECT")
    if matches[0]["role"] != expected_role:
        raise ContractError("R23B_PRINCIPAL_ROLE_MISMATCH", disposition="REJECT")
    return matches[0]


REVIEW_BINDING_FIELDS = (
    "review_packet_key",
    "packet_payload_sha256",
    "component_record_sha256",
    "content_sha256",
    "media_binding_sha256",
    "evidence_binding_sha256",
)


def _validate_review_submission(
    value: Any, registry: Mapping[str, Any]
) -> dict[str, Any]:
    row = _strict_dict(
        value,
        {
            *REVIEW_BINDING_FIELDS,
            "principal_id",
            "action_correct",
            "object_tokens_correct",
            "decision",
            "reasons",
        },
        "R23B_REVIEW_SUBMISSION_FIELD_SET_INVALID",
    )
    if any(not _valid_hash(row[field]) for field in REVIEW_BINDING_FIELDS):
        raise ContractError("R23B_REVIEW_BINDING_INVALID", disposition="REJECT")
    _principal(registry, row["principal_id"], "reviewer")
    if type(row["action_correct"]) is not bool or type(
        row["object_tokens_correct"]
    ) is not bool:
        raise ContractError("R23B_REVIEW_BOOLEAN_INVALID", disposition="REJECT")
    expected = (
        "PASS"
        if row["action_correct"] and row["object_tokens_correct"]
        else "FAIL"
    )
    if row["decision"] != expected:
        raise ContractError(
            "R23B_REVIEW_DECISION_INCONSISTENT", disposition="REJECT"
        )
    if type(row["reasons"]) is not list or any(
        not isinstance(item, str) for item in row["reasons"]
    ):
        raise ContractError("R23B_REVIEW_REASONS_INVALID", disposition="REJECT")
    return copy.deepcopy(row)


def _validate_adjudication(
    value: Any, registry: Mapping[str, Any]
) -> dict[str, Any]:
    row = _strict_dict(
        value,
        {
            *REVIEW_BINDING_FIELDS,
            "principal_id",
            "decision",
            "reasons",
        },
        "R23B_ADJUDICATION_FIELD_SET_INVALID",
    )
    if any(not _valid_hash(row[field]) for field in REVIEW_BINDING_FIELDS):
        raise ContractError("R23B_ADJUDICATION_BINDING_INVALID", disposition="REJECT")
    _principal(registry, row["principal_id"], "adjudicator")
    if row["decision"] not in {"PASS", "FAIL"}:
        raise ContractError(
            "R23B_ADJUDICATION_DECISION_INVALID", disposition="REJECT"
        )
    if type(row["reasons"]) is not list or any(
        not isinstance(item, str) for item in row["reasons"]
    ):
        raise ContractError("R23B_ADJUDICATION_REASONS_INVALID", disposition="REJECT")
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
    binding = _packet_binding(packet)
    if reviewer_1 is None or reviewer_2 is None:
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "MISSING_REQUIRED_REVIEWER",
        }
    left = _validate_review_submission(reviewer_1, principal_registry)
    right = _validate_review_submission(reviewer_2, principal_registry)
    for index, row in enumerate((left, right), 1):
        if any(row[field] != binding[field] for field in REVIEW_BINDING_FIELDS):
            return {
                "status": "FAIL_CLOSED",
                "decision": "REJECT_SAMPLE",
                "reason": f"REVIEWER_{index}_PACKET_BINDING_MISMATCH",
            }
    left_principal = _principal(
        principal_registry, left["principal_id"], "reviewer"
    )
    right_principal = _principal(
        principal_registry, right["principal_id"], "reviewer"
    )
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
    if left["decision"] == right["decision"]:
        return {
            "status": "COMPLETE",
            "decision": (
                "PASS_REVIEW" if left["decision"] == "PASS" else "REJECT_SAMPLE"
            ),
            "reason": "REVIEWERS_AGREE",
        }
    if adjudication is None:
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "CONFLICT_REQUIRES_ADJUDICATION",
        }
    resolved = _validate_adjudication(adjudication, principal_registry)
    if any(
        resolved[field] != binding[field] for field in REVIEW_BINDING_FIELDS
    ):
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "ADJUDICATION_PACKET_BINDING_MISMATCH",
        }
    adjudicator = _principal(
        principal_registry, resolved["principal_id"], "adjudicator"
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
    return {
        "status": "COMPLETE",
        "decision": (
            "PASS_REVIEW"
            if resolved["decision"] == "PASS"
            else "REJECT_SAMPLE"
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
    registry = verify_principal_registry(principal_registry)
    decision = evaluate_review_result(
        review_packet,
        trusted_component_record,
        reviewer_1,
        reviewer_2,
        adjudication,
        registry,
    )
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
        "review_packet": copy.deepcopy(dict(review_packet)),
        "reviewer_1": copy.deepcopy(dict(reviewer_1)),
        "reviewer_2": copy.deepcopy(dict(reviewer_2)),
        "adjudication": (
            copy.deepcopy(dict(adjudication)) if adjudication is not None else None
        ),
        "decision": decision,
    }
    payload["receipt_payload_sha256"] = semantic_hash(payload)
    return payload


REVIEW_RECEIPT_FIELDS = {
    "schema_version",
    "integrity_claim",
    "external_signature_verified",
    "component_record_sha256",
    "principal_registry_schema_version",
    "principal_registry_payload_sha256",
    "review_packet",
    "reviewer_1",
    "reviewer_2",
    "adjudication",
    "decision",
    "receipt_payload_sha256",
}


def verify_review_receipt(
    receipt: Mapping[str, Any],
    trusted_component_record: Mapping[str, Any],
    principal_registry: Mapping[str, Any],
) -> dict[str, Any]:
    row = _strict_dict(
        receipt, REVIEW_RECEIPT_FIELDS, "R23B_REVIEW_RECEIPT_FIELD_SET_INVALID"
    )
    payload = copy.deepcopy(row)
    observed = payload.pop("receipt_payload_sha256")
    if observed != semantic_hash(payload):
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


def _selection_hash(record: Mapping[str, Any]) -> str:
    payload = record["component_record"]
    return semantic_hash(
        {
            "component_identity_sha256": payload[
                "component_identity_sha256"
            ],
            "content_sha256": payload["content_sha256"],
            "source_binding_sha256": payload["source_binding_sha256"],
        }
    )


def _human_review_interface(
    component_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_identity: dict[str, Mapping[str, Any]] = {}
    for record in sorted(component_records, key=_selection_hash):
        identity = record["component_record"]["component_identity_sha256"]
        by_identity.setdefault(identity, record)
    candidates = list(by_identity.values())
    count = math.ceil(len(candidates) * HUMAN_REVIEW_RATE)
    selected = sorted(candidates, key=_selection_hash)[:count]
    packets = [
        build_review_packet(
            record,
            record["component_record"]["source_binding"],
            _expected_stratum(record["component_record"]["family_role"]),
        )
        for record in selected
    ]
    return {
        "status": "INTERFACE_ONLY_NOT_EXECUTED",
        "candidate_count": len(candidates),
        "planned_review_count": count,
        "derivation": (
            "sealed successful component/source record -> mechanical packet"
        ),
        "review_rows": packets,
    }


def execution_scope() -> dict[str, Any]:
    return {
        "integrity_claim": INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
        "external_signature_verified": False,
        "real_human_identity_proven": False,
        "model_calls": 0,
        "authorization_calls": 0,
        "media_decode": False,
        "existing_authoring_modified": False,
        "existing_canary_selection_modified": False,
        "existing_markers_modified": False,
        "existing_capsules_modified": False,
    }


def synthetic_samples() -> list[dict[str, Any]]:
    return V5.synthetic_samples()


def build_authoring_bundle(
    samples: Sequence[Any],
    slot_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes)):
        raise ContractError("R23B_INPUT_SET_NOT_SEQUENCE", disposition="REJECT")
    raw_samples = list(samples)
    trusted_manifest = verify_slot_manifest(slot_manifest)
    if trusted_manifest["input_count"] != len(raw_samples):
        raise ContractError("R23B_SLOT_MANIFEST_COUNT_MISMATCH", disposition="REJECT")
    manifest_hash = trusted_manifest["slot_manifest_payload_sha256"]
    sealed_inputs = [
        _capture_input_identity(value, slot, manifest_hash)
        for value, slot in zip(
            raw_samples, trusted_manifest["slots"], strict=True
        )
    ]

    sample_results: list[dict[str, Any]] = []
    component_records: list[dict[str, Any]] = []
    primary_queries: list[dict[str, Any]] = []
    ambient_occurrences: list[dict[str, Any]] = []
    semantic_failures = False
    for raw, identity in zip(raw_samples, sealed_inputs, strict=True):
        try:
            if identity["canonicalization_status"] != "CANONICAL":
                raise ContractError("CANONICALIZATION_FAILED")
            safe = _audit_to_safe_value(identity["audit_input"])
            authored = V5.author_sample(safe, identity)
            primary_queries.extend(authored["primary_queries"])
            ambient_occurrences.extend(authored["ambient_occurrences"])
            for ordinal in range(1, len(authored["sample"]["components"]) + 1):
                component_records.append(
                    build_component_record(authored["sample"], identity, ordinal)
                )
            sample_results.append(
                {
                    "slot_index": identity["slot_index"],
                    "slot_identity_sha256": identity["slot_identity_sha256"],
                    "sample_key": identity["sample_key"],
                    "sample_identity_sha256": identity[
                        "sample_identity_sha256"
                    ],
                    "exact_input_sha256": identity["exact_input_sha256"],
                    "disposition": "STRUCTURED_CANDIDATE",
                    "failure_stage": None,
                    "reasons": [],
                }
            )
        except Exception as exc:  # noqa: BLE001 - per-sample fail closed
            semantic_failures = True
            code = exc.code if isinstance(exc, ContractError) else getattr(
                exc, "code", f"R23B_PREVALIDATION_EXCEPTION:{_native_exception_label(exc)}"
            )
            sample_results.append(
                {
                    "slot_index": identity["slot_index"],
                    "slot_identity_sha256": identity["slot_identity_sha256"],
                    "sample_key": identity["sample_key"],
                    "sample_identity_sha256": identity[
                        "sample_identity_sha256"
                    ],
                    "exact_input_sha256": identity["exact_input_sha256"],
                    "disposition": "ABSTAIN",
                    "failure_stage": "PREVALIDATION_OR_AUTHORING",
                    "reasons": [str(code)],
                }
            )

    identity_analysis = _identity_analysis(sealed_inputs)
    inherited_analysis = V5.analyze_global_distinctiveness(
        primary_queries, ambient_occurrences, sealed_inputs
    )
    hard_by_class = {
        row["identity_class"]: copy.deepcopy(row)
        for row in inherited_analysis["hard_global_identity_failures"]
    }
    for row in identity_analysis["hard_global_identity_failures"]:
        hard_by_class[row["identity_class"]] = copy.deepcopy(row)
    hard = [hard_by_class[name] for name in sorted(hard_by_class)]
    gates = {
        **copy.deepcopy(inherited_analysis["gates"]),
        **copy.deepcopy(identity_analysis["gates"]),
    }
    blocking_gates = [
        name for name, result in gates.items() if result["status"] != "PASS"
    ]
    global_analysis = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "status": "PASS" if not blocking_gates else "FAIL_CLOSED",
        "blocking_gates": blocking_gates,
        "hard_global_identity_failures": hard,
        "content_duplicates": copy.deepcopy(
            identity_analysis["content_duplicates"]
        ),
        "gates": gates,
        "inherited_v5_policy": copy.deepcopy(inherited_analysis["policy"]),
        "v6_duplicate_policy": (
            "same audited content in different slots is recorded and is not "
            "exempt from the global duplicate rejection policy"
        ),
    }
    if hard:
        decision = "REJECT_SAMPLE_SET"
        for result in sample_results:
            result["disposition"] = "REJECTED_BY_GLOBAL_IDENTITY_GATE"
            result["failure_stage"] = "HARD_GLOBAL_IDENTITY_FAILURES"
            result["reasons"] = [
                finding["identity_class"] for finding in hard
            ]
    elif global_analysis["status"] != "PASS" and component_records:
        decision = "REJECT_SAMPLE_SET"
        for result in sample_results:
            if result["disposition"] == "STRUCTURED_CANDIDATE":
                result["disposition"] = "REJECTED_BY_GLOBAL_GATE"
                result["failure_stage"] = "GLOBAL_GATES"
                result["reasons"] = list(blocking_gates)
    elif semantic_failures or not raw_samples:
        decision = "ABSTAIN"
    else:
        decision = "DESIGN_PREFLIGHT_PASS"
        for result in sample_results:
            result["disposition"] = "ELIGIBLE_FOR_FUTURE_REVIEW"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "date": CURRENT_DATE,
        "decision_token": DECISION_TOKEN,
        "decision": decision,
        "slot_manifest_binding": {
            "schema_version": trusted_manifest["schema_version"],
            "manifest_id": trusted_manifest["manifest_id"],
            "input_count": trusted_manifest["input_count"],
            "slot_manifest_payload_sha256": manifest_hash,
        },
        "sealed_inputs": sealed_inputs,
        "sample_results": sample_results,
        "successful_component_records": component_records,
        "primary_queries": primary_queries,
        "ambient_occurrences": ambient_occurrences,
        "global_distinctiveness": global_analysis,
        "human_review": _human_review_interface(component_records),
        "scope": execution_scope(),
        "provenance": {
            "tool_source_sha256": file_sha256(Path(__file__).resolve()),
            "v5_semantic_parent_source_sha256": file_sha256(ROOT / V5_TOOL),
            "slot_manifest_payload_sha256": manifest_hash,
            "sealed_input_set_sha256": semantic_hash(sealed_inputs),
            "principal_registry_schema_sha256": semantic_hash(
                principal_registry_schema_manifest()
            ),
        },
    }
    payload["bundle_payload_sha256"] = semantic_hash(payload)
    return payload


BUNDLE_FIELDS = {
    "schema_version",
    "date",
    "decision_token",
    "decision",
    "slot_manifest_binding",
    "sealed_inputs",
    "sample_results",
    "successful_component_records",
    "primary_queries",
    "ambient_occurrences",
    "global_distinctiveness",
    "human_review",
    "scope",
    "provenance",
    "bundle_payload_sha256",
}


def verify_bundle(
    bundle: Mapping[str, Any],
    trusted_slot_manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Verify with an external manifest; sealed identity fields are never trusted."""

    if trusted_slot_manifest is None:
        raise ContractError(
            "R23B_TRUSTED_SLOT_MANIFEST_REQUIRED", disposition="REJECT"
        )
    row = _strict_dict(bundle, BUNDLE_FIELDS, "R23B_BUNDLE_FIELD_SET_INVALID")
    payload = copy.deepcopy(row)
    observed = payload.pop("bundle_payload_sha256")
    if observed != semantic_hash(payload):
        raise ContractError("R23B_BUNDLE_HASH_MISMATCH", disposition="REJECT")
    manifest = verify_slot_manifest(trusted_slot_manifest)
    if row["slot_manifest_binding"] != {
        "schema_version": manifest["schema_version"],
        "manifest_id": manifest["manifest_id"],
        "input_count": manifest["input_count"],
        "slot_manifest_payload_sha256": manifest[
            "slot_manifest_payload_sha256"
        ],
    }:
        raise ContractError(
            "R23B_SLOT_MANIFEST_BINDING_MISMATCH", disposition="REJECT"
        )
    sealed_inputs = row["sealed_inputs"]
    if type(sealed_inputs) is not list or len(sealed_inputs) != manifest[
        "input_count"
    ]:
        raise ContractError("R23B_SEALED_INPUT_SET_INVALID", disposition="REJECT")
    safe_inputs: list[Any] = []
    for sealed, slot in zip(sealed_inputs, manifest["slots"], strict=True):
        raw_capture = _validate_raw_capture(sealed)
        rederived = _derive_sealed_identity(
            raw_capture, slot, manifest["slot_manifest_payload_sha256"]
        )
        if canonical_bytes(rederived) != canonical_bytes(sealed):
            raise ContractError(
                "R23B_SEALED_INPUT_IDENTITY_MISMATCH", disposition="REJECT"
            )
        if sealed["canonicalization_status"] == "CANONICAL":
            try:
                safe_inputs.append(_audit_to_safe_value(sealed["audit_input"]))
            except ContractError as exc:
                raise ContractError(
                    "R23B_CANONICAL_AUDIT_SEMANTIC_DECODE_FAILED",
                    disposition="REJECT",
                ) from exc
        else:
            safe_inputs.append(_AuditReplayValue(sealed["audit_input"]))
    expected = build_authoring_bundle(safe_inputs, manifest)
    if canonical_bytes(expected) != canonical_bytes(row):
        raise ContractError(
            "R23B_BUNDLE_RECOMPUTATION_MISMATCH", disposition="REJECT"
        )
    return {
        "status": "PASS",
        "integrity_claim": INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
        "bundle_payload_sha256": observed,
        "trusted_slot_manifest_sha256": manifest[
            "slot_manifest_payload_sha256"
        ],
    }


class _AuditReplayValue:
    """Internal replay carrier; it never carries or returns a sealed identity."""

    __slots__ = ("audit_input",)

    def __init__(self, audit_input: Mapping[str, Any]) -> None:
        self.audit_input = copy.deepcopy(dict(audit_input))


_ORIGINAL_AUDIT_ENCODE = _audit_encode


def _audit_encode(value: Any, *, seen: set[int] | None = None) -> dict[str, Any]:
    if type(value) is _AuditReplayValue:
        return copy.deepcopy(value.audit_input)
    return _ORIGINAL_AUDIT_ENCODE(value, seen=seen)


def principal_registry_schema_manifest() -> dict[str, Any]:
    return {
        "$id": PRINCIPAL_REGISTRY_SCHEMA_VERSION,
        "normalization": "strip + Unicode casefold + collapse whitespace",
        "lookup": "submission must already equal normalized form; exact registry match",
        "roles": ["reviewer", "adjudicator"],
        "role_exclusivity": True,
        "unique_subject_commitment": True,
        "identity_claim": (
            "externally provisioned registry consistency only; no real-human proof"
        ),
    }


def runtime_constants() -> dict[str, Any]:
    return {
        "raw_audit_encoding_version": 3,
        "human_review_rate": HUMAN_REVIEW_RATE,
        "unknown_public_key": UNKNOWN_PUBLIC_KEY,
        "review_packet_version": 6,
    }


def build_plan() -> dict[str, Any]:
    registry = build_synthetic_principal_registry()
    payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "date": CURRENT_DATE,
        "decision": DECISION_TOKEN,
        "experiment": "R23-B-v6",
        "complete_scientific_go": False,
        "integrity_claim": INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
        "runtime_constants": runtime_constants(),
        "slot_manifest_contract": {
            "schema_version": SLOT_MANIFEST_SCHEMA_VERSION,
            "trusted_external_argument_required_by_verify_bundle": True,
        },
        "canonicalization_contract": {
            "sealed_identity_self_reporting_permitted": False,
            "exact_input_sha256_equals_raw_bytes_sha256": True,
            "public_key_extraction": (
                "safe typed mapping pair-list string key/value or unknown"
            ),
            "same_content_different_slots": (
                "different slot identity, recorded content duplicate, hard global gate"
            ),
        },
        "review_contract": {
            "packet_source": "sealed successful component/source record",
            "packet_verifier_requires_trusted_component_record": True,
            "coordinated_packet_receipt_reseal_without_record_change": "REJECT",
            "external_signature_absent_claim": INTEGRITY_CLAIM,
        },
        "principal_registry_contract": principal_registry_schema_manifest(),
        "synthetic_principal_registry": registry,
        "synthetic_principal_registry_payload_sha256": registry[
            "registry_payload_sha256"
        ],
        "scope": execution_scope(),
        "tool": "tools/p23_102_global_distinctiveness_v6.py",
        "tests": "tooling/tests/test_p23_102_global_distinctiveness_v6.py",
        "design_doc": "docs/design/p23_102_global_distinctiveness_v6.md",
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
    plan = build_plan() if plan is None else dict(plan)
    verify_plan(plan)
    registry_manifest = principal_registry_schema_manifest()
    synthetic_registry = build_synthetic_principal_registry()
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
            "tool_source_sha256": file_sha256(Path(__file__).resolve()),
            "tests_source_sha256": file_sha256(ROOT / TEST_FILE),
            "design_doc_sha256": file_sha256(ROOT / DESIGN_DOC),
            "plan_payload_sha256": plan["plan_payload_sha256"],
            "slot_manifest_schema_sha256": semantic_hash(
                {"$id": SLOT_MANIFEST_SCHEMA_VERSION}
            ),
            "principal_registry_schema": registry_manifest,
            "principal_registry_schema_sha256": semantic_hash(
                registry_manifest
            ),
            "principal_registry_manifest": synthetic_registry,
            "principal_registry_manifest_payload_sha256": synthetic_registry[
                "registry_payload_sha256"
            ],
            "runtime_constants": runtime_constants(),
            "runtime_constants_sha256": semantic_hash(runtime_constants()),
            "v5_semantic_parent_source_sha256": file_sha256(ROOT / V5_TOOL),
        },
        "identity_disclaimer": (
            "tool verifies externally-provisioned registry consistency only; "
            "it does not prove a principal is a real human"
        ),
    }
    payload["commitment_request_payload_sha256"] = semantic_hash(payload)
    return payload


def verify_external_commitment_request(
    request: Mapping[str, Any],
) -> dict[str, Any]:
    expected = build_external_commitment_request()
    if canonical_bytes(expected) != canonical_bytes(request):
        raise ContractError(
            "R23B_COMMITMENT_REQUEST_CURRENT_BINDING_MISMATCH",
            disposition="REJECT",
        )
    return {
        "status": "PASS",
        "integrity_claim": INTEGRITY_CLAIM,
        "external_attested": False,
        "commitment_request_payload_sha256": request[
            "commitment_request_payload_sha256"
        ],
    }


def write_json(path: Path, value: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return file_sha256(path)


def _review_fixture() -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
]:
    samples = synthetic_samples()
    manifest = build_slot_manifest(len(samples))
    bundle = build_authoring_bundle(samples, manifest)
    record = bundle["successful_component_records"][0]
    packet = build_review_packet(
        record,
        record["component_record"]["source_binding"],
        _expected_stratum(record["component_record"]["family_role"]),
    )
    registry = build_synthetic_principal_registry()
    return manifest, bundle, record, packet | {"_registry": registry}


def run_self_test() -> dict[str, Any]:
    samples = synthetic_samples()
    manifest = build_slot_manifest(len(samples))
    bundle = build_authoring_bundle(samples, manifest)
    verify_bundle(bundle, manifest)

    hostile = object()
    hostile_manifest = build_slot_manifest(2, manifest_id="self-test-duplicate")
    duplicate_bundle = build_authoring_bundle([hostile, hostile], hostile_manifest)
    verify_bundle(duplicate_bundle, hostile_manifest)
    if duplicate_bundle["decision"] != "REJECT_SAMPLE_SET":
        raise ContractError("R23B_SELF_TEST_CONTENT_DUPLICATE_NOT_REJECTED")

    record = bundle["successful_component_records"][0]
    packet = build_review_packet(
        record,
        record["component_record"]["source_binding"],
        _expected_stratum(record["component_record"]["family_role"]),
    )
    registry = build_synthetic_principal_registry()
    binding = _packet_binding(packet)
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
    receipt = build_review_receipt(
        packet, record, left, right, None, registry
    )
    verify_review_receipt(receipt, record, registry)
    forged = copy.deepcopy(receipt)
    forged["review_packet"]["packet_payload"]["blind_atoms"][
        "action_claim"
    ] = "forged"
    forged_packet_payload = forged["review_packet"]["packet_payload"]
    forged["review_packet"]["packet_payload_sha256"] = semantic_hash(
        forged_packet_payload
    )
    forged["review_packet"]["review_packet_key"] = semantic_hash(
        {
            "schema": REVIEW_PACKET_SCHEMA_VERSION,
            "version": 6,
            "trusted_component_record_sha256": record[
                "component_record_sha256"
            ],
            "packet_payload_sha256": forged["review_packet"][
                "packet_payload_sha256"
            ],
        }
    )
    forged_payload = copy.deepcopy(forged)
    forged_payload.pop("receipt_payload_sha256")
    forged["receipt_payload_sha256"] = semantic_hash(forged_payload)
    try:
        verify_review_receipt(forged, record, registry)
    except ContractError:
        pass
    else:
        raise ContractError("R23B_SELF_TEST_COORDINATED_PACKET_RESEAL_ACCEPTED")
    return {
        "status": "PASS",
        "decision": DECISION_TOKEN,
        "integrity_claim": INTEGRITY_CLAIM,
        "checks": [
            "sealed_identity_rederived_not_self_reported",
            "exact_input_equals_raw_bytes_hash",
            "content_duplicate_global_reject",
            "packet_rebuilt_from_trusted_component_record",
            "principal_registry_exact_canonical_lookup",
            "current_integrity_not_external_identity_or_signature",
        ],
        "bundle_payload_sha256": bundle["bundle_payload_sha256"],
        "model_calls": 0,
        "authorization_calls": 0,
    }


def run_preflight() -> dict[str, Any]:
    samples = synthetic_samples()
    manifest = build_slot_manifest(len(samples))
    bundle = build_authoring_bundle(samples, manifest)
    bundle_verification = verify_bundle(bundle, manifest)
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
        "bundle_verifier": bundle_verification,
        "plan_verifier": plan_verification,
        "commitment_request_verifier": request_verification,
        "sample_count": len(samples),
        "component_record_count": len(
            bundle["successful_component_records"]
        ),
        "primary_query_count": len(bundle["primary_queries"]),
        "model_calls": 0,
        "authorization_calls": 0,
        "real_families_selected": 0,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("self-test")
    commands.add_parser("preflight")
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
        elif args.command == "preflight":
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


if __name__ == "__main__":
    raise SystemExit(main())
