#!/usr/bin/env python3
"""Shared fail-closed helpers for semantic A/V source prescreening."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SPEC_ROOT = ROOT / "docs/spec"
INVENTORY_SCHEMA = SPEC_ROOT / "semantic_av_source_prescreen_inventory_schema.json"
PLAN_SCHEMA = SPEC_ROOT / "semantic_av_source_prescreen_plan_schema.json"
ANNOTATION_SCHEMA = SPEC_ROOT / "semantic_av_source_prescreen_annotation_schema.json"
IMPORT_SCHEMA = SPEC_ROOT / "semantic_av_source_prescreen_import_schema.json"
EXPOSURE_SCHEMA = (
    SPEC_ROOT / "semantic_av_source_prescreen_exposure_ledger_schema.json"
)

READY = "SEMANTIC_AV_SOURCE_PRESCREEN_READY"
REPAIR = "SEMANTIC_AV_SOURCE_PRESCREEN_REPAIR"
NO_GO = "SEMANTIC_AV_SOURCE_PRESCREEN_NO_GO"
BLIND_ROLE_EXCLUSIONS = [
    "blind_alternative_evidence_finder",
    "blind_post_adjudication_saturation_auditor",
]


class SemanticPrescreenError(ValueError):
    """Raised when a semantic source-prescreen artifact fails closed."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SemanticPrescreenError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def validate_instance(instance: Any, schema_path: Path, label: str) -> None:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(instance), key=lambda error: list(error.absolute_path)
    )
    if errors:
        rendered = []
        for error in errors[:20]:
            location = ".".join(str(part) for part in error.absolute_path) or "$"
            rendered.append(f"{location}: {error.message}")
        raise SemanticPrescreenError(
            f"{label} failed schema validation: " + "; ".join(rendered)
        )


def validate_inventory(inventory: Any) -> None:
    validate_instance(inventory, INVENTORY_SCHEMA, "prescreen inventory")
    source_ids = [source["source_id"] for source in inventory["sources"]]
    if len(source_ids) != len(set(source_ids)):
        raise SemanticPrescreenError("inventory source_id values must be unique")


def plan_hash(plan: dict[str, Any]) -> str:
    envelope = {key: value for key, value in plan.items() if key != "plan_sha256"}
    return sha256_bytes(canonical_json_bytes(envelope))


def validate_plan(plan: Any) -> None:
    validate_instance(plan, PLAN_SCHEMA, "prescreen sample plan")
    if plan["plan_sha256"] != plan_hash(plan):
        raise SemanticPrescreenError("prescreen plan_sha256 mismatch")
    if len(plan["samples"]) != plan["sample_count"]:
        raise SemanticPrescreenError("sample_count does not match samples")
    sample_ids = [sample["sample_id"] for sample in plan["samples"]]
    if len(sample_ids) != len(set(sample_ids)):
        raise SemanticPrescreenError("sample_id values must be unique")
    counts: dict[str, int] = {}
    previous_end: dict[str, float] = {}
    for sample in plan["samples"]:
        if sample["end_s"] <= sample["start_s"]:
            raise SemanticPrescreenError(f"invalid interval {sample['sample_id']}")
        source_id = sample["source_id"]
        counts[source_id] = counts.get(source_id, 0) + 1
        if sample["start_s"] < previous_end.get(source_id, 0.0):
            raise SemanticPrescreenError(
                f"source intervals overlap or are out of order: {source_id}"
            )
        previous_end[source_id] = sample["end_s"]
    if max(counts.values()) - min(counts.values()) > 1:
        raise SemanticPrescreenError("sample allocation is not source-uniform")
    if min(counts.values()) != plan["source_uniformity"]["minimum_per_source"]:
        raise SemanticPrescreenError("minimum_per_source mismatch")
    if max(counts.values()) != plan["source_uniformity"]["maximum_per_source"]:
        raise SemanticPrescreenError("maximum_per_source mismatch")


def validate_annotation(annotation: Any) -> None:
    validate_instance(annotation, ANNOTATION_SCHEMA, "prescreen annotation")


def exposure_ledger_hash(ledger: dict[str, Any]) -> str:
    envelope = {key: value for key, value in ledger.items() if key != "ledger_sha256"}
    return sha256_bytes(canonical_json_bytes(envelope))


def validate_exposure_ledger(ledger: Any) -> None:
    validate_instance(ledger, EXPOSURE_SCHEMA, "prescreen exposure ledger")
    if ledger["ledger_sha256"] != exposure_ledger_hash(ledger):
        raise SemanticPrescreenError("prescreen exposure ledger_sha256 mismatch")
    event_ids = [event["event_id"] for event in ledger["events"]]
    if len(event_ids) != len(set(event_ids)):
        raise SemanticPrescreenError("prescreen exposure event_id values must be unique")


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)
