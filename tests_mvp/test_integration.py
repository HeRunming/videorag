from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path

from av_trace.schemas import SchemaRegistry
from av_trace_mvp.agents import DeterministicAgent
from av_trace_mvp.backend import FixedBackend
from av_trace_mvp.experiment import run_agent_episode
from av_trace_mvp.integration import run_all
from av_trace_mvp.index import BackendManifest, FixedIndex, load_generated

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = SchemaRegistry(ROOT)


def test_agents_do_not_reference_hidden_or_gold_fields() -> None:
    source = (ROOT / "src/av_trace_mvp/agents.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {
        "state_role",
        "oracle",
        "claim_evidence_graph",
        "accepted_sufficient_sets",
        "necessity_groups",
    }
    string_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not forbidden.intersection(string_literals)


def test_full_workflow_is_reproducible_and_uses_frozen_backend(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    first_results = tmp_path / "first"
    second_results = tmp_path / "second"
    first = run_all(
        repository_root=ROOT,
        generated_root=generated,
        results_root=first_results,
        seed=20260905,
        bootstrap_samples=25,
        bootstrap_seed=7,
        probe=False,
    )
    second = run_all(
        repository_root=ROOT,
        generated_root=generated,
        results_root=second_results,
        seed=20260905,
        bootstrap_samples=25,
        bootstrap_seed=7,
        probe=False,
    )
    assert first["counts"]["agent_episodes"] == 96
    assert first["counts"]["valid_trajectories"] == 96
    assert first["hashes"] == second["hashes"]
    assert (generated / "backend_manifest.json").is_file()
    assert (generated / "backend_index.json").is_file()
    corpus = load_generated(generated)
    assert corpus.manifest.root == generated
    assert len(corpus.index.records) >= 16
    assert json.loads((first_results / "validation.json").read_text())["status"] == "PASS"


def test_cli_exposes_required_commands() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_mvp.py"), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    for command in ("generate", "validate", "run", "all"):
        assert command in completed.stdout


@dataclass(frozen=True)
class ResponseProbeAgent(DeterministicAgent):
    captured: list[dict]

    def __init__(self, captured: list[dict]) -> None:
        object.__setattr__(self, "name", "ResponseProbe")
        object.__setattr__(self, "captured", captured)

    def run(self, session) -> None:
        response = session.call(
            "get_channel_status",
            {"channels": ["visual"]},
            {
                "p_sufficient": 0.1,
                "verdict": "insufficient",
                "missing_modality_probabilities": {"vision": 0.8, "speech": 0.1, "ambient": 0.1},
                "missing_hop_types": [],
                "missingness_cause_probabilities": {
                    "source_evidence_absent": 0.1,
                    "evidence_in_source_but_inaccessible": 0.6,
                    "evidence_accessible_but_not_found": 0.1,
                    "not_missing": 0.1,
                    "uncertain": 0.1,
                },
                "next_action_rationale": "Probe response visibility.",
            },
        )
        self.captured.append(dict(response))
        final = {
            "p_sufficient": 0.1,
            "verdict": "insufficient",
            "answer_mode": "abstain",
            "claims": [],
            "diagnosis": {
                "modality_probabilities": {"vision": 0.8, "speech": 0.1, "ambient": 0.1},
                "hop_types": [],
                "cause_probabilities": {
                    "source_evidence_absent": 0.1,
                    "evidence_in_source_but_inaccessible": 0.6,
                    "evidence_accessible_but_not_found": 0.1,
                    "not_missing": 0.1,
                    "uncertain": 0.1,
                },
                "recovery_route_declared": True,
                "description": "Probe only.",
            },
            "natural_language_answer": "",
            "termination_reason": "no_recovery_route",
        }
        session.finish(final, {
            "p_sufficient": final["p_sufficient"],
            "verdict": final["verdict"],
            "missing_modality_probabilities": final["diagnosis"]["modality_probabilities"],
            "missing_hop_types": [],
            "missingness_cause_probabilities": final["diagnosis"]["cause_probabilities"],
            "next_action_rationale": "Finalize probe.",
        })


def test_agent_visible_tool_response_uses_opaque_episode_handle() -> None:
    family = json.loads(
        (ROOT / "docs/spec/fixtures/positive_episode_family.json").read_text()
    )
    records = [
        {
            "record_id": "opaque1",
            "family_id": None,
            "asset_id": family["source"]["asset_id"],
            "modality": unit["modality"],
            "interval": unit["intervals"][0],
            "payload": {"description": unit["observation"]},
            "search_text": unit["observation"],
            "preview": "candidate",
            "route_evidence_ids": [unit["evidence_id"]],
            "is_distractor": False,
            "transcript_sources": ["asr"] if unit["modality"] == "speech" else [],
        }
        for unit in family["claim_evidence_graph"]["evidence_units"][:1]
    ]
    records.append({
        **records[0],
        "record_id": "opaque2",
        "modality": "vision",
        "interval": family["claim_evidence_graph"]["evidence_units"][1]["intervals"][0],
        "payload": {"description": family["claim_evidence_graph"]["evidence_units"][1]["observation"]},
        "search_text": family["claim_evidence_graph"]["evidence_units"][1]["observation"],
        "route_evidence_ids": ["e2"],
        "transcript_sources": [],
    })
    index = FixedIndex.from_records(records)
    manifest = BackendManifest.for_index(index, family["episodes"][0]["budget"]["tool_costs"])
    for episode in family["episodes"]:
        episode["backend"]["index_hash"] = index.index_hash
        episode["backend"]["backend_version"] = manifest.backend_version
    captured: list[dict] = []
    trajectory = run_agent_episode(
        ResponseProbeAgent(captured),
        FixedBackend(deepcopy(family), "BLOCKED", index, manifest, REGISTRY),
        family,
        "BLOCKED",
    )
    assert captured[0]["episode_id"] == "episode"
    assert all(
        "_route_refs" not in result.get("payload", {})
        for result in captured[0]["results"]
    )
    assert trajectory["events"][0]["response"]["episode_id"].endswith(".blocked")
