"""Stable validation result objects shared by all validation layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


def json_pointer(parts: Iterable[Any]) -> str:
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "" if not escaped else "/" + "/".join(escaped)


@dataclass(frozen=True, order=True)
class ValidationIssue:
    """One deterministic validation diagnostic."""

    code: str
    pointer: str
    message: str
    involved_ids: tuple[str, ...] = field(default_factory=tuple, compare=True)
    severity: str = field(default="error", compare=True)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": self.code,
            "pointer": self.pointer,
            "message": self.message,
            "severity": self.severity,
        }
        if self.involved_ids:
            data["involved_ids"] = list(self.involved_ids)
        return data


@dataclass(frozen=True)
class ValidationReport:
    """A sorted, serializable collection of validation diagnostics."""

    issues: tuple[ValidationIssue, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def status(self) -> str:
        return "PASS" if self.ok else "FAIL"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status,
            "issues": [issue.to_dict() for issue in self.issues],
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result


def make_report(issues: Iterable[ValidationIssue], **metadata: Any) -> ValidationReport:
    unique = {issue for issue in issues}
    ordered = tuple(sorted(unique, key=lambda i: (i.code, i.pointer, i.message, i.involved_ids)))
    return ValidationReport(ordered, metadata)
