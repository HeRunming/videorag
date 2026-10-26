"""Deterministic offline baselines using only blind task inputs and tool results.

The policies intentionally avoid episode ``state_role``, intervention metadata,
claim/evidence graphs, accepted sufficient sets, and oracle labels.  They see a
question, budgets/tool names, search pointers, citable observations, and typed
tool failures.  Registered claim IDs are attached later by the evaluator's
frozen exact-text mapper.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


MODALITIES = ("vision", "speech", "ambient")
CAUSES = (
    "source_evidence_absent",
    "evidence_in_source_but_inaccessible",
    "evidence_accessible_but_not_found",
    "not_missing",
    "uncertain",
)

_MODALITY_QUERY_TERMS = {
    "vision": "visual visible shape symbol arrow appeared shown",
    "speech": "speech spoken says code instruction announcement report status units bin route",
    "ambient": "ambient sound audio bell pulse machine motor click confirmation chime",
}


class AgentSession(Protocol):
    """Blind, backend-independent surface exposed to deterministic agents."""

    start: Mapping[str, Any]

    @property
    def observations(self) -> Sequence[Mapping[str, Any]]: ...

    @property
    def responses(self) -> Sequence[Mapping[str, Any]]: ...

    def can_call(self, tool: str) -> bool: ...

    def call(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        belief_state: Mapping[str, Any],
    ) -> Mapping[str, Any] | None: ...

    def finish(
        self,
        final_answer: Mapping[str, Any],
        belief_state: Mapping[str, Any],
    ) -> None: ...


def _question(session: AgentSession) -> str:
    return str(session.start["question"])


def _relevant_modalities(question: str) -> tuple[str, ...]:
    text = question.casefold()
    selected: list[str] = []
    if any(word in text for word in ("shape", "symbol", "arrow", "visible")):
        selected.append("vision")
    if any(
        word in text
        for word in (
            "spoken",
            "instruction",
            "announced",
            "inspector",
            "report",
            "status",
            "units",
            "code",
            "bin",
            "route",
        )
    ):
        selected.append("speech")
    if any(
        word in text
        for word in ("ambient", "sound", "bell", "pulse", "machine", "motor", "click", "chime")
    ):
        selected.append("ambient")
    return tuple(selected or MODALITIES)


def _expected_observations(question: str) -> int:
    # Every MVP question asks for two linked facts. This rule is deliberately
    # question-format based rather than family-annotation based.
    return 2 if " and " in question.casefold() else 1


def _observation_counts(session: AgentSession) -> dict[str, int]:
    counts = {modality: 0 for modality in MODALITIES}
    for observation in session.observations:
        for modality in observation.get("modalities", ()):
            if modality in counts:
                counts[modality] += 1
    return counts


def _is_sufficient(session: AgentSession) -> bool:
    question = _question(session)
    relevant = _relevant_modalities(question)
    counts = _observation_counts(session)
    unique_observations = {
        item.get("observation_id") for item in session.observations
    }
    return (
        len(unique_observations) >= _expected_observations(question)
        and all(counts[modality] >= 1 for modality in relevant)
    )


def _missing_modalities(session: AgentSession) -> set[str]:
    counts = _observation_counts(session)
    relevant = _relevant_modalities(_question(session))
    missing = {modality for modality in relevant if counts[modality] == 0}
    unique_observations = {
        item.get("observation_id") for item in session.observations
    }
    if not missing and len(unique_observations) < _expected_observations(_question(session)):
        missing.update(relevant)
    return missing


def _saw_unavailable(session: AgentSession) -> bool:
    return any(response.get("status") == "channel_unavailable" for response in session.responses)


def _used_status(session: AgentSession) -> bool:
    return any(response.get("tool") == "get_channel_status" for response in session.responses)


def _cause_distribution(kind: str) -> dict[str, float]:
    distributions = {
        "not_missing": {
            "source_evidence_absent": 0.01,
            "evidence_in_source_but_inaccessible": 0.01,
            "evidence_accessible_but_not_found": 0.01,
            "not_missing": 0.96,
            "uncertain": 0.01,
        },
        "always_answer": {
            "source_evidence_absent": 0.02,
            "evidence_in_source_but_inaccessible": 0.03,
            "evidence_accessible_but_not_found": 0.04,
            "not_missing": 0.88,
            "uncertain": 0.03,
        },
        "not_found": {
            "source_evidence_absent": 0.05,
            "evidence_in_source_but_inaccessible": 0.18,
            "evidence_accessible_but_not_found": 0.67,
            "not_missing": 0.03,
            "uncertain": 0.07,
        },
        "typed_unavailable": {
            "source_evidence_absent": 0.01,
            "evidence_in_source_but_inaccessible": 0.90,
            "evidence_accessible_but_not_found": 0.03,
            "not_missing": 0.01,
            "uncertain": 0.05,
        },
        "status_checked_missing": {
            "source_evidence_absent": 0.02,
            "evidence_in_source_but_inaccessible": 0.80,
            "evidence_accessible_but_not_found": 0.10,
            "not_missing": 0.02,
            "uncertain": 0.06,
        },
    }
    return dict(distributions[kind])


def _missing_hop_types(session: AgentSession) -> list[str]:
    question = _question(session).casefold()
    hops: set[str] = set()
    missing = _missing_modalities(session)
    if "vision" in missing:
        hops.add("event_detection")
    if "speech" in missing:
        hops.add("speech_content")
    if "ambient" in missing:
        hops.add("ambient_event")
    if any(word in question for word in ("first", "later", "then", "early")):
        hops.add("temporal_order")
    if len(_relevant_modalities(question)) > 1:
        hops.add("cross_modal_binding")
    return sorted(hops)


def _belief(
    session: AgentSession,
    *,
    style: str,
    rationale: str,
) -> dict[str, Any]:
    sufficient = _is_sufficient(session)
    missing = _missing_modalities(session)
    if style == "always":
        p_sufficient = 0.90
        verdict = "sufficient"
        cause = _cause_distribution("always_answer")
        modality_probabilities = {modality: 0.08 for modality in MODALITIES}
        hop_types: list[str] = []
    elif sufficient:
        p_sufficient = {"single": 0.90, "react": 0.92, "belief": 0.96}[style]
        verdict = "sufficient"
        cause = _cause_distribution("not_missing")
        modality_probabilities = {modality: 0.02 for modality in MODALITIES}
        hop_types = []
    else:
        base = {"single": 0.10, "react": 0.08, "belief": 0.05}[style]
        p_sufficient = min(0.40, base + (0.15 if session.observations else 0.0))
        verdict = "uncertain" if style == "react" else "insufficient"
        if _saw_unavailable(session):
            cause = _cause_distribution("typed_unavailable")
        elif _used_status(session):
            cause = _cause_distribution("status_checked_missing")
        else:
            cause = _cause_distribution("not_found")
        low, high = (0.06, 0.88) if style == "belief" else (0.12, 0.72)
        modality_probabilities = {
            modality: high if modality in missing else low for modality in MODALITIES
        }
        hop_types = _missing_hop_types(session) if style == "belief" else []
    return {
        "p_sufficient": p_sufficient,
        "verdict": verdict,
        "missing_modality_probabilities": modality_probabilities,
        "missing_hop_types": hop_types,
        "missingness_cause_probabilities": cause,
        "next_action_rationale": rationale[:240],
    }


def _search_tool(modality: str) -> str:
    return {
        "vision": "search_visual",
        "speech": "search_speech",
        "ambient": "search_ambient_audio",
    }[modality]


def _search_query(question: str, modality: str) -> str:
    """Build a query from public question text plus modality-generic terms."""

    return f"{question} {_MODALITY_QUERY_TERMS[modality]}"[:500]


def _retrieve_modality(session: AgentSession, modality: str, *, style: str) -> None:
    search_tool = _search_tool(modality)
    if not session.can_call(search_tool):
        return
    response = session.call(
        search_tool,
        {
            "query": _search_query(_question(session), modality),
            "top_k": 20,
            "time_range": {"start_s": 0.0, "end_s": float(session.start["video_duration_s"])},
            "exclude_result_ids": [],
            **({"speaker_hint": None} if modality == "speech" else {}),
        },
        _belief(session, style=style, rationale=f"Search the likely {modality} route from the question."),
    )
    if not response:
        return
    pointers = [
        item for item in response.get("results", ()) if item.get("result_type") == "search_pointer"
    ]
    for pointer in pointers:
        if modality == "speech":
            tool = "read_transcript"
            arguments = {
                "interval": dict(pointer["interval"]),
                "source": "asr",
                "include_word_timestamps": False,
            }
        else:
            tool = "inspect_clip"
            arguments = {
                "interval": dict(pointer["interval"]),
                "include_video": modality == "vision",
                "include_audio": modality == "ambient",
            }
        if not session.can_call(tool):
            return
        session.call(
            tool,
            arguments,
            _belief(session, style=style, rationale="Inspect a returned pointer to obtain citable evidence."),
        )


def _retrieve_relevant(session: AgentSession, *, style: str) -> None:
    for modality in _relevant_modalities(_question(session)):
        _retrieve_modality(session, modality, style=style)


def _retrieve_missing(session: AgentSession, *, style: str) -> None:
    for modality in sorted(_missing_modalities(session)):
        _retrieve_modality(session, modality, style=style)


def _payload_text(observation: Mapping[str, Any]) -> str:
    payload = observation.get("payload", {})
    values = [
        payload.get("text"),
        payload.get("description"),
        payload.get("audio_event"),
    ]
    return " ".join(str(value) for value in values if isinstance(value, str))


def _ordered_text(session: AgentSession) -> list[str]:
    unique = {
        item["observation_id"]: item for item in session.observations
    }
    observations = sorted(
        unique.values(),
        key=lambda item: (item["interval"]["start_s"], item["observation_id"]),
    )
    return [_payload_text(item) for item in observations]


def _answer_text(session: AgentSession) -> str:
    """Synthesize fixture task forms from observed, not pre-enumerated, values."""

    question = _question(session).casefold()
    joined = " | ".join(_ordered_text(session))
    upper = joined.upper()
    shapes = [
        f"{color.lower()} {shape.lower()}"
        for color, shape in re.findall(
            r"\b([A-Z][A-Z0-9_-]*)\s+(TRIANGLE|CIRCLE|SQUARE|STAR|HEXAGON)\b",
            upper,
        )
    ]
    if "which shape appeared first" in question and len(shapes) >= 2:
        return f"The {shapes[0]} appeared first; the {shapes[1]} appeared later."
    if "what code was spoken" in question:
        code = re.search(r"CODE IS ([A-Z0-9_-]+(?: [A-Z0-9_-]+){0,3})", upper)
        instruction = re.search(r"SAYS ([A-Z0-9_-]+(?: [A-Z0-9_-]+){0,3})", upper)
        if code and instruction:
            return f"The code was {code.group(1)}, and the later instruction was {instruction.group(1)}."
    if "bell pulses" in question and shapes:
        count = re.search(r"\b([A-Z0-9_-]+) BELL PULSES\b", upper)
        if count:
            return f"{count.group(1).title()} bell pulses sounded, and a {shapes[-1]} appeared later."
    if "visible symbol" in question and shapes:
        bin_match = re.search(r"BIN ([A-Z0-9_-]+)", upper)
        if bin_match:
            return f"A {shapes[0]} was shown, and the later instruction named bin {bin_match.group(1).lower()}."
    if "which route was announced" in question:
        route = re.search(r"ROUTE ([A-Z0-9_-]+)", upper)
        direction = re.search(r"POINTS ([A-Z0-9_-]+)", upper)
        if route and direction:
            return f"Route {route.group(1)} was announced, and the matching arrow pointed {direction.group(1).lower()}."
    if "ambient machine sound" in question:
        sound = re.search(r"\b([A-Z0-9_-]+ MOTOR HUM)\b", upper)
        clicks = re.search(r"\b([A-Z0-9_-]+) CLICK PULSES\b", upper)
        if sound and clicks:
            return (
                f"A {sound.group(1).lower()} occurred, and "
                f"{clicks.group(1).lower()} click pulses sounded later."
            )
    if "ambient confirmation" in question and shapes:
        chime = re.search(r"\b([A-Z0-9_-]+ CONFIRMATION CHIME)\b", upper)
        if chime:
            return (
                f"An {shapes[0]} was shown early, and a "
                f"{chime.group(1).lower()} sounded later."
            )
    if "how many units" in question:
        units = re.search(r"SAYS ([A-Z0-9_-]+) UNITS", upper)
        status = re.search(r"STATUS ([A-Z0-9_-]+)", upper)
        if units and status:
            return f"The inspector reported {units.group(1).lower()} units and later reported status {status.group(1)}."
    return "Insufficient observed evidence."


def _citations(session: AgentSession) -> list[dict[str, Any]]:
    unique = {
        item["observation_id"]: item for item in session.observations
    }
    return [
        {
            "observation_id": item["observation_id"],
            "interval": dict(item["interval"]),
            "modalities": list(item["modalities"]),
        }
        for item in sorted(
            unique.values(),
            key=lambda value: (value["interval"]["start_s"], value["observation_id"]),
        )
    ]


def _finish(session: AgentSession, *, style: str, force_answer: bool = False) -> None:
    sufficient = _is_sufficient(session)
    belief = _belief(
        session,
        style=style,
        rationale="Answer from citable observations." if sufficient else "The observed evidence is incomplete.",
    )
    answer = _answer_text(session)
    claims = []
    if sufficient or force_answer:
        claims = [
            {
                "claim_id": "agent.claim",
                "registered_claim_id": None,
                "text": answer,
                "confidence": 0.90 if sufficient else 0.82,
                "citations": _citations(session),
            }
        ]
    if force_answer:
        belief["p_sufficient"] = 0.90
        belief["verdict"] = "sufficient"
    final = {
        "p_sufficient": belief["p_sufficient"],
        "verdict": belief["verdict"],
        "answer_mode": "answer" if claims else "abstain",
        "claims": claims,
        "diagnosis": {
            "modality_probabilities": dict(belief["missing_modality_probabilities"]),
            "hop_types": list(belief["missing_hop_types"]),
            "cause_probabilities": dict(belief["missingness_cause_probabilities"]),
            "recovery_route_declared": False,
            "description": "Observed evidence is sufficient." if sufficient else "A requested evidence route remains unavailable or unfound.",
        },
        "natural_language_answer": answer if claims else "",
        "termination_reason": "sufficient_evidence" if sufficient or force_answer else "no_recovery_route",
    }
    session.finish(final, belief)


@dataclass(frozen=True)
class DeterministicAgent:
    name: str

    def run(self, session: AgentSession) -> None:
        raise NotImplementedError


class AlwaysAnswerAgent(DeterministicAgent):
    def __init__(self) -> None:
        super().__init__("AlwaysAnswer")

    def run(self, session: AgentSession) -> None:
        _retrieve_relevant(session, style="always")
        _finish(session, style="always", force_answer=True)


class SingleShotRAGAgent(DeterministicAgent):
    def __init__(self) -> None:
        super().__init__("SingleShotRAG")

    def run(self, session: AgentSession) -> None:
        _retrieve_relevant(session, style="single")
        _finish(session, style="single")


class ReActHeuristicAgent(DeterministicAgent):
    def __init__(self) -> None:
        super().__init__("ReActHeuristic")

    def run(self, session: AgentSession) -> None:
        _retrieve_relevant(session, style="react")
        if not _is_sufficient(session) and _saw_unavailable(session) and session.can_call("get_channel_status"):
            channels = sorted(
                {"visual" if item == "vision" else item for item in _missing_modalities(session)}
            )
            session.call(
                "get_channel_status",
                {"channels": channels or ["clip"]},
                _belief(session, style="react", rationale="A typed outage warrants a status check."),
            )
            _retrieve_missing(session, style="react")
        _finish(session, style="react")


class EvidenceBeliefStateAgent(DeterministicAgent):
    def __init__(self) -> None:
        super().__init__("EvidenceBeliefState")

    def run(self, session: AgentSession) -> None:
        _retrieve_relevant(session, style="belief")
        if not _is_sufficient(session) and session.can_call("get_channel_status"):
            channels = sorted(
                {"visual" if item == "vision" else item for item in _missing_modalities(session)}
            )
            if "speech" in channels:
                channels.append("transcript")
            session.call(
                "get_channel_status",
                {"channels": channels or ["clip"]},
                _belief(session, style="belief", rationale="Probe the operational status of the missing route."),
            )
            _retrieve_missing(session, style="belief")
        _finish(session, style="belief")


DEFAULT_AGENTS: tuple[DeterministicAgent, ...] = (
    AlwaysAnswerAgent(),
    SingleShotRAGAgent(),
    ReActHeuristicAgent(),
    EvidenceBeliefStateAgent(),
)
