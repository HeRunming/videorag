from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from av_trace.util import load_json

ROOT = Path(__file__).resolve().parents[1]


def fixture(relative: str) -> Any:
    return load_json(ROOT / relative)


def positive_family() -> dict[str, Any]:
    return fixture("docs/spec/fixtures/positive_episode_family.json")


def positive_manifest() -> dict[str, Any]:
    return fixture("docs/data/fixtures/positive_acquisition_manifest.json")


def positive_trajectory() -> dict[str, Any]:
    return fixture("docs/spec/fixtures/positive_trajectory.json")


def belief(
    *,
    p_sufficient: float = 0.2,
    verdict: str = "insufficient",
) -> dict[str, Any]:
    return {
        "p_sufficient": p_sufficient,
        "verdict": verdict,
        "missing_modality_probabilities": {
            "vision": 0.1,
            "speech": 0.8,
            "ambient": 0.1,
        },
        "missing_hop_types": ["speech_content"],
        "missingness_cause_probabilities": {
            "source_evidence_absent": 0.05,
            "evidence_in_source_but_inaccessible": 0.75,
            "evidence_accessible_but_not_found": 0.1,
            "not_missing": 0.05,
            "uncertain": 0.05,
        },
        "next_action_rationale": "Use the synthetic route.",
    }


def action(
    episode_id: str,
    step_index: int,
    tool: str,
    arguments: dict[str, Any],
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "protocol_version": "0.2.0",
        "episode_id": episode_id,
        "request_id": request_id or f"r{step_index}",
        "step_index": step_index,
        "belief_state": belief(),
        "action": {"tool": tool, "arguments": arguments},
    }


def records() -> dict[str, dict[str, Any]]:
    return {
        "e1": {
            "interval": {"start_s": 100.0, "end_s": 110.0},
            "modality": "speech",
            "payload": {"text": "A pressure drop caused the warning."},
        },
        "e2": {
            "interval": {"start_s": 112.0, "end_s": 120.0},
            "modality": "vision",
            "payload": {"description": "The operator closes the valve."},
        },
    }


def alternative_ses_family() -> dict[str, Any]:
    """Return a valid family with two alternative speech units in one group."""
    family = positive_family()
    graph = family["claim_evidence_graph"]
    e3 = deepcopy(graph["evidence_units"][0])
    e3["evidence_id"] = "e3"
    e3["intervals"] = [{"start_s": 130.0, "end_s": 140.0}]
    e3["observation"] = "A second speaker independently states that pressure dropped."
    graph["evidence_units"].append(e3)

    h3 = deepcopy(graph["hops"][0])
    h3["hop_id"] = "h3"
    h3["input_evidence_ids"] = ["e3"]
    graph["hops"].append(h3)
    graph["support_edges"].extend(
        [
            {
                "edge_id": "edge4",
                "relation": "supports_hop",
                "from_ids": ["e3"],
                "to_id": "h3",
            },
            {
                "edge_id": "edge5",
                "relation": "hop_supports_claim",
                "from_ids": ["h3", "h2"],
                "to_id": "c1",
            },
        ]
    )
    graph["accepted_sufficient_sets"].append(
        {
            "set_id": "ses2",
            "claim_ids": ["c1"],
            "evidence_ids": ["e3", "e2"],
            "hop_ids": ["h3", "h2"],
            "satisfiability_validated": True,
            "minimality_validated": True,
            "validator_ids": ["validator_a", "validator_b"],
        }
    )
    graph["necessity_groups"][0]["member_evidence_ids"] = ["e1", "e3"]
    graph["necessity_groups"][0]["required_hop_ids"] = ["h1", "h3"]
    for episode in family["episodes"]:
        if episode["state_role"] == "CLEAN":
            episode["initial_state"]["accessible_evidence_ids"] = ["e1", "e2", "e3"]
            episode["oracle"]["accepted_final_set_ids"] = ["ses1", "ses2"]
        else:
            episode["initial_state"]["accessible_evidence_ids"] = ["e2"]
            episode["interventions"][0]["affected_evidence_ids"] = ["e1", "e3"]
            episode["oracle"]["gold_missing_hop_ids"] = ["h1", "h3"]
            if episode["state_role"] == "RESTORED":
                episode["interventions"][1]["affected_evidence_ids"] = ["e1", "e3"]
                episode["oracle"]["accepted_final_set_ids"] = ["ses1", "ses2"]
    return family


def channel_outage_family() -> dict[str, Any]:
    family = positive_family()
    family["intervention_mechanism"] = "modality_channel_outage"
    clean, blocked, restored = family["episodes"]
    for episode in (blocked, restored):
        episode["initial_state"]["enabled_channels"].remove("speech")
        block = episode["interventions"][0]
        block["mechanism"] = "modality_channel_outage"
        block["affected_necessity_group_id"] = None
        block["affected_channel"] = "speech"
    restore = restored["interventions"][1]
    restore["mechanism"] = "modality_channel_outage"
    restore["affected_necessity_group_id"] = None
    restore["affected_channel"] = "speech"
    return family
