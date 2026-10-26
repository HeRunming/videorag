"""AV-TRACE model-agnostic strong-baseline adapters.

The package is intentionally inference-framework neutral.  It contains frozen
interfaces, dry fixtures, validators, and competence tooling; it downloads no
weights and performs no real model inference.
"""

from .adapters import (
    AdapterContext,
    AdapterFailure,
    AdapterKind,
    DirectAVAdapter,
    EvidenceBundleAdapter,
    PreparedInvocation,
    SameBackboneEvidenceSufficiencyAdapter,
    SameBackboneReActAdapter,
    SharedGroundedFinalizer,
    SingleShotRAGAdapter,
    build_canonical_agent_action,
    fail_closed,
)
from .comparator import TRACE_STYLE_LABEL, TraceStyleAdaptation
from .contracts import (
    FALLBACK_BINDINGS,
    PRIMARY_BINDINGS,
    BudgetLedger,
    CommonBudget,
    InferenceStatus,
    LoadStatus,
    ModelBinding,
)
from .deterministic import DeterministicControl
from .errors import (
    EvaluationViolation,
    IdentityViolation,
    IsolationViolation,
    SchemaViolation,
    StrongBaselineError,
)
from .fixtures import dry_adapter_fixture_matrix
from .restoration import (
    CHECKPOINT_EVENT,
    CompletedCycle,
    EarlyTerminalAssignment,
    FrozenBlockedPrefix,
    StagedContinuation,
    copy_early_terminal_assignments,
    fork_restored_no_trigger,
)
from .runtime import build_schema_only_repair_request
from .security import (
    IsolationAttestation,
    ObservedEvidenceLock,
    OutputProvenance,
)

__all__ = [
    "CHECKPOINT_EVENT",
    "FALLBACK_BINDINGS",
    "PRIMARY_BINDINGS",
    "TRACE_STYLE_LABEL",
    "AdapterContext",
    "AdapterFailure",
    "AdapterKind",
    "BudgetLedger",
    "CommonBudget",
    "CompletedCycle",
    "DeterministicControl",
    "DirectAVAdapter",
    "EarlyTerminalAssignment",
    "EvaluationViolation",
    "EvidenceBundleAdapter",
    "FrozenBlockedPrefix",
    "IdentityViolation",
    "InferenceStatus",
    "IsolationAttestation",
    "IsolationViolation",
    "LoadStatus",
    "ModelBinding",
    "ObservedEvidenceLock",
    "OutputProvenance",
    "PreparedInvocation",
    "SameBackboneEvidenceSufficiencyAdapter",
    "SameBackboneReActAdapter",
    "SchemaViolation",
    "SharedGroundedFinalizer",
    "SingleShotRAGAdapter",
    "StagedContinuation",
    "StrongBaselineError",
    "TraceStyleAdaptation",
    "build_canonical_agent_action",
    "build_schema_only_repair_request",
    "copy_early_terminal_assignments",
    "dry_adapter_fixture_matrix",
    "fail_closed",
    "fork_restored_no_trigger",
]
