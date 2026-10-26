"""Learned generator and agent controllers using only a public state."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backend import FullTimelineBackend
from .process import ModelProcessError, QwenProcess
from .schema import (
    PublicSchemaError,
    controller_schema_prompt,
    finalization_schema_prompt,
    validate_controller_decision,
    validate_finalization,
)

PROMPT_ROOT = Path(__file__).with_name("prompts")


def prompt_text(name: str) -> str:
    return (PROMPT_ROOT / name).read_text(encoding="utf-8").strip()


def prompt_hashes() -> dict[str, str]:
    return {
        path.name: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(PROMPT_ROOT.glob("*.txt"))
    }


@dataclass(frozen=True)
class GenerationConfig:
    max_new_tokens: int = 512
    repair_max_new_tokens: int = 512
    max_public_history: int = 12


class LearnedCallFailure(RuntimeError):
    def __init__(self, code: str, details: Mapping[str, Any]) -> None:
        super().__init__(code)
        self.code = code
        self.details = dict(details)

    @property
    def attempts(self) -> tuple[dict[str, Any], ...]:
        """Return retained model attempts in generation order."""

        value = self.details.get("attempts", [])
        return tuple(dict(item) for item in value if isinstance(item, Mapping))

    def to_record(self) -> dict[str, Any]:
        """Return a persistence-safe typed failure and every retained attempt."""

        return {
            "code": self.code,
            "details": {
                **self.details,
                "attempts": [dict(item) for item in self.attempts],
            },
        }


def _generate_validated(
    model: QwenProcess,
    *,
    system_prompt: str,
    payload: Mapping[str, Any],
    validator: Callable[[Any], dict[str, Any]],
    config: GenerationConfig,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    current_system = system_prompt
    current_payload = dict(payload)
    for attempt in range(2):
        request_hash = "sha256:" + hashlib.sha256(
            json.dumps(
                {"system": current_system, "payload": current_payload},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        try:
            response = model.generate(
                system=current_system,
                payload=current_payload,
                max_new_tokens=(
                    config.max_new_tokens
                    if attempt == 0
                    else config.repair_max_new_tokens
                ),
            )
        except ModelProcessError as exc:
            attempts.append(
                {
                    "attempt": attempt,
                    "status": "process_error",
                    "request_hash": request_hash,
                    "system_prompt_sha256": "sha256:"
                    + hashlib.sha256(current_system.encode()).hexdigest(),
                    "raw_text": None,
                    "raw_sha256": None,
                    "prompt_tokens": None,
                    "generated_tokens": None,
                    "latency_seconds": None,
                    "peak_rss_kib": None,
                    "peak_rss_bytes": None,
                    "error_code": exc.code,
                    "error": str(exc),
                    "process_error": exc.to_record(),
                }
            )
            raise LearnedCallFailure(
                exc.code,
                {
                    "attempts": attempts,
                    "process_error": exc.to_record(),
                },
            ) from exc
        raw = str(response.get("raw_text", ""))
        record = {
            "attempt": attempt,
            "status": "generated",
            "request_hash": request_hash,
            "system_prompt_sha256": "sha256:"
            + hashlib.sha256(current_system.encode()).hexdigest(),
            "raw_sha256": "sha256:" + hashlib.sha256(raw.encode()).hexdigest(),
            "raw_text": raw,
            "prompt_tokens": response.get("prompt_tokens"),
            "generated_tokens": response.get("generated_tokens"),
            "latency_seconds": response.get("latency_seconds"),
            "peak_rss_kib": response.get("peak_rss_kib"),
            "peak_rss_bytes": response.get("peak_rss_bytes"),
        }
        try:
            parsed = response.get("parsed")
            if parsed is None:
                raise PublicSchemaError(
                    str(response.get("parse_error") or "MALFORMED_MODEL_JSON")
                )
            validated = validator(parsed)
        except PublicSchemaError as exc:
            record.update(
                {
                    "status": "invalid",
                    "validation_error": str(exc),
                    "validation_error_type": type(exc).__name__,
                }
            )
            attempts.append(record)
            if attempt == 1:
                raise LearnedCallFailure(
                    "MALFORMED_AFTER_REPAIR", {"attempts": attempts}
                ) from exc
            current_system = prompt_text("repair_v1.txt")
            current_payload = {
                "task": payload.get("task"),
                "policy": payload.get("policy"),
                "question": payload.get("question"),
                "output_schema": payload.get("output_schema"),
                "public_claim_slots": payload.get("public_claim_slots", []),
                "known_pointers": payload.get("known_pointers", []),
                "citable_observations": payload.get("citable_observations", []),
                "recent_public_events": payload.get("recent_public_events", []),
                "remaining_budget": payload.get("remaining_budget"),
                "response_template": payload.get("response_template"),
                "allowed_claim_handles": [
                    item.get("claim_handle")
                    for item in payload.get("public_claim_slots", [])
                ],
                "allowed_pointer_ids": [
                    item.get("pointer_id")
                    for item in payload.get("known_pointers", [])
                ],
                "allowed_observation_ids": [
                    item.get("observation_id")
                    for item in payload.get("citable_observations", [])
                ],
                "invalid_response": raw,
                "validation_error": str(exc),
            }
            continue
        record["status"] = "valid"
        attempts.append(record)
        return validated, attempts
    raise AssertionError("unreachable")


def run_grounded_generator(
    model: QwenProcess,
    *,
    question: str,
    claim_slots: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    condition: str,
    config: GenerationConfig | None = None,
) -> dict[str, Any]:
    cfg = config or GenerationConfig()
    claim_handles = {item["claim_handle"] for item in claim_slots}
    observation_ids = {item["observation_id"] for item in observations}
    payload = {
        "task": "grounded_finalization",
        "question": question,
        "public_claim_slots": claim_slots,
        "citable_observations": observations,
        "allowed_modalities": ["vision", "speech", "ambient"],
        "allowed_hops": [
            "entity_identity",
            "event_detection",
            "speech_content",
            "ambient_event",
            "temporal_order",
            "cross_modal_binding",
            "causal_link",
            "state_change",
            "comparison",
            "counting",
            "other",
        ],
        "allowed_missingness_causes": [
            "source_evidence_absent",
            "evidence_in_source_but_inaccessible",
            "evidence_accessible_but_not_found",
            "not_missing",
            "uncertain",
        ],
        "output_schema": finalization_schema_prompt(
            claim_handles=sorted(claim_handles),
            observation_ids=sorted(observation_ids),
        ),
        "response_template": {
            "verdict": "insufficient",
            "answer_text": "",
            "asserted_claims": [],
            "claim_to_citations": {},
            "missing_modalities": ["speech"],
            "missing_hops": ["other"],
            "missingness_cause": "uncertain",
            "p_sufficient": 0.1,
            "recovery_intent": "Acquire the missing evidence.",
            "stop_rationale": "Required evidence is not yet available.",
        },
    }
    final, attempts = _generate_validated(
        model,
        system_prompt=prompt_text("generator_v1.txt"),
        payload=payload,
        validator=lambda value: validate_finalization(
            value,
            claim_handles=claim_handles,
            observation_ids=observation_ids,
        ),
        config=cfg,
    )
    return {"final": final, "model_calls": attempts}


def _public_history(events: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return events[-limit:]


def _action_menu(
    *,
    question: str,
    pointers: Mapping[str, Mapping[str, Any]],
    observations: Mapping[str, Mapping[str, Any]],
    available_tools: set[str],
    turn: int,
    no_progress_rounds: int,
    remaining_steps: int | None = None,
    remaining_cost: float | None = None,
    tool_costs: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    # A model may spend the early budget exploring, but the last available
    # action is reserved for model-authored finalization. This is a protocol
    # budget guard, not a deterministic answer substitution: Qwen still writes
    # the final verdict, claims, citations, and diagnosis.
    if turn >= 9 or no_progress_rounds >= 2 or (remaining_steps is not None and remaining_steps <= 1):
        return [{"type": "finalize"}]
    costs = dict(tool_costs or {})

    def affordable(tool: str) -> bool:
        if remaining_cost is None:
            return True
        return float(costs.get(tool, 0.0)) <= remaining_cost + 1e-9

    menu: list[dict[str, Any]] = []
    observed_pointer_ids = {
        str(item.get("source_pointer_id"))
        for item in observations.values()
        if item.get("source_pointer_id")
    }
    for pointer_id in list(pointers)[:3]:
        modality = str(pointers[pointer_id].get("modality", ""))
        observation_tool = "read_transcript" if modality == "speech" else "inspect_clip"
        if pointer_id not in observed_pointer_ids and affordable(observation_tool):
            menu.append({"type": "observe", "pointer_id": pointer_id})
    if not menu:
        for modality, tool in (
            ("speech", "search_speech"),
            ("ambient", "search_ambient_audio"),
            ("vision", "search_visual"),
        ):
            if tool not in available_tools or not affordable(tool):
                continue
            menu.extend(
                [
                    {
                        "type": "search",
                        "modality": modality,
                        "query": question,
                        "top_k": 5,
                    },
                    {
                        "type": "search",
                        "modality": modality,
                        "query": f"{question} {modality} supporting evidence",
                        "top_k": 5,
                    },
                ]
            )
    if "get_channel_status" in available_tools and affordable("get_channel_status"):
        for modality in ("speech", "ambient", "vision"):
            menu.append({"type": "status", "modalities": [modality]})
    if observations or turn >= 2 or not menu:
        menu.append({"type": "finalize"})
    return menu


def run_controller_decision(
    model: QwenProcess,
    *,
    policy: str,
    turn: int,
    question: str,
    claim_slots: list[dict[str, Any]],
    available_tools: list[str],
    remaining_budget: Mapping[str, Any],
    known_pointers: list[dict[str, Any]],
    citable_observations: list[dict[str, Any]],
    recent_public_events: list[dict[str, Any]],
    action_menu: list[dict[str, Any]],
    no_progress_rounds: int = 0,
    config: GenerationConfig | None = None,
) -> dict[str, Any]:
    """Run one model-authored controller turn against an explicit public menu."""

    if policy not in {"react", "evidence_sufficiency"}:
        raise ValueError("unknown learned policy")
    cfg = config or GenerationConfig()
    claim_handles = {item["claim_handle"] for item in claim_slots}
    pointer_ids = {item["pointer_id"] for item in known_pointers}
    observation_ids = {
        item["observation_id"] for item in citable_observations
    }
    payload = {
        "task": "choose_next_action",
        "policy": policy,
        "turn": turn,
        "question": question,
        "public_claim_slots": claim_slots,
        "available_tools": available_tools,
        "remaining_budget": dict(remaining_budget),
        "known_pointers": known_pointers,
        "citable_observations": citable_observations,
        "recent_public_events": recent_public_events,
        "no_progress_rounds": no_progress_rounds,
        "output_schema": controller_schema_prompt(action_menu),
        "response_template": {
            "public_state": {
                "p_sufficient": 0.1,
                "covered_claim_handles": [],
                "missing_modalities": ["speech"],
                "missing_hops": ["speech_content"],
                "missingness_cause": "evidence_accessible_but_not_found",
                "recovery_intent": "Search speech evidence.",
            },
            "action_index": 0,
        },
    }

    def validate_turn(value: Any) -> dict[str, Any]:
        decision = validate_controller_decision(
            value,
            claim_handles=claim_handles,
            pointer_ids=pointer_ids,
            observation_ids=observation_ids,
            available_tools=set(available_tools),
            action_menu=action_menu,
        )
        action = decision["action"]
        if action["type"] == "search":
            signature = (
                action["modality"],
                " ".join(action["query"].casefold().split()),
            )
            prior_signatures = {
                (
                    str(event["action"].get("modality")),
                    " ".join(
                        str(event["action"].get("query", ""))
                        .casefold()
                        .split()
                    ),
                )
                for event in recent_public_events
                if event.get("action", {}).get("type") == "search"
            }
            observed_pointer_ids = {
                str(event.get("action", {}).get("pointer_id"))
                for event in recent_public_events
                if event.get("action", {}).get("type") == "observe"
            }
            if (
                signature in prior_signatures
                and pointer_ids - observed_pointer_ids
            ):
                raise PublicSchemaError(
                    "REPEATED_SEARCH_WITH_UNOBSERVED_POINTERS"
                )
        return decision

    decision, attempts = _generate_validated(
        model,
        system_prompt=prompt_text(
            "react_v1.txt" if policy == "react" else "sufficiency_v1.txt"
        ),
        payload=payload,
        validator=validate_turn,
        config=cfg,
    )
    return {
        "decision": decision,
        "model_calls": attempts,
        "public_payload": payload,
    }


def run_learned_agent(
    model: QwenProcess,
    *,
    backend: FullTimelineBackend,
    policy: str,
    config: GenerationConfig | None = None,
) -> dict[str, Any]:
    if policy not in {"react", "evidence_sufficiency"}:
        raise ValueError("unknown learned policy")
    cfg = config or GenerationConfig()
    start = backend.public_start()
    pointers: dict[str, dict[str, Any]] = {}
    observations: dict[str, dict[str, Any]] = {}
    public_events: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    final: dict[str, Any] | None = None
    terminal_error: dict[str, Any] | None = None
    no_progress_rounds = 0
    for turn in range(start["budget"]["max_steps"]):
        snapshot = backend.snapshot()
        action_menu = _action_menu(
            question=start["question"],
            pointers=pointers,
            observations=observations,
            available_tools=set(start["available_tools"]),
            turn=turn,
            no_progress_rounds=no_progress_rounds,
            remaining_steps=snapshot["remaining_steps"],
            remaining_cost=snapshot["remaining_cost"],
            tool_costs=start["tool_costs"],
        )
        try:
            generated_decision = run_controller_decision(
                model,
                policy=policy,
                turn=turn,
                question=start["question"],
                claim_slots=start["claim_slots"],
                available_tools=start["available_tools"],
                remaining_budget={
                    "steps": snapshot["remaining_steps"],
                    "cost": snapshot["remaining_cost"],
                    "tool_costs": start["tool_costs"],
                },
                known_pointers=list(pointers.values()),
                citable_observations=list(observations.values()),
                recent_public_events=_public_history(
                    public_events, cfg.max_public_history
                ),
                action_menu=action_menu,
                no_progress_rounds=no_progress_rounds,
                config=cfg,
            )
        except LearnedCallFailure as exc:
            calls.extend(exc.details.get("attempts", []))
            terminal_error = {"code": exc.code, "turn": turn}
            break
        decision = generated_decision["decision"]
        attempts = generated_decision["model_calls"]
        calls.extend(attempts)
        action = decision["action"]
        observations_before = len(observations)
        event: dict[str, Any] = {
            "turn": turn,
            "public_state": decision["public_state"],
            "action": action,
        }
        try:
            if action["type"] == "search":
                response = backend.search(
                    action["modality"], action["query"], action["top_k"]
                )
                for item in response.get("results", []):
                    pointers[item["pointer_id"]] = item
            elif action["type"] == "observe":
                response = backend.observe(action["pointer_id"])
                observation = response.get("observation")
                if isinstance(observation, Mapping):
                    public_observation = dict(observation)
                    public_observation["source_pointer_id"] = action["pointer_id"]
                    observations[str(observation["observation_id"])] = public_observation
            elif action["type"] == "status":
                response = backend.status(action["modalities"])
            else:
                try:
                    generated = run_grounded_generator(
                        model,
                        question=start["question"],
                        claim_slots=start["claim_slots"],
                        observations=list(observations.values()),
                        condition="agent_finalization",
                        config=cfg,
                    )
                except LearnedCallFailure as exc:
                    calls.extend(exc.details.get("attempts", []))
                    terminal_error = {
                        "code": exc.code,
                        "turn": turn,
                        "phase": "grounded_finalization",
                    }
                    event["response"] = {
                        "status": "typed_failure",
                        "code": exc.code,
                    }
                    public_events.append(event)
                    break
                calls.extend(generated["model_calls"])
                final = generated["final"]
                response = backend.finalize(final)
                event["response"] = response
                public_events.append(event)
                break
        except RuntimeError as exc:
            terminal_error = {"code": str(exc), "turn": turn}
            event["response"] = {"status": "over_budget", "code": str(exc)}
            public_events.append(event)
            break
        event["response"] = response
        public_events.append(event)
        no_progress_rounds = (
            0 if len(observations) > observations_before
            else no_progress_rounds + 1
        )
    if final is None and terminal_error is None:
        terminal_error = {"code": "NO_FINALIZATION_WITHIN_STEP_LIMIT"}
    return {
        "policy": policy,
        "actual_learned_model": True,
        "public_start": start,
        "events": public_events,
        "final": final,
        "terminal_error": terminal_error,
        "model_calls": calls,
        "backend_snapshot": backend.snapshot(),
    }
