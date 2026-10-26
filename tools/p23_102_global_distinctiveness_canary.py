"""R23-C exposed-development calibration canary for P23_102.

This isolated pipeline consumes only the five clips already exposed by the
terminal R21/R22 development lineage. Planning, preflight, self-test, and the
synthetic stage runner never decode media, load a model, consume an
authorization, create an attempt marker, run retrieval, or compute embeddings.
A future real calibration requires a separately signed authorization receipt.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import itertools
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT_DATE = "2026-10-23"
PIPELINE_ID = "AV-TRACE-P23-102-R23-C-EXPOSED-DEVELOPMENT-CALIBRATION-CANARY-V1"
STATUS_TOKEN = "R23_C_EXPOSED_CALIBRATION_IMPLEMENTATION_READY"
SCHEMA_VERSION = "av-trace.p23-102-r23c-exposed-calibration-bundle/1.0"
PLAN_SCHEMA_VERSION = "av-trace.p23-102-r23c-exposed-calibration-plan/1.0"
SELECTION_SCHEMA_VERSION = "av-trace.p23-102-r23c-exposed-selection/1.0"
AUTHORIZATION_SCHEMA_VERSION = (
    "av-trace.p23-102-r23c-exposed-calibration-authorization/1.0"
)
ATTEMPT_MARKER_SCHEMA_VERSION = (
    "av-trace.p23-102-r23c-exposed-calibration-attempt-marker/1.0"
)
STAGE_OUTPUT_SCHEMA_VERSION = (
    "av-trace.p23-102-r23c-exposed-calibration-stage-output/1.0"
)
REVIEW_PACKET_SET_SCHEMA_VERSION = (
    "av-trace.p23-102-r23c-exposed-review-packet-set/1.0"
)

R23B_V9_TOOL = Path("tools/p23_102_global_distinctiveness_v9.py")
PARENT_AMBIENT_TOOL = Path("tools/p23_102_query_authoring_v2.py")
EXPOSED_SOURCE_SUBSET = Path(
    "data/restricted/p23_102_query_authoring_v2_canary2_run_v1.failure-"
    'PUBLIC_REDACTED_IDENTIFIER'
    "canary2_subset_bundle.json"
)
EXPOSED_SOURCE_TARGET_MANIFEST = Path(
    "data/restricted/p23_102_query_authoring_v2_canary2_run_v1.failure-"
    'PUBLIC_REDACTED_IDENTIFIER'
)
EXPOSED_SOURCE_CONTRACT = Path(
    "data/restricted/p23_102_query_authoring_v2_canary2_run_v1.failure-"
    'PUBLIC_REDACTED_IDENTIFIER'
)
R22_EXPOSURE_LEDGER = Path(
    "data/restricted/p23_102_query_authoring_v2_canary2_r22f_governance_ledger.json"
)
R22_PUBLIC_TERMINAL = Path(
    "data/rehearsal_plan/p23_102_canary2_r22_terminal_public.json"
)
MEDIA_MANIFEST = Path(
    "data/restricted/epic_p23_102_source_v1/manifests/"
    "epic_p23_102_exact_manifest.json"
)
TEST_FILE = Path("tooling/tests/test_p23_102_global_distinctiveness_canary.py")
DESIGN_DOC = Path("docs/design/p23_102_r23c_exposed_calibration_canary.md")
DEFAULT_PLAN = Path(
    "data/rehearsal_plan/p23_102_r23c_exposed_calibration_canary_plan.json"
)
DEFAULT_PUBLIC_SUMMARY = Path(
    "data/rehearsal_plan/p23_102_r23c_exposed_calibration_canary_public.json"
)
DEFAULT_RESTRICTED_LEDGER = Path(
    "data/restricted/p23_102_r23c_exposed_calibration_canary_ledger.json"
)
DEFAULT_OUTPUT = Path(
    "data/restricted/p23_102_r23c_exposed_calibration_canary_run_v1"
)

VISUAL_CALL_BUDGET = 5
AMBIENT_CALL_BUDGET = 5
RELATION_CALL_BUDGET = 3
TOTAL_CALL_BUDGET = 13
FAMILY_COUNT = 3
CLIP_COUNT = 5
PRIMARY_QUERY_COUNT = 13
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")

EXPECTED_EXPOSED = {
    "family-009": {
        "family_role": "local_v15_structure",
        "family_structural_sha256": (
            "sha256:e53b1fd19b6011baf0f84c5333faeff52a141b7c34ffaf1a3f06a41c9341a787"
        ),
        "shape": "one_component",
        "clips": [("clip-003", 260000000, 268000000)],
        "relation": "single",
    },
    "family-005": {
        "family_role": "far_vocalization_asr_ambiguity",
        "family_structural_sha256": (
            "sha256:d474a0ddaaa53b45d64b1e61895b65f466295a343e6b752161bdb9d075424796"
        ),
        "shape": "two_component_ordered",
        "clips": [
            ("clip-011", 1356000000, 1364000000),
            ("clip-019", 2200000000, 2208000000),
        ],
        "relation": "before",
    },
    "family-003": {
        "family_role": "far_continuity_anaphora",
        "family_structural_sha256": (
            "sha256:9299122a52e29ef0bb4431fa8037f0cf2a02593f47077c1bc53f6a59899c2d38"
        ),
        "shape": "two_component_ordered",
        "clips": [
            ("clip-007", 720000000, 728000000),
            ("clip-010", 960000000, 968000000),
        ],
        "relation": "after",
    },
}
EXPECTED_FAMILY_ORDER = ("family-009", "family-005", "family-003")


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R23B = _load_module(R23B_V9_TOOL, "r23b_v9_for_r23c")
PARENT = R23B.V5.PARENT
ContractError = R23B.ContractError


def canonical_bytes(value: Any) -> bytes:
    return R23B.canonical_bytes(value)


def semantic_hash(value: Any) -> str:
    return R23B.semantic_hash(value)


def file_sha256(path: Path) -> str:
    return R23B.file_sha256(path)


def _strict_dict(value: Any, fields: set[str], code: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise ContractError(code, disposition="REJECT")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ContractError("R23C_JSON_INPUT_INVALID", disposition="REJECT") from exc
    if type(value) is not dict:
        raise ContractError("R23C_JSON_INPUT_NOT_OBJECT", disposition="REJECT")
    return value


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _hash_body(value: Mapping[str, Any], field: str) -> str:
    body = copy.deepcopy(dict(value))
    body.pop(field, None)
    return semantic_hash(body)


def _parse_strict_json_object(raw_text: Any, code: str) -> dict[str, Any]:
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ContractError(code, disposition="REJECT")

    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    try:
        value = json.loads(
            raw_text,
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except Exception as exc:
        raise ContractError(code, disposition="REJECT") from exc
    if type(value) is not dict:
        raise ContractError(code, disposition="REJECT")
    return value


def parse_visual_model_output(raw_text: Any) -> dict[str, Any]:
    """Strict single-object JSON followed by exact R23-B v9 atom validation."""

    value = _parse_strict_json_object(raw_text, "R23C_VISUAL_JSON_INVALID")
    try:
        return R23B.V5.validate_visual_atoms(value)
    except Exception as exc:
        raise ContractError(
            "R23C_VISUAL_ATOM_VALIDATION_FAILED", disposition="REJECT"
        ) from exc


def parse_ambient_model_output(raw_text: Any) -> dict[str, Any]:
    """Parse one ambient trie leaf and revalidate the exact parent tuple."""

    value = _parse_strict_json_object(raw_text, "R23C_AMBIENT_JSON_INVALID")
    try:
        return PARENT.validate_ambient_semantic_tuple(value)
    except Exception as exc:
        raise ContractError(
            "R23C_AMBIENT_TUPLE_VALIDATION_FAILED", disposition="REJECT"
        ) from exc


def parse_relation_model_output(
    raw_text: Any, *, required_relation: str
) -> str:
    """Accept exactly one closed relation field equal to the frozen requirement."""

    value = _parse_strict_json_object(raw_text, "R23C_RELATION_JSON_INVALID")
    if (
        set(value) != {"relation"}
        or value["relation"] not in R23B.V5.FAMILY_RELATIONS
        or value["relation"] != required_relation
    ):
        raise ContractError("R23C_RELATION_KIND_MISMATCH", disposition="REJECT")
    return required_relation


def visual_constraint_contract() -> dict[str, Any]:
    registry = copy.deepcopy(R23B.V5.VISUAL_REGISTRY_MANIFEST)
    schema = copy.deepcopy(R23B.V5.VISUAL_ATOM_SCHEMA)
    return {
        "schema_version": "av-trace.p23-102-r23c-visual-constraint/1.0",
        "constraint_kind": (
            "strict_json_object_boundary_plus_exact_r23b_v9_post_validation"
        ),
        "closed_finite_language": True,
        "canonical_json": {
            "sort_keys": True,
            "separators": [",", ":"],
            "ensure_ascii": False,
            "allow_nan": False,
        },
        "schema_sha256": semantic_hash(schema),
        "registry_sha256": semantic_hash(registry),
        "canonical_leaf_count": _visual_leaf_count(),
        "runtime_boundary": (
            "decoder must stop at the first complete top-level JSON object; "
            "extra text and trailing objects are forbidden"
        ),
        "schema_repair_permitted": False,
        "semantic_retry_permitted": False,
        "post_parse_validation": "R23-B v9 validate_visual_atoms exact",
        "boundary": (
            "the accepted language has more than 33 million canonical leaves, so a "
            "token trie is not committed as a practical runtime object. The allowed "
            "alternative boundary is strict single-object JSON decoding followed by "
            "exact field-set, enum, cardinality, uniqueness, state, specificity, and "
            "R23-B v9 global-gate validation. Any failure is terminal ABSTAIN/fail-closed"
        ),
    }


def _visual_leaf_count() -> int:
    # Count only leaves accepted by the authoritative specificity validator.
    # Object and attribute arrays use the canonical registry order, avoiding
    # semantically duplicate permutations in the constrained language.
    object_count = len(R23B.V5.VISUAL_OBJECTS)
    object_lists = object_count + object_count * (object_count - 1) // 2
    specific_object_lists = object_lists - (
        len(R23B.V5.GENERIC_OBJECTS)
        + len(R23B.V5.GENERIC_OBJECTS)
        * (len(R23B.V5.GENERIC_OBJECTS) - 1)
        // 2
    )
    attribute_count = len(R23B.V5.VISUAL_ATTRIBUTES)
    nonempty_attribute_lists = (
        attribute_count + attribute_count * (attribute_count - 1) // 2
    )
    dimensions = (
        (len(R23B.V5.VISUAL_ACTIONS) - len(R23B.V5.GENERIC_ACTIONS), True),
        (len(R23B.V5.GENERIC_ACTIONS), False),
    )
    objects = (
        (specific_object_lists, True),
        (object_lists - specific_object_lists, False),
    )
    attributes = ((nonempty_attribute_lists, True), (1, False))
    locations = ((len(R23B.V5.VISUAL_LOCATIONS), True), (1, False))
    event_states = ((len(R23B.V5.VISUAL_STATES), True), (1, False))
    state_states = ((len(R23B.V5.VISUAL_STATES), True),)

    def accepted_count(states: Sequence[tuple[int, bool]]) -> int:
        total = 0
        for action, objects_row, attribute, location, state in itertools.product(
            dimensions, objects, attributes, locations, states
        ):
            rows = (action, objects_row, attribute, location, state)
            if sum(int(present) for _, present in rows) >= 2:
                product_count = 1
                for count, _ in rows:
                    product_count *= count
                total += product_count
        return total

    return accepted_count(event_states) + accepted_count(state_states)


def relation_constraint_contract() -> dict[str, Any]:
    return {
        "schema_version": "av-trace.p23-102-r23c-relation-constraint/1.0",
        "constraint_kind": "closed_required_relation_kind",
        "allowed": ["single", "after", "before"],
        "per_family_required": {
            key: EXPECTED_EXPOSED[key]["relation"] for key in EXPECTED_FAMILY_ORDER
        },
        "natural_language_authorship": False,
        "schema_repair_permitted": False,
    }


def ambient_constraint_contract() -> dict[str, Any]:
    return copy.deepcopy(PARENT.ambient_constraint_contract())


def generator_contract() -> dict[str, Any]:
    return {
        "visual": copy.deepcopy(R23B.V5.GENERATOR_MANIFEST),
        "ambient": copy.deepcopy(PARENT.ambient_derivation_contract()),
        "family_relation": relation_constraint_contract(),
        "description_query_model_authorship": False,
        "mechanical_build_and_verify": "R23-B v9 inherited v5 semantic gates",
    }


def load_exposed_selection(root: Path = ROOT) -> dict[str, Any]:
    subset_path = root / EXPOSED_SOURCE_SUBSET
    ledger_path = root / R22_EXPOSURE_LEDGER
    target_path = root / EXPOSED_SOURCE_TARGET_MANIFEST
    terminal_path = root / R22_PUBLIC_TERMINAL
    subset = _load_json(subset_path)
    ledger = _load_json(ledger_path)
    target = _load_json(target_path)
    terminal = _load_json(terminal_path)

    exposure = ledger.get("exposure")
    if type(exposure) is not dict:
        raise ContractError("R23C_EXPOSURE_LEDGER_INVALID", disposition="REJECT")
    expected_family_keys = sorted(EXPECTED_EXPOSED)
    expected_clip_keys = sorted(
        clip
        for item in EXPECTED_EXPOSED.values()
        for clip, _, _ in item["clips"]
    )
    if (
        sorted(exposure.get("family_keys", [])) != expected_family_keys
        or sorted(exposure.get("clip_keys", [])) != expected_clip_keys
        or terminal.get("decision_token")
        != "R22_SCIENTIFIC_NO_GO_PERMANENT_R23_REQUIRED"
    ):
        raise ContractError("R23C_EXPOSED_IDENTITY_SET_MISMATCH", disposition="REJECT")

    subset_families = {
        row.get("family_key"): row for row in subset.get("families", [])
    }
    target_rows = {row.get("clip_key"): row for row in target.get("targets", [])}
    families = []
    clips = []
    for family_key in EXPECTED_FAMILY_ORDER:
        expected = EXPECTED_EXPOSED[family_key]
        row = subset_families.get(family_key)
        if type(row) is not dict:
            raise ContractError("R23C_EXPOSED_FAMILY_MISSING", disposition="REJECT")
        if row.get("shape") != expected["shape"]:
            raise ContractError("R23C_EXPOSED_FAMILY_SHAPE_MISMATCH", disposition="REJECT")
        selected_clips = []
        for clip_key, start_us, end_us in expected["clips"]:
            target_row = target_rows.get(clip_key)
            if type(target_row) is not dict or (
                target_row.get("start_us") != start_us
                or target_row.get("end_us") != end_us
            ):
                raise ContractError("R23C_EXPOSED_CLIP_BINDING_MISMATCH", disposition="REJECT")
            selected = {
                "clip_key": clip_key,
                "family_key": family_key,
                "component_ordinal": len(selected_clips) + 1,
                "start_us": start_us,
                "end_us": end_us,
                "video_sha256": target_row["video_sha256"],
                "audio_sha256": target_row["audio_sha256"],
            }
            selected["clip_binding_sha256"] = semantic_hash(selected)
            selected_clips.append(selected)
            clips.append(copy.deepcopy(selected))
        families.append(
            {
                "family_key": family_key,
                "family_role": expected["family_role"],
                "family_structural_sha256": expected["family_structural_sha256"],
                "shape": expected["shape"],
                "required_relation": expected["relation"],
                "clips": selected_clips,
            }
        )

    if len(families) != FAMILY_COUNT or len(clips) != CLIP_COUNT:
        raise ContractError("R23C_EXPOSED_CARDINALITY_MISMATCH", disposition="REJECT")
    payload = {
        "schema_version": SELECTION_SCHEMA_VERSION,
        "pipeline_id": PIPELINE_ID,
        "date": CURRENT_DATE,
        "selection_status": "FIXED_ALREADY_EXPOSED_DEVELOPMENT_INPUTS",
        "fresh_or_untouched": False,
        "fresh_reserve_consumed": False,
        "selection_basis": (
            "exactly the identities already exposed by the terminal R21/R22 "
            "development lineage; no ranking, redraw, replacement, or reserve read"
        ),
        "families": families,
        "clips": clips,
        "counts": {
            "families": FAMILY_COUNT,
            "clips": CLIP_COUNT,
            "primary_queries": PRIMARY_QUERY_COUNT,
        },
        "source_hashes": {
            EXPOSED_SOURCE_SUBSET.as_posix(): file_sha256(subset_path),
            R22_EXPOSURE_LEDGER.as_posix(): file_sha256(ledger_path),
            EXPOSED_SOURCE_TARGET_MANIFEST.as_posix(): file_sha256(target_path),
            R22_PUBLIC_TERMINAL.as_posix(): file_sha256(terminal_path),
        },
        "unselected_reserve": {
            "read": False,
            "included": False,
            "disclosed": False,
        },
    }
    payload["selection_payload_sha256"] = semantic_hash(payload)
    return payload


def verify_exposed_selection(selection: Mapping[str, Any], root: Path = ROOT) -> dict[str, Any]:
    expected = load_exposed_selection(root)
    if canonical_bytes(expected) != canonical_bytes(selection):
        raise ContractError("R23C_EXPOSED_SELECTION_MISMATCH", disposition="REJECT")
    return {
        "status": "PASS",
        "selection_payload_sha256": expected["selection_payload_sha256"],
        "fresh_reserve_consumed": False,
    }


def _source_media_sha256(root: Path) -> str:
    manifest = _load_json(root / MEDIA_MANIFEST)
    value = manifest.get("media", {}).get("sha256")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ContractError("R23C_MEDIA_MANIFEST_INVALID", disposition="REJECT")
    return "sha256:" + value


def _model_snapshot_binding(root: Path) -> dict[str, Any]:
    contract = _load_json(root / EXPOSED_SOURCE_CONTRACT)
    authoring = contract.get("model_identities", {}).get("authoring")
    model_hash = (
        contract.get("input_fingerprints", {})
        .get("model_hashes", {})
        .get("authoring_omni")
    )
    if type(authoring) is not dict:
        raise ContractError("R23C_PARENT_MODEL_BINDING_MISSING", disposition="REJECT")
    if type(model_hash) is not dict:
        raise ContractError(
            "R23C_PARENT_MODEL_CONTENT_BINDING_MISSING", disposition="REJECT"
        )
    required = {"repo_id", "revision", "snapshot", "generation"}
    if set(authoring) != required:
        raise ContractError("R23C_PARENT_MODEL_BINDING_INVALID", disposition="REJECT")
    if authoring["snapshot"] != model_hash.get("snapshot"):
        raise ContractError(
            "R23C_PARENT_MODEL_SNAPSHOT_MISMATCH", disposition="REJECT"
        )
    return {
        **copy.deepcopy(authoring),
        "snapshot_content_sha256": model_hash.get("snapshot_content_sha256"),
        "sha256s_file_sha256": model_hash.get("sha256s_file_sha256"),
        "verified_file_count": model_hash.get("verified_file_count"),
    }


def build_plan(root: Path = ROOT) -> dict[str, Any]:
    selection = load_exposed_selection(root)
    payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "pipeline_id": PIPELINE_ID,
        "date": CURRENT_DATE,
        "status": STATUS_TOKEN,
        "experiment_class": "EXPOSED_DEVELOPMENT_CALIBRATION_NOT_FRESH_EVALUATION",
        "scientific_go": False,
        "selection": selection,
        "call_budget": {
            "visual_video_only": VISUAL_CALL_BUDGET,
            "ambient_audio_only": AMBIENT_CALL_BUDGET,
            "relation_text_only_closed_kind": RELATION_CALL_BUDGET,
            "total": TOTAL_CALL_BUDGET,
            "additional_repair_retry_calls": 0,
        },
        "constraints": {
            "visual": visual_constraint_contract(),
            "ambient": ambient_constraint_contract(),
            "relation": relation_constraint_contract(),
        },
        "generators": generator_contract(),
        "machine_calibration": {
            "estimand": "query_identifiability_before_retrieval",
            "retrieval_or_embedding": False,
            "all_global_gates_required": True,
            "fail_closed_on": [
                "ABSTAIN",
                "duplicate",
                "Jaccard threshold failure",
                "ambient tuple duplicate",
                "generic query",
                "identity failure",
                "review interface failure",
            ],
            "maximum_success_status": "MACHINE_CALIBRATION_PASS_HUMAN_PENDING",
        },
        "human_review": {
            "packets_generated": True,
            "results_filled": False,
            "machine_calibration_blocked_by_unfilled_packets": False,
            "scientific_go_blocked_by_unfilled_packets": True,
        },
        "one_shot": {
            "real_execution_only": True,
            "new_schema_and_namespace": True,
            "authorization_schema_version": AUTHORIZATION_SCHEMA_VERSION,
            "attempt_marker_schema_version": ATTEMPT_MARKER_SCHEMA_VERSION,
            "same_receipt_rerun_permitted": False,
            "failure_retains_marker": True,
            "future_code_versions_require_new_pipeline_id_output_and_receipt": True,
            "future_code_experiment_permitted_because_data_are_exposed": True,
            "future_runs_must_not_be_called_fresh_evaluation": True,
            "external_signature_verifier_required_before_marker": True,
        },
        "model_visible_contract": {
            "visual": {
                "media": "one exact target video; audio absent",
                "output": "R23-B v9 visual atom object only",
                "free_description_or_query": False,
            },
            "ambient": {
                "media": "one exact target audio; video absent",
                "output": "parent R21 structured ambient tuple only",
                "free_description_or_query": False,
            },
            "relation": {
                "media": "none",
                "output": "one required closed relation kind only",
                "natural_language": False,
            },
        },
        "provenance": build_provenance(root, selection),
        "scope": {
            "model_calls": 0,
            "authorization_calls": 0,
            "attempt_marker_created": False,
            "media_decode": False,
            "retrieval": False,
            "embeddings": False,
            "old_r22_marker_capsule_authorization_modified": False,
        },
    }
    payload["plan_payload_sha256"] = semantic_hash(payload)
    return payload


def build_provenance(root: Path, selection: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "r23c_tool_source_sha256": file_sha256(Path(__file__).resolve()),
        "r23b_v9_tool_path": R23B_V9_TOOL.as_posix(),
        "r23b_v9_tool_source_sha256": file_sha256(root / R23B_V9_TOOL),
        "r23b_v9_plan_path": R23B.DEFAULT_PLAN.as_posix(),
        "r23b_v9_plan_file_sha256": file_sha256(root / R23B.DEFAULT_PLAN),
        "r23b_v9_commitment_path": R23B.DEFAULT_COMMITMENT_REQUEST.as_posix(),
        "r23b_v9_commitment_file_sha256": file_sha256(
            root / R23B.DEFAULT_COMMITMENT_REQUEST
        ),
        "parent_ambient_tool_path": PARENT_AMBIENT_TOOL.as_posix(),
        "parent_ambient_tool_source_sha256": file_sha256(root / PARENT_AMBIENT_TOOL),
        "parent_authoring_model": _model_snapshot_binding(root),
        "source_media_sha256": _source_media_sha256(root),
        "selection_payload_sha256": selection["selection_payload_sha256"],
        "visual_schema_sha256": semantic_hash(R23B.V5.VISUAL_ATOM_SCHEMA),
        "visual_registry_sha256": semantic_hash(R23B.V5.VISUAL_REGISTRY_MANIFEST),
        "visual_constraint_sha256": semantic_hash(visual_constraint_contract()),
        "ambient_schema_sha256": semantic_hash(PARENT.AMBIENT_OUTPUT_SCHEMA),
        "ambient_registry_sha256": PARENT.STRUCTURED_AMBIENT_REGISTRY_SHA256,
        "ambient_generator_sha256": PARENT.AMBIENT_GENERATOR_SHA256,
        "ambient_template_sha256": PARENT.AMBIENT_TEMPLATE_SHA256,
        "ambient_constraint_manifest_sha256": (
            PARENT.AMBIENT_CONSTRAINT_MANIFEST_SHA256
        ),
        "relation_constraint_sha256": semantic_hash(relation_constraint_contract()),
        "generator_contract_sha256": semantic_hash(generator_contract()),
    }


def verify_plan(plan: Mapping[str, Any], root: Path = ROOT) -> dict[str, Any]:
    expected = build_plan(root)
    if canonical_bytes(expected) != canonical_bytes(plan):
        raise ContractError("R23C_PLAN_RUNTIME_CONTRACT_MISMATCH", disposition="REJECT")
    return {
        "status": "PASS",
        "decision": STATUS_TOKEN,
        "plan_payload_sha256": expected["plan_payload_sha256"],
        "model_calls": 0,
        "authorization_calls": 0,
    }


def build_public_summary(root: Path = ROOT) -> dict[str, Any]:
    selection = load_exposed_selection(root)
    payload = {
        "schema_version": "av-trace.p23-102-r23c-exposed-calibration-public/1.0",
        "artifact_id": "P23_102_R23C_EXPOSED_CALIBRATION_CANARY_PUBLIC",
        "date": CURRENT_DATE,
        "status": STATUS_TOKEN,
        "pipeline_id": PIPELINE_ID,
        "experiment_class": "EXPOSED_DEVELOPMENT_CALIBRATION_NOT_FRESH_EVALUATION",
        "selected_families": [
            {
                "family_key": row["family_key"],
                "family_role": row["family_role"],
                "clip_keys": [clip["clip_key"] for clip in row["clips"]],
            }
            for row in selection["families"]
        ],
        "counts": selection["counts"],
        "fresh_reserve_consumed": False,
        "unselected_reserve_disclosed": False,
        "budget": {
            "visual": VISUAL_CALL_BUDGET,
            "ambient": AMBIENT_CALL_BUDGET,
            "relation": RELATION_CALL_BUDGET,
            "total": TOTAL_CALL_BUDGET,
        },
        "retrieval_or_embedding_permitted": False,
        "maximum_future_run_status": "MACHINE_CALIBRATION_PASS_HUMAN_PENDING",
        "scientific_go": False,
        "implementation_only": True,
    }
    payload["public_summary_payload_sha256"] = semantic_hash(payload)
    return payload


def build_restricted_ledger(root: Path = ROOT) -> dict[str, Any]:
    selection = load_exposed_selection(root)
    payload = {
        "schema_version": "av-trace.p23-102-r23c-exposed-calibration-ledger/1.0",
        "pipeline_id": PIPELINE_ID,
        "date": CURRENT_DATE,
        "status": STATUS_TOKEN,
        "selection": selection,
        "exact_input_hashes": copy.deepcopy(selection["source_hashes"]),
        "planned_output_path": DEFAULT_OUTPUT.as_posix(),
        "planned_attempt_marker_template": (
            DEFAULT_OUTPUT.as_posix() + ".attempt-{authorization_id}.json"
        ),
        "planned_failure_capsule_template": (
            DEFAULT_OUTPUT.as_posix() + ".failure-{authorization_id}"
        ),
        "old_r22_paths_reused": False,
        "fresh_reserve_consumed": False,
        "unselected_reserve_read": False,
        "authorization_created": False,
        "attempt_marker_created": False,
        "real_model_run_performed": False,
        "retrieval_or_embedding_performed": False,
        "one_shot_versioning": {
            "same_receipt_rerun_permitted": False,
            "new_code_version_requires_new_pipeline_id": True,
            "new_code_version_requires_new_output_path": True,
            "new_code_version_requires_new_authorization_receipt": True,
        },
    }
    payload["ledger_payload_sha256"] = semantic_hash(payload)
    return payload


def verify_stage_output(
    stage_output: Mapping[str, Any], selection: Mapping[str, Any]
) -> dict[str, Any]:
    row = _strict_dict(
        stage_output,
        {
            "schema_version",
            "pipeline_id",
            "selection_payload_sha256",
            "visual_atoms",
            "ambient_tuples",
            "relations",
            "call_accounting",
            "stage_output_payload_sha256",
        },
        "R23C_STAGE_OUTPUT_FIELD_SET_INVALID",
    )
    if row["stage_output_payload_sha256"] != _hash_body(
        row, "stage_output_payload_sha256"
    ):
        raise ContractError("R23C_STAGE_OUTPUT_HASH_MISMATCH", disposition="REJECT")
    if (
        row["schema_version"] != STAGE_OUTPUT_SCHEMA_VERSION
        or row["pipeline_id"] != PIPELINE_ID
        or row["selection_payload_sha256"]
        != selection["selection_payload_sha256"]
    ):
        raise ContractError("R23C_STAGE_OUTPUT_BINDING_MISMATCH", disposition="REJECT")
    clips = {row["clip_key"]: row for row in selection["clips"]}
    if type(row["visual_atoms"]) is not dict or set(row["visual_atoms"]) != set(clips):
        raise ContractError("R23C_VISUAL_OUTPUT_SET_MISMATCH", disposition="REJECT")
    if type(row["ambient_tuples"]) is not dict or set(row["ambient_tuples"]) != set(clips):
        raise ContractError("R23C_AMBIENT_OUTPUT_SET_MISMATCH", disposition="REJECT")
    if type(row["relations"]) is not dict or set(row["relations"]) != set(EXPECTED_FAMILY_ORDER):
        raise ContractError("R23C_RELATION_OUTPUT_SET_MISMATCH", disposition="REJECT")
    try:
        validated_visual = {
            key: R23B.V5.validate_visual_atoms(value)
            for key, value in row["visual_atoms"].items()
        }
    except Exception as exc:
        raise ContractError(
            "R23C_VISUAL_ATOM_VALIDATION_FAILED", disposition="REJECT"
        ) from exc
    try:
        validated_ambient = {
            key: PARENT.validate_ambient_semantic_tuple(value)
            for key, value in row["ambient_tuples"].items()
        }
    except Exception as exc:
        raise ContractError(
            "R23C_AMBIENT_TUPLE_VALIDATION_FAILED", disposition="REJECT"
        ) from exc
    for family_key in EXPECTED_FAMILY_ORDER:
        if row["relations"][family_key] != EXPECTED_EXPOSED[family_key]["relation"]:
            raise ContractError("R23C_RELATION_KIND_MISMATCH", disposition="REJECT")
    expected_accounting = {
        "visual_video_only": VISUAL_CALL_BUDGET,
        "ambient_audio_only": AMBIENT_CALL_BUDGET,
        "relation_text_only_closed_kind": RELATION_CALL_BUDGET,
        "total": TOTAL_CALL_BUDGET,
        "repair_or_retry": 0,
        "retrieval": 0,
        "embedding": 0,
    }
    if row["call_accounting"] != expected_accounting:
        raise ContractError("R23C_CALL_BUDGET_MISMATCH", disposition="REJECT")
    return {
        "visual_atoms": validated_visual,
        "ambient_tuples": validated_ambient,
        "relations": copy.deepcopy(row["relations"]),
        "call_accounting": copy.deepcopy(row["call_accounting"]),
    }


def _sample_from_stage(
    family: Mapping[str, Any], stage: Mapping[str, Any], media_sha256: str
) -> dict[str, Any]:
    components = []
    for clip in family["clips"]:
        clip_key = clip["clip_key"]
        components.append(
            {
                "component_key": f"r23c-{clip_key}",
                "visual_atoms": copy.deepcopy(stage["visual_atoms"][clip_key]),
                "ambient_tuple": copy.deepcopy(stage["ambient_tuples"][clip_key]),
                "media_binding": {
                    "media_sha256": media_sha256,
                    "evidence_sha256": clip["clip_binding_sha256"],
                    "evidence_start_ms": clip["start_us"] // 1000,
                    "evidence_end_ms": clip["end_us"] // 1000,
                },
            }
        )
    return {
        "sample_key": f"r23c-{family['family_key']}",
        "family_role": family["family_role"],
        "components": components,
        "composition_atoms": {"relation": stage["relations"][family["family_key"]]},
    }


def build_review_packet_set(bundle: Mapping[str, Any]) -> dict[str, Any]:
    component_records = bundle.get("successful_component_records")
    if type(component_records) is not list or len(component_records) != CLIP_COUNT:
        raise ContractError("R23C_REVIEW_INTERFACE_COMPONENT_SET_INVALID", disposition="REJECT")
    packets = []
    for record in component_records:
        trusted = R23B.verify_component_record(record)
        component = trusted["component_record"]
        packet = R23B.build_review_packet(
            trusted,
            component["source_binding"],
            R23B._expected_stratum(component["family_role"]),
        )
        R23B.verify_review_packet(packet, trusted)
        packets.append(packet)
    payload = {
        "schema_version": REVIEW_PACKET_SET_SCHEMA_VERSION,
        "status": "UNFILLED_HUMAN_REVIEW_PACKETS_ONLY",
        "human_results_present": False,
        "machine_calibration_blocking": False,
        "scientific_go_blocking": True,
        "packet_count": len(packets),
        "packets": packets,
    }
    payload["review_packet_set_payload_sha256"] = semantic_hash(payload)
    return payload


def build_calibration_bundle(
    stage_output: Mapping[str, Any], root: Path = ROOT
) -> dict[str, Any]:
    selection = load_exposed_selection(root)
    stage = verify_stage_output(stage_output, selection)
    media_sha256 = _source_media_sha256(root)
    samples = [
        _sample_from_stage(family, stage, media_sha256)
        for family in selection["families"]
    ]
    slot_manifest = R23B.build_slot_manifest(
        len(samples),
        manifest_id="r23c-exposed-calibration-v1",
        external_seal="FUTURE_AUTHORIZATION_REQUIRED_CURRENT_SYNTHETIC_ONLY",
    )
    r23b_bundle = R23B.build_authoring_bundle(samples, slot_manifest)
    R23B.verify_bundle(r23b_bundle, slot_manifest)
    if r23b_bundle["decision"] != "DESIGN_PREFLIGHT_PASS":
        raise ContractError("R23C_GLOBAL_GATES_FAILED", disposition="REJECT")
    if len(r23b_bundle["primary_queries"]) != PRIMARY_QUERY_COUNT:
        raise ContractError(
            "R23C_PRIMARY_QUERY_COUNT_MISMATCH", disposition="REJECT"
        )
    review_packets = build_review_packet_set(r23b_bundle)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_id": PIPELINE_ID,
        "date": CURRENT_DATE,
        "status": "MACHINE_CALIBRATION_PASS_HUMAN_PENDING",
        "scientific_go": False,
        "fresh_evaluation": False,
        "selection": selection,
        "stage_output": copy.deepcopy(dict(stage_output)),
        "r23b_v9_bundle": r23b_bundle,
        "review_packet_set": review_packets,
        "call_accounting": stage["call_accounting"],
        "retrieval_or_embedding_executed": False,
        "provenance": build_provenance(root, selection),
    }
    payload["bundle_payload_sha256"] = semantic_hash(payload)
    return payload


def verify_calibration_bundle(bundle: Mapping[str, Any], root: Path = ROOT) -> dict[str, Any]:
    row = _strict_dict(
        bundle,
        {
            "schema_version",
            "pipeline_id",
            "date",
            "status",
            "scientific_go",
            "fresh_evaluation",
            "selection",
            "stage_output",
            "r23b_v9_bundle",
            "review_packet_set",
            "call_accounting",
            "retrieval_or_embedding_executed",
            "provenance",
            "bundle_payload_sha256",
        },
        "R23C_BUNDLE_FIELD_SET_INVALID",
    )
    if row["bundle_payload_sha256"] != _hash_body(row, "bundle_payload_sha256"):
        raise ContractError("R23C_BUNDLE_HASH_MISMATCH", disposition="REJECT")
    expected = build_calibration_bundle(row["stage_output"], root)
    if canonical_bytes(expected) != canonical_bytes(row):
        raise ContractError("R23C_BUNDLE_RECOMPUTATION_MISMATCH", disposition="REJECT")
    if row["status"] != "MACHINE_CALIBRATION_PASS_HUMAN_PENDING":
        raise ContractError("R23C_SEALED_STATUS_INVALID", disposition="REJECT")
    if row["review_packet_set"] is None:
        raise ContractError("R23C_REVIEW_INTERFACE_MISSING", disposition="REJECT")
    if row["scientific_go"] is not False:
        raise ContractError("R23C_SCIENTIFIC_GO_FORBIDDEN", disposition="REJECT")
    return {
        "status": "PASS",
        "calibration_status": row["status"],
        "scientific_go": False,
        "bundle_payload_sha256": row["bundle_payload_sha256"],
    }


def synthetic_stage_output(
    *, mutation: str | None = None, root: Path = ROOT
) -> dict[str, Any]:
    selection = load_exposed_selection(root)
    visual = {
        "clip-003": {
            "kind": "event", "action": "cutting", "objects": ["knife", "carrot"],
            "attributes": ["red"], "location": "cutting_board", "state": "active",
        },
        "clip-011": {
            "kind": "event", "action": "placing", "objects": ["bowl", "tray"],
            "attributes": ["green"], "location": "counter", "state": "resting",
        },
        "clip-019": {
            "kind": "event", "action": "washing", "objects": ["cup", "tap"],
            "attributes": ["small"], "location": "sink", "state": "held",
        },
        "clip-007": {
            "kind": "event", "action": "opening", "objects": ["drawer"],
            "attributes": ["large"], "location": "drawer", "state": "open",
        },
        "clip-010": {
            "kind": "event", "action": "lifting", "objects": ["pot", "lid"],
            "attributes": ["metal"], "location": "stove", "state": "held",
        },
    }
    ambient = {
        "clip-003": {"event_kind": "scrape", "acoustic_properties": {"timbre": "sharp", "loudness": "soft", "temporal_pattern": "rhythmic"}},
        "clip-011": {"event_kind": "clink", "acoustic_properties": {"timbre": "metallic", "loudness": "faint", "temporal_pattern": "brief"}},
        "clip-019": {"event_kind": "continuous_liquid_flow", "acoustic_properties": {"timbre": "crisp", "loudness": "loud", "temporal_pattern": "steady"}},
        "clip-007": {"event_kind": "creak", "acoustic_properties": {"timbre": "hollow", "loudness": "faint", "temporal_pattern": "brief"}},
        "clip-010": {"event_kind": "clang", "acoustic_properties": {"timbre": "metallic", "loudness": "loud", "temporal_pattern": "brief"}},
    }
    relations = {key: EXPECTED_EXPOSED[key]["relation"] for key in EXPECTED_FAMILY_ORDER}
    if mutation == "ambient_duplicate":
        ambient["clip-010"] = copy.deepcopy(ambient["clip-011"])
    elif mutation == "visual_duplicate":
        visual["clip-010"] = copy.deepcopy(visual["clip-011"])
    elif mutation == "generic":
        visual["clip-010"] = {
            "kind": "event", "action": "holding", "objects": ["object"],
            "attributes": [], "location": None, "state": None,
        }
    elif mutation == "bad_relation":
        relations["family-003"] = "before"
    payload = {
        "schema_version": STAGE_OUTPUT_SCHEMA_VERSION,
        "pipeline_id": PIPELINE_ID,
        "selection_payload_sha256": selection["selection_payload_sha256"],
        "visual_atoms": visual,
        "ambient_tuples": ambient,
        "relations": relations,
        "call_accounting": {
            "visual_video_only": VISUAL_CALL_BUDGET,
            "ambient_audio_only": AMBIENT_CALL_BUDGET,
            "relation_text_only_closed_kind": RELATION_CALL_BUDGET,
            "total": TOTAL_CALL_BUDGET,
            "repair_or_retry": 0,
            "retrieval": 0,
            "embedding": 0,
        },
    }
    payload["stage_output_payload_sha256"] = semantic_hash(payload)
    return payload


def run_synthetic_stage_runner(
    *, mutation: str | None = None, root: Path = ROOT
) -> dict[str, Any]:
    return synthetic_stage_output(mutation=mutation, root=root)


def _safe_authorization_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    if not safe:
        raise ContractError("R23C_AUTHORIZATION_ID_INVALID", disposition="REJECT")
    return safe


def attempt_marker_path(output: Path, authorization_id: str) -> Path:
    return output.with_name(
        output.name + f".attempt-{_safe_authorization_id(authorization_id)}.json"
    )


def validate_authorization(
    authorization_path: Path,
    *,
    root: Path = ROOT,
    external_verifier: Callable[
        [Mapping[str, Any], Path], Mapping[str, Any]
    ]
    | None = None,
) -> dict[str, Any]:
    path = authorization_path if authorization_path.is_absolute() else root / authorization_path
    value = _load_json(path)
    required = {
        "schema_version", "pipeline_id", "authorization_id", "plan_payload_sha256",
        "selection_payload_sha256", "output_path", "attempt_marker_path",
        "exact_input_hashes", "call_budget", "r23b_v9_tool_source_sha256",
        "r23c_tool_source_sha256", "authorizer", "signature",
        "authorization_payload_sha256",
    }
    row = _strict_dict(value, required, "R23C_AUTHORIZATION_FIELD_SET_INVALID")
    if row["authorization_payload_sha256"] != _hash_body(row, "authorization_payload_sha256"):
        raise ContractError("R23C_AUTHORIZATION_HASH_MISMATCH", disposition="REJECT")
    plan = build_plan(root)
    output = Path(row["output_path"])
    expected_marker = attempt_marker_path(output, row["authorization_id"]).as_posix()
    if (
        row["schema_version"] != AUTHORIZATION_SCHEMA_VERSION
        or row["pipeline_id"] != PIPELINE_ID
        or row["plan_payload_sha256"] != plan["plan_payload_sha256"]
        or row["selection_payload_sha256"]
        != plan["selection"]["selection_payload_sha256"]
        or row["output_path"] != DEFAULT_OUTPUT.as_posix()
        or row["attempt_marker_path"] != expected_marker
        or row["exact_input_hashes"] != plan["selection"]["source_hashes"]
        or row["call_budget"] != plan["call_budget"]
        or row["r23b_v9_tool_source_sha256"]
        != plan["provenance"]["r23b_v9_tool_source_sha256"]
        or row["r23c_tool_source_sha256"]
        != plan["provenance"]["r23c_tool_source_sha256"]
        or type(row["authorizer"]) is not dict
        or type(row["signature"]) is not dict
    ):
        raise ContractError("R23C_AUTHORIZATION_BINDING_MISMATCH", disposition="REJECT")
    if external_verifier is None:
        raise ContractError(
            "R23C_EXTERNAL_AUTHORIZATION_VERIFIER_REQUIRED",
            disposition="REJECT",
        )
    try:
        verification = external_verifier(copy.deepcopy(row), path)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(
            "R23C_EXTERNAL_AUTHORIZATION_VERIFICATION_FAILED",
            disposition="REJECT",
        ) from exc
    if (
        type(verification) is not dict
        or verification.get("external_signature_verified") is not True
        or verification.get("authorization_payload_sha256")
        != row["authorization_payload_sha256"]
    ):
        raise ContractError(
            "R23C_EXTERNAL_AUTHORIZATION_SIGNATURE_INVALID",
            disposition="REJECT",
        )
    return copy.deepcopy(row)


def _create_attempt_marker(
    authorization_path: Path,
    authorization: Mapping[str, Any],
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    marker_rel = Path(authorization["attempt_marker_path"])
    marker_path = marker_rel if marker_rel.is_absolute() else root / marker_rel
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": ATTEMPT_MARKER_SCHEMA_VERSION,
        "pipeline_id": PIPELINE_ID,
        "authorization_id": authorization["authorization_id"],
        "authorization_receipt_path": (
            authorization_path.as_posix()
            if not authorization_path.is_absolute()
            else authorization_path.relative_to(root).as_posix()
        ),
        "authorization_receipt_sha256": file_sha256(
            authorization_path if authorization_path.is_absolute() else root / authorization_path
        ),
        "output_path": authorization["output_path"],
        "failure_consumes_receipt": True,
    }
    payload["attempt_marker_payload_sha256"] = semantic_hash(payload)
    fd = os.open(marker_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(marker_path, 0o600)
    directory_fd = os.open(marker_path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return payload


def execute(
    *,
    authorization: Path,
    output: Path = DEFAULT_OUTPUT,
    stage_runner: Callable[..., Mapping[str, Any]] | None = None,
    external_authorization_verifier: Callable[
        [Mapping[str, Any], Path], Mapping[str, Any]
    ]
    | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    # Real execution is deliberately impossible without an externally created,
    # exact-input authorization. Tests pass a synthetic stage runner and a temp root.
    if stage_runner is None:
        raise ContractError(
            "R23C_REAL_STAGE_RUNNER_NOT_IMPLEMENTED", disposition="REJECT"
        )
    receipt = validate_authorization(
        authorization,
        root=root,
        external_verifier=external_authorization_verifier,
    )
    expected_output = Path(receipt["output_path"])
    if output != expected_output:
        raise ContractError("R23C_OUTPUT_PATH_MISMATCH", disposition="REJECT")
    marker = _create_attempt_marker(authorization, receipt, root=root)
    stage_output = stage_runner(root=root)
    bundle = build_calibration_bundle(stage_output, root=root)
    output_path = output if output.is_absolute() else root / output
    output_path.mkdir(parents=True, exist_ok=False)
    (output_path / "calibration_bundle.json").write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "status": bundle["status"],
        "scientific_go": False,
        "attempt_marker": marker,
        "output_path": output.as_posix(),
        "bundle_payload_sha256": bundle["bundle_payload_sha256"],
    }


def run_self_test(root: Path = ROOT) -> dict[str, Any]:
    selection = load_exposed_selection(root)
    verify_exposed_selection(selection, root)
    good = build_calibration_bundle(run_synthetic_stage_runner(root=root), root)
    verified = verify_calibration_bundle(good, root)
    if good["status"] != "MACHINE_CALIBRATION_PASS_HUMAN_PENDING":
        raise ContractError("R23C_SELF_TEST_PASS_STATUS_INVALID", disposition="REJECT")
    try:
        build_calibration_bundle(
            run_synthetic_stage_runner(mutation="ambient_duplicate", root=root), root
        )
    except ContractError as exc:
        if exc.code != "R23C_GLOBAL_GATES_FAILED":
            raise
    else:
        raise ContractError("R23C_SELF_TEST_DUPLICATE_NOT_REJECTED", disposition="REJECT")
    for mutation in ("visual_duplicate",):
        try:
            build_calibration_bundle(
                run_synthetic_stage_runner(mutation=mutation, root=root), root
            )
        except ContractError as exc:
            if exc.code != "R23C_GLOBAL_GATES_FAILED":
                raise
        else:
            raise ContractError("R23C_SELF_TEST_GLOBAL_GATE_NOT_REJECTED", disposition="REJECT")
    try:
        build_calibration_bundle(
            run_synthetic_stage_runner(mutation="generic", root=root), root
        )
    except ContractError:
        pass
    else:
        raise ContractError("R23C_SELF_TEST_GENERIC_NOT_REJECTED", disposition="REJECT")
    return {
        "status": "PASS",
        "decision": STATUS_TOKEN,
        "calibration_status": verified["calibration_status"],
        "selection_payload_sha256": selection["selection_payload_sha256"],
        "bundle_payload_sha256": good["bundle_payload_sha256"],
        "visual_constraint_leaf_count": _visual_leaf_count(),
        "model_calls": 0,
        "authorization_calls": 0,
        "attempt_markers_created": 0,
        "retrieval_or_embedding_calls": 0,
    }


def run_preflight(root: Path = ROOT) -> dict[str, Any]:
    plan = build_plan(root)
    plan_verification = verify_plan(plan, root)
    selection_verification = verify_exposed_selection(plan["selection"], root)
    stage = run_synthetic_stage_runner(root=root)
    bundle = build_calibration_bundle(stage, root)
    bundle_verification = verify_calibration_bundle(bundle, root)
    return {
        "status": "PASS",
        "decision": STATUS_TOKEN,
        "plan": plan_verification,
        "selection": selection_verification,
        "synthetic_calibration": bundle_verification,
        "model_calls": 0,
        "authorization_calls": 0,
        "attempt_markers_created": 0,
        "media_decode": False,
        "retrieval_or_embedding": False,
    }


def write_json(path: Path, value: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return file_sha256(path)


def write_committed_artifacts(root: Path = ROOT) -> dict[str, Any]:
    plan = build_plan(root)
    public = build_public_summary(root)
    ledger = build_restricted_ledger(root)
    return {
        "plan": write_json(root / DEFAULT_PLAN, plan),
        "public_summary": write_json(root / DEFAULT_PUBLIC_SUMMARY, public),
        "restricted_ledger": write_json(root / DEFAULT_RESTRICTED_LEDGER, ledger),
        "plan_payload_sha256": plan["plan_payload_sha256"],
        "public_summary_payload_sha256": public["public_summary_payload_sha256"],
        "ledger_payload_sha256": ledger["ledger_payload_sha256"],
        "model_calls": 0,
        "authorization_calls": 0,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("self-test")
    commands.add_parser("preflight")
    commands.add_parser("preflight0")
    commands.add_parser("plan")
    commands.add_parser("write-artifacts")
    execute_parser = commands.add_parser("execute")
    execute_parser.add_argument("--authorization", type=Path, required=True)
    execute_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
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
            result = {**verify_plan(plan), "plan": plan}
        elif args.command == "write-artifacts":
            result = {"status": "PASS", **write_committed_artifacts()}
        elif args.command == "execute":
            result = execute(authorization=args.authorization, output=args.output)
        else:  # pragma: no cover
            raise ContractError("R23C_COMMAND_INVALID", disposition="REJECT")
    except FileExistsError:
        print(json.dumps({"status": "FAIL_CLOSED", "error": "R23C_ONE_SHOT_ALREADY_CONSUMED"}, indent=2, sort_keys=True), file=sys.stderr)
        return 2
    except ContractError as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "error": exc.code}, indent=2, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
