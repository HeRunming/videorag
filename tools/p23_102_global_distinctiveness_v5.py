#!/usr/bin/env python3
"""Fail-closed, model-free R23-B v5 global-distinctiveness audit contract.

This isolated tool validates sealed structured inputs, mechanically regenerates
all descriptions/queries/rows, reruns every global gate, emits unfilled human
review packets, and checks bundles/plans against the currently loaded
implementation.  Those checks are current-implementation recomputation, not an
external trust root: coordinated code changes plus newly generated hashes are
not prevented or externally authorized by this tool.  A separate commitment
request artifact exposes exact bindings for a future independent authorization.
The tool does not run models, consume authorization, decode media, or modify
the older P23_102 authoring/canary/marker/capsule surfaces.
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
DECISION_TOKEN = "R23_B_V5_DESIGN_READY"
SCHEMA_VERSION = "av-trace.p23-102-r23b-global-distinctiveness/5.0"
PLAN_SCHEMA_VERSION = "av-trace.p23-102-r23b-global-distinctiveness-plan/5.0"
ANALYSIS_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-global-distinctiveness-analysis/5.0"
)
COMMITMENT_REQUEST_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-external-commitment-request/3.0"
)
RAW_AUDIT_ENCODING_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-canonical-typed-raw-audit/2.0"
)
REVIEW_PACKET_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-review-packet/5.0"
)
REVIEW_RECEIPT_SCHEMA_VERSION = (
    "av-trace.p23-102-r23b-review-receipt/2.0"
)
INTEGRITY_CLAIM = (
    "CURRENT_IMPLEMENTATION_RECOMPUTED_INTEGRITY_NOT_EXTERNAL_AUTHORIZATION"
)
DEFAULT_PLAN = Path(
    "data/rehearsal_plan/p23_102_global_distinctiveness_v5_plan.json"
)
DEFAULT_COMMITMENT_REQUEST = Path(
    "data/rehearsal_plan/"
    "p23_102_global_distinctiveness_v5_external_commitment_request.json"
)
PARENT_TOOL = Path("tools/p23_102_query_authoring_v2.py")
TEST_FILE = Path("tooling/tests/test_p23_102_global_distinctiveness_v5.py")
DESIGN_DOC = Path("docs/design/p23_102_global_distinctiveness_v5.md")

JACCARD_MAX_EXCLUSIVE = 0.92
MAX_VISUAL_OBJECTS = 2
MIN_DISCRIMINATIVE_DIMENSIONS = 2
HUMAN_REVIEW_RATE = 0.20
REVIEWER_COUNT = 2
MIN_BUNDLE_SAMPLE_COUNT = 1
MIN_BUNDLE_COMPONENT_COUNT = 1
MIN_EXPECTED_QUERY_COUNT = 1
SYNTHETIC_FIXTURE_SAMPLE_COUNT = 3
SYNTHETIC_FIXTURE_COMPONENT_COUNT = 6
SYNTHETIC_FIXTURE_EXPECTED_QUERY_COUNT = 15

VISUAL_KINDS = frozenset({"event", "state"})
VISUAL_ACTIONS = frozenset(
    {
        "arranging",
        "carrying",
        "closing",
        "cutting",
        "holding",
        "inspecting",
        "kneading",
        "lifting",
        "mixing",
        "opening",
        "peeling",
        "placing",
        "pouring",
        "scooping",
        "slicing",
        "standing",
        "stirring",
        "transferring",
        "turning",
        "washing",
        "wiping",
    }
)
VISUAL_OBJECTS = frozenset(
    {
        "apple",
        "bottle",
        "bowl",
        "bread",
        "carrot",
        "cloth",
        "container",
        "cup",
        "dough",
        "drawer",
        "item",
        "jar",
        "knife",
        "lid",
        "object",
        "onion",
        "pan",
        "person",
        "plate",
        "pot",
        "spoon",
        "tap",
        "tray",
    }
)
VISUAL_ATTRIBUTES = frozenset(
    {
        "closed",
        "empty",
        "full",
        "green",
        "large",
        "metal",
        "open",
        "red",
        "small",
        "wooden",
    }
)
VISUAL_LOCATIONS = frozenset(
    {"counter", "cutting_board", "drawer", "sink", "stove", "table", "tray"}
)
VISUAL_STATES = frozenset(
    {"active", "closed", "held", "open", "resting", "upright"}
)
GENERIC_ACTIONS = frozenset({"holding", "standing"})
GENERIC_OBJECTS = frozenset({"container", "object", "item", "person"})

LOCAL_FAMILY_ROLES = frozenset({"local_v15_structure"})
FAR_FAMILY_ROLES = frozenset(
    {
        "far_continuity_anaphora",
        "far_vocalization_asr_ambiguity",
        "far_structural",
    }
)
FAMILY_ROLES = LOCAL_FAMILY_ROLES | FAR_FAMILY_ROLES
ORDERED_FAMILY_RELATIONS = frozenset({"after", "before", "then"})
FAMILY_RELATIONS = ORDERED_FAMILY_RELATIONS | {"single"}

GENERIC_BLACKLIST_PATTERNS = (
    re.compile(r"\bwhat is (?:the )?person doing\b", re.IGNORECASE),
    re.compile(r"\bwhat happens (?:in|during) (?:the )?video\b", re.IGNORECASE),
    re.compile(r"\bdescribe (?:the )?(?:scene|video)\b", re.IGNORECASE),
    re.compile(r"\bwhich (?:pot|object|item|container)\b", re.IGNORECASE),
    re.compile(r"\bwhat (?:object|item|container)\b", re.IGNORECASE),
)
FORBIDDEN_LITERAL_PATTERNS = (
    re.compile(r"\b(?:family|sample|clip|query|source)[-_ ]?\d+\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?\b"),
    re.compile(r"\b(?:epic|p23[_-]?102|dataset|source video)\b", re.IGNORECASE),
)
TOKEN_RE = re.compile(r"[a-z0-9]+")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ContractError(RuntimeError):
    """Fail-closed R23-B contract error."""

    def __init__(self, code: str, *, disposition: str = "ABSTAIN") -> None:
        super().__init__(code)
        self.code = code
        self.disposition = disposition


class _SealedAuditValue:
    """Sealed fallback placeholder; never reconstructs the original object."""

    def __init__(
        self,
        audit_envelope: Mapping[str, Any],
        raw_type: str | None = None,
        sealed_identity: Mapping[str, Any] | None = None,
    ) -> None:
        self.audit_envelope = copy.deepcopy(dict(audit_envelope))
        self.raw_type = raw_type or str(audit_envelope.get("type", "audit.sealed"))
        self.sealed_identity = (
            copy.deepcopy(dict(sealed_identity))
            if sealed_identity is not None
            else None
        )


class _AuditMappingPairs(Mapping[Any, Any]):
    """Decoded audit mapping that preserves ordered key/value pairs.

    It deliberately never rebuilds a ``dict`` because audited keys may be
    unhashable (for example list or mapping keys from a hostile Mapping).
    """

    def __init__(
        self,
        entries: Sequence[tuple[Any, Any]],
        raw_type: str = "builtins.dict",
    ) -> None:
        self._entries = tuple(entries)
        self.raw_type = raw_type

    def __iter__(self):
        return (key for key, _ in self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __getitem__(self, key: Any) -> Any:
        for candidate, value in self._entries:
            try:
                if candidate == key:
                    return value
            except Exception:  # noqa: BLE001,S112 - hostile equality is untrusted
                continue
        raise KeyError(key)

    def items(self):
        return iter(self._entries)

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except (KeyError, TypeError, ValueError):
            return default


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


def _load_parent() -> Any:
    path = ROOT / PARENT_TOOL
    spec = importlib.util.spec_from_file_location(
        "p23_102_query_authoring_v2_r23b_ambient", path
    )
    if spec is None or spec.loader is None:
        raise ContractError("R23B_PARENT_AMBIENT_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PARENT = _load_parent()

MEDIA_BINDING_SCHEMA = {
    "$id": "av-trace.p23-102-r23b-media-binding/5.0",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "media_sha256",
        "evidence_sha256",
        "evidence_start_ms",
        "evidence_end_ms",
    ],
    "properties": {
        "media_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "evidence_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "evidence_start_ms": {"type": "integer", "minimum": 0},
        "evidence_end_ms": {"type": "integer", "exclusiveMinimum": 0},
    },
}
VISUAL_ATOM_SCHEMA = {
    "$id": "av-trace.p23-102-r23b-visual-atoms/5.0",
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "action", "objects", "attributes", "location", "state"],
    "properties": {
        "kind": {"enum": sorted(VISUAL_KINDS)},
        "action": {"enum": sorted(VISUAL_ACTIONS)},
        "objects": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_VISUAL_OBJECTS,
            "uniqueItems": True,
            "items": {"enum": sorted(VISUAL_OBJECTS)},
        },
        "attributes": {
            "type": "array",
            "maxItems": 2,
            "uniqueItems": True,
            "items": {"enum": sorted(VISUAL_ATTRIBUTES)},
        },
        "location": {"enum": [None, *sorted(VISUAL_LOCATIONS)]},
        "state": {"enum": [None, *sorted(VISUAL_STATES)]},
    },
}
COMPOSITION_ATOM_SCHEMA = {
    "$id": "av-trace.p23-102-r23b-composition-atoms/5.0",
    "type": "object",
    "additionalProperties": False,
    "required": ["relation"],
    "properties": {"relation": {"enum": sorted(FAMILY_RELATIONS)}},
}
SAMPLE_SCHEMA = {
    "$id": "av-trace.p23-102-r23b-sealed-input/5.0",
    "type": "object",
    "additionalProperties": False,
    "required": ["sample_key", "family_role", "components", "composition_atoms"],
    "properties": {
        "sample_key": {"type": "string", "minLength": 1},
        "family_role": {"enum": sorted(FAMILY_ROLES)},
        "components": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "component_key",
                    "visual_atoms",
                    "ambient_tuple",
                    "media_binding",
                ],
            },
        },
        "composition_atoms": COMPOSITION_ATOM_SCHEMA,
    },
}
REVIEW_SUBMISSION_SCHEMA = {
    "$id": "av-trace.p23-102-r23b-human-review-submission/5.0",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "review_packet_key",
        "packet_payload_sha256",
        "content_sha256",
        "media_binding_sha256",
        "evidence_binding_sha256",
        "reviewer_id",
        "action_correct",
        "object_tokens_correct",
        "decision",
        "reasons",
    ],
    "properties": {
        "review_packet_key": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "packet_payload_sha256": {
            "type": "string",
            "pattern": "^sha256:[0-9a-f]{64}$",
        },
        "content_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "media_binding_sha256": {
            "type": "string",
            "pattern": "^sha256:[0-9a-f]{64}$",
        },
        "evidence_binding_sha256": {
            "type": "string",
            "pattern": "^sha256:[0-9a-f]{64}$",
        },
        "reviewer_id": {"type": "string", "minLength": 1},
        "action_correct": {"type": "boolean"},
        "object_tokens_correct": {"type": "boolean"},
        "decision": {"enum": ["PASS", "FAIL"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
}
ADJUDICATION_SCHEMA = {
    "$id": "av-trace.p23-102-r23b-human-review-adjudication/5.0",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "review_packet_key",
        "packet_payload_sha256",
        "content_sha256",
        "media_binding_sha256",
        "evidence_binding_sha256",
        "adjudicator_id",
        "decision",
        "reasons",
    ],
    "properties": {
        "review_packet_key": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "packet_payload_sha256": {
            "type": "string",
            "pattern": "^sha256:[0-9a-f]{64}$",
        },
        "content_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "media_binding_sha256": {
            "type": "string",
            "pattern": "^sha256:[0-9a-f]{64}$",
        },
        "evidence_binding_sha256": {
            "type": "string",
            "pattern": "^sha256:[0-9a-f]{64}$",
        },
        "adjudicator_id": {"type": "string", "minLength": 1},
        "decision": {"enum": ["PASS", "FAIL"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
}
REVIEW_RECEIPT_SCHEMA = {
    "$id": REVIEW_RECEIPT_SCHEMA_VERSION,
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "review_packet",
        "reviewer_1",
        "reviewer_2",
        "adjudication",
        "decision",
        "receipt_payload_sha256",
    ],
}
REVIEW_PACKET_SCHEMA = {
    "$id": REVIEW_PACKET_SCHEMA_VERSION,
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "packet_payload",
        "packet_payload_sha256",
        "review_packet_key",
        "reviewer_1",
        "reviewer_2",
        "adjudication",
        "decision",
    ],
    "properties": {
        "schema_version": {"const": REVIEW_PACKET_SCHEMA_VERSION},
        "packet_payload_sha256": {
            "type": "string",
            "pattern": "^sha256:[0-9a-f]{64}$",
        },
        "review_packet_key": {
            "type": "string",
            "pattern": "^sha256:[0-9a-f]{64}$",
        },
    },
}
COMMITMENT_REQUEST_SCHEMA = {
    "$id": COMMITMENT_REQUEST_SCHEMA_VERSION,
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "date",
        "decision",
        "request_purpose",
        "integrity_claim",
        "execution",
        "external_attested",
        "bindings",
        "commitment_request_payload_sha256",
    ],
    "properties": {
        "schema_version": {"const": COMMITMENT_REQUEST_SCHEMA_VERSION},
        "execution": {"const": False},
        "external_attested": {"const": False},
    },
}

VISUAL_REGISTRY_MANIFEST = {
    "kinds": sorted(VISUAL_KINDS),
    "actions": sorted(VISUAL_ACTIONS),
    "objects": sorted(VISUAL_OBJECTS),
    "attributes": sorted(VISUAL_ATTRIBUTES),
    "locations": sorted(VISUAL_LOCATIONS),
    "states": sorted(VISUAL_STATES),
    "generic_actions": sorted(GENERIC_ACTIONS),
    "generic_objects": sorted(GENERIC_OBJECTS),
}
FAMILY_REGISTRY_MANIFEST = {
    "local_roles": sorted(LOCAL_FAMILY_ROLES),
    "far_roles": sorted(FAR_FAMILY_ROLES),
    "ordered_relations": sorted(ORDERED_FAMILY_RELATIONS),
    "single_relation": "single",
}
GENERATOR_MANIFEST = {
    "visual": "strict-kind-atoms-to-description-query/5.0",
    "ambient": "inherited-parent-deterministic-renderer",
    "family": "ordered-component-kind-visual-ambient-composition/5.0",
    "query_key": "global-keys-plus-sealed-identities-plus-query-kind/5.0",
}
GATE_MANIFEST = {
    "nonempty_primary_query_set": True,
    "row_integrity_and_regeneration": True,
    "global_sample_component_query_key_identity_uniqueness": True,
    "hard_global_identity_failure_precedence": (
        "sample_key/component_key/query_key/sample_identity/component_identity "
        "duplicates unconditionally yield REJECT_SAMPLE_SET before ABSTAIN"
    ),
    "normalized_exact_query_uniqueness": True,
    "token_jaccard_max_exclusive": JACCARD_MAX_EXCLUSIVE,
    "content_atom_signature_uniqueness": True,
    "ambient_tuple_global_uniqueness": True,
    "family_query_pair_near_collision": True,
    "atom_level_visual_specificity": {
        "minimum_independent_dimensions": MIN_DISCRIMINATIVE_DIMENSIONS,
        "generic_actions_do_not_count": sorted(GENERIC_ACTIONS),
        "generic_objects_do_not_count": sorted(GENERIC_OBJECTS),
    },
    "phrase_blacklist_defense_in_depth": True,
    "adaptive_rewrite_or_retry": False,
}
REPLACEMENT_POLICY = {
    "policy_id": "r23b-v5-preregistered-replacement-only",
    "automatic_rewrite_permitted": False,
    "adaptive_retry_permitted": False,
    "replacement_requires_future_preregistration": True,
    "replacement_pointer": None,
    "replacement_exhaustion": "NOT_EVALUATED",
}
REVIEW_POLICY = {
    "sampling_rate": HUMAN_REVIEW_RATE,
    "count_rule": "ceil(rate*candidate_count)",
    "selection_basis": "globally unique component_identity_sha256",
    "pool_deduplication": (
        "deduplicate every pool and final selection by component_identity_sha256"
    ),
    "stratification": (
        "remove selected candidates from every later pool; cover every available "
        "family-role stratum when count >= available role-stratum count"
    ),
    "reviewer_count": REVIEWER_COUNT,
    "identity_rule": (
        "two distinct reviewer IDs; conflict adjudicator ID distinct from both"
    ),
    "packet_binding_rule": (
        "all reviewer/adjudicator records exactly match review_packet_key, "
        "packet_payload_sha256, content_sha256, media_binding_sha256, and "
        "evidence_binding_sha256"
    ),
    "conflict_rule": "two reviewer disagreement requires independent adjudication",
    "missing_rule": "missing reviewer or required adjudication => FAIL_CLOSED",
    "failed_review_rule": "REJECT_SAMPLE; no text rewrite",
    "receipt_rule": (
        "recompute packet payload and key; seal exact packet, submissions, "
        "adjudication, decision, and hash"
    ),
}

CARDINALITY_POLICY = {
    "minimum_bundle_sample_count": MIN_BUNDLE_SAMPLE_COUNT,
    "minimum_bundle_component_count": MIN_BUNDLE_COMPONENT_COUNT,
    "minimum_expected_query_count": MIN_EXPECTED_QUERY_COUNT,
    "empty_input_behavior": "FAIL_CLOSED_AUDITED_ABSTAIN",
    "synthetic_fixture_counts": {
        "sample_count": SYNTHETIC_FIXTURE_SAMPLE_COUNT,
        "component_count": SYNTHETIC_FIXTURE_COMPONENT_COUNT,
        "expected_query_count": SYNTHETIC_FIXTURE_EXPECTED_QUERY_COUNT,
    },
}


def runtime_constants() -> dict[str, Any]:
    return {
        "raw_audit_encoding_version": 2,
        "jaccard_max_exclusive": JACCARD_MAX_EXCLUSIVE,
        "max_visual_objects": MAX_VISUAL_OBJECTS,
        "minimum_discriminative_dimensions": MIN_DISCRIMINATIVE_DIMENSIONS,
        "human_review_rate": HUMAN_REVIEW_RATE,
        "reviewer_count": REVIEWER_COUNT,
        "minimum_bundle_sample_count": MIN_BUNDLE_SAMPLE_COUNT,
        "minimum_bundle_component_count": MIN_BUNDLE_COMPONENT_COUNT,
        "minimum_expected_query_count": MIN_EXPECTED_QUERY_COUNT,
    }


def schema_manifest() -> dict[str, Any]:
    return {
        "raw_audit_encoding": {
            "$id": RAW_AUDIT_ENCODING_SCHEMA_VERSION,
            "version": 2,
            "root": "typed recursive tag tree with sealed unsupported envelope",
        },
        "review_packet": REVIEW_PACKET_SCHEMA,
        "media_binding": MEDIA_BINDING_SCHEMA,
        "visual_atoms": VISUAL_ATOM_SCHEMA,
        "composition_atoms": COMPOSITION_ATOM_SCHEMA,
        "sample": SAMPLE_SCHEMA,
        "review_submission": REVIEW_SUBMISSION_SCHEMA,
        "adjudication": ADJUDICATION_SCHEMA,
        "review_receipt": REVIEW_RECEIPT_SCHEMA,
        "commitment_request": COMMITMENT_REQUEST_SCHEMA,
    }


def _strict_keys(value: Any, expected: set[str], *, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ContractError(code)
    return value


def _validate_enum(value: Any, allowed: frozenset[str], code: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ContractError(code)
    return value


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _forbid_literals(text: str, *, field: str) -> None:
    if any(pattern.search(text) for pattern in FORBIDDEN_LITERAL_PATTERNS):
        raise ContractError(f"R23B_FORBIDDEN_LITERAL:{field}")


def _without_renameable_ids(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _without_renameable_ids(item)
            for key, item in value.items()
            if key not in {"sample_key", "component_key"}
        }
    if isinstance(value, list):
        return [_without_renameable_ids(item) for item in value]
    return copy.deepcopy(value)


def _type_label(value: Any) -> str:
    if isinstance(value, _SealedAuditValue):
        return value.raw_type
    if isinstance(value, _AuditMappingPairs):
        return value.raw_type
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _unsupported_type_envelope(
    value: Any,
    *,
    capture_error_type: str | None = None,
    seen: set[int] | None = None,
) -> dict[str, Any]:
    """Create a deterministic, explicitly unsupported audit envelope.

    A plain object is never represented by type alone.  An exact ``__dict__``
    is included only when it can itself be typed-encoded without recursion.
    Otherwise the envelope states that content distinction is unavailable;
    slot-bound identities provide unique audit locations without pretending
    to distinguish unobservable object content.
    """

    if isinstance(value, _SealedAuditValue):
        return copy.deepcopy(value.audit_envelope)
    value_type = type(value)
    type_label = f"{value_type.__module__}.{value_type.__qualname__}"
    envelope: dict[str, Any] = {
        "tag": "UNSUPPORTED_TYPE",
        "type": type_label,
        "module": value_type.__module__,
        "qualname": value_type.__qualname__,
        "state_status": "UNAVAILABLE",
        "failure": "UNSUPPORTED_OBJECT_TYPE",
    }
    if capture_error_type is not None:
        envelope["capture_error_type"] = capture_error_type
    state_payload: dict[str, Any] = {}
    try:
        state = object.__getattribute__(value, "__dict__")
    except Exception:  # noqa: BLE001 - object state access is optional
        state = None
    if type(state) is dict:
        state_payload["dict"] = state
    slot_names: list[str] = []
    for cls in value_type.__mro__:
        declared = cls.__dict__.get("__slots__", ())
        if isinstance(declared, str):
            declared = (declared,)
        if isinstance(declared, (tuple, list)):
            slot_names.extend(
                slot
                for slot in declared
                if isinstance(slot, str)
                and slot not in {"__dict__", "__weakref__"}
            )
    slot_state: dict[str, Any] = {}
    for slot in sorted(set(slot_names)):
        try:
            slot_state[slot] = object.__getattribute__(value, slot)
        except AttributeError:
            continue
        except Exception as exc:  # noqa: BLE001 - state is optional and fail-closed
            envelope["slot_state_error_type"] = _type_label(exc)
            slot_state = {}
            break
    if slot_state:
        state_payload["slots"] = slot_state
    if state_payload and (seen is None or id(state_payload) not in seen):
        try:
            encoded_state = _audit_encode(state_payload, seen=seen)
            envelope["state_status"] = "SAFE_TYPED_STATE"
            envelope["state"] = encoded_state
            envelope["state_sha256"] = semantic_hash(encoded_state)
        except Exception as exc:  # noqa: BLE001 - downgrade to explicit unsupported
            envelope["state_status"] = "STATE_ENCODING_FAILED"
            envelope["state_error_type"] = _type_label(exc)
    return envelope


def _safe_mapping_get(value: Any, key: str, default: Any = None) -> Any:
    if not isinstance(value, Mapping):
        return default
    try:
        return value.get(key, default)
    except Exception:  # noqa: BLE001 - hostile Mapping implementations
        return default


def _audit_encode(
    value: Any, *, seen: set[int] | None = None
) -> dict[str, Any]:
    """Encode arbitrary input with recursive type tags and canonical ordering."""

    if seen is None:
        seen = set()
    if isinstance(value, _SealedAuditValue):
        return copy.deepcopy(value.audit_envelope)
    if value is None:
        return {"tag": "null"}
    if isinstance(value, bool):
        return {"tag": "bool", "value": value}
    if isinstance(value, str):
        return {"tag": "str", "value": value}
    if isinstance(value, int):
        return {"tag": "int", "value": str(value)}
    if isinstance(value, float):
        if math.isnan(value):
            return {"tag": "float", "value": "NaN"}
        if math.isinf(value):
            return {
                "tag": "float",
                "value": "+Infinity" if value > 0 else "-Infinity",
            }
        return {"tag": "float", "value": value.hex()}
    if isinstance(value, bytes):
        return {
            "tag": "bytes",
            "base64": base64.b64encode(value).decode("ascii"),
        }
    if isinstance(value, tuple):
        if id(value) in seen:
            raise ContractError("R23B_AUDIT_RECURSION_UNSUPPORTED")
        seen.add(id(value))
        try:
            items = [_audit_encode(item, seen=seen) for item in value]
        finally:
            seen.remove(id(value))
        return {
            "tag": "tuple",
            "items": items,
        }
    if isinstance(value, list):
        if id(value) in seen:
            raise ContractError("R23B_AUDIT_RECURSION_UNSUPPORTED")
        seen.add(id(value))
        try:
            items = [_audit_encode(item, seen=seen) for item in value]
        finally:
            seen.remove(id(value))
        return {
            "tag": "list",
            "items": items,
        }
    if isinstance(value, (set, frozenset)):
        if id(value) in seen:
            raise ContractError("R23B_AUDIT_RECURSION_UNSUPPORTED")
        seen.add(id(value))
        try:
            items = [_audit_encode(item, seen=seen) for item in value]
        finally:
            seen.remove(id(value))
        items.sort(key=canonical_bytes)
        return {
            "tag": "frozenset" if isinstance(value, frozenset) else "set",
            "items": items,
        }
    if isinstance(value, Mapping):
        if id(value) in seen:
            raise ContractError("R23B_AUDIT_RECURSION_UNSUPPORTED")
        seen.add(id(value))
        try:
            entries = [
                {
                    "key": _audit_encode(key, seen=seen),
                    "value": _audit_encode(item, seen=seen),
                }
                for key, item in value.items()
            ]
        finally:
            seen.remove(id(value))
        entries.sort(
            key=lambda entry: (
                canonical_bytes(entry["key"]),
                canonical_bytes(entry["value"]),
            )
        )
        return {"tag": "mapping", "entries": entries}
    return _unsupported_type_envelope(value, seen=seen)


def _audit_encode_safely(value: Any) -> dict[str, Any]:
    try:
        return _audit_encode(value)
    except Exception as exc:  # noqa: BLE001  # pragma: no cover
        return _unsupported_type_envelope(
            value, capture_error_type=_type_label(exc)
        )


def _validate_audit_tree(value: Any) -> None:
    """Validate the sealed typed tree without reconstructing original objects."""

    row = _strict_keys(
        value,
        set(value) if isinstance(value, Mapping) else set(),
        code="R23B_AUDIT_ENCODING_INVALID",
    )
    tag = row.get("tag")
    if tag == "null":
        if set(row) != {"tag"}:
            raise ContractError(
                "R23B_AUDIT_ENCODING_INVALID", disposition="REJECT"
            )
        return
    if tag in {"bool", "str", "int", "float"}:
        if set(row) != {"tag", "value"}:
            raise ContractError(
                "R23B_AUDIT_ENCODING_INVALID", disposition="REJECT"
            )
        return
    if tag == "bytes":
        if set(row) != {"tag", "base64"}:
            raise ContractError(
                "R23B_AUDIT_ENCODING_INVALID", disposition="REJECT"
            )
        try:
            base64.b64decode(row["base64"], validate=True)
        except (TypeError, ValueError) as exc:
            raise ContractError(
                "R23B_AUDIT_ENCODING_INVALID", disposition="REJECT"
            ) from exc
        return
    if tag in {"list", "tuple", "set", "frozenset"}:
        if set(row) != {"tag", "items"} or not isinstance(row["items"], list):
            raise ContractError(
                "R23B_AUDIT_ENCODING_INVALID", disposition="REJECT"
            )
        for item in row["items"]:
            _validate_audit_tree(item)
        return
    if tag == "mapping":
        if set(row) != {"tag", "entries"} or not isinstance(
            row["entries"], list
        ):
            raise ContractError(
                "R23B_AUDIT_ENCODING_INVALID", disposition="REJECT"
            )
        for entry in row["entries"]:
            pair = _strict_keys(
                entry,
                {"key", "value"},
                code="R23B_AUDIT_ENCODING_INVALID",
            )
            _validate_audit_tree(pair["key"])
            _validate_audit_tree(pair["value"])
        return
    if tag == "UNSUPPORTED_TYPE":
        required = {
            "tag",
            "type",
            "module",
            "qualname",
            "state_status",
            "failure",
        }
        allowed = required | {
            "state",
            "state_sha256",
            "capture_error_type",
            "state_error_type",
            "slot_state_error_type",
        }
        if not required <= set(row) or not set(row) <= allowed:
            raise ContractError(
                "R23B_AUDIT_ENCODING_INVALID", disposition="REJECT"
            )
        if row["state_status"] == "SAFE_TYPED_STATE":
            if not {"state", "state_sha256"} <= set(row):
                raise ContractError(
                    "R23B_AUDIT_ENCODING_INVALID", disposition="REJECT"
                )
            _validate_audit_tree(row["state"])
            if row["state_sha256"] != semantic_hash(row["state"]):
                raise ContractError(
                    "R23B_AUDIT_ENCODING_INVALID", disposition="REJECT"
                )
        return
    raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")


def _audit_decode(
    value: Any,
    *,
    raw_type: str | None = None,
    preserve_mapping_pairs: bool = False,
) -> Any:
    if not isinstance(value, Mapping):
        raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")
    audit_type = value.get("tag")
    if audit_type == "null":
        return None
    if audit_type in {"bool", "str"}:
        return value["value"]
    if audit_type == "int":
        return int(value["value"])
    if audit_type == "float":
        names = {
            "NaN": math.nan,
            "+Infinity": math.inf,
            "-Infinity": -math.inf,
        }
        encoded = value["value"]
        return names[encoded] if encoded in names else float.fromhex(encoded)
    if audit_type == "bytes":
        return base64.b64decode(value["base64"], validate=True)
    if audit_type == "list":
        return [
            _audit_decode(
                item, preserve_mapping_pairs=preserve_mapping_pairs
            )
            for item in value["items"]
        ]
    if audit_type == "tuple":
        return tuple(
            _audit_decode(
                item, preserve_mapping_pairs=preserve_mapping_pairs
            )
            for item in value["items"]
        )
    if audit_type == "set":
        return {
            _audit_decode(
                item, preserve_mapping_pairs=preserve_mapping_pairs
            )
            for item in value["items"]
        }
    if audit_type == "frozenset":
        return frozenset(
            _audit_decode(
                item, preserve_mapping_pairs=preserve_mapping_pairs
            )
            for item in value["items"]
        )
    if audit_type == "mapping":
        entries = [
            (
                _audit_decode(
                    entry["key"],
                    preserve_mapping_pairs=preserve_mapping_pairs,
                ),
                _audit_decode(
                    entry["value"],
                    preserve_mapping_pairs=preserve_mapping_pairs,
                ),
            )
            for entry in value["entries"]
        ]
        if preserve_mapping_pairs:
            return _AuditMappingPairs(entries, raw_type or "builtins.dict")
        try:
            return dict(entries)
        except (TypeError, ValueError) as exc:
            raise ContractError(
                "R23B_AUDIT_MAPPING_KEYS_UNHASHABLE",
                disposition="REJECT",
            ) from exc
    if audit_type == "UNSUPPORTED_TYPE":
        return _SealedAuditValue(value, str(value["type"]))
    raise ContractError("R23B_AUDIT_ENCODING_INVALID", disposition="REJECT")


def _audit_decode_safely(
    value: Any,
    *,
    raw_type: str | None = None,
    preserve_mapping_pairs: bool = False,
) -> Any:
    try:
        return _audit_decode(
            value,
            raw_type=raw_type,
            preserve_mapping_pairs=preserve_mapping_pairs,
        )
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(
            "R23B_AUDIT_ENCODING_INVALID", disposition="REJECT"
        ) from exc


def _contains_unobservable_unsupported(value: Any) -> bool:
    if isinstance(value, Mapping):
        if (
            value.get("tag") == "UNSUPPORTED_TYPE"
            and value.get("state_status") != "SAFE_TYPED_STATE"
        ):
            return True
        return any(
            _contains_unobservable_unsupported(key)
            or _contains_unobservable_unsupported(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_unobservable_unsupported(item) for item in value)
    return False


def _capture_raw_bytes(value: Any) -> dict[str, Any]:
    type_label = _type_label(value)
    audit_input = _audit_encode_safely(value)
    typed_payload = {
        "schema": RAW_AUDIT_ENCODING_SCHEMA_VERSION,
        "version": 2,
        "value": audit_input,
    }
    typed_payload_sha256 = semantic_hash(typed_payload)
    try:
        raw_bytes = canonical_bytes(value)
        status = "CANONICAL"
        failure_reasons: list[str] = []
        encoding = "CANONICAL_JSON_UTF8"
    except Exception:  # noqa: BLE001 - canonicalization is a fail-closed boundary
        raw_bytes = canonical_bytes(typed_payload)
        status = "CANONICALIZATION_FAILED"
        failure_reasons = ["CANONICALIZATION_FAILED"]
        encoding = "CANONICAL_TYPED_AUDIT_JSON_UTF8"
    return {
        "raw_encoding": encoding,
        "raw_encoding_schema": RAW_AUDIT_ENCODING_SCHEMA_VERSION,
        "raw_encoding_version": 2,
        "raw_encoding_payload_sha256": typed_payload_sha256,
        "raw_bytes_base64": base64.b64encode(raw_bytes).decode("ascii"),
        "raw_bytes_sha256": bytes_hash(raw_bytes),
        "raw_type": type_label,
        "raw_type_sha256": semantic_hash(type_label),
        "canonicalization_status": status,
        "capture_reasons": failure_reasons,
        "audit_input": audit_input,
    }


def _capture_input_identity(value: Any, slot_index: int) -> dict[str, Any]:
    if (
        isinstance(value, _SealedAuditValue)
        and value.sealed_identity is not None
    ):
        if value.sealed_identity.get("slot_index") != slot_index:
            raise ContractError(
                "R23B_SEALED_INPUT_SLOT_ORDER_INVALID",
                disposition="REJECT",
            )
        return copy.deepcopy(value.sealed_identity)
    raw_capture = _capture_raw_bytes(value)
    exact_input_sha256 = raw_capture["raw_bytes_sha256"]
    try:
        content_input = _without_renameable_ids(value)
        content_input_sha256 = semantic_hash(content_input)
    except Exception:  # noqa: BLE001 - raw hostile input must become audit data
        content_input = raw_capture["audit_input"]
        content_input_sha256 = semantic_hash(
            {
                "kind": "noncanonical_content_input",
                "audit_input": content_input,
            }
        )
    components = _safe_mapping_get(value, "components", [])
    component_records = []
    if isinstance(components, list):
        for ordinal, component in enumerate(components, 1):
            try:
                component_exact_hash = semantic_hash(component)
                component_content = _without_renameable_ids(component)
                component_identity = semantic_hash(component_content)
            except (TypeError, ValueError, OverflowError, RecursionError):
                component_audit = _audit_encode_safely(component)
                component_exact_hash = semantic_hash(
                    {"kind": "noncanonical_component", "audit": component_audit}
                )
                component_identity_payload = {
                    "kind": "noncanonical_component_identity",
                    "audit": component_audit,
                }
                if _contains_unobservable_unsupported(component_audit):
                    component_identity_payload["unsupported_audit_position"] = {
                        "slot_index": slot_index,
                        "component_ordinal": ordinal,
                        "claim": "POSITION_UNIQUE_CONTENT_NOT_DISTINGUISHED",
                    }
                component_identity = semantic_hash(component_identity_payload)
            component_records.append(
                {
                    "component_ordinal": ordinal,
                    "component_key": (
                        _safe_mapping_get(component, "component_key")
                        if isinstance(component, Mapping)
                        else None
                    ),
                    "exact_component_input_sha256": component_exact_hash,
                    "component_identity_sha256": component_identity,
                }
            )
    sample_identity_payload = {
        "kind": "sample_content_identity",
        "content": content_input,
    }
    if _contains_unobservable_unsupported(raw_capture["audit_input"]):
        sample_identity_payload["unsupported_audit_position"] = {
            "slot_index": slot_index,
            "claim": "POSITION_UNIQUE_CONTENT_NOT_DISTINGUISHED",
        }
    sample_identity_sha256 = semantic_hash(sample_identity_payload)
    return {
        "slot_index": slot_index,
        "slot_identity_sha256": semantic_hash(
            {
                "kind": "input_slot",
                "slot_index": slot_index,
                "schema_version": SCHEMA_VERSION,
            }
        ),
        "sample_key": _safe_mapping_get(value, "sample_key"),
        "exact_input_sha256": exact_input_sha256,
        "content_input_sha256": content_input_sha256,
        "sample_identity_sha256": sample_identity_sha256,
        "component_identities": component_records,
        **raw_capture,
    }


def validate_media_binding(value: Any) -> dict[str, Any]:
    row = _strict_keys(
        value,
        {"media_sha256", "evidence_sha256", "evidence_start_ms", "evidence_end_ms"},
        code="R23B_MEDIA_BINDING_FIELD_SET_INVALID",
    )
    if not _valid_hash(row["media_sha256"]) or not _valid_hash(row["evidence_sha256"]):
        raise ContractError("R23B_MEDIA_BINDING_HASH_INVALID")
    start = row["evidence_start_ms"]
    end = row["evidence_end_ms"]
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or end <= start
    ):
        raise ContractError("R23B_MEDIA_BINDING_INTERVAL_INVALID")
    return dict(row)


def discriminative_dimensions(value: Mapping[str, Any]) -> tuple[str, ...]:
    dimensions = []
    if value["action"] not in GENERIC_ACTIONS:
        dimensions.append("specific_action")
    if any(item not in GENERIC_OBJECTS for item in value["objects"]):
        dimensions.append("specific_object")
    if value["attributes"]:
        dimensions.append("attribute")
    if value["location"] is not None:
        dimensions.append("location")
    if value["state"] is not None:
        dimensions.append("state")
    return tuple(dimensions)


def _visual_target_content_atoms(atoms: Mapping[str, Any]) -> tuple[str, ...]:
    result = [f"kind:{atoms['kind']}", f"action:{atoms['action']}"]
    result.extend(f"object:{item}" for item in atoms["objects"])
    result.extend(f"attribute:{item}" for item in atoms["attributes"])
    if atoms["location"] is not None:
        result.append(f"location:{atoms['location']}")
    if atoms["state"] is not None:
        result.append(f"state:{atoms['state']}")
    return tuple(result)


def validate_visual_atoms(value: Any) -> dict[str, Any]:
    row = _strict_keys(
        value,
        {"kind", "action", "objects", "attributes", "location", "state"},
        code="R23B_VISUAL_ATOM_FIELD_SET_INVALID",
    )
    kind = _validate_enum(row["kind"], VISUAL_KINDS, "R23B_VISUAL_KIND_INVALID")
    action = _validate_enum(row["action"], VISUAL_ACTIONS, "R23B_VISUAL_ACTION_INVALID")
    objects = row["objects"]
    if (
        not isinstance(objects, list)
        or not 1 <= len(objects) <= MAX_VISUAL_OBJECTS
        or len(set(objects)) != len(objects)
        or any(item not in VISUAL_OBJECTS for item in objects)
    ):
        raise ContractError("R23B_VISUAL_OBJECTS_INVALID")
    attributes = row["attributes"]
    if (
        not isinstance(attributes, list)
        or len(attributes) > 2
        or len(set(attributes)) != len(attributes)
        or any(item not in VISUAL_ATTRIBUTES for item in attributes)
    ):
        raise ContractError("R23B_VISUAL_ATTRIBUTES_INVALID")
    location = row["location"]
    if location is not None and location not in VISUAL_LOCATIONS:
        raise ContractError("R23B_VISUAL_LOCATION_INVALID")
    state = row["state"]
    if state is not None and state not in VISUAL_STATES:
        raise ContractError("R23B_VISUAL_STATE_INVALID")
    if kind == "state" and state is None:
        raise ContractError("R23B_VISUAL_STATE_REQUIRED")
    accepted = {
        "kind": kind,
        "action": action,
        "objects": list(objects),
        "attributes": list(attributes),
        "location": location,
        "state": state,
    }
    _forbid_literals(canonical_bytes(accepted).decode(), field="visual_atoms")
    if len(discriminative_dimensions(accepted)) < MIN_DISCRIMINATIVE_DIMENSIONS:
        raise ContractError("R23B_VISUAL_DISCRIMINATIVE_DIMENSIONS_INSUFFICIENT")
    return accepted


def visual_target_content_atoms(value: Mapping[str, Any]) -> tuple[str, ...]:
    return _visual_target_content_atoms(validate_visual_atoms(value))


def validate_composition_atoms(value: Any, *, component_count: int) -> dict[str, str]:
    row = _strict_keys(
        value, {"relation"}, code="R23B_COMPOSITION_ATOM_FIELD_SET_INVALID"
    )
    relation = _validate_enum(
        row["relation"], FAMILY_RELATIONS, "R23B_COMPOSITION_RELATION_INVALID"
    )
    if component_count == 1 and relation != "single":
        raise ContractError("R23B_SINGLE_COMPONENT_RELATION_INVALID")
    if component_count > 1 and relation not in ORDERED_FAMILY_RELATIONS:
        raise ContractError("R23B_MULTI_COMPONENT_ORDERED_RELATION_REQUIRED")
    return {"relation": relation}


def validate_component(value: Any) -> dict[str, Any]:
    row = _strict_keys(
        value,
        {"component_key", "visual_atoms", "ambient_tuple", "media_binding"},
        code="R23B_COMPONENT_FIELD_SET_INVALID",
    )
    component_key = row["component_key"]
    if not isinstance(component_key, str) or not component_key:
        raise ContractError("R23B_COMPONENT_KEY_INVALID")
    visual = validate_visual_atoms(row["visual_atoms"])
    ambient = PARENT.validate_ambient_semantic_tuple(row["ambient_tuple"])
    ambient_atoms = PARENT.ambient_semantic_content_atoms(ambient)
    if not any(
        atom.startswith(("timbre:", "loudness:", "temporal_pattern:"))
        for atom in ambient_atoms
    ):
        raise ContractError("R23B_COMPONENT_AMBIENT_EVENT_PLUS_PROPERTY_REQUIRED")
    return {
        "component_key": component_key,
        "visual_atoms": visual,
        "ambient_tuple": ambient,
        "media_binding": validate_media_binding(row["media_binding"]),
    }


def validate_sample(value: Any) -> dict[str, Any]:
    row = _strict_keys(
        value,
        {"sample_key", "family_role", "components", "composition_atoms"},
        code="R23B_SAMPLE_FIELD_SET_INVALID",
    )
    sample_key = row["sample_key"]
    if not isinstance(sample_key, str) or not sample_key:
        raise ContractError("R23B_SAMPLE_KEY_INVALID")
    family_role = _validate_enum(
        row["family_role"], FAMILY_ROLES, "R23B_FAMILY_ROLE_UNREGISTERED"
    )
    components_raw = row["components"]
    if not isinstance(components_raw, list) or not 1 <= len(components_raw) <= 3:
        raise ContractError("R23B_COMPONENT_COUNT_INVALID")
    components = [validate_component(item) for item in components_raw]
    component_keys = [item["component_key"] for item in components]
    if len(set(component_keys)) != len(component_keys):
        raise ContractError("R23B_COMPONENT_KEY_DUPLICATE")
    composition = validate_composition_atoms(
        row["composition_atoms"], component_count=len(components)
    )
    if family_role in FAR_FAMILY_ROLES:
        if len(components) < 2:
            raise ContractError("R23B_FAR_ROLE_REQUIRES_AT_LEAST_TWO_COMPONENTS")
        if composition["relation"] not in ORDERED_FAMILY_RELATIONS:
            raise ContractError("R23B_FAR_ROLE_ORDERED_RELATION_REQUIRED")
    return {
        "sample_key": sample_key,
        "family_role": family_role,
        "components": components,
        "composition_atoms": composition,
    }


def _render_token(value: str) -> str:
    return value.replace("_", " ")


def derive_visual_texts(value: Mapping[str, Any]) -> dict[str, Any]:
    atoms = validate_visual_atoms(value)
    clauses = [
        f"kind {atoms['kind']}",
        f"action {_render_token(atoms['action'])}",
        "objects " + " and ".join(_render_token(x) for x in atoms["objects"]),
    ]
    if atoms["attributes"]:
        clauses.append(
            "attributes " + " and ".join(_render_token(x) for x in atoms["attributes"])
        )
    if atoms["location"] is not None:
        clauses.append(f"location {_render_token(atoms['location'])}")
    if atoms["state"] is not None:
        clauses.append(f"state {_render_token(atoms['state'])}")
    description = "The visual target has " + ", ".join(clauses) + "."
    query = "Find the visual target with " + ", ".join(clauses) + "."
    _forbid_literals(description, field="visual_description")
    _forbid_literals(query, field="visual_query")
    return {
        "visual_description": description,
        "visual_query": query,
        "content_atoms": list(_visual_target_content_atoms(atoms)),
        "discriminative_dimensions": list(discriminative_dimensions(atoms)),
    }


def _ambient_anchor_text(value: Mapping[str, Any]) -> str:
    semantic = PARENT.validate_ambient_semantic_tuple(value)
    props = semantic["acoustic_properties"]
    anchors = [f"event {_render_token(semantic['event_kind'])}"]
    for name in ("timbre", "temporal_pattern", "loudness"):
        if props[name] is not None:
            anchors.append(f"{name} {_render_token(props[name])}")
    return ", ".join(anchors)


def _component_anchor_text(component: Mapping[str, Any]) -> str:
    visual = validate_visual_atoms(component["visual_atoms"])
    parts = [
        f"kind {_render_token(visual['kind'])}",
        f"action {_render_token(visual['action'])}",
        "objects " + " and ".join(_render_token(x) for x in visual["objects"]),
    ]
    if visual["attributes"]:
        parts.append(
            "attributes " + " and ".join(_render_token(x) for x in visual["attributes"])
        )
    if visual["location"] is not None:
        parts.append(f"location {_render_token(visual['location'])}")
    if visual["state"] is not None:
        parts.append(f"state {_render_token(visual['state'])}")
    return (
        "visual "
        + ", ".join(parts)
        + "; ambient "
        + _ambient_anchor_text(component["ambient_tuple"])
    )


def family_content_atoms(sample: Mapping[str, Any]) -> tuple[str, ...]:
    accepted = validate_sample(sample)
    result = [f"relation:{accepted['composition_atoms']['relation']}"]
    for component in accepted["components"]:
        result.extend(
            f"visual:{atom}" for atom in _visual_target_content_atoms(
                component["visual_atoms"]
            )
        )
        result.extend(
            f"ambient:{atom}"
            for atom in PARENT.ambient_semantic_content_atoms(
                component["ambient_tuple"]
            )
        )
    return tuple(result)


def derive_family_texts(sample: Mapping[str, Any]) -> dict[str, Any]:
    accepted = validate_sample(sample)
    relation = accepted["composition_atoms"]["relation"]
    body = f" {relation} ".join(
        f"[{_component_anchor_text(component)}]"
        for component in accepted["components"]
    )
    description = "The family target has " + body + "."
    query = "Find the family target with " + body + "."
    _forbid_literals(description, field="family_description")
    _forbid_literals(query, field="family_query")
    return {
        "family_description": description,
        "family_query": query,
        "content_atoms": list(family_content_atoms(accepted)),
    }


def derive_query_key(
    *,
    sample_identity_sha256: str,
    component_identity_sha256: str | None,
    component_ordinal: int | None,
    query_kind: str,
) -> str:
    return semantic_hash(
        {
            "sample_identity_sha256": sample_identity_sha256,
            "component_identity_sha256": component_identity_sha256,
            "component_ordinal": component_ordinal,
            "query_kind": query_kind,
        }
    )


def _make_query_row(
    *,
    query_kind: str,
    sample: Mapping[str, Any],
    component: Mapping[str, Any] | None,
    component_ordinal: int | None,
    sample_identity_sha256: str,
    component_identity_sha256: str | None,
    description: str,
    query: str,
    content_atoms: Sequence[str],
    semantic_input: Mapping[str, Any],
) -> dict[str, Any]:
    row = {
        "query_key": derive_query_key(
            sample_identity_sha256=sample_identity_sha256,
            component_identity_sha256=component_identity_sha256,
            component_ordinal=component_ordinal,
            query_kind=query_kind,
        ),
        "query_kind": query_kind,
        "sample_key": sample["sample_key"],
        "component_key": component["component_key"] if component else None,
        "sample_identity_sha256": sample_identity_sha256,
        "component_identity_sha256": component_identity_sha256,
        "component_ordinal": component_ordinal,
        "description_text": description,
        "query_text": query,
        "content_atoms": list(content_atoms),
        "content_atom_signature_sha256": semantic_hash(list(content_atoms)),
        "semantic_input": copy.deepcopy(semantic_input),
        "semantic_input_sha256": semantic_hash(semantic_input),
        "description_sha256": semantic_hash(description),
        "query_sha256": semantic_hash(query),
    }
    row["row_payload_sha256"] = semantic_hash(row)
    return row


def author_sample(value: Any, identity: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if identity is None:
        identity = _capture_input_identity(value, 1)
    sample = validate_sample(value)
    component_identities = identity["component_identities"]
    if len(component_identities) != len(sample["components"]):
        raise ContractError("R23B_COMPONENT_IDENTITY_COUNT_MISMATCH")
    rows = []
    ambient_occurrences = []
    for ordinal, component in enumerate(sample["components"], 1):
        component_identity = component_identities[ordinal - 1][
            "component_identity_sha256"
        ]
        visual = derive_visual_texts(component["visual_atoms"])
        rows.append(
            _make_query_row(
                query_kind="visual",
                sample=sample,
                component=component,
                component_ordinal=ordinal,
                sample_identity_sha256=identity["sample_identity_sha256"],
                component_identity_sha256=component_identity,
                description=visual["visual_description"],
                query=visual["visual_query"],
                content_atoms=visual["content_atoms"],
                semantic_input=component["visual_atoms"],
            )
        )
        ambient = PARENT.derive_ambient_texts(component["ambient_tuple"])
        ambient_atoms = list(
            PARENT.ambient_semantic_content_atoms(component["ambient_tuple"])
        )
        rows.append(
            _make_query_row(
                query_kind="ambient",
                sample=sample,
                component=component,
                component_ordinal=ordinal,
                sample_identity_sha256=identity["sample_identity_sha256"],
                component_identity_sha256=component_identity,
                description=ambient["ambient_description"],
                query=ambient["ambient_query"],
                content_atoms=ambient_atoms,
                semantic_input=component["ambient_tuple"],
            )
        )
        ambient_occurrences.append(
            {
                "sample_key": sample["sample_key"],
                "component_key": component["component_key"],
                "sample_identity_sha256": identity["sample_identity_sha256"],
                "component_identity_sha256": component_identity,
                "component_ordinal": ordinal,
                "ambient_tuple": copy.deepcopy(component["ambient_tuple"]),
                "ambient_tuple_sha256": semantic_hash(component["ambient_tuple"]),
            }
        )
    family = derive_family_texts(sample)
    rows.append(
        _make_query_row(
            query_kind="family",
            sample=sample,
            component=None,
            component_ordinal=None,
            sample_identity_sha256=identity["sample_identity_sha256"],
            component_identity_sha256=None,
            description=family["family_description"],
            query=family["family_query"],
            content_atoms=family["content_atoms"],
            semantic_input=sample,
        )
    )
    return {
        "sample": sample,
        "primary_queries": rows,
        "ambient_occurrences": ambient_occurrences,
        "disposition": "STRUCTURED_CANDIDATE",
    }


def _error_code(exc: Exception) -> str:
    if isinstance(exc, ContractError):
        return exc.code
    if isinstance(exc, PARENT.AuthoringError):
        return str(exc)
    return f"R23B_PREVALIDATION_EXCEPTION:{_type_label(exc)}"


def author_sample_or_abstain(
    value: Any, identity: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    if identity is None:
        identity = _capture_input_identity(value, 1)
    if identity["canonicalization_status"] != "CANONICAL":
        return {
            "disposition": "ABSTAIN",
            "failure_stage": "INPUT_CAPTURE_CANONICALIZATION",
            "reasons": list(identity["capture_reasons"]),
            "primary_queries": [],
            "ambient_occurrences": [],
            "sample": None,
        }
    try:
        return author_sample(value, identity)
    except Exception as exc:  # noqa: BLE001 - per-sample fail-closed boundary
        return {
            "disposition": "ABSTAIN",
            "failure_stage": "STRUCTURED_INPUT_VALIDATION",
            "reasons": [_error_code(exc)],
            "primary_queries": [],
            "ambient_occurrences": [],
            "sample": None,
        }


def _normalized_tokens(text: str) -> tuple[str, ...]:
    return tuple(TOKEN_RE.findall(text.casefold()))


def _normalized_text(text: str) -> str:
    return " ".join(_normalized_tokens(text))


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(_normalized_tokens(left))
    right_tokens = set(_normalized_tokens(right))
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def _expected_texts(row: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    kind = row["query_kind"]
    semantic = row["semantic_input"]
    if kind == "visual":
        derived = derive_visual_texts(semantic)
        return (
            derived["visual_description"],
            derived["visual_query"],
            derived["content_atoms"],
        )
    if kind == "ambient":
        semantic = PARENT.validate_ambient_semantic_tuple(semantic)
        derived = PARENT.derive_ambient_texts(semantic)
        return (
            derived["ambient_description"],
            derived["ambient_query"],
            list(PARENT.ambient_semantic_content_atoms(semantic)),
        )
    if kind == "family":
        derived = derive_family_texts(semantic)
        return (
            derived["family_description"],
            derived["family_query"],
            derived["content_atoms"],
        )
    raise ContractError("R23B_QUERY_KIND_INVALID", disposition="REJECT")


def query_to_content_atoms(row: Mapping[str, Any]) -> list[str]:
    """Return atoms only when the query is the exact mechanical projection."""

    _, expected_query, expected_atoms = _expected_texts(row)
    if row.get("query_text") != expected_query:
        raise ContractError(
            "R23B_QUERY_TO_ATOMS_TEXT_MISMATCH", disposition="REJECT"
        )
    if row.get("content_atoms") != expected_atoms:
        raise ContractError(
            "R23B_QUERY_TO_ATOMS_CONTENT_MISMATCH", disposition="REJECT"
        )
    return list(expected_atoms)


QUERY_ROW_FIELDS = {
    "query_key",
    "query_kind",
    "sample_key",
    "component_key",
    "sample_identity_sha256",
    "component_identity_sha256",
    "component_ordinal",
    "description_text",
    "query_text",
    "content_atoms",
    "content_atom_signature_sha256",
    "semantic_input",
    "semantic_input_sha256",
    "description_sha256",
    "query_sha256",
    "row_payload_sha256",
}


def validate_query_row_integrity(row: Mapping[str, Any]) -> None:
    _strict_keys(row, QUERY_ROW_FIELDS, code="R23B_QUERY_ROW_FIELD_SET_INVALID")
    payload = dict(row)
    observed_row_hash = payload.pop("row_payload_sha256")
    if observed_row_hash != semantic_hash(payload):
        raise ContractError("R23B_QUERY_ROW_HASH_MISMATCH", disposition="REJECT")
    if row["semantic_input_sha256"] != semantic_hash(row["semantic_input"]):
        raise ContractError("R23B_QUERY_SEMANTIC_HASH_MISMATCH", disposition="REJECT")
    if row["description_sha256"] != semantic_hash(row["description_text"]):
        raise ContractError("R23B_DESCRIPTION_HASH_MISMATCH", disposition="REJECT")
    if row["query_sha256"] != semantic_hash(row["query_text"]):
        raise ContractError("R23B_QUERY_HASH_MISMATCH", disposition="REJECT")
    if row["content_atom_signature_sha256"] != semantic_hash(row["content_atoms"]):
        raise ContractError("R23B_CONTENT_SIGNATURE_HASH_MISMATCH", disposition="REJECT")
    expected_query_key = derive_query_key(
        sample_identity_sha256=row["sample_identity_sha256"],
        component_identity_sha256=row["component_identity_sha256"],
        component_ordinal=row["component_ordinal"],
        query_kind=row["query_kind"],
    )
    if row["query_key"] != expected_query_key:
        raise ContractError("R23B_QUERY_KEY_DERIVATION_MISMATCH", disposition="REJECT")
    expected_description, expected_query, expected_atoms = _expected_texts(row)
    if (
        row["description_text"] != expected_description
        or row["query_text"] != expected_query
        or row["content_atoms"] != expected_atoms
    ):
        raise ContractError("R23B_QUERY_REGENERATION_MISMATCH", disposition="REJECT")
    if query_to_content_atoms(row) != expected_atoms:
        raise ContractError("R23B_QUERY_TO_ATOMS_MISMATCH", disposition="REJECT")


def _gate(status: bool, **details: Any) -> dict[str, Any]:
    return {"status": "PASS" if status else "FAIL_CLOSED", **details}


def _duplicate_values(values: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for value, location in values:
        grouped[value].append(location)
    return [
        {
            "value": value,
            "value_sha256": semantic_hash(value),
            "locations": locations,
        }
        for value, locations in sorted(grouped.items())
        if len(locations) > 1
    ]


def analyze_global_distinctiveness(
    rows: Sequence[Mapping[str, Any]],
    ambient_occurrences: Sequence[Mapping[str, Any]],
    sealed_inputs: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    integrity_findings = []
    generic_findings = []
    for row in rows:
        try:
            validate_query_row_integrity(row)
        except (ContractError, PARENT.AuthoringError) as exc:
            integrity_findings.append(
                {"query_key": row.get("query_key"), "reason": _error_code(exc)}
            )
            continue
        matches = [
            pattern.pattern
            for pattern in GENERIC_BLACKLIST_PATTERNS
            if pattern.search(row["query_text"])
        ]
        if matches:
            generic_findings.append(
                {"query_key": row["query_key"], "matched_patterns": matches}
            )
        if row["query_kind"] == "visual":
            dimensions = discriminative_dimensions(row["semantic_input"])
            if len(dimensions) < MIN_DISCRIMINATIVE_DIMENSIONS:
                generic_findings.append(
                    {
                        "query_key": row["query_key"],
                        "matched_patterns": [
                            "atom_level_discriminative_dimensions_insufficient"
                        ],
                    }
                )

    sample_key_values = []
    component_key_values = []
    if sealed_inputs is not None:
        for sealed in sealed_inputs:
            sample_key = sealed.get("sample_key")
            if isinstance(sample_key, str) and sample_key:
                sample_key_values.append(
                    (
                        sample_key,
                        f"slot:{sealed['slot_index']}",
                    )
                )
            for component in sealed.get("component_identities", []):
                component_key = component.get("component_key")
                if isinstance(component_key, str) and component_key:
                    component_key_values.append(
                        (
                            component_key,
                            (
                                f"slot:{sealed['slot_index']}:component:"
                                f"{component['component_ordinal']}"
                            ),
                        )
                    )
    valid_sample_key_values = [
        (value, location)
        for value, location in sample_key_values
        if isinstance(value, str) and value
    ]
    valid_component_key_values = [
        (value, location)
        for value, location in component_key_values
        if isinstance(value, str) and value
    ]
    key_findings = {
        "sample_key_duplicates": _duplicate_values(valid_sample_key_values),
        "component_key_duplicates": _duplicate_values(valid_component_key_values),
        "query_key_duplicates": _duplicate_values(
            [(str(row["query_key"]), f"row:{index}") for index, row in enumerate(rows)]
        ),
        "sample_identity_sha256_duplicates": _duplicate_values(
            [
                (
                    str(sealed["sample_identity_sha256"]),
                    f"slot:{sealed['slot_index']}",
                )
                for sealed in (sealed_inputs or [])
            ]
        ),
        "component_identity_sha256_duplicates": _duplicate_values(
            [
                (
                    str(component["component_identity_sha256"]),
                    (
                        f"slot:{sealed['slot_index']}:"
                        f"component:{component['component_ordinal']}"
                    ),
                )
                for sealed in (sealed_inputs or [])
                for component in sealed["component_identities"]
            ]
        ),
    }
    key_unique = not any(key_findings.values())
    hard_global_identity_failures = [
        {
            "identity_class": identity_class,
            "duplicates": copy.deepcopy(duplicates),
        }
        for identity_class, duplicates in key_findings.items()
        if duplicates
    ]

    exact_groups = _duplicate_values(
        [
            (_normalized_text(str(row["query_text"])), str(row["query_key"]))
            for row in rows
        ]
    )
    near_collisions = []
    family_near_collisions = []
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            similarity = token_jaccard(left["query_text"], right["query_text"])
            if similarity >= JACCARD_MAX_EXCLUSIVE:
                finding = {
                    "left_query_key": left["query_key"],
                    "right_query_key": right["query_key"],
                    "jaccard": round(similarity, 8),
                }
                near_collisions.append(finding)
                if left["query_kind"] == right["query_kind"] == "family":
                    family_near_collisions.append(finding)
    signature_groups = _duplicate_values(
        [
            (str(row["content_atom_signature_sha256"]), str(row["query_key"]))
            for row in rows
        ]
    )

    ambient_integrity_findings = []
    ambient_by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    expected_ambient_fields = {
        "sample_key",
        "component_key",
        "sample_identity_sha256",
        "component_identity_sha256",
        "component_ordinal",
        "ambient_tuple",
        "ambient_tuple_sha256",
    }
    for occurrence in ambient_occurrences:
        try:
            _strict_keys(
                occurrence,
                expected_ambient_fields,
                code="R23B_AMBIENT_OCCURRENCE_FIELD_SET_INVALID",
            )
            semantic = PARENT.validate_ambient_semantic_tuple(
                occurrence["ambient_tuple"]
            )
            observed = semantic_hash(semantic)
            if observed != occurrence["ambient_tuple_sha256"]:
                raise ContractError("R23B_AMBIENT_TUPLE_HASH_MISMATCH")
            ambient_by_hash[observed].append(
                {
                    "sample_identity_sha256": occurrence["sample_identity_sha256"],
                    "component_identity_sha256": occurrence[
                        "component_identity_sha256"
                    ],
                    "component_ordinal": occurrence["component_ordinal"],
                }
            )
        except (ContractError, PARENT.AuthoringError, KeyError) as exc:
            ambient_integrity_findings.append({"reason": _error_code(exc)})
    ambient_duplicates = [
        {"ambient_tuple_sha256": value, "occurrences": occurrences}
        for value, occurrences in sorted(ambient_by_hash.items())
        if len(occurrences) > 1
    ]

    gates = {
        "nonempty_primary_query_set": _gate(
            len(rows) >= MIN_EXPECTED_QUERY_COUNT,
            minimum=MIN_EXPECTED_QUERY_COUNT,
            observed=len(rows),
        ),
        "row_integrity_and_exact_regeneration": _gate(
            not integrity_findings, findings=integrity_findings
        ),
        "global_sample_component_query_key_identity_uniqueness": _gate(
            key_unique, findings=key_findings
        ),
        "normalized_exact_uniqueness_all_primary": _gate(
            not exact_groups, findings=exact_groups
        ),
        "token_jaccard_strictly_below_threshold_all_primary": _gate(
            not near_collisions,
            threshold=JACCARD_MAX_EXCLUSIVE,
            comparator="<",
            findings=near_collisions,
        ),
        "content_atom_signature_uniqueness": _gate(
            not signature_groups, findings=signature_groups
        ),
        "ambient_tuple_global_uniqueness": _gate(
            not ambient_duplicates and not ambient_integrity_findings,
            duplicate_findings=ambient_duplicates,
            integrity_findings=ambient_integrity_findings,
        ),
        "family_query_pair_near_collision": _gate(
            not family_near_collisions,
            threshold=JACCARD_MAX_EXCLUSIVE,
            comparator="<",
            findings=family_near_collisions,
        ),
        "atom_specificity_and_phrase_blacklist": _gate(
            not generic_findings,
            atom_level_authoritative=True,
            phrase_blacklist_defense_in_depth=True,
            findings=generic_findings,
        ),
    }
    blocking = [name for name, result in gates.items() if result["status"] != "PASS"]
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "status": "PASS" if not blocking else "FAIL_CLOSED",
        "blocking_gates": blocking,
        "hard_global_identity_failures": hard_global_identity_failures,
        "gates": gates,
        "policy": copy.deepcopy(GATE_MANIFEST),
    }


def _review_stratum(family_role: str) -> str:
    role_class = "far" if family_role in FAR_FAMILY_ROLES else "local"
    return f"{role_class}:{family_role}"


def _review_candidate(
    authored: Mapping[str, Any], identity: Mapping[str, Any], ordinal: int
) -> dict[str, Any]:
    sample = authored["sample"]
    component = sample["components"][ordinal - 1]
    component_identity = identity["component_identities"][ordinal - 1][
        "component_identity_sha256"
    ]
    binding = component["media_binding"]
    evidence_binding = {
        "evidence_sha256": binding["evidence_sha256"],
        "evidence_start_ms": binding["evidence_start_ms"],
        "evidence_end_ms": binding["evidence_end_ms"],
    }
    content_hash = semantic_hash(
        {
            "visual_atoms": component["visual_atoms"],
            "ambient_tuple": component["ambient_tuple"],
        }
    )
    selection_hash = semantic_hash(
        {
            "component_identity_sha256": component_identity,
            "content_sha256": content_hash,
            "media_binding_sha256": semantic_hash(binding),
            "evidence_binding_sha256": semantic_hash(evidence_binding),
        }
    )
    return {
        "selection_hash": selection_hash,
        "role_class": (
            "far" if sample["family_role"] in FAR_FAMILY_ROLES else "local"
        ),
        "stratum": _review_stratum(sample["family_role"]),
        "sample_key": sample["sample_key"],
        "sample_identity_sha256": identity["sample_identity_sha256"],
        "component_key": component["component_key"],
        "component_identity_sha256": component_identity,
        "component_ordinal": ordinal,
        "exact_input_sha256": identity["exact_input_sha256"],
        "content_sha256": content_hash,
        "media_binding": copy.deepcopy(binding),
        "media_binding_sha256": semantic_hash(binding),
        "evidence_binding_sha256": semantic_hash(evidence_binding),
        "blind_atoms": {
            "action_claim": component["visual_atoms"]["action"],
            "object_claims": list(component["visual_atoms"]["objects"]),
        },
    }


def _select_review_candidates(
    candidates: Sequence[Mapping[str, Any]], count: int
) -> list[Mapping[str, Any]]:
    if count == 0:
        return []
    unique_by_component: dict[str, Mapping[str, Any]] = {}
    for candidate in sorted(candidates, key=lambda row: row["selection_hash"]):
        unique_by_component.setdefault(
            str(candidate["component_identity_sha256"]), candidate
        )
    remaining = list(unique_by_component.values())
    selected: list[Mapping[str, Any]] = []
    selected_components: set[str] = set()

    def select_first(field: str, value: str) -> bool:
        for index, candidate in enumerate(remaining):
            component_identity = str(candidate["component_identity_sha256"])
            if (
                candidate[field] == value
                and component_identity not in selected_components
            ):
                selected.append(candidate)
                selected_components.add(component_identity)
                remaining.pop(index)
                return True
        return False

    available_strata = sorted(
        {candidate["stratum"] for candidate in remaining},
        key=lambda name: (
            min(
                candidate["selection_hash"]
                for candidate in remaining
                if candidate["stratum"] == name
            ),
            name,
        ),
    )
    if count >= len(available_strata):
        for stratum in available_strata:
            select_first("stratum", stratum)
    else:
        available_classes = sorted(
            {candidate["role_class"] for candidate in remaining},
            key=lambda name: (
                min(
                    candidate["selection_hash"]
                    for candidate in remaining
                    if candidate["role_class"] == name
                ),
                name,
            ),
        )
        if count >= len(available_classes):
            for role_class in available_classes:
                if len(selected) >= count:
                    break
                select_first("role_class", role_class)
        for stratum in available_strata:
            if len(selected) >= count:
                break
            if not any(row["stratum"] == stratum for row in selected):
                select_first("stratum", stratum)

    for candidate in list(remaining):
        if len(selected) >= count:
            break
        component_identity = str(candidate["component_identity_sha256"])
        if component_identity in selected_components:
            continue
        selected.append(candidate)
        selected_components.add(component_identity)
        remaining.remove(candidate)
    return sorted(selected, key=lambda row: row["selection_hash"])


def _human_review_interface(
    authored_with_identity: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> dict[str, Any]:
    candidates = []
    for authored, identity in authored_with_identity:
        for ordinal in range(1, len(authored["sample"]["components"]) + 1):
            candidates.append(_review_candidate(authored, identity, ordinal))
    unique_component_count = len(
        {str(row["component_identity_sha256"]) for row in candidates}
    )
    count = math.ceil(unique_component_count * HUMAN_REVIEW_RATE)
    selected = _select_review_candidates(candidates, count)
    review_rows = []
    for candidate in selected:
        packet_payload = dict(candidate)
        packet_payload.pop("selection_hash")
        packet_payload["questions"] = [
            "Is the blinded action claim correct for the exact evidence interval?",
            "Are all blinded object claims correct for the exact evidence interval?",
        ]
        packet_payload_sha256 = semantic_hash(packet_payload)
        row = {
            "schema_version": REVIEW_PACKET_SCHEMA_VERSION,
            "packet_payload": packet_payload,
            "packet_payload_sha256": packet_payload_sha256,
            "review_packet_key": semantic_hash(
                {
                    "schema": REVIEW_PACKET_SCHEMA_VERSION,
                    "version": 5,
                    "packet_payload_sha256": packet_payload_sha256,
                }
            ),
            "reviewer_1": None,
            "reviewer_2": None,
            "adjudication": None,
            "decision": None,
        }
        review_rows.append(row)
    return {
        "status": "INTERFACE_ONLY_NOT_EXECUTED",
        "policy": copy.deepcopy(REVIEW_POLICY),
        "candidate_count": unique_component_count,
        "raw_candidate_occurrence_count": len(candidates),
        "planned_review_count": count,
        "review_submission_schema": copy.deepcopy(REVIEW_SUBMISSION_SCHEMA),
        "adjudication_schema": copy.deepcopy(ADJUDICATION_SCHEMA),
        "review_receipt_schema": copy.deepcopy(REVIEW_RECEIPT_SCHEMA),
        "review_rows": review_rows,
    }


REVIEW_BINDING_FIELDS = (
    "review_packet_key",
    "packet_payload_sha256",
    "content_sha256",
    "media_binding_sha256",
    "evidence_binding_sha256",
)


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

REVIEW_PACKET_PAYLOAD_FIELDS = {
    "role_class",
    "stratum",
    "sample_key",
    "sample_identity_sha256",
    "component_key",
    "component_identity_sha256",
    "component_ordinal",
    "exact_input_sha256",
    "content_sha256",
    "media_binding",
    "media_binding_sha256",
    "evidence_binding_sha256",
    "blind_atoms",
    "questions",
}


def _validate_review_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    row = _strict_keys(
        packet,
        REVIEW_PACKET_FIELDS,
        code="R23B_REVIEW_PACKET_FIELD_SET_INVALID",
    )
    if row["schema_version"] != REVIEW_PACKET_SCHEMA_VERSION:
        raise ContractError(
            "R23B_REVIEW_PACKET_SCHEMA_INVALID", disposition="REJECT"
        )
    packet_payload = _strict_keys(
        row["packet_payload"],
        REVIEW_PACKET_PAYLOAD_FIELDS,
        code="R23B_REVIEW_PACKET_PAYLOAD_FIELD_SET_INVALID",
    )
    expected_payload_sha256 = semantic_hash(packet_payload)
    if row["packet_payload_sha256"] != expected_payload_sha256:
        raise ContractError(
            "R23B_REVIEW_PACKET_PAYLOAD_HASH_MISMATCH",
            disposition="REJECT",
        )
    binding = _packet_binding(row)
    media_binding = validate_media_binding(packet_payload["media_binding"])
    if semantic_hash(media_binding) != binding["media_binding_sha256"]:
        raise ContractError(
            "R23B_REVIEW_PACKET_MEDIA_BINDING_MISMATCH", disposition="REJECT"
        )
    evidence_binding = {
        "evidence_sha256": media_binding["evidence_sha256"],
        "evidence_start_ms": media_binding["evidence_start_ms"],
        "evidence_end_ms": media_binding["evidence_end_ms"],
    }
    if semantic_hash(evidence_binding) != binding["evidence_binding_sha256"]:
        raise ContractError(
            "R23B_REVIEW_PACKET_EVIDENCE_BINDING_MISMATCH", disposition="REJECT"
        )
    expected_key = semantic_hash(
        {
            "schema": REVIEW_PACKET_SCHEMA_VERSION,
            "version": 5,
            "packet_payload_sha256": expected_payload_sha256,
        }
    )
    if row["review_packet_key"] != expected_key:
        raise ContractError(
            "R23B_REVIEW_PACKET_KEY_DERIVATION_MISMATCH", disposition="REJECT"
        )
    if any(
        row[field] is not None
        for field in ("reviewer_1", "reviewer_2", "adjudication", "decision")
    ):
        raise ContractError(
            "R23B_REVIEW_PACKET_NOT_UNFILLED", disposition="REJECT"
        )
    return copy.deepcopy(dict(row))


def _packet_binding(packet: Mapping[str, Any]) -> dict[str, str]:
    packet_payload = packet.get("packet_payload")
    binding = {
        "review_packet_key": packet.get("review_packet_key"),
        "packet_payload_sha256": packet.get("packet_payload_sha256"),
        "content_sha256": (
            packet_payload.get("content_sha256")
            if isinstance(packet_payload, Mapping)
            else None
        ),
        "media_binding_sha256": (
            packet_payload.get("media_binding_sha256")
            if isinstance(packet_payload, Mapping)
            else None
        ),
        "evidence_binding_sha256": (
            packet_payload.get("evidence_binding_sha256")
            if isinstance(packet_payload, Mapping)
            else None
        ),
    }
    if any(not _valid_hash(value) for value in binding.values()):
        raise ContractError("R23B_REVIEW_PACKET_BINDING_INVALID", disposition="REJECT")
    return binding  # type: ignore[return-value]


def _validate_review_submission(value: Any) -> dict[str, Any]:
    row = _strict_keys(
        value,
        {
            *REVIEW_BINDING_FIELDS,
            "reviewer_id",
            "action_correct",
            "object_tokens_correct",
            "decision",
            "reasons",
        },
        code="R23B_REVIEW_SUBMISSION_FIELD_SET_INVALID",
    )
    if any(not _valid_hash(row[field]) for field in REVIEW_BINDING_FIELDS):
        raise ContractError("R23B_REVIEW_BINDING_INVALID", disposition="REJECT")
    if not isinstance(row["reviewer_id"], str) or not row["reviewer_id"]:
        raise ContractError("R23B_REVIEWER_ID_INVALID", disposition="REJECT")
    if not isinstance(row["action_correct"], bool) or not isinstance(
        row["object_tokens_correct"], bool
    ):
        raise ContractError("R23B_REVIEW_BOOLEAN_INVALID", disposition="REJECT")
    if row["decision"] not in {"PASS", "FAIL"}:
        raise ContractError("R23B_REVIEW_DECISION_INVALID", disposition="REJECT")
    expected = (
        "PASS"
        if row["action_correct"] and row["object_tokens_correct"]
        else "FAIL"
    )
    if row["decision"] != expected:
        raise ContractError("R23B_REVIEW_DECISION_INCONSISTENT", disposition="REJECT")
    if not isinstance(row["reasons"], list) or any(
        not isinstance(item, str) for item in row["reasons"]
    ):
        raise ContractError("R23B_REVIEW_REASONS_INVALID", disposition="REJECT")
    return dict(row)


def _validate_adjudication(value: Any) -> dict[str, Any]:
    row = _strict_keys(
        value,
        {*REVIEW_BINDING_FIELDS, "adjudicator_id", "decision", "reasons"},
        code="R23B_ADJUDICATION_FIELD_SET_INVALID",
    )
    if any(not _valid_hash(row[field]) for field in REVIEW_BINDING_FIELDS):
        raise ContractError("R23B_ADJUDICATION_BINDING_INVALID", disposition="REJECT")
    if not isinstance(row["adjudicator_id"], str) or not row["adjudicator_id"]:
        raise ContractError("R23B_ADJUDICATOR_ID_INVALID", disposition="REJECT")
    if row["decision"] not in {"PASS", "FAIL"}:
        raise ContractError("R23B_ADJUDICATION_DECISION_INVALID", disposition="REJECT")
    if not isinstance(row["reasons"], list) or any(
        not isinstance(item, str) for item in row["reasons"]
    ):
        raise ContractError("R23B_ADJUDICATION_REASONS_INVALID", disposition="REJECT")
    return dict(row)


def evaluate_review_result(
    review_packet: Mapping[str, Any],
    reviewer_1: Any,
    reviewer_2: Any,
    adjudication: Any,
) -> dict[str, Any]:
    """Apply the preregistered missing/conflict policy to supplied judgments."""

    packet_binding = _packet_binding(_validate_review_packet(review_packet))
    if reviewer_1 is None or reviewer_2 is None:
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "MISSING_REQUIRED_REVIEWER",
        }
    left = _validate_review_submission(reviewer_1)
    right = _validate_review_submission(reviewer_2)
    if any(left[field] != packet_binding[field] for field in REVIEW_BINDING_FIELDS):
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "REVIEWER_1_PACKET_BINDING_MISMATCH",
        }
    if any(right[field] != packet_binding[field] for field in REVIEW_BINDING_FIELDS):
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "REVIEWER_2_PACKET_BINDING_MISMATCH",
        }
    if any(left[field] != right[field] for field in REVIEW_BINDING_FIELDS):
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "CROSS_PACKET_REPLAY_REJECTED",
        }
    if left["reviewer_id"] == right["reviewer_id"]:
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "REVIEWERS_NOT_INDEPENDENT",
        }
    if left["decision"] == right["decision"]:
        if adjudication is not None:
            resolved = _validate_adjudication(adjudication)
            if any(
                resolved[field] != packet_binding[field]
                for field in REVIEW_BINDING_FIELDS
            ):
                return {
                    "status": "FAIL_CLOSED",
                    "decision": "REJECT_SAMPLE",
                    "reason": "ADJUDICATION_PACKET_BINDING_MISMATCH",
                }
            return {
                "status": "FAIL_CLOSED",
                "decision": "REJECT_SAMPLE",
                "reason": "UNNEEDED_ADJUDICATION_PRESENT",
            }
        return {
            "status": "COMPLETE",
            "decision": (
                "PASS_REVIEW" if left["decision"] == "PASS" else "REJECT_SAMPLE"
            ),
            "reason": "TWO_REVIEWER_AGREEMENT",
        }
    if adjudication is None:
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "CONFLICT_REQUIRES_ADJUDICATION",
        }
    resolved = _validate_adjudication(adjudication)
    if any(
        resolved[field] != packet_binding[field] for field in REVIEW_BINDING_FIELDS
    ):
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "ADJUDICATION_PACKET_BINDING_MISMATCH",
        }
    if resolved["adjudicator_id"] in {
        left["reviewer_id"],
        right["reviewer_id"],
    }:
        return {
            "status": "FAIL_CLOSED",
            "decision": "REJECT_SAMPLE",
            "reason": "ADJUDICATOR_NOT_INDEPENDENT",
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
    reviewer_1: Mapping[str, Any],
    reviewer_2: Mapping[str, Any],
    adjudication: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Seal one exact packet, its judgments, and the derived decision."""

    decision = evaluate_review_result(
        review_packet, reviewer_1, reviewer_2, adjudication
    )
    payload = {
        "schema_version": REVIEW_RECEIPT_SCHEMA_VERSION,
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
    "review_packet",
    "reviewer_1",
    "reviewer_2",
    "adjudication",
    "decision",
    "receipt_payload_sha256",
}


