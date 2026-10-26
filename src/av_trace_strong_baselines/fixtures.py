"""Source-free dry adapter matrix for integration and review."""

from __future__ import annotations

from typing import Any

from .comparator import TRACE_STYLE_LABEL
from .contracts import PRIMARY_BINDINGS, CommonBudget, sha256_json


def dry_adapter_fixture_matrix() -> dict[str, Any]:
    """Return all Task-148 rows without loading or invoking a model."""

    rows = [
        {
            "system_id": "DLC-B-QWEN25OMNI7B",
            "adapter": "DirectAVAdapter",
            "model_binding": PRIMARY_BINDINGS["direct_av"].to_dict(),
            "staged_event_capable": False,
            "restoration_eligibility": (
                "STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT"
            ),
            "status": "NOT_ACQUIRED_NOT_RUN",
        },
        {
            "system_id": "RAG-A-GRANITE33-8B",
            "adapter": "SingleShotRAGAdapter",
            "model_binding": PRIMARY_BINDINGS["controller"].to_dict(),
            "finalizer_binding": PRIMARY_BINDINGS["finalizer"].to_dict(),
            "staged_event_capable": True,
            "status": "NOT_ACQUIRED_NOT_RUN",
        },
        {
            "system_id": "REACT-A-GRANITE33-8B",
            "adapter": "SameBackboneReActAdapter",
            "model_binding": PRIMARY_BINDINGS["controller"].to_dict(),
            "finalizer_binding": PRIMARY_BINDINGS["finalizer"].to_dict(),
            "staged_event_capable": True,
            "status": "NOT_ACQUIRED_NOT_RUN",
        },
        {
            "system_id": "SUFF-A-GRANITE33-8B",
            "adapter": "SameBackboneEvidenceSufficiencyAdapter",
            "model_binding": PRIMARY_BINDINGS["controller"].to_dict(),
            "finalizer_binding": PRIMARY_BINDINGS["finalizer"].to_dict(),
            "staged_event_capable": True,
            "status": "NOT_ACQUIRED_NOT_RUN",
        },
        {
            "system_id": "ORACLE-A-GRANITE33-8B",
            "adapter": "EvidenceBundleAdapter.ORACLE_EVIDENCE",
            "model_binding": PRIMARY_BINDINGS["finalizer"].to_dict(),
            "staged_event_capable": False,
            "diagnostic_only": True,
            "status": "NOT_ACQUIRED_NOT_RUN",
        },
        {
            "system_id": "PARTIAL-A-GRANITE33-8B",
            "adapter": "EvidenceBundleAdapter.PARTIAL_EVIDENCE",
            "model_binding": PRIMARY_BINDINGS["finalizer"].to_dict(),
            "staged_event_capable": False,
            "diagnostic_only": True,
            "status": "NOT_ACQUIRED_NOT_RUN",
        },
        {
            "system_id": "TRACE-STYLE-A-GRANITE33-8B",
            "adapter": "TraceStyleAdaptation",
            "model_binding": PRIMARY_BINDINGS["controller"].to_dict(),
            "finalizer_binding": PRIMARY_BINDINGS["finalizer"].to_dict(),
            "staged_event_capable": True,
            "adaptation_label": TRACE_STYLE_LABEL,
            "official_reproduction": False,
            "status": "NOT_ACQUIRED_NOT_RUN",
        },
        {
            "system_id": "DET-REACT",
            "adapter": "DeterministicControl",
            "staged_event_capable": True,
            "learned_system_substitute": False,
            "status": "DRY_CONTROL_ONLY",
        },
        {
            "system_id": "DET-SUFF",
            "adapter": "DeterministicControl",
            "staged_event_capable": True,
            "learned_system_substitute": False,
            "status": "DRY_CONTROL_ONLY",
        },
        {
            "system_id": "NO-TRIGGER",
            "adapter": "fork_restored_no_trigger.NO_TRIGGER",
            "staged_event_capable": True,
            "hidden_route_restored": False,
            "status": "DRY_CONTROL_ONLY",
        },
    ]
    matrix: dict[str, Any] = {
        "schema_version": "av-trace.strong-baseline-dry-matrix/1.0",
        "budget": CommonBudget().to_dict(),
        "rows": rows,
        "weights_downloaded": False,
        "model_inference_run": False,
    }
    matrix["matrix_hash"] = sha256_json(matrix)
    return matrix
