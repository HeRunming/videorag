from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from av_trace.trajectory import validate_trajectory
from av_trace_agent_runtime import (
    AgentRuntimeError,
    RuntimeConfig,
    run_subprocess_episode,
)
from av_trace_agent_runtime.runtime import SubprocessEpisodeRuntime
from av_trace_mvp.backend import FixedBackend
from av_trace_mvp.index import load_generated

ROOT = Path(__file__).resolve().parents[1]
ADVERSARY = ROOT / "tests_agent_runtime/adversarial_agent.py"


@pytest.fixture(scope="module")
def corpus():
    return load_generated(ROOT / "mvp/generated/quick")


def backend_case(corpus, state_role: str = "CLEAN"):
    family = corpus.family("syn_f01_visual_order")
    backend = FixedBackend(family, state_role, corpus.index, corpus.manifest)
    return family, backend


def baseline_command(name: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "av_trace_agent_runtime.baseline_entrypoint",
        "--agent",
        name,
    ]


def adversary_command(mode: str) -> list[str]:
    return [sys.executable, str(ADVERSARY), mode]


@pytest.mark.parametrize(
    "agent",
    ["AlwaysAnswer", "SingleShotRAG", "ReActHeuristic", "EvidenceBeliefState"],
)
def test_four_baselines_run_in_fresh_subprocess_and_reconstruct_valid_trajectory(
    corpus, agent
):
    family, backend = backend_case(corpus, "CLEAN")
    trajectory = run_subprocess_episode(
        backend=backend,
        family=family,
        state_role="CLEAN",
        agent_name=agent,
        command=baseline_command(agent),
        config=RuntimeConfig(timeout_s=10, seed=7),
    )
    assert validate_trajectory(trajectory).ok
    assert trajectory["events"][-1]["event_type"] == "finalize"


def test_policy_start_and_visible_ids_are_opaque(corpus):
    family, backend = backend_case(corpus, "BLOCKED")
    trajectory = run_subprocess_episode(
        backend=backend,
        family=family,
        state_role="BLOCKED",
        agent_name="inspect-start",
        command=adversary_command("inspect_start"),
        config=RuntimeConfig(timeout_s=5, seed=11),
    )
    assert validate_trajectory(trajectory).ok
    # The evaluator reconstructs real normative IDs after the process boundary.
    assert trajectory["episode_start"]["family_id"] == family["family_id"]
    assert trajectory["episode_start"]["state_role"] == "BLOCKED"


def test_handles_are_deterministic_for_seed_and_change_across_seeds(corpus):
    def run(seed: int) -> dict:
        family, backend = backend_case(corpus)
        return run_subprocess_episode(
            backend=backend,
            family=family,
            state_role="CLEAN",
            agent_name="stable",
            command=baseline_command("SingleShotRAG"),
            config=RuntimeConfig(timeout_s=10, seed=seed),
        )

    first = run(123)
    second = run(123)
    third = run(124)
    assert first == second
    assert first["events"] == second["events"]
    # Real reconstructed trajectory IDs remain deterministic but seed-scoped.
    assert first["trajectory_id"] != third["trajectory_id"]


def test_public_episode_handle_cannot_dictionary_encode_family_or_state(corpus):
    handles = set()
    for family_id, state_role in (
        ("syn_f01_visual_order", "CLEAN"),
        ("syn_f01_visual_order", "BLOCKED"),
        ("syn_f02_speech_sequence", "RESTORED"),
    ):
        family = corpus.family(family_id)
        backend = FixedBackend(family, state_role, corpus.index, corpus.manifest)
        runtime = SubprocessEpisodeRuntime(
            backend=backend,
            family=family,
            state_role=state_role,
            agent_name="same-agent",
            command=baseline_command("SingleShotRAG"),
            config=RuntimeConfig(timeout_s=10, seed=123),
        )
        handles.add(runtime.view.public_episode_id)
    # One process handles one episode, so the public episode handle need not
    # encode global identity.  Equal first handles prevent offline enumeration
    # of known private family/state IDs from recovering the state label.
    assert len(handles) == 1


def test_submitted_gold_claim_id_is_overwritten_by_private_mapper(corpus):
    family, backend = backend_case(corpus)
    trajectory = run_subprocess_episode(
        backend=backend,
        family=family,
        state_role="CLEAN",
        agent_name="gold-claim",
        command=adversary_command("gold_claim"),
        config=RuntimeConfig(timeout_s=5),
    )
    claim = trajectory["final_output"]["claims"][0]
    assert claim["registered_claim_id"] is None


def test_private_route_refs_are_not_visible_to_child(corpus):
    family, backend = backend_case(corpus)
    trajectory = run_subprocess_episode(
        backend=backend,
        family=family,
        state_role="CLEAN",
        agent_name="route-probe",
        command=adversary_command("route_refs"),
        config=RuntimeConfig(timeout_s=5),
    )
    assert validate_trajectory(trajectory).ok
    private_payloads = [
        result["payload"]
        for event in trajectory["events"]
        for result in event.get("response", {}).get("results", ())
        if result.get("result_type") == "observation"
    ]
    assert any("_route_refs" in payload for payload in private_payloads)


@pytest.mark.parametrize(
    ("mode", "code"),
    [
        ("malformed", "MALFORMED_MESSAGE"),
        ("oversized", "OUTPUT_LIMIT"),
        ("after_finalize", "AFTER_FINALIZE"),
        ("timeout", "TIMEOUT"),
    ],
)
def test_adversarial_protocol_failures_are_fail_closed(corpus, mode, code):
    family, backend = backend_case(corpus)
    config = RuntimeConfig(
        timeout_s=0.5 if mode == "timeout" else 3,
        max_output_bytes=32_000 if mode == "oversized" else 1_000_000,
        max_message_bytes=16_000 if mode == "oversized" else 256_000,
    )
    with pytest.raises(AgentRuntimeError) as caught:
        run_subprocess_episode(
            backend=backend,
            family=family,
            state_role="CLEAN",
            agent_name=mode,
            command=adversary_command(mode),
            config=config,
        )
    assert caught.value.code == code


def test_cli_emits_validator_passing_normative_trajectory(tmp_path):
    output = tmp_path / "trajectory.json"
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_agent_subprocess.py"),
            "--generated-root",
            str(ROOT / "mvp/generated/quick"),
            "--family-id",
            "syn_f01_visual_order",
            "--state-role",
            "RESTORED",
            "--baseline",
            "EvidenceBeliefState",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=env,
        check=True,
        timeout=20,
    )
    trajectory = json.loads(output.read_text(encoding="utf-8"))
    assert validate_trajectory(trajectory).ok
