"""Prospective Granite-native strong-baseline adapter v2.

This package is development-only. It does not import a model runtime, execute
the Task-172 suite, or authorize scientific evaluation.
"""

from .adapter import (
    NativeActionPlan,
    action_choice_spec,
    build_native_action_plan,
    controller_factor_contracts,
    evidence_state_spec,
    finalizer_factor_contracts,
    finalizer_factor_specs,
    parse_controller_factors,
    parse_factor_attempts,
    parse_finalizer_factors,
    project_evidence_state,
    serialize_controller_decision,
    serialize_finalizer_factors,
)
from .contracts import (
    ADAPTER_SCHEMA_VERSION,
    AttemptKind,
    ControllerFactorResult,
    FactorOutcome,
    FactorSpec,
    FactorStatus,
    FinalizerFactorResult,
    NativeActionChoice,
    ProjectionStatus,
    RawFactorAttempt,
    StateProjection,
)
from .development import run_task172_structural_regression
from .suite_generator import (
    FutureSealedSuiteGenerator,
    FutureSuiteBundle,
    generator_contract,
    model_public_case,
    validate_future_seed,
)

__all__ = [
    "ADAPTER_SCHEMA_VERSION",
    "AttemptKind",
    "ControllerFactorResult",
    "FactorOutcome",
    "FactorSpec",
    "FactorStatus",
    "FinalizerFactorResult",
    "FutureSealedSuiteGenerator",
    "FutureSuiteBundle",
    "NativeActionChoice",
    "NativeActionPlan",
    "ProjectionStatus",
    "RawFactorAttempt",
    "StateProjection",
    "action_choice_spec",
    "build_native_action_plan",
    "controller_factor_contracts",
    "evidence_state_spec",
    "finalizer_factor_contracts",
    "finalizer_factor_specs",
    "generator_contract",
    "model_public_case",
    "parse_controller_factors",
    "parse_factor_attempts",
    "parse_finalizer_factors",
    "project_evidence_state",
    "run_task172_structural_regression",
    "serialize_controller_decision",
    "serialize_finalizer_factors",
    "validate_future_seed",
]
