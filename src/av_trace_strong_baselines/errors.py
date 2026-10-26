"""Stable fail-closed errors for the strong-baseline adapter framework."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class StrongBaselineError(RuntimeError):
    """An adapter contract violation with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.details = dict(details or {})


class SchemaViolation(StrongBaselineError):
    """A model-authored or runner-authored public object is invalid."""


class IdentityViolation(StrongBaselineError):
    """The loaded model or processor does not match the frozen binding."""


class IsolationViolation(StrongBaselineError):
    """A staged continuation violates session or cache isolation."""


class EvaluationViolation(StrongBaselineError):
    """A competence result cannot be evaluated under the frozen contract."""
