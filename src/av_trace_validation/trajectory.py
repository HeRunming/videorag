"""Private-oracle validator planning and normative trajectory generation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from av_trace.util import sha256_json
from av_trace_mvp.backend import FixedBackend
from av_trace_mvp.experiment import EpisodeSession
from av_trace_mvp.index import GeneratedCorpus

from .graph import reachable_ses_ids


CAUSES = (
    "source_evidence_absent",
    "evidence_in_source_but_inaccessible",
    "evidence_accessible_but_not_found",
    "not_missing",
    "uncertain",
)
MODALITIES = ("vision", "speech", "ambient")


def evidence_ids_from_trajectory(
    family: Mapping[str, Any],
    trajectory: Mapping[str, Any],
) -> set[str]:
    hashes = {
        sha256_json({"evidence_id": item["evidence_id"]}): item["evidence_id"]
        for item in family["claim_evidence_graph"]["evidence_units"]
    }
    observed: set[str] = set()
    for event in trajectory["events"]:
        for result in event.get("response", {}).get("results", ()):
            if result.get("result_type") != "observation":
                continue
            for route_ref in result.get("payload", {}).get("_route_refs", ()):
                evidence_id = hashes.get(route_ref)
                if evidence_id is not None:
                    observed.add(evidence_id)
    return observed


def observation_ids_by_evidence(
    family: Mapping[str, Any],
    trajectory: Mapping[str, Any],
) -> dict[str, list[str]]:
    hashes = {
        sha256_json({"evidence_id": item["evidence_id"]}): item["evidence_id"]
        for item in family["claim_evidence_graph"]["evidence_units"]
    }
    result: dict[str, list[str]] = {item: [] for item in hashes.values()}
    for event in trajectory["events"]:
        for observation in event.get("response", {}).get("results", ()):
            if observation.get("result_type") != "observation":
                continue
            for route_ref in observation.get("payload", {}).get("_route_refs", ()):
                evidence_id = hashes.get(route_ref)
                if evidence_id is not None:
                    result[evidence_id].append(observation["observation_id"])
    return {key: sorted(set(value)) for key, value in result.items() if value}


def evidence_ids_from_observations(
    family: Mapping[str, Any],
    observations: Iterable[Mapping[str, Any]],
) -> set[str]:
    """Map private or redacted observations to graph evidence deterministically."""

    evidence = _evidence_map(family)
    hashes = {
        sha256_json({"evidence_id": evidence_id}): evidence_id
        for evidence_id in evidence
    }
    matched: set[str] = set()
    for observation in observations:
        route_refs = observation.get("payload", {}).get("_route_refs", ())
        matched.update(hashes[item] for item in route_refs if item in hashes)
        if route_refs:
            continue
        interval = observation.get("interval")
        modalities = set(observation.get("modalities", ()))
        for evidence_id, item in evidence.items():
            if item["modality"] not in modalities:
                continue
            if interval in item["intervals"]:
                matched.add(evidence_id)
    return matched


def _cause(kind: str) -> dict[str, float]:
    if kind == "not_missing":
        return {
            "source_evidence_absent": 0.01,
            "evidence_in_source_but_inaccessible": 0.01,
            "evidence_accessible_but_not_found": 0.01,
            "not_missing": 0.96,
            "uncertain": 0.01,
        }
    if kind == "inaccessible":
        return {
            "source_evidence_absent": 0.01,
            "evidence_in_source_but_inaccessible": 0.94,
            "evidence_accessible_but_not_found": 0.02,
            "not_missing": 0.01,
            "uncertain": 0.02,
        }
    return {
        "source_evidence_absent": 0.02,
        "evidence_in_source_but_inaccessible": 0.08,
        "evidence_accessible_but_not_found": 0.82,
        "not_missing": 0.02,
        "uncertain": 0.06,
    }


def _belief(
    *,
    sufficient: bool,
    missing_modalities: Iterable[str],
    missing_hops: Iterable[str],
    inaccessible: bool,
    rationale: str,
) -> dict[str, Any]:
    missing = set(missing_modalities)
    return {
        "p_sufficient": 0.98 if sufficient else 0.03,
        "verdict": "sufficient" if sufficient else "insufficient",
        "missing_modality_probabilities": {
            modality: 0.97 if modality in missing else 0.02
            for modality in MODALITIES
        },
        "missing_hop_types": [] if sufficient else sorted(set(missing_hops)),
        "missingness_cause_probabilities": _cause(
            "not_missing" if sufficient else ("inaccessible" if inaccessible else "not_found")
        ),
        "next_action_rationale": rationale[:240],
    }


def _episode(family: Mapping[str, Any], state_role: str) -> Mapping[str, Any]:
    return next(item for item in family["episodes"] if item["state_role"] == state_role)


def _evidence_map(family: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        item["evidence_id"]: item
        for item in family["claim_evidence_graph"]["evidence_units"]
    }


def _required_union(family: Mapping[str, Any]) -> list[str]:
    return sorted(
        {
            evidence_id
            for ses in family["claim_evidence_graph"]["accepted_sufficient_sets"]
            for evidence_id in ses["evidence_ids"]
        }
    )


def _missing_metadata(
    family: Mapping[str, Any],
    acquired: set[str],
) -> tuple[set[str], set[str]]:
    graph = family["claim_evidence_graph"]
    evidence = _evidence_map(family)
    candidate_missing = [
        set(ses["evidence_ids"]) - acquired
        for ses in graph["accepted_sufficient_sets"]
    ]
    best = min(candidate_missing, key=lambda item: (len(item), sorted(item)))
    modalities = {evidence[item]["modality"] for item in best}
    hop_ids = {
        hop_id
        for ses in graph["accepted_sufficient_sets"]
        if set(ses["evidence_ids"]) - acquired == best
        for hop_id in ses["hop_ids"]
    }
    hop_types = {
        hop["hop_type"] for hop in graph["hops"] if hop["hop_id"] in hop_ids
    }
    return modalities, hop_types


def _query_arguments(family: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    arguments = {
        "query": evidence["observation"],
        "top_k": 20,
        "time_range": {"start_s": 0.0, "end_s": family["source"]["duration_s"]},
        "exclude_result_ids": [],
    }
    if evidence["modality"] == "speech":
        arguments["speaker_hint"] = None
    return arguments


def observation_call(evidence: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    interval = deepcopy(evidence["intervals"][0])
    if evidence["modality"] == "speech":
        return (
            "read_transcript",
            {
                "interval": interval,
                "source": "asr",
                "include_word_timestamps": False,
            },
        )
    return (
        "inspect_clip",
        {
            "interval": interval,
            "include_video": evidence["modality"] == "vision",
            "include_audio": evidence["modality"] == "ambient",
        },
    )


def search_tool(modality: str) -> str:
    return {
        "vision": "search_visual",
        "speech": "search_speech",
        "ambient": "search_ambient_audio",
    }[modality]


def direct_route_cost(family: Mapping[str, Any], evidence_ids: Iterable[str]) -> float:
    episode = family["episodes"][0]
    evidence = _evidence_map(family)
    return sum(
        episode["budget"]["tool_costs"][observation_call(evidence[item])[0]]
        for item in evidence_ids
    )


def _ordered_evidence(family: Mapping[str, Any], validator_id: str) -> list[str]:
    evidence = _evidence_map(family)
    ids = _required_union(family)
    chronological = sorted(
        ids,
        key=lambda item: (
            evidence[item]["intervals"][0]["start_s"],
            item,
        ),
    )
    if validator_id.endswith("_b"):
        chronological.reverse()
    return chronological


def _trigger_calls(
    session: EpisodeSession,
    family: Mapping[str, Any],
    acquired: set[str],
    *,
    validator_id: str,
) -> None:
    restore = next(
        item
        for item in _episode(family, "RESTORED")["interventions"]
        if item["phase"] == "restoration"
    )
    spec = restore["restoration"]
    modalities, hops = _missing_metadata(family, acquired)
    belief = _belief(
        sufficient=False,
        missing_modalities=modalities,
        missing_hops=hops,
        inaccessible=True,
        rationale="Exercise the predeclared restoration trigger before evidence acquisition.",
    )
    if spec["trigger_type"] == "get_channel_status":
        channel = restore.get("affected_channel")
        channels = [channel] if channel else sorted(
            {
                {
                    "vision": "visual",
                    "speech": "speech",
                    "ambient": "ambient",
                }[_evidence_map(family)[item]["modality"]]
                for item in restore["affected_evidence_ids"]
            }
        )
        session.call("get_channel_status", {"channels": channels}, belief)
        return
    trigger_index = int(spec["trigger_value"])
    while len(session.responses) <= trigger_index:
        session.call(
            "get_channel_status",
            {"channels": ["clip"] if validator_id.endswith("_a") else ["transcript"]},
            belief,
        )


def _acquire(
    session: EpisodeSession,
    family: Mapping[str, Any],
    evidence_id: str,
    acquired: set[str],
    *,
    use_search: bool,
    inaccessible: bool,
) -> None:
    evidence = _evidence_map(family)[evidence_id]
    modalities, hops = _missing_metadata(family, acquired)
    belief = _belief(
        sufficient=bool(reachable_ses_ids(family["claim_evidence_graph"], acquired)),
        missing_modalities=modalities,
        missing_hops=hops,
        inaccessible=inaccessible,
        rationale=f"Acquire validator evidence route {evidence_id}.",
    )
    if use_search:
        session.call(
            search_tool(evidence["modality"]),
            _query_arguments(family, evidence),
            belief,
        )
    tool, arguments = observation_call(evidence)
    response = session.call(tool, arguments, belief)
    if response:
        acquired.update(
            evidence_ids_from_observations(
                family,
                (
                    result
                    for result in response.get("results", ())
                    if result.get("result_type") == "observation"
                ),
            )
        )


def _citations_for(
    family: Mapping[str, Any],
    session: EpisodeSession,
    evidence_ids: set[str],
) -> list[dict[str, Any]]:
    citations = []
    for observation in session.observations:
        routes = evidence_ids_from_observations(family, [observation])
        if not routes.intersection(evidence_ids):
            continue
        citations.append(
            {
                "observation_id": observation["observation_id"],
                "interval": deepcopy(observation["interval"]),
                "modalities": list(observation["modalities"]),
            }
        )
    return citations


def _finish(
    session: EpisodeSession,
    family: Mapping[str, Any],
    state_role: str,
    acquired: set[str],
) -> None:
    graph = family["claim_evidence_graph"]
    reachable = reachable_ses_ids(graph, acquired)
    if state_role == "BLOCKED":
        modalities, hops = _missing_metadata(family, acquired)
        belief = _belief(
            sufficient=False,
            missing_modalities=modalities,
            missing_hops=hops,
            inaccessible=True,
            rationale="No accepted SES is reachable; record the blocked access diagnosis.",
        )
        final = {
            "p_sufficient": belief["p_sufficient"],
            "verdict": "insufficient",
            "answer_mode": "abstain",
            "claims": [],
            "diagnosis": {
                "modality_probabilities": deepcopy(belief["missing_modality_probabilities"]),
                "hop_types": list(belief["missing_hop_types"]),
                "cause_probabilities": deepcopy(belief["missingness_cause_probabilities"]),
                "recovery_route_declared": False,
                "description": "Required source evidence exists but the registered route is inaccessible.",
            },
            "natural_language_answer": "",
            "termination_reason": "no_recovery_route",
        }
        session.finish(final, belief)
        return
    if not reachable:
        raise RuntimeError(f"Validator failed to acquire an SES in {state_role}.")
    claim_ids = family["answer_spec"]["required_claim_ids"]
    claims = []
    for index, claim_id in enumerate(claim_ids):
        claim = next(item for item in graph["claims"] if item["claim_id"] == claim_id)
        relevant_evidence = {
            evidence_id
            for ses in graph["accepted_sufficient_sets"]
            if claim_id in ses["claim_ids"] and ses["set_id"] in reachable
            for evidence_id in ses["evidence_ids"]
        }
        claims.append(
            {
                "claim_id": f"validator.claim.{index}",
                "registered_claim_id": claim_id,
                "text": claim["proposition"],
                "confidence": 0.99,
                "citations": _citations_for(family, session, relevant_evidence),
            }
        )
    belief = _belief(
        sufficient=True,
        missing_modalities=(),
        missing_hops=(),
        inaccessible=False,
        rationale="All required claims have an accepted citable SES.",
    )
    final = {
        "p_sufficient": belief["p_sufficient"],
        "verdict": "sufficient",
        "answer_mode": "answer",
        "claims": claims,
        "diagnosis": {
            "modality_probabilities": deepcopy(belief["missing_modality_probabilities"]),
            "hop_types": [],
            "cause_probabilities": deepcopy(belief["missingness_cause_probabilities"]),
            "recovery_route_declared": False,
            "description": "An accepted minimal sufficient evidence set was acquired.",
        },
        "natural_language_answer": family["answer_spec"]["display_answer"],
        "termination_reason": "sufficient_evidence",
    }
    session.finish(final, belief)


def generate_validator_trajectory(
    corpus: GeneratedCorpus,
    family: Mapping[str, Any],
    state_role: str,
    validator_id: str,
) -> dict[str, Any]:
    """Execute one oracle-assisted but protocol-valid validator trajectory."""

    backend = FixedBackend(
        deepcopy(dict(family)),
        state_role,
        corpus.index,
        corpus.manifest,
    )
    session = EpisodeSession(
        backend,
        family,
        state_role,
        f"validator-{validator_id}",
    )
    acquired: set[str] = set()
    evidence_order = _ordered_evidence(family, validator_id)
    restore = next(
        (
            item
            for item in _episode(family, "RESTORED")["interventions"]
            if item["phase"] == "restoration"
        ),
        None,
    )
    if (
        state_role == "RESTORED"
        and restore is not None
        and restore["restoration"]["trigger_type"] == "get_channel_status"
    ):
        _trigger_calls(
            session,
            family,
            acquired,
            validator_id=validator_id,
        )
    use_search = validator_id.endswith("_a")
    for evidence_id in evidence_order:
        _acquire(
            session,
            family,
            evidence_id,
            acquired,
            use_search=use_search,
            inaccessible=(
                state_role == "BLOCKED"
                or (
                    state_role == "RESTORED"
                    and not backend.interventions.snapshot.restored
                )
            ),
        )
    _finish(session, family, state_role, acquired)
    return session.trajectory()