def verify_review_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    _strict_keys(
        receipt,
        REVIEW_RECEIPT_FIELDS,
        code="R23B_REVIEW_RECEIPT_FIELD_SET_INVALID",
    )
    if receipt["schema_version"] != REVIEW_RECEIPT_SCHEMA_VERSION:
        raise ContractError("R23B_REVIEW_RECEIPT_SCHEMA_INVALID", disposition="REJECT")
    payload = copy.deepcopy(dict(receipt))
    observed = payload.pop("receipt_payload_sha256")
    if observed != semantic_hash(payload):
        raise ContractError("R23B_REVIEW_RECEIPT_HASH_MISMATCH", disposition="REJECT")
    expected_decision = evaluate_review_result(
        receipt["review_packet"],
        receipt["reviewer_1"],
        receipt["reviewer_2"],
        receipt["adjudication"],
    )
    if receipt["decision"] != expected_decision:
        raise ContractError(
            "R23B_REVIEW_RECEIPT_DECISION_MISMATCH", disposition="REJECT"
        )
    return {
        "status": "PASS",
        "review_packet_key": receipt["review_packet"]["review_packet_key"],
        "receipt_payload_sha256": observed,
        "decision": copy.deepcopy(receipt["decision"]),
    }


def execution_scope() -> dict[str, Any]:
    return {
        "integrity_claim": INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
        "synthetic_opaque_fixtures_only": True,
        "real_family_selection_read": False,
        "private_selection_integrated": False,
        "model_calls": 0,
        "authorization_created_or_consumed": False,
        "media_decode": False,
        "embedding_calls": 0,
        "retrieval_calls": 0,
        "asr_calls": 0,
        "existing_authoring_modified": False,
        "existing_canary_selection_modified": False,
        "existing_markers_modified": False,
        "existing_capsules_modified": False,
    }


