"""Deterministic controls that can select actions but never substitute answers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import StrongBaselineError


@dataclass(frozen=True)
class DeterministicControlDecision:
    system_id: str
    action_index: int
    action: Mapping[str, Any]
    learned_system_substitute: bool = False
    final_answer: None = None


class DeterministicControl:
    """Simple independent control policy over a frozen public action menu."""

    def __init__(self, *, system_id: str, sufficiency_guard: bool) -> None:
        if system_id not in {"DET-REACT", "DET-SUFF"}:
            raise ValueError("unknown deterministic control")
        self.system_id = system_id
        self.sufficiency_guard = sufficiency_guard

    def choose_action(
        self,
        action_menu: Sequence[Mapping[str, Any]],
        *,
        observed_claim_count: int,
        required_claim_count: int,
    ) -> DeterministicControlDecision:
        if not action_menu:
            raise StrongBaselineError("DETERMINISTIC_ACTION_MENU_EMPTY")
        selected: int | None = None
        if self.sufficiency_guard and observed_claim_count >= required_claim_count:
            selected = next(
                (
                    index
                    for index, item in enumerate(action_menu)
                    if item.get("tool") == "finalize"
                ),
                None,
            )
        if selected is None:
            selected = next(
                (
                    index
                    for index, item in enumerate(action_menu)
                    if item.get("tool") != "finalize"
                ),
                None,
            )
        if selected is None:
            selected = 0
        return DeterministicControlDecision(
            system_id=self.system_id,
            action_index=selected,
            action=action_menu[selected],
        )

    @staticmethod
    def reject_learned_substitution(
        decision: DeterministicControlDecision, *, target_system_id: str
    ) -> None:
        if target_system_id not in {"DET-REACT", "DET-SUFF"}:
            raise StrongBaselineError(
                "DETERMINISTIC_CONTROL_CANNOT_SUBSTITUTE_LEARNED_RESULT",
                details={
                    "control_system_id": decision.system_id,
                    "target_system_id": target_system_id,
                },
            )
