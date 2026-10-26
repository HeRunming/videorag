"""Public-packet validation, input commitments, and output sealing."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .schemas import canonical_json_bytes

PUBLIC_PACKET_VERSION = "av-trace.controller-v2-public-holdout/2.0.0"
ATTESTATION_VERSION = "av-trace.controller-v2-implementation-attestation/1.0"
FORBIDDEN_EVALUATOR_KEY_RELATIVE = (
    "data/rehearsal_plan/controller_v2_holdout/"
    "restricted_evaluator_key.json"
)
FORBIDDEN_PUBLIC_KEYS = {
    "expected_action_index",
    "expected_action",
    "expected_state",
    "oracle_support",
    "required_terms",
    "answer_key",
    "labels",
    "primary_stratum",
    "secondary_capabilities",
}


class PacketValidationError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PacketValidationError(f"JSON_OBJECT_REQUIRED:{path.name}")
    return value


def assert_path_is_not_forbidden(*, repo_root: Path, path: Path) -> None:
    """Reject the evaluator-key pathname before any filesystem access."""

    forbidden = os.path.abspath(repo_root / FORBIDDEN_EVALUATOR_KEY_RELATIVE)
    candidate = os.path.abspath(path)
    if candidate == forbidden:
        raise PacketValidationError("FORBIDDEN_EVALUATOR_KEY_PATH")


def _walk_keys(value: Any):
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def validate_public_packet(packet: Mapping[str, Any]) -> None:
    expected_top = {
        "schema_version",
        "packet_id",
        "visibility",
        "synthetic_only",
        "contains_source_media",
        "contains_expected_outputs",
        "model_inputs_only",
        "case_order_frozen",
        "cases",
    }
    if set(packet) != expected_top:
        raise PacketValidationError("PACKET_FIELD_SET_MISMATCH")
    if packet["schema_version"] != PUBLIC_PACKET_VERSION:
        raise PacketValidationError("PACKET_VERSION_MISMATCH")
    if (
        packet["visibility"] != "PUBLIC_TO_IMPLEMENTATION_WORKER"
        or packet["synthetic_only"] is not True
        or packet["contains_source_media"] is not False
        or packet["contains_expected_outputs"] is not False
        or packet["model_inputs_only"] is not True
        or packet["case_order_frozen"] is not True
    ):
        raise PacketValidationError("PACKET_BOUNDARY_VIOLATION")
    leaked = FORBIDDEN_PUBLIC_KEYS.intersection(_walk_keys(packet))
    if leaked:
        raise PacketValidationError(
            f"PACKET_PRIVATE_LABEL_KEY:{min(leaked)}"
        )
    cases = packet["cases"]
    if not isinstance(cases, list) or not cases:
        raise PacketValidationError("PACKET_CASES_INVALID")
    expected_case_keys = {
        "case_id",
        "policy",
        "question",
        "public_claim_slots",
        "known_pointers",
        "citable_observations",
        "recent_public_events",
        "no_progress_rounds",
        "remaining_budget",
        "action_menu",
        "action_output_contract",
        "state_output_contract",
    }
    case_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != expected_case_keys:
            raise PacketValidationError("CASE_FIELD_SET_MISMATCH")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            raise PacketValidationError("CASE_ID_INVALID")
        case_ids.add(case_id)
        if case["policy"] not in {"react", "evidence_sufficiency"}:
            raise PacketValidationError("CASE_POLICY_INVALID")
        if not isinstance(case["question"], str):
            raise PacketValidationError("CASE_QUESTION_INVALID")
        menu = case["action_menu"]
        if not isinstance(menu, list) or not 1 <= len(menu) <= 4:
            raise PacketValidationError("CASE_ACTION_MENU_INVALID")
        if any(not isinstance(action, dict) for action in menu):
            raise PacketValidationError("CASE_ACTION_MENU_INVALID")
        indices = case["action_output_contract"].get(
            "allowed_action_indices"
        )
        if indices != list(range(len(menu))):
            raise PacketValidationError("CASE_ACTION_ENUM_INVALID")
        slots = case["public_claim_slots"]
        if not isinstance(slots, list) or len(slots) > 8:
            raise PacketValidationError("CASE_CLAIM_SLOTS_INVALID")
        handles = [
            slot.get("claim_handle") if isinstance(slot, dict) else None
            for slot in slots
        ]
        if any(not isinstance(handle, str) for handle in handles):
            raise PacketValidationError("CASE_CLAIM_HANDLE_INVALID")
        if len(set(handles)) != len(handles):
            raise PacketValidationError("CASE_CLAIM_HANDLE_DUPLICATE")
        if (
            case["state_output_contract"].get("allowed_claim_handles")
            != handles
        ):
            raise PacketValidationError("CASE_CLAIM_ENUM_INVALID")


def load_public_packet(path: Path) -> dict[str, Any]:
    packet = _load_json(path)
    validate_public_packet(packet)
    return packet


def load_implementation_attestation(path: Path) -> dict[str, Any]:
    value = _load_json(path)
    required = {
        "schema_version",
        "implementation_worker",
        "attested_at",
        "forbidden_evaluator_key_not_accessed",
        "holdout_not_executed_during_implementation",
        "no_expected_outputs_or_labels_inspected",
    }
    if not required <= set(value):
        raise PacketValidationError("IMPLEMENTATION_ATTESTATION_FIELDS")
    if value["schema_version"] != ATTESTATION_VERSION:
        raise PacketValidationError("IMPLEMENTATION_ATTESTATION_VERSION")
    if not isinstance(value["implementation_worker"], str) or not value[
        "implementation_worker"
    ]:
        raise PacketValidationError("IMPLEMENTATION_ATTESTATION_WORKER")
    if not isinstance(value["attested_at"], str) or not value["attested_at"]:
        raise PacketValidationError("IMPLEMENTATION_ATTESTATION_DATE")
    for field in (
        "forbidden_evaluator_key_not_accessed",
        "holdout_not_executed_during_implementation",
        "no_expected_outputs_or_labels_inspected",
    ):
        if value[field] is not True:
            raise PacketValidationError(
                f"IMPLEMENTATION_ATTESTATION_FALSE:{field}"
            )
    if FORBIDDEN_PUBLIC_KEYS.intersection(_walk_keys(value)):
        raise PacketValidationError("IMPLEMENTATION_ATTESTATION_LABEL_KEY")
    return value


def verify_contract_inputs(
    *,
    repo_root: Path,
    public_packet_path: Path,
) -> dict[str, Any]:
    contract_path = (
        repo_root / "data/rehearsal_plan/controller_v2_holdout_contract.json"
    )
    contract = _load_json(contract_path)
    canonical = {
        key: item for key, item in contract.items() if key != "contract_hash"
    }
    actual_contract_hash = "sha256:" + hashlib.sha256(
        canonical_json_bytes(canonical)
    ).hexdigest()
    if contract.get("contract_hash") != actual_contract_hash:
        raise PacketValidationError("CONTRACT_HASH_MISMATCH")
    expected_packet = os.path.abspath(
        repo_root / contract["separation"]["public_execution_packet"]
    )
    supplied_packet = os.path.abspath(public_packet_path)
    if supplied_packet != expected_packet:
        raise PacketValidationError("PUBLIC_PACKET_PATH_NOT_CONTRACTED")

    checked: dict[str, str] = {}
    artifact_paths = {
        "design": repo_root / "docs/design/controller_interface_v2.md",
        "action_schema": (
            repo_root / "docs/spec/controller_v2_action_schema.json"
        ),
        "state_schema": repo_root / "docs/spec/controller_v2_state_schema.json",
        "public_execution_packet": public_packet_path,
    }
    for key, path in artifact_paths.items():
        actual = sha256_file(path)
        if actual != contract["artifact_hashes"][key]:
            raise PacketValidationError(f"ARTIFACT_HASH_MISMATCH:{key}")
        checked[key] = actual
    return {
        "contract": contract,
        "contract_file_sha256": sha256_file(contract_path),
        "contract_hash": actual_contract_hash,
        "checked_artifacts": checked,
        "task111_protected_artifacts_accessed": False,
        "task111_protected_hashes_from_contract": dict(
            contract["task111_protected_hashes"]
        ),
        "restricted_evaluator_key_checked": False,
    }


def verify_model_snapshot(
    *,
    repo_root: Path,
    snapshot: Path,
) -> dict[str, Any]:
    manifest_path = (
        repo_root
        / "data/restricted/scale1b/manifests/"
        "strong_controller_model_acquisition.json"
    )
    manifest = _load_json(manifest_path)
    candidate = manifest["candidate"]
    expected_snapshot = os.path.abspath(repo_root / candidate["snapshot_dir"])
    if os.path.abspath(snapshot) != expected_snapshot:
        raise PacketValidationError("MODEL_SNAPSHOT_PATH_MISMATCH")
    verified: dict[str, dict[str, Any]] = {}
    acquisition_by_path = {
        item["path"]: item for item in manifest["acquisition"]["files"]
    }
    for item in candidate["allowlist"]:
        relative = item["path"]
        path = snapshot / relative
        actual_hash = sha256_file(path)
        expected_hash = "sha256:" + acquisition_by_path[relative]["sha256"]
        if actual_hash != expected_hash:
            raise PacketValidationError(
                f"MODEL_SNAPSHOT_HASH_MISMATCH:{relative}"
            )
        size = path.stat().st_size
        if size != item["expected_bytes"]:
            raise PacketValidationError(
                f"MODEL_SNAPSHOT_SIZE_MISMATCH:{relative}"
            )
        verified[relative] = {"sha256": actual_hash, "bytes": size}
    return {
        "manifest_sha256": sha256_file(manifest_path),
        "repo_id": candidate["repo_id"],
        "revision": candidate["revision"],
        "snapshot_path": os.path.abspath(snapshot),
        "files": verified,
    }


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(canonical_json_bytes(value) + b"\n")
    os.replace(temporary, path)


def write_jsonl(path: Path, values: list[Mapping[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as handle:
        for value in values:
            handle.write(canonical_json_bytes(value) + b"\n")
    os.replace(temporary, path)


def seal_output_files(
    output_dir: Path,
    *,
    names: list[str],
    input_commitments: Mapping[str, Any],
) -> dict[str, Any]:
    files = {
        name: {
            "sha256": sha256_file(output_dir / name),
            "bytes": (output_dir / name).stat().st_size,
        }
        for name in names
    }
    seal = {
        "schema_version": "av-trace.controller-v2-output-seal/1.0",
        "immutable": True,
        "correctness_scored": False,
        "evaluator_labels_loaded": False,
        "input_commitments": dict(input_commitments),
        "files": files,
    }
    write_json(output_dir / "output_seal.json", seal)
    for name in [*names, "output_seal.json"]:
        (output_dir / name).chmod(0o444)
    return seal


def verify_execution_seal(output_dir: Path) -> bool:
    seal = _load_json(output_dir / "output_seal.json")
    if (
        seal.get("immutable") is not True
        or seal.get("correctness_scored") is not False
        or seal.get("evaluator_labels_loaded") is not False
    ):
        return False
    files = seal.get("files")
    if not isinstance(files, dict):
        return False
    for name, expected in files.items():
        path = output_dir / name
        if sha256_file(path) != expected.get("sha256"):
            return False
        if path.stat().st_size != expected.get("bytes"):
            return False
    return True