def runtime_provenance() -> dict[str, Any]:
    return {
        "tool_source_sha256": file_sha256(Path(__file__).resolve()),
        "parent_ambient_tool_source_sha256": file_sha256(ROOT / PARENT_TOOL),
        "media_binding_schema_sha256": semantic_hash(MEDIA_BINDING_SCHEMA),
        "visual_schema_sha256": semantic_hash(VISUAL_ATOM_SCHEMA),
        "composition_schema_sha256": semantic_hash(COMPOSITION_ATOM_SCHEMA),
        "sample_schema_sha256": semantic_hash(SAMPLE_SCHEMA),
        "raw_audit_encoding_schema_sha256": semantic_hash(
            {
                "$id": RAW_AUDIT_ENCODING_SCHEMA_VERSION,
                "version": 2,
                "root": (
                    "typed recursive tag tree with sealed unsupported envelope"
                ),
            }
        ),
        "review_submission_schema_sha256": semantic_hash(REVIEW_SUBMISSION_SCHEMA),
        "adjudication_schema_sha256": semantic_hash(ADJUDICATION_SCHEMA),
        "review_packet_schema_sha256": semantic_hash(REVIEW_PACKET_SCHEMA),
        "review_receipt_schema_sha256": semantic_hash(REVIEW_RECEIPT_SCHEMA),
        "commitment_request_schema_sha256": semantic_hash(
            COMMITMENT_REQUEST_SCHEMA
        ),
        "schema_manifest_sha256": semantic_hash(schema_manifest()),
        "visual_registry_sha256": semantic_hash(VISUAL_REGISTRY_MANIFEST),
        "family_registry_sha256": semantic_hash(FAMILY_REGISTRY_MANIFEST),
        "generator_manifest_sha256": semantic_hash(GENERATOR_MANIFEST),
        "visual_generator_sha256": semantic_hash(GENERATOR_MANIFEST["visual"]),
        "family_generator_sha256": semantic_hash(GENERATOR_MANIFEST["family"]),
        "query_key_generator_sha256": semantic_hash(
            GENERATOR_MANIFEST["query_key"]
        ),
        "gate_manifest_sha256": semantic_hash(GATE_MANIFEST),
        "review_policy_sha256": semantic_hash(REVIEW_POLICY),
        "replacement_policy_sha256": semantic_hash(REPLACEMENT_POLICY),
        "cardinality_policy_sha256": semantic_hash(CARDINALITY_POLICY),
        "runtime_constants_sha256": semantic_hash(runtime_constants()),
        "ambient_registry_sha256": PARENT.STRUCTURED_AMBIENT_REGISTRY_SHA256,
        "ambient_template_sha256": PARENT.AMBIENT_TEMPLATE_SHA256,
        "ambient_generator_sha256": PARENT.AMBIENT_GENERATOR_SHA256,
    }


