"""Frozen common contracts shared by every strong-baseline adapter."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from .errors import IdentityViolation, StrongBaselineError

SCHEMA_VERSION = "av-trace.strong-baseline-adapter/1.0"
MODEL_REVISION_PATTERN = re.compile(r"^[a-f0-9]{40}$")

CANONICAL_TOOLS = (
    "search_visual",
    "search_speech",
    "search_ambient_audio",
    "inspect_clip",
    "read_transcript",
    "get_channel_status",
    "finalize",
)

TOOL_COSTS: dict[str, float] = {
    "search_visual": 1.0,
    "search_speech": 1.0,
    "search_ambient_audio": 1.0,
    "inspect_clip": 2.0,
    "read_transcript": 1.0,
    "get_channel_status": 0.25,
    "finalize": 0.0,
}


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a public object canonically for sealing and replay."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class LoadStatus(StrEnum):
    NOT_ACQUIRED = "NOT_ACQUIRED"
    UNCHECKED = "UNCHECKED"
    LOAD_FAILED = "LOAD_FAILED"
    LOADED_VERIFIED = "LOADED_VERIFIED"


class InferenceStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    VALID = "VALID"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    LOAD_NOT_VERIFIED = "LOAD_NOT_VERIFIED"
    SNAPSHOT_MISMATCH = "SNAPSHOT_MISMATCH"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    PROCESS_FAILURE = "PROCESS_FAILURE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    OOM = "OOM"


@dataclass(frozen=True)
class ModelBinding:
    """Immutable model, processor, tokenizer, and role identity."""

    repo_id: str
    revision: str
    role: str
    processor_revision: str | None = None
    tokenizer_revision: str | None = None

    def __post_init__(self) -> None:
        if not self.repo_id or "/" not in self.repo_id:
            raise IdentityViolation("MODEL_REPO_ID_INVALID")
        if not MODEL_REVISION_PATTERN.fullmatch(self.revision):
            raise IdentityViolation("MODEL_REVISION_NOT_IMMUTABLE_SHA")
        for name, revision in (
            ("processor", self.processor_revision),
            ("tokenizer", self.tokenizer_revision),
        ):
            if revision is not None and not MODEL_REVISION_PATTERN.fullmatch(revision):
                raise IdentityViolation(
                    f"{name.upper()}_REVISION_NOT_IMMUTABLE_SHA"
                )
        if not self.role.strip():
            raise IdentityViolation("MODEL_ROLE_EMPTY")

    @property
    def resolved_processor_revision(self) -> str:
        return self.processor_revision or self.revision

    @property
    def resolved_tokenizer_revision(self) -> str:
        return self.tokenizer_revision or self.revision

    @property
    def fingerprint(self) -> str:
        return sha256_json(self.to_dict())

    def to_dict(self) -> dict[str, str]:
        return {
            "repo_id": self.repo_id,
            "revision": self.revision,
            "role": self.role,
            "processor_revision": self.resolved_processor_revision,
            "tokenizer_revision": self.resolved_tokenizer_revision,
        }


def require_exact_binding(
    expected: ModelBinding,
    observed: ModelBinding,
    *,
    load_status: LoadStatus,
) -> None:
    """Stop before inference unless every frozen identity field matches."""

    if load_status is not LoadStatus.LOADED_VERIFIED:
        raise IdentityViolation(
            "MODEL_LOAD_NOT_VERIFIED",
            details={"load_status": str(load_status)},
        )
    if expected.to_dict() != observed.to_dict():
        raise IdentityViolation(
            "MODEL_SNAPSHOT_MISMATCH",
            details={
                "expected_fingerprint": expected.fingerprint,
                "observed_fingerprint": observed.fingerprint,
            },
        )


@dataclass(frozen=True)
class CommonBudget:
    """Task-138/148 common learned-system budget."""

    max_canonical_actions_including_finalize: int = 10
    cost_limit: float = 12.0
    search_top_k: int = 5
    context_cap_processor_tokens: int = 32_768
    max_new_tokens_per_call: int = 512
    max_model_invocations_including_repair: int = 12
    schema_only_repairs: int = 1
    semantic_repairs: int = 0
    best_of_n: int = 1
    tool_costs: Mapping[str, float] = field(
        default_factory=lambda: dict(TOOL_COSTS)
    )

    def __post_init__(self) -> None:
        if self.max_canonical_actions_including_finalize != 10:
            raise StrongBaselineError("COMMON_ACTION_BUDGET_MISMATCH")
        if self.cost_limit != 12.0:
            raise StrongBaselineError("COMMON_COST_BUDGET_MISMATCH")
        if self.search_top_k != 5:
            raise StrongBaselineError("COMMON_TOP_K_MISMATCH")
        if self.context_cap_processor_tokens != 32_768:
            raise StrongBaselineError("COMMON_CONTEXT_CAP_MISMATCH")
        if self.max_new_tokens_per_call != 512:
            raise StrongBaselineError("COMMON_OUTPUT_CAP_MISMATCH")
        if self.max_model_invocations_including_repair != 12:
            raise StrongBaselineError("COMMON_MODEL_CALL_CAP_MISMATCH")
        if self.schema_only_repairs != 1:
            raise StrongBaselineError("COMMON_REPAIR_CAP_MISMATCH")
        if self.semantic_repairs != 0 or self.best_of_n != 1:
            raise StrongBaselineError("SEMANTIC_REPAIR_OR_VOTING_FORBIDDEN")
        if dict(self.tool_costs) != TOOL_COSTS:
            raise StrongBaselineError("COMMON_TOOL_COST_MISMATCH")
        object.__setattr__(
            self, "tool_costs", MappingProxyType(dict(self.tool_costs))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_canonical_actions_including_finalize": (
                self.max_canonical_actions_including_finalize
            ),
            "cost_limit": self.cost_limit,
            "search_top_k": self.search_top_k,
            "context_cap_processor_tokens": self.context_cap_processor_tokens,
            "max_new_tokens_per_call": self.max_new_tokens_per_call,
            "max_model_invocations_including_repair": (
                self.max_model_invocations_including_repair
            ),
            "schema_only_repairs": self.schema_only_repairs,
            "semantic_repairs": self.semantic_repairs,
            "best_of_n": self.best_of_n,
            "tool_costs": dict(self.tool_costs),
        }


@dataclass
class BudgetLedger:
    """Mutable canonical action/cost/model-call ledger."""

    budget: CommonBudget = field(default_factory=CommonBudget)
    actions_used: int = 0
    cost_used: float = 0.0
    model_calls_used: int = 0
    schema_repairs_used: int = 0
    finalized: bool = False

    def charge_action(self, action: Mapping[str, Any]) -> None:
        tool = action.get("tool")
        if tool not in CANONICAL_TOOLS:
            raise StrongBaselineError("UNKNOWN_CANONICAL_TOOL")
        if self.finalized:
            raise StrongBaselineError("ACTION_AFTER_FINALIZE")
        if (
            self.actions_used + 1
            > self.budget.max_canonical_actions_including_finalize
        ):
            raise StrongBaselineError("ACTION_BUDGET_EXHAUSTED")
        if tool.startswith("search_"):
            top_k = action.get("arguments", {}).get("top_k")
            if top_k != self.budget.search_top_k:
                raise StrongBaselineError("SEARCH_TOP_K_NOT_FROZEN")
        charge = float(self.budget.tool_costs[tool])
        if self.cost_used + charge > self.budget.cost_limit + 1e-9:
            raise StrongBaselineError("COST_BUDGET_EXHAUSTED")
        self.actions_used += 1
        self.cost_used += charge
        if tool == "finalize":
            self.finalized = True

    def charge_model_call(self, *, schema_repair: bool = False) -> None:
        if (
            self.model_calls_used + 1
            > self.budget.max_model_invocations_including_repair
        ):
            raise StrongBaselineError("MODEL_CALL_BUDGET_EXHAUSTED")
        if schema_repair:
            if self.schema_repairs_used + 1 > self.budget.schema_only_repairs:
                raise StrongBaselineError("SCHEMA_REPAIR_BUDGET_EXHAUSTED")
            self.schema_repairs_used += 1
        self.model_calls_used += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "actions_used": self.actions_used,
            "actions_remaining": (
                self.budget.max_canonical_actions_including_finalize
                - self.actions_used
            ),
            "cost_used": round(self.cost_used, 6),
            "cost_remaining": round(
                self.budget.cost_limit - self.cost_used, 6
            ),
            "model_calls_used": self.model_calls_used,
            "model_calls_remaining": (
                self.budget.max_model_invocations_including_repair
                - self.model_calls_used
            ),
            "schema_repairs_used": self.schema_repairs_used,
            "finalized": self.finalized,
        }


PRIMARY_BINDINGS = {
    "direct_av": ModelBinding(
        repo_id="Qwen/Qwen2.5-Omni-7B",
        revision="ae9e1690543ffd5c0221dc27f79834d0294cba00",
        role="DIRECT_AV_MODEL",
    ),
    "controller": ModelBinding(
        repo_id="ibm-granite/granite-3.3-8b-instruct",
        revision="51dd4bc2ade4059a6bd87649d68aa11e4fb2529b",
        role="TOOL_CONTROLLER_BACKBONE",
    ),
    "finalizer": ModelBinding(
        repo_id="ibm-granite/granite-3.3-8b-instruct",
        revision="51dd4bc2ade4059a6bd87649d68aa11e4fb2529b",
        role="GROUNDED_FINALIZER",
    ),
}

FALLBACK_BINDINGS = {
    "direct_av": ModelBinding(
        repo_id="microsoft/Phi-4-multimodal-instruct",
        revision="93f923e1a7727d1c4f446756212d9d3e8fcc5d81",
        role="DIRECT_PACKED_AV_MODEL",
    ),
    "controller": ModelBinding(
        repo_id="Qwen/Qwen3-8B",
        revision="b968826d9c46dd6066d109eabc6255188de91218",
        role="TOOL_CONTROLLER_BACKBONE",
    ),
    "finalizer": ModelBinding(
        repo_id="Qwen/Qwen3-8B",
        revision="b968826d9c46dd6066d109eabc6255188de91218",
        role="GROUNDED_FINALIZER",
    ),
}
