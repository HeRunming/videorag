"""JSON-Schema loading and fail-closed validation for validator records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from av_trace.util import load_json

from .io import SCHEMA_ROOT


SCHEMA_FILES = {
    "identity": "validator_identity_schema.json",
    "trajectory_link": "validator_trajectory_link_schema.json",
    "ses_demonstration": "validator_ses_demonstration_schema.json",
    "minimality_result": "validator_minimality_result_schema.json",
    "blocked_proof": "validator_blocked_proof_schema.json",
    "restored_proof": "validator_restored_proof_schema.json",
    "feasible_route": "validator_feasible_route_schema.json",
    "denominator": "validator_denominator_schema.json",
    "dataset_certificate": "validator_dataset_certificate_schema.json",
}


@dataclass(frozen=True)
class SchemaIssue:
    pointer: str
    message: str


class ValidatorSchemaError(ValueError):
    def __init__(self, schema_name: str, issues: list[SchemaIssue]) -> None:
        first = issues[0]
        super().__init__(f"{schema_name} {first.pointer}: {first.message}")
        self.schema_name = schema_name
        self.issues = tuple(issues)


def schema_path(name: str, root: str | Path | None = None) -> Path:
    try:
        filename = SCHEMA_FILES[name]
    except KeyError as exc:
        raise KeyError(f"Unknown validator schema {name!r}.") from exc
    return Path(root or SCHEMA_ROOT) / filename


def validate_document(
    name: str,
    document: Any,
    *,
    schema_root: str | Path | None = None,
) -> list[SchemaIssue]:
    schema = load_json(schema_path(name, schema_root))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues = []
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        pointer = "/" + "/".join(str(part) for part in error.absolute_path)
        issues.append(SchemaIssue(pointer or "/", error.message))
    return issues


def require_valid(
    name: str,
    document: Any,
    *,
    schema_root: str | Path | None = None,
) -> None:
    issues = validate_document(name, document, schema_root=schema_root)
    if issues:
        raise ValidatorSchemaError(name, issues)