def _sample_result(
    identity: Mapping[str, Any],
    authored: Mapping[str, Any],
) -> dict[str, Any]:
    successful = authored["disposition"] == "STRUCTURED_CANDIDATE"
    return {
        "slot_index": identity["slot_index"],
        "slot_identity_sha256": identity["slot_identity_sha256"],
        "sample_key": identity["sample_key"],
        "sample_identity_sha256": identity["sample_identity_sha256"],
        "exact_input_sha256": identity["exact_input_sha256"],
        "content_input_sha256": identity["content_input_sha256"],
        "component_identities": copy.deepcopy(identity["component_identities"]),
        "disposition": "STRUCTURED_CANDIDATE" if successful else "ABSTAIN",
        "failure_stage": None if successful else authored["failure_stage"],
        "reasons": [] if successful else list(authored["reasons"]),
        "query_keys": [row["query_key"] for row in authored["primary_queries"]],
        "provenance": {
            "identity_captured_before_validation": True,
            "raw_bytes_retained": True,
            "audit_input_retained": True,
            "automatic_rewrite_permitted": False,
            "contract_provenance_sha256": semantic_hash(runtime_provenance()),
        },
    }


def _raw_component_slot_count(samples: Sequence[Any]) -> int:
    count = 0
    for value in samples:
        if (
            isinstance(value, _SealedAuditValue)
            and value.sealed_identity is not None
        ):
            count += len(value.sealed_identity["component_identities"])
            continue
        components = _safe_mapping_get(value, "components", [])
        if isinstance(components, list):
            count += len(components)
    return count


