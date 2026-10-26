"""Loading and structural validation for the frozen version 0.2.0 schemas."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .errors import ValidationIssue, ValidationReport, json_pointer, make_report
from .util import json_value_error, load_json, sha256_json

SCHEMA_FILES = {
    "episode-family": "docs/spec/episode_schema.json",
    "agent-action": "docs/spec/agent_action_schema.json",
    "tool-response": "docs/spec/tool_response_schema.json",
    "final-answer": "docs/spec/final_answer_schema.json",
    "trajectory": "docs/spec/trajectory_schema.json",
    "acquisition-manifest": "docs/data/acquisition_manifest_schema.json",
}


def find_repository_root(start: str | Path | None = None) -> Path:
    candidates = []
    if start is not None:
        candidates.append(Path(start).resolve())
    else:
        candidates.extend([Path.cwd().resolve(), Path(__file__).resolve()])
        installed_sibling = Path(__file__).resolve().parent.parent / "av_trace_data"
        if (installed_sibling / "docs/spec/episode_schema.json").is_file():
            return installed_sibling
    for candidate in candidates:
        if candidate.is_file():
            candidate = candidate.parent
        for parent in (candidate, *candidate.parents):
            if (parent / "docs/spec/episode_schema.json").is_file():
                return parent
    if start is None:
        try:
            files = metadata.files("av-trace") or ()
            for entry in files:
                if str(entry).replace("\\", "/").endswith("av_trace_data/docs/spec/episode_schema.json"):
                    installed_root = Path(entry.locate()).resolve().parents[2]
                    if (installed_root / "docs/spec/episode_schema.json").is_file():
                        return installed_root
        except metadata.PackageNotFoundError:
            pass
    raise FileNotFoundError("AV-TRACE repository root not found; expected docs/spec/episode_schema.json")


class SchemaRegistry:
    """Repository-backed immutable registry for all normative JSON schemas."""

    def __init__(self, repository_root: str | Path | None = None) -> None:
        self.root = find_repository_root(repository_root)
        self.schemas = {name: load_json(self.root / relative) for name, relative in SCHEMA_FILES.items()}
        resources = [
            (schema["$id"], Resource.from_contents(schema))
            for schema in self.schemas.values()
        ]
        self._registry = Registry().with_resources(resources)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self.schemas))

    def schema_hash(self, name: str) -> str:
        return sha256_json(self.schemas[name])

    def check_schemas(self) -> ValidationReport:
        issues: list[ValidationIssue] = []
        ids: dict[str, str] = {}
        for name in self.names:
            schema = self.schemas[name]
            try:
                Draft202012Validator.check_schema(schema)
            except Exception as exc:  # jsonschema exposes several check exceptions
                issues.append(ValidationIssue("SCHEMA-001", f"/{name}", f"Invalid Draft 2020-12 schema: {exc}"))
            schema_id = schema.get("$id")
            if schema_id in ids:
                issues.append(
                    ValidationIssue(
                        "SCHEMA-002",
                        f"/{name}/$id",
                        f"Duplicate schema identifier also used by {ids[schema_id]}.",
                    )
                )
            elif isinstance(schema_id, str):
                ids[schema_id] = name
            if not isinstance(schema_id, str) or not schema_id.startswith("urn:av-trace:schema:") or not schema_id.endswith(":0.2.0"):
                issues.append(ValidationIssue("SCHEMA-003", f"/{name}/$id", "Schema ID must use the immutable AV-TRACE 0.2.0 URN namespace."))
            if isinstance(schema_id, str):
                resolver = self._registry.resolver(schema_id)
                pending: list[tuple[tuple[Any, ...], Any]] = [((), schema)]
                while pending:
                    path, value = pending.pop()
                    if isinstance(value, dict):
                        reference = value.get("$ref")
                        if isinstance(reference, str):
                            try:
                                resolver.lookup(reference)
                            except Exception as exc:
                                issues.append(
                                    ValidationIssue(
                                        "SCHEMA-004",
                                        json_pointer((name, *path, "$ref")),
                                        f"Unresolvable schema reference {reference!r}: {exc}",
                                    )
                                )
                        pending.extend((path + (key,), child) for key, child in value.items())
                    elif isinstance(value, list):
                        pending.extend((path + (index,), child) for index, child in enumerate(value))
        return make_report(issues, schemas=list(self.names))

    def validator(self, name: str) -> Draft202012Validator:
        if name not in self.schemas:
            raise KeyError(f"Unknown schema name: {name}")
        return Draft202012Validator(
            self.schemas[name],
            registry=self._registry,
            format_checker=FormatChecker(),
        )

    def validate(self, name: str, instance: Any) -> ValidationReport:
        issues = []
        input_error = json_value_error(instance)
        if input_error:
            return make_report(
                [ValidationIssue("INPUT-001", "", input_error)],
                schema=name,
                schema_hash=self.schema_hash(name),
            )
        try:
            errors = sorted(
                self.validator(name).iter_errors(instance),
                key=lambda e: (tuple(str(part) for part in e.absolute_path), e.message),
            )
        except Exception as exc:
            issues.append(
                ValidationIssue(
                    "SCHEMA-004",
                    "",
                    f"Schema reference resolution failed: {exc}",
                )
            )
        else:
            for error in errors:
                issues.append(
                    ValidationIssue(
                        "SCHEMA-VALIDATION",
                        json_pointer(error.absolute_path),
                        error.message,
                    )
                )
        return make_report(issues, schema=name, schema_hash=self.schema_hash(name))

    def validate_many(self, pairs: Iterable[tuple[str, Any]]) -> ValidationReport:
        issues: list[ValidationIssue] = []
        for name, instance in pairs:
            report = self.validate(name, instance)
            issues.extend(report.issues)
        return make_report(issues)
