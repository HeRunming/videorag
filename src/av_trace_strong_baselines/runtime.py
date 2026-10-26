"""Model-agnostic, fail-closed invocation boundary.

This module intentionally provides interfaces and dry drivers only. It does
not import a model framework, download weights, or perform real inference.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import (
    InferenceStatus,
    LoadStatus,
    ModelBinding,
    require_exact_binding,
)
from .errors import IdentityViolation, StrongBaselineError
from .security import assert_public_surface

SCHEMA_REPAIRABLE_ERRORS = frozenset(
    {
        "MODEL_OUTPUT_EMPTY",
        "MODEL_OUTPUT_INVALID_UTF8",
        "MODEL_OUTPUT_MALFORMED_JSON",
        "MODEL_OUTPUT_DUPLICATE_KEY",
        "MODEL_OUTPUT_TRAILING_CONTENT",
        "MODEL_OUTPUT_TOO_LARGE",
        "AGENT_ACTION_SCHEMA_INVALID",
        "FINAL_ANSWER_SCHEMA_INVALID",
        "CONTROLLER_DECISION_FIELD_SET",
        "CONTROLLER_ACTION_INDEX_INVALID",
    }
)


@dataclass(frozen=True)
class GenerationRequest:
    request_id: str
    role: str
    public_payload: Mapping[str, Any]
    max_new_tokens: int
    context_cap_processor_tokens: int
    schema_only_repair: bool = False


@dataclass(frozen=True)
class DriverResponse:
    raw_output: bytes
    inference_status: InferenceStatus
    prompt_tokens: int | None = None
    generated_tokens: int | None = None
    error_code: str | None = None


class ModelDriver(Protocol):
    @property
    def observed_binding(self) -> ModelBinding: ...

    @property
    def load_status(self) -> LoadStatus: ...

    def generate(self, request: GenerationRequest) -> DriverResponse: ...


@dataclass(frozen=True)
class InvocationOutcome:
    status: InferenceStatus
    raw_output: bytes | None
    error_code: str | None
    model_binding_fingerprint: str
    model_was_called: bool


def build_schema_only_repair_request(
    original: GenerationRequest,
    *,
    invalid_raw_output: bytes,
    validation_error_code: str,
    public_output_schema: Mapping[str, Any],
) -> GenerationRequest:
    """Build the sole permitted repair without adding semantic guidance."""

    if original.schema_only_repair:
        raise StrongBaselineError("SECOND_REPAIR_FORBIDDEN")
    if validation_error_code not in SCHEMA_REPAIRABLE_ERRORS:
        raise StrongBaselineError(
            "SEMANTIC_REPAIR_FORBIDDEN",
            details={"validation_error_code": validation_error_code},
        )
    repair_payload = {
        "task": "schema_only_repair",
        "original_task": original.public_payload.get("task"),
        "public_output_schema": dict(public_output_schema),
        "invalid_output_utf8": invalid_raw_output.decode(
            "utf-8", errors="replace"
        ),
        "validation_error_code": validation_error_code,
        "instruction": (
            "Return the same attempted content in exactly the required JSON "
            "structure. Do not add facts, claims, citations, or answers."
        ),
    }
    assert_public_surface(repair_payload)
    return GenerationRequest(
        request_id=f"{original.request_id}.schema-repair",
        role=original.role,
        public_payload=repair_payload,
        max_new_tokens=original.max_new_tokens,
        context_cap_processor_tokens=original.context_cap_processor_tokens,
        schema_only_repair=True,
    )


def invoke_fail_closed(
    driver: ModelDriver,
    *,
    expected_binding: ModelBinding,
    request: GenerationRequest,
) -> InvocationOutcome:
    """Verify identity before every call and never substitute an answer."""

    try:
        require_exact_binding(
            expected_binding,
            driver.observed_binding,
            load_status=driver.load_status,
        )
    except IdentityViolation as exc:
        status = (
            InferenceStatus.SNAPSHOT_MISMATCH
            if exc.code == "MODEL_SNAPSHOT_MISMATCH"
            else InferenceStatus.LOAD_NOT_VERIFIED
        )
        return InvocationOutcome(
            status=status,
            raw_output=None,
            error_code=exc.code,
            model_binding_fingerprint=expected_binding.fingerprint,
            model_was_called=False,
        )
    try:
        response = driver.generate(request)
    except TimeoutError:
        return InvocationOutcome(
            status=InferenceStatus.TIMEOUT,
            raw_output=None,
            error_code="MODEL_TIMEOUT",
            model_binding_fingerprint=expected_binding.fingerprint,
            model_was_called=True,
        )
    except MemoryError:
        return InvocationOutcome(
            status=InferenceStatus.OOM,
            raw_output=None,
            error_code="MODEL_OOM",
            model_binding_fingerprint=expected_binding.fingerprint,
            model_was_called=True,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return InvocationOutcome(
            status=InferenceStatus.PROVIDER_FAILURE,
            raw_output=None,
            error_code=type(exc).__name__,
            model_binding_fingerprint=expected_binding.fingerprint,
            model_was_called=True,
        )
    if response.inference_status is not InferenceStatus.VALID:
        return InvocationOutcome(
            status=response.inference_status,
            raw_output=None,
            error_code=response.error_code or "MODEL_CALL_NOT_VALID",
            model_binding_fingerprint=expected_binding.fingerprint,
            model_was_called=True,
        )
    return InvocationOutcome(
        status=InferenceStatus.VALID,
        raw_output=response.raw_output,
        error_code=None,
        model_binding_fingerprint=expected_binding.fingerprint,
        model_was_called=True,
    )


class DryModelDriver:
    """Explicit non-inference driver used by planning and unit fixtures."""

    def __init__(
        self,
        binding: ModelBinding,
        *,
        load_status: LoadStatus = LoadStatus.NOT_ACQUIRED,
    ) -> None:
        self._binding = binding
        self._load_status = load_status
        self.calls = 0

    @property
    def observed_binding(self) -> ModelBinding:
        return self._binding

    @property
    def load_status(self) -> LoadStatus:
        return self._load_status

    def generate(self, request: GenerationRequest) -> DriverResponse:
        self.calls += 1
        raise StrongBaselineError(
            "DRY_DRIVER_INFERENCE_FORBIDDEN",
            details={"request_id": request.request_id},
        )