def _cardinality_report(
    *,
    input_slot_count: int,
    visible_component_slot_count: int,
    expected_query_count: int,
) -> dict[str, Any]:
    checks = {
        "minimum_bundle_sample_count": {
            "minimum": MIN_BUNDLE_SAMPLE_COUNT,
            "observed": input_slot_count,
            "status": (
                "PASS"
                if input_slot_count >= MIN_BUNDLE_SAMPLE_COUNT
                else "FAIL_CLOSED"
            ),
        },
        "minimum_bundle_component_count": {
            "minimum": MIN_BUNDLE_COMPONENT_COUNT,
            "observed": visible_component_slot_count,
            "status": (
                "PASS"
                if visible_component_slot_count >= MIN_BUNDLE_COMPONENT_COUNT
                else "FAIL_CLOSED"
            ),
        },
        "minimum_expected_query_count": {
            "minimum": MIN_EXPECTED_QUERY_COUNT,
            "observed": expected_query_count,
            "status": (
                "PASS"
                if expected_query_count >= MIN_EXPECTED_QUERY_COUNT
                else "FAIL_CLOSED"
            ),
        },
    }
    blocking = [
        name for name, check in checks.items() if check["status"] != "PASS"
    ]
    return {
        "status": "PASS" if not blocking else "FAIL_CLOSED",
        "blocking_checks": blocking,
        "checks": checks,
        "policy": copy.deepcopy(CARDINALITY_POLICY),
    }


def build_authoring_bundle(samples: Sequence[Any]) -> dict[str, Any]:
    if not isinstance(samples, Sequence) or isinstance(samples, (str, bytes)):
        raise ContractError("R23B_INPUT_SET_NOT_SEQUENCE", disposition="REJECT")
    raw_samples = list(samples)
    sealed_inputs = [
        _capture_input_identity(value, slot_index)
        for slot_index, value in enumerate(raw_samples, 1)
    ]
    authored_records = []
    sample_results = []
    for value, identity in zip(raw_samples, sealed_inputs, strict=True):
        authored = author_sample_or_abstain(value, identity)
        authored_records.append((authored, identity))
        sample_results.append(_sample_result(identity, authored))

    successes = [
        (authored, identity)
        for authored, identity in authored_records
        if authored["disposition"] == "STRUCTURED_CANDIDATE"
    ]
    rows = [row for authored, _ in successes for row in authored["primary_queries"]]
    ambient_occurrences = [
        occurrence
        for authored, _ in successes
        for occurrence in authored["ambient_occurrences"]
    ]
    analysis = analyze_global_distinctiveness(rows, ambient_occurrences, sealed_inputs)
    hard_global_identity_failures = analysis[
        "hard_global_identity_failures"
    ]
    visible_components = _raw_component_slot_count(raw_samples)
    cardinality = _cardinality_report(
        input_slot_count=len(raw_samples),
        visible_component_slot_count=visible_components,
        expected_query_count=len(rows),
    )
    has_abstain = any(item["disposition"] == "ABSTAIN" for item in sample_results)
    if not raw_samples:
        decision = "ABSTAIN"
    elif hard_global_identity_failures:
        decision = "REJECT_SAMPLE_SET"
        for item in sample_results:
            item["disposition"] = "REJECTED_BY_GLOBAL_IDENTITY_GATE"
            item["failure_stage"] = "HARD_GLOBAL_IDENTITY_FAILURES"
            item["reasons"] = [
                failure["identity_class"]
                for failure in hard_global_identity_failures
            ]
    elif analysis["status"] != "PASS" and successes:
        decision = "REJECT_SAMPLE_SET"
        for item in sample_results:
            if item["disposition"] == "STRUCTURED_CANDIDATE":
                item["disposition"] = "REJECTED_BY_GLOBAL_GATE"
                item["failure_stage"] = "GLOBAL_GATES"
                item["reasons"] = list(analysis["blocking_gates"])
    elif has_abstain or cardinality["status"] != "PASS":
        decision = "ABSTAIN"
    else:
        decision = "DESIGN_PREFLIGHT_PASS"
        for item in sample_results:
            item["disposition"] = "ELIGIBLE_FOR_FUTURE_REVIEW"

    decision_derivation = {
        "source": "sample_results_plus_recomputed_global_gates_and_cardinality",
        "sample_dispositions": [
            {
                "slot_index": item["slot_index"],
                "disposition": item["disposition"],
                "failure_stage": item["failure_stage"],
                "reasons": list(item["reasons"]),
            }
            for item in sample_results
        ],
        "global_gate_status": analysis["status"],
        "global_blocking_gates": list(analysis["blocking_gates"]),
        "hard_global_identity_failures": copy.deepcopy(
            hard_global_identity_failures
        ),
        "decision_precedence": [
            "CONTRACT_ERROR",
            "HARD_GLOBAL_IDENTITY_FAILURES",
            "OTHER_GLOBAL_GATES",
            "SAMPLE_ABSTAIN_OR_CARDINALITY",
            "DESIGN_PREFLIGHT_PASS",
        ],
        "cardinality_status": cardinality["status"],
        "cardinality_blocking_checks": list(cardinality["blocking_checks"]),
        "derived_decision": decision,
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "date": CURRENT_DATE,
        "decision_token": DECISION_TOKEN,
        "decision": decision,
        "sealed_inputs": sealed_inputs,
        "sample_results": sample_results,
        "primary_queries": rows,
        "ambient_occurrences": ambient_occurrences,
        "global_distinctiveness": analysis,
        "cardinality": cardinality,
        "decision_derivation": decision_derivation,
        "budgets": {
            "input_slot_count": len(raw_samples),
            "visible_component_slot_count": visible_components,
            "validated_sample_count": len(successes),
            "future_visual_structured_call_per_component": 1,
            "future_ambient_structured_call_per_component": 1,
            "future_composition_relation_call_per_sample": 1,
            "additional_distinctiveness_model_calls": 0,
            "model_calls_in_this_task": 0,
        },
        "human_review": _human_review_interface(successes),
        "replacement_governance": copy.deepcopy(REPLACEMENT_POLICY),
        "scope": execution_scope(),
        "public_verifier": {
            "integrity_claim": INTEGRITY_CLAIM,
            "execution": False,
            "external_attested": False,
        },
        "scientific_estimand": {
            "name": "query_identifiability_before_learned_retrieval",
            "scientific_go_claimed": False,
            "collision_is_authoring_failure": True,
        },
        "provenance": {
            **runtime_provenance(),
            "sealed_input_set_sha256": semantic_hash(sealed_inputs),
        },
    }
    return seal_bundle(payload)


def seal_bundle(payload: Mapping[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(dict(payload))
    if "bundle_payload_sha256" in sealed:
        raise ContractError("R23B_BUNDLE_ALREADY_SEALED", disposition="REJECT")
    sealed["bundle_payload_sha256"] = semantic_hash(sealed)
    return sealed


BUNDLE_FIELDS = {
    "schema_version",
    "date",
    "decision_token",
    "decision",
    "sealed_inputs",
    "sample_results",
    "primary_queries",
    "ambient_occurrences",
    "global_distinctiveness",
    "cardinality",
    "decision_derivation",
    "budgets",
    "human_review",
    "replacement_governance",
    "scope",
    "public_verifier",
    "scientific_estimand",
    "provenance",
    "bundle_payload_sha256",
}


def verify_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute against current code; this is not external authorization."""

    _strict_keys(bundle, BUNDLE_FIELDS, code="R23B_BUNDLE_FIELD_SET_INVALID")
    payload = copy.deepcopy(dict(bundle))
    observed = payload.pop("bundle_payload_sha256")
    if observed != semantic_hash(payload):
        raise ContractError("R23B_BUNDLE_HASH_MISMATCH", disposition="REJECT")
    sealed_inputs = bundle["sealed_inputs"]
    if not isinstance(sealed_inputs, list):
        raise ContractError("R23B_SEALED_INPUT_SET_INVALID", disposition="REJECT")
    raw_inputs = []
    for expected_slot, sealed in enumerate(sealed_inputs, 1):
        expected_fields = {
            "slot_index",
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
            "raw_type",
            "raw_type_sha256",
            "canonicalization_status",
            "capture_reasons",
            "audit_input",
        }
        _strict_keys(
            sealed, expected_fields, code="R23B_SEALED_INPUT_FIELD_SET_INVALID"
        )
        if sealed["slot_index"] != expected_slot:
            raise ContractError("R23B_SEALED_INPUT_SLOT_ORDER_INVALID", disposition="REJECT")
        try:
            raw_bytes = base64.b64decode(
                sealed["raw_bytes_base64"], validate=True
            )
        except (TypeError, ValueError) as exc:
            raise ContractError(
                "R23B_RAW_BYTES_ENCODING_INVALID", disposition="REJECT"
            ) from exc
        if bytes_hash(raw_bytes) != sealed["raw_bytes_sha256"]:
            raise ContractError("R23B_RAW_BYTES_HASH_MISMATCH", disposition="REJECT")
        typed_payload = {
            "schema": sealed["raw_encoding_schema"],
            "version": sealed["raw_encoding_version"],
            "value": sealed["audit_input"],
        }
        if (
            sealed["raw_encoding_schema"] != RAW_AUDIT_ENCODING_SCHEMA_VERSION
            or sealed["raw_encoding_version"] != 2
            or sealed["raw_encoding_payload_sha256"] != semantic_hash(typed_payload)
        ):
            raise ContractError(
                "R23B_RAW_AUDIT_ENCODING_BINDING_MISMATCH",
                disposition="REJECT",
            )
        _validate_audit_tree(sealed["audit_input"])
        if (
            sealed["canonicalization_status"] == "CANONICALIZATION_FAILED"
            and raw_bytes != canonical_bytes(typed_payload)
        ):
            raise ContractError(
                "R23B_RAW_AUDIT_BYTES_MISMATCH", disposition="REJECT"
            )
        if sealed["canonicalization_status"] == "CANONICALIZATION_FAILED":
            raw_input = _SealedAuditValue(
                sealed["audit_input"],
                str(sealed["raw_type"]),
                sealed_identity=sealed,
            )
        else:
            raw_input = _audit_decode_safely(
                sealed["audit_input"],
                raw_type=sealed["raw_type"],
            )
        recaptured = _capture_input_identity(raw_input, expected_slot)
        if recaptured != sealed:
            raise ContractError(
                "R23B_SEALED_INPUT_IDENTITY_MISMATCH",
                disposition="REJECT",
            )
        raw_inputs.append(raw_input)
    expected = build_authoring_bundle(raw_inputs)
    if canonical_bytes(expected) != canonical_bytes(bundle):
        raise ContractError(
            "R23B_BUNDLE_RECOMPUTATION_MISMATCH",
            disposition="REJECT",
        )
    return {
        "status": "PASS",
        "integrity_claim": INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
        "bundle_payload_sha256": bundle["bundle_payload_sha256"],
    }


def _media(label: str, start: int) -> dict[str, Any]:
    return {
        "media_sha256": semantic_hash({"media": label}),
        "evidence_sha256": semantic_hash({"evidence": label, "start": start}),
        "evidence_start_ms": start,
        "evidence_end_ms": start + 2000,
    }


def synthetic_samples() -> list[dict[str, Any]]:
    """Opaque fixtures with no binding to real/private families."""

    def ambient(
        event: str,
        timbre: str | None,
        loudness: str | None,
        pattern: str | None,
    ) -> dict[str, Any]:
        return {
            "event_kind": event,
            "acoustic_properties": {
                "timbre": timbre,
                "loudness": loudness,
                "temporal_pattern": pattern,
            },
        }

    return [
        {
            "sample_key": "opaque-alpha",
            "family_role": "far_structural",
            "components": [
                {
                    "component_key": "opaque-alpha-a",
                    "visual_atoms": {
                        "kind": "event",
                        "action": "cutting",
                        "objects": ["knife", "carrot"],
                        "attributes": ["red"],
                        "location": "cutting_board",
                        "state": "active",
                    },
                    "ambient_tuple": ambient("scrape", "sharp", "soft", "rhythmic"),
                    "media_binding": _media("alpha-a", 1000),
                },
                {
                    "component_key": "opaque-alpha-b",
                    "visual_atoms": {
                        "kind": "event",
                        "action": "placing",
                        "objects": ["carrot", "bowl"],
                        "attributes": ["green"],
                        "location": "counter",
                        "state": "resting",
                    },
                    "ambient_tuple": ambient("clink", "metallic", "faint", "brief"),
                    "media_binding": _media("alpha-b", 4000),
                },
            ],
            "composition_atoms": {"relation": "then"},
        },
        {
            "sample_key": "opaque-beta",
            "family_role": "far_continuity_anaphora",
            "components": [
                {
                    "component_key": "opaque-beta-a",
                    "visual_atoms": {
                        "kind": "event",
                        "action": "washing",
                        "objects": ["cup", "tap"],
                        "attributes": ["small"],
                        "location": "sink",
                        "state": "held",
                    },
                    "ambient_tuple": ambient(
                        "continuous_liquid_flow", "crisp", "loud", "steady"
                    ),
                    "media_binding": _media("beta-a", 7000),
                },
                {
                    "component_key": "opaque-beta-b",
                    "visual_atoms": {
                        "kind": "event",
                        "action": "wiping",
                        "objects": ["cup", "cloth"],
                        "attributes": ["wooden"],
                        "location": "table",
                        "state": "upright",
                    },
                    "ambient_tuple": ambient("rustle", "muffled", "soft", "repeated"),
                    "media_binding": _media("beta-b", 10000),
                },
            ],
            "composition_atoms": {"relation": "after"},
        },
        {
            "sample_key": "opaque-gamma",
            "family_role": "far_vocalization_asr_ambiguity",
            "components": [
                {
                    "component_key": "opaque-gamma-a",
                    "visual_atoms": {
                        "kind": "event",
                        "action": "opening",
                        "objects": ["drawer"],
                        "attributes": ["large"],
                        "location": "counter",
                        "state": "open",
                    },
                    "ambient_tuple": ambient("creak", "hollow", "faint", "brief"),
                    "media_binding": _media("gamma-a", 13000),
                },
                {
                    "component_key": "opaque-gamma-b",
                    "visual_atoms": {
                        "kind": "event",
                        "action": "lifting",
                        "objects": ["pot", "lid"],
                        "attributes": ["metal"],
                        "location": "stove",
                        "state": "held",
                    },
                    "ambient_tuple": ambient("clang", "metallic", "loud", "brief"),
                    "media_binding": _media("gamma-b", 16000),
                },
            ],
            "composition_atoms": {"relation": "before"},
        },
    ]


def build_plan() -> dict[str, Any]:
    payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "date": CURRENT_DATE,
        "decision": DECISION_TOKEN,
        "experiment": "R23-B-v5",
        "complete_scientific_go": False,
        "integrity_claim": INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
        "runtime_constants": runtime_constants(),
        "schemas": schema_manifest(),
        "registries": {
            "visual": VISUAL_REGISTRY_MANIFEST,
            "family": FAMILY_REGISTRY_MANIFEST,
            "ambient_parent_schema": PARENT.AMBIENT_OUTPUT_SCHEMA,
        },
        "generators": GENERATOR_MANIFEST,
        "fixed_gates": GATE_MANIFEST,
        "ambient_uniqueness_policy": "global exact tuple uniqueness; fail closed",
        "review_policy": REVIEW_POLICY,
        "replacement_policy": REPLACEMENT_POLICY,
        "cardinality_policy": CARDINALITY_POLICY,
        "budget_policy": {
            "visual_structured_call_per_component": 1,
            "ambient_structured_call_per_component": 1,
            "composition_relation_call_per_sample": 1,
            "additional_distinctiveness_model_calls": 0,
        },
        "scope": execution_scope(),
        "provenance": runtime_provenance(),
        "tool": "tools/p23_102_global_distinctiveness_v5.py",
        "tests": "tooling/tests/test_p23_102_global_distinctiveness_v5.py",
        "design_doc": "docs/design/p23_102_global_distinctiveness_v5.md",
    }
    payload["plan_payload_sha256"] = semantic_hash(payload)
    return payload


PLAN_FIELDS = {
    "schema_version",
    "date",
    "decision",
    "experiment",
    "complete_scientific_go",
    "integrity_claim",
    "execution",
    "external_attested",
    "runtime_constants",
    "schemas",
    "registries",
    "generators",
    "fixed_gates",
    "ambient_uniqueness_policy",
    "review_policy",
    "replacement_policy",
    "cardinality_policy",
    "budget_policy",
    "scope",
    "provenance",
    "tool",
    "tests",
    "design_doc",
    "plan_payload_sha256",
}


def verify_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute current plan integrity without claiming external attestation."""

    _strict_keys(plan, PLAN_FIELDS, code="R23B_PLAN_FIELD_SET_INVALID")
    payload = dict(plan)
    observed = payload.pop("plan_payload_sha256")
    if observed != semantic_hash(payload):
        raise ContractError("R23B_PLAN_HASH_MISMATCH", disposition="REJECT")
    expected = build_plan()
    if canonical_bytes(expected) != canonical_bytes(plan):
        raise ContractError("R23B_PLAN_RUNTIME_CONTRACT_MISMATCH", disposition="REJECT")
    return {
        "status": "PASS",
        "integrity_claim": INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
        "plan_payload_sha256": plan["plan_payload_sha256"],
    }


def build_external_commitment_request(
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if plan is None:
        plan = build_plan()
    verify_plan(plan)
    bindings = {
        "tool_source_sha256": file_sha256(Path(__file__).resolve()),
        "tests_source_sha256": file_sha256(ROOT / TEST_FILE),
        "design_doc_sha256": file_sha256(ROOT / DESIGN_DOC),
        "plan_payload_sha256": plan["plan_payload_sha256"],
        "plan_file_expected_canonical_sha256": bytes_hash(
            json.dumps(plan, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        ),
        "gate_manifest_sha256": semantic_hash(GATE_MANIFEST),
        "schema_manifest_sha256": semantic_hash(schema_manifest()),
        "raw_audit_encoding_schema_sha256": semantic_hash(
            schema_manifest()["raw_audit_encoding"]
        ),
        "review_submission_schema_sha256": semantic_hash(
            REVIEW_SUBMISSION_SCHEMA
        ),
        "adjudication_schema_sha256": semantic_hash(ADJUDICATION_SCHEMA),
        "review_packet_schema_sha256": semantic_hash(REVIEW_PACKET_SCHEMA),
        "review_receipt_schema_sha256": semantic_hash(REVIEW_RECEIPT_SCHEMA),
        "commitment_request_schema_sha256": semantic_hash(
            COMMITMENT_REQUEST_SCHEMA
        ),
        "runtime_constants": runtime_constants(),
        "runtime_constants_sha256": semantic_hash(runtime_constants()),
        "parent_ambient_tool_source_sha256": file_sha256(ROOT / PARENT_TOOL),
    }
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
        "bindings": bindings,
    }
    payload["commitment_request_payload_sha256"] = semantic_hash(payload)
    return payload


COMMITMENT_REQUEST_FIELDS = {
    "schema_version",
    "date",
    "decision",
    "request_purpose",
    "integrity_claim",
    "execution",
    "external_attested",
    "bindings",
    "commitment_request_payload_sha256",
}


def verify_external_commitment_request(request: Mapping[str, Any]) -> dict[str, Any]:
    _strict_keys(
        request,
        COMMITMENT_REQUEST_FIELDS,
        code="R23B_COMMITMENT_REQUEST_FIELD_SET_INVALID",
    )
    payload = copy.deepcopy(dict(request))
    observed = payload.pop("commitment_request_payload_sha256")
    if observed != semantic_hash(payload):
        raise ContractError(
            "R23B_COMMITMENT_REQUEST_HASH_MISMATCH", disposition="REJECT"
        )
    expected = build_external_commitment_request()
    if canonical_bytes(expected) != canonical_bytes(request):
        raise ContractError(
            "R23B_COMMITMENT_REQUEST_CURRENT_BINDING_MISMATCH",
            disposition="REJECT",
        )
    return {
        "status": "PASS",
        "integrity_claim": INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
        "commitment_request_payload_sha256": observed,
    }


def write_json(path: Path, value: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return file_sha256(path)


def run_preflight() -> dict[str, Any]:
    bundle = build_authoring_bundle(synthetic_samples())
    bundle_verification = verify_bundle(bundle)
    plan = build_plan()
    plan_verification = verify_plan(plan)
    commitment_request = build_external_commitment_request(plan)
    commitment_verification = verify_external_commitment_request(
        commitment_request
    )
    if bundle["decision"] != "DESIGN_PREFLIGHT_PASS":
        raise ContractError("R23B_SYNTHETIC_PREFLIGHT_FAILED", disposition="REJECT")
    if len(bundle["sealed_inputs"]) != SYNTHETIC_FIXTURE_SAMPLE_COUNT:
        raise ContractError("R23B_SYNTHETIC_SAMPLE_COUNT_MISMATCH")
    if (
        bundle["budgets"]["visible_component_slot_count"]
        != SYNTHETIC_FIXTURE_COMPONENT_COUNT
    ):
        raise ContractError("R23B_SYNTHETIC_COMPONENT_COUNT_MISMATCH")
    if len(bundle["primary_queries"]) != SYNTHETIC_FIXTURE_EXPECTED_QUERY_COUNT:
        raise ContractError("R23B_SYNTHETIC_QUERY_COUNT_MISMATCH")
    return {
        "status": "PASS",
        "decision": DECISION_TOKEN,
        "integrity_claim": INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
        "bundle_payload_sha256": bundle["bundle_payload_sha256"],
        "plan_payload_sha256": plan["plan_payload_sha256"],
        "commitment_request_payload_sha256": commitment_request[
            "commitment_request_payload_sha256"
        ],
        "bundle_verifier": bundle_verification,
        "plan_verifier": plan_verification,
        "commitment_request_verifier": commitment_verification,
        "primary_query_count": len(bundle["primary_queries"]),
        "ambient_tuple_count": len(bundle["ambient_occurrences"]),
        "review_packet_count": bundle["human_review"]["planned_review_count"],
        "model_calls": 0,
        "embedding_calls": 0,
        "retrieval_calls": 0,
        "authorization_calls": 0,
        "real_families_selected": 0,
    }


def run_self_test() -> dict[str, Any]:
    bundle = build_authoring_bundle(synthetic_samples())
    verify_bundle(bundle)
    noncanonical = synthetic_samples()
    noncanonical[0]["components"][0]["visual_atoms"]["location"] = math.nan
    noncanonical_bundle = build_authoring_bundle(noncanonical)
    verify_bundle(json.loads(json.dumps(noncanonical_bundle, allow_nan=False)))
    if noncanonical_bundle["decision"] != "ABSTAIN":
        raise ContractError("R23B_SELF_TEST_NONCANONICAL_NOT_ABSTAIN")
    duplicate = synthetic_samples()
    duplicate[1]["components"][0]["ambient_tuple"] = copy.deepcopy(
        duplicate[0]["components"][0]["ambient_tuple"]
    )
    rejected = build_authoring_bundle(duplicate)
    verify_bundle(rejected)
    if rejected["decision"] != "REJECT_SAMPLE_SET":
        raise ContractError("R23B_SELF_TEST_AMBIENT_DUPLICATE_NOT_REJECTED")
    duplicate_component = synthetic_samples()
    cloned_component = copy.deepcopy(duplicate_component[0]["components"][0])
    cloned_component["component_key"] = "renamed-component"
    duplicate_component[1]["components"][0] = cloned_component
    identity_rejected = build_authoring_bundle(duplicate_component)
    verify_bundle(identity_rejected)
    if identity_rejected["decision"] != "REJECT_SAMPLE_SET":
        raise ContractError("R23B_SELF_TEST_COMPONENT_IDENTITY_NOT_REJECTED")
    malformed_duplicates = [
        {
            "sample_key": "duplicate-malformed",
            "family_role": "unknown",
            "components": [
                {
                    "component_key": "duplicate-malformed-component",
                    "visual_atoms": {},
                    "ambient_tuple": {},
                    "media_binding": {},
                }
            ],
            "composition_atoms": {},
        },
        {
            "sample_key": "duplicate-malformed",
            "family_role": "also-unknown",
            "components": [
                {
                    "component_key": "duplicate-malformed-component",
                    "visual_atoms": {"bad": True},
                    "ambient_tuple": {"bad": True},
                    "media_binding": {"bad": True},
                }
            ],
            "composition_atoms": {"bad": True},
        },
    ]
    malformed_identity_rejected = build_authoring_bundle(
        malformed_duplicates
    )
    verify_bundle(malformed_identity_rejected)
    if malformed_identity_rejected["decision"] != "REJECT_SAMPLE_SET":
        raise ContractError(
            "R23B_SELF_TEST_MALFORMED_DUPLICATE_IDS_NOT_REJECTED"
        )
    generic = synthetic_samples()
    generic[0]["components"][0]["visual_atoms"].update(
        {
            "action": "holding",
            "objects": ["container"],
            "attributes": [],
            "location": None,
            "state": None,
        }
    )
    abstained = build_authoring_bundle(generic)
    verify_bundle(abstained)
    if abstained["decision"] != "ABSTAIN":
        raise ContractError("R23B_SELF_TEST_GENERIC_ATOMS_NOT_REJECTED")
    tampered = copy.deepcopy(bundle)
    tampered["primary_queries"][0]["query_text"] += " tampered"
    tampered["primary_queries"][0]["query_sha256"] = semantic_hash(
        tampered["primary_queries"][0]["query_text"]
    )
    row_payload = dict(tampered["primary_queries"][0])
    row_payload.pop("row_payload_sha256")
    tampered["primary_queries"][0]["row_payload_sha256"] = semantic_hash(row_payload)
    bundle_payload = dict(tampered)
    bundle_payload.pop("bundle_payload_sha256")
    tampered["bundle_payload_sha256"] = semantic_hash(bundle_payload)
    try:
        verify_bundle(tampered)
    except ContractError:
        pass
    else:
        raise ContractError("R23B_SELF_TEST_RESEALED_TAMPER_NOT_REJECTED")
    review_packet = bundle["human_review"]["review_rows"][0]
    review_binding = _packet_binding(review_packet)
    reviewer_1 = {
        **review_binding,
        "reviewer_id": "self-test-reviewer-1",
        "action_correct": True,
        "object_tokens_correct": True,
        "decision": "PASS",
        "reasons": [],
    }
    reviewer_2 = {
        **review_binding,
        "reviewer_id": "self-test-reviewer-2",
        "action_correct": True,
        "object_tokens_correct": True,
        "decision": "PASS",
        "reasons": [],
    }
    receipt = build_review_receipt(
        review_packet, reviewer_1, reviewer_2, None
    )
    verify_review_receipt(receipt)
    tampered_receipt = copy.deepcopy(receipt)
    tampered_receipt["decision"]["reason"] = "tampered"
    try:
        verify_review_receipt(tampered_receipt)
    except ContractError:
        pass
    else:
        raise ContractError("R23B_SELF_TEST_REVIEW_RECEIPT_TAMPER_NOT_REJECTED")
    packet_tampered_receipt = copy.deepcopy(receipt)
    packet_tampered_receipt["review_packet"]["packet_payload"][
        "blind_atoms"
    ]["action_claim"] = "forged-action"
    receipt_payload = copy.deepcopy(packet_tampered_receipt)
    receipt_payload.pop("receipt_payload_sha256")
    packet_tampered_receipt["receipt_payload_sha256"] = semantic_hash(
        receipt_payload
    )
    try:
        verify_review_receipt(packet_tampered_receipt)
    except ContractError:
        pass
    else:
        raise ContractError(
            "R23B_SELF_TEST_RESEALED_PACKET_TAMPER_NOT_REJECTED"
        )

    class SelfTestUnknown:
        def __init__(self, state: str) -> None:
            self.state = state

    if (
        _capture_raw_bytes(SelfTestUnknown("left"))["raw_bytes_sha256"]
        == _capture_raw_bytes(SelfTestUnknown("right"))["raw_bytes_sha256"]
    ):
        raise ContractError(
            "R23B_SELF_TEST_UNKNOWN_STATE_NOT_DISTINGUISHED"
        )
    return {
        "status": "PASS",
        "decision": DECISION_TOKEN,
        "integrity_claim": INTEGRITY_CLAIM,
        "execution": False,
        "external_attested": False,
        "checks": [
            "full_bundle_recomputation",
            "canonical_typed_raw_audit_json_roundtrip",
            "ambient_global_duplicate_rejects",
            "duplicate_component_identity_rejects_globally",
            "duplicate_public_ids_reject_even_when_all_samples_malformed",
            "generic_holding_container_abstains",
            "resealed_tamper_rejects",
            "review_receipt_tamper_rejects",
            "review_packet_payload_tamper_rejects_after_receipt_reseal",
            "unknown_safe_state_changes_audit_hash",
            "current_recomputation_does_not_claim_external_attestation",
            "no_model_or_authorization_calls",
        ],
        "bundle_payload_sha256": bundle["bundle_payload_sha256"],
        "model_calls": 0,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("self-test")
    subparsers.add_parser("preflight")
    plan = subparsers.add_parser("plan")
    plan.add_argument("--output", type=Path, default=DEFAULT_PLAN)
    commitment = subparsers.add_parser("commitment-request")
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
            output = args.output
            if not output.is_absolute():
                output = ROOT / output
            plan_hash = write_json(output, plan)
            verify_plan(plan)
            result = {
                "status": "PASS",
                "decision": DECISION_TOKEN,
                "integrity_claim": INTEGRITY_CLAIM,
                "execution": False,
                "external_attested": False,
                "plan_path": output.relative_to(ROOT).as_posix(),
                "plan_file_sha256": plan_hash,
                "plan_payload_sha256": plan["plan_payload_sha256"],
                "model_calls": 0,
            }
        elif args.command == "commitment-request":
            request = build_external_commitment_request()
            output = args.output
            if not output.is_absolute():
                output = ROOT / output
            request_hash = write_json(output, request)
            verify_external_commitment_request(request)
            result = {
                "status": "PASS",
                "decision": DECISION_TOKEN,
                "integrity_claim": INTEGRITY_CLAIM,
                "execution": False,
                "external_attested": False,
                "commitment_request_path": output.relative_to(ROOT).as_posix(),
                "commitment_request_file_sha256": request_hash,
                "commitment_request_payload_sha256": request[
                    "commitment_request_payload_sha256"
                ],
                "model_calls": 0,
            }
        else:
            raise ContractError("R23B_COMMAND_INVALID")
    except (ContractError, PARENT.AuthoringError) as exc:
        print(
            json.dumps(
                {"status": "FAIL_CLOSED", "error": str(exc)},
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
