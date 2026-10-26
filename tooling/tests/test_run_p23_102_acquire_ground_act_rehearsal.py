from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = (
    ROOT / "scripts/run_p23_102_acquire_ground_act_rehearsal.py"
)
SPEC = importlib.util.spec_from_file_location(
    "p23_102_rehearsal_runner", RUNNER_PATH
)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


class MockBackend:
    def __init__(
        self,
        *,
        mechanism: str = "SILENT_ROUTE_WITHHOLDING",
        arm: str = "R",
        empty_search: bool = False,
        fail_on_search: bool = False,
    ) -> None:
        self.mechanism = mechanism
        self.arm = arm
        self.empty_search = empty_search
        self.fail_on_search = fail_on_search
        self.budget = {"max_steps": 10, "cost_limit": 12.0}
        self.costs = dict(RUNNER.FIXED_BUDGET["tool_costs"])
        self.steps_used = 0
        self.cost_used = 0.0
        self.restored = arm == "C"
        self.triggered = False
        self.events: list[dict[str, Any]] = []
        self.pointer_private: dict[str, dict[str, Any]] = {}
        self.observation_private: dict[str, dict[str, Any]] = {}
        self.evidence_by_observation: dict[str, list[str]] = {}

    def clone(self) -> MockBackend:
        return copy.deepcopy(self)

    def apply_exogenous_restoration(self) -> None:
        self.restored = True
        self.triggered = True

    def pack_accessible_observations(
        self, token_cap: int
    ) -> list[dict[str, Any]]:
        del token_cap
        if not self.restored:
            return []
        observation = {
            "observation_id": "obs.direct",
            "modality": "vision",
            "interval": {"start_s": 0.0, "end_s": 1.0},
            "content": "direct evidence",
            "citable": True,
        }
        self.observation_private["obs.direct"] = observation
        self.evidence_by_observation["obs.direct"] = [
            "evidence.vision"
        ]
        return [observation]

    def public_start(self) -> dict[str, Any]:
        return {
            "question": "What happened?",
            "claim_slots": [
                {
                    "claim_handle": "slot.c01",
                    "description": "The event.",
                }
            ],
            "available_tools": [
                "search_visual",
                "search_speech",
                "search_ambient_audio",
                "inspect_clip",
                "read_transcript",
                "get_channel_status",
                "finalize",
            ],
            "budget": dict(self.budget),
            "tool_costs": dict(self.costs),
            "remaining_steps": 10,
            "remaining_cost": 12.0,
            "video_duration_s": 30.0,
        }

    def _charge(self, tool: str) -> None:
        self.steps_used += 1
        self.cost_used += self.costs[tool]

    def search(
        self, modality: str, query: str, top_k: int
    ) -> dict[str, Any]:
        if self.fail_on_search:
            raise RuntimeError("TOOL_TIMEOUT")
        tool = {
            "vision": "search_visual",
            "speech": "search_speech",
            "ambient": "search_ambient_audio",
        }[modality]
        self._charge(tool)
        if (
            self.mechanism == "EXPLICIT_CHANNEL_OUTAGE"
            and not self.restored
        ):
            response = {
                "status": "unavailable",
                "error": {
                    "code": "REGISTERED_ROUTE_CHANNEL_UNAVAILABLE",
                    "retryable": self.arm == "R",
                },
            }
        elif self.empty_search:
            response = {"status": "not_found", "results": []}
        else:
            pointer_id = f"ptr.{modality}"
            self.pointer_private[pointer_id] = {
                "modality": modality,
                "record_id": f"record.{modality}",
            }
            response = {
                "status": "ok",
                "results": [
                    {
                        "pointer_id": pointer_id,
                        "modality": modality,
                        "preview": "candidate",
                    }
                ],
            }
        self.events.append(
            {
                "tool": tool,
                "request": {"query": query, "top_k": top_k},
                "response": response,
            }
        )
        return response

    def observe(self, pointer_id: str) -> dict[str, Any]:
        modality = pointer_id.removeprefix("ptr.")
        tool = (
            "read_transcript"
            if modality == "speech"
            else "inspect_clip"
        )
        self._charge(tool)
        if not self.restored:
            response = {
                "status": (
                    "unavailable"
                    if self.mechanism
                    == "EXPLICIT_CHANNEL_OUTAGE"
                    else "access_failure"
                ),
                "error": {
                    "code": (
                        "REGISTERED_ROUTE_CHANNEL_UNAVAILABLE"
                        if self.mechanism
                        == "EXPLICIT_CHANNEL_OUTAGE"
                        else "ROUTE_INACCESSIBLE"
                    ),
                    "retryable": self.arm == "R",
                },
            }
        else:
            observation_id = f"obs.{modality}"
            observation = {
                "observation_id": observation_id,
                "modality": modality,
                "interval": {"start_s": 0.0, "end_s": 1.0},
                "content": "mock evidence",
                "citable": True,
            }
            self.observation_private[observation_id] = observation
            self.evidence_by_observation[observation_id] = [
                f"evidence.{modality}"
            ]
            response = {
                "status": "ok",
                "observation": observation,
            }
        self.events.append(
            {
                "tool": tool,
                "request": {"pointer_id": pointer_id},
                "response": response,
            }
        )
        return response

    def status(self, modalities: list[str]) -> dict[str, Any]:
        self._charge("get_channel_status")
        response = {
            "status": "ok",
            "channels": {
                modality: {
                    "status": (
                        "available"
                        if self.restored
                        else "unavailable"
                    ),
                    "retryable": self.arm == "R",
                }
                for modality in modalities
            },
        }
        self.events.append(
            {
                "tool": "get_channel_status",
                "request": {"modalities": modalities},
                "response": response,
            }
        )
        return response

    def snapshot(self) -> dict[str, Any]:
        return {
            "remaining_steps": 10 - self.steps_used,
            "remaining_cost": 12.0 - self.cost_used,
            "triggered": self.triggered,
            "suppressed_segment_ids": (
                [] if self.restored else ["record.route"]
            ),
            "known_pointer_ids": sorted(self.pointer_private),
            "known_observation_ids": sorted(
                self.observation_private
            ),
        }

    def finalize(
        self, final: Mapping[str, Any]
    ) -> dict[str, Any]:
        self._charge("finalize")
        return {
            "status": "finalized",
            "verdict": final["verdict"],
        }


class MockModel:
    def __init__(
        self,
        actions: list[int] | None = None,
        *,
        malformed: bool = False,
    ) -> None:
        self.actions = list(actions or [])
        self.malformed = malformed
        self.calls = 0
        self.payloads: list[dict[str, Any]] = []

    def generate(
        self,
        *,
        system: str,
        payload: Mapping[str, Any],
        max_new_tokens: int,
    ) -> dict[str, Any]:
        del system, max_new_tokens
        self.calls += 1
        self.payloads.append(copy.deepcopy(dict(payload)))
        if self.malformed:
            parsed: Any = {"bad": "shape"}
            raw = json.dumps(parsed)
        elif payload["task"] == "choose_next_action":
            action_index = (
                self.actions.pop(0)
                if self.actions
                else 0
            )
            parsed = {
                "public_state": {
                    "p_sufficient": 0.1,
                    "covered_claim_handles": [],
                    "missing_modalities": ["vision"],
                    "missing_hops": ["event_detection"],
                    "missingness_cause": (
                        "evidence_accessible_but_not_found"
                    ),
                    "recovery_intent": "Acquire evidence.",
                },
                "action_index": action_index,
            }
            raw = json.dumps(parsed)
        else:
            observations = list(
                payload["citable_observations"]
            )
            if observations:
                observation_id = observations[0][
                    "observation_id"
                ]
                handle = payload["public_claim_slots"][0][
                    "claim_handle"
                ]
                parsed = {
                    "verdict": "answer",
                    "answer_text": "mock answer",
                    "asserted_claims": [
                        {
                            "claim_handle": handle,
                            "text": "mock evidence",
                            "citations": [observation_id],
                        }
                    ],
                    "claim_to_citations": {
                        handle: [observation_id]
                    },
                    "missing_modalities": [],
                    "missing_hops": [],
                    "missingness_cause": "not_missing",
                    "p_sufficient": 0.9,
                    "recovery_intent": "No recovery needed.",
                    "stop_rationale": (
                        "The acquired evidence supports the answer."
                    ),
                }
            else:
                parsed = {
                    "verdict": "insufficient",
                    "answer_text": "",
                    "asserted_claims": [],
                    "claim_to_citations": {},
                    "missing_modalities": ["vision"],
                    "missing_hops": ["event_detection"],
                    "missingness_cause": (
                        "evidence_in_source_but_inaccessible"
                    ),
                    "p_sufficient": 0.1,
                    "recovery_intent": "Acquire evidence.",
                    "stop_rationale": "Evidence is unavailable.",
                }
            raw = json.dumps(parsed)
        return {
            "raw_text": raw,
            "parsed": parsed,
            "parse_error": None,
            "prompt_tokens": 10,
            "generated_tokens": 10,
            "latency_seconds": 0.01,
            "peak_rss_kib": 1,
            "peak_rss_bytes": 1024,
        }


def test_validate_only_is_ready_but_execute_is_unauthorized() -> None:
    report = RUNNER.validate_repository(ROOT)
    assert report["validation_status"] == "READY"
    assert report["execution_authorized"] is False
    assert report["model_or_media_execution_performed"] is False
    assert report["qwen_agent_competence"] == (
        "LEARNED_AGENT_INCOMPLETE"
    )
    assert {
        "QWEN15_AGENT_COMPETENCE_NOT_READY",
        "BUNDLE_SEMANTICS_MACHINE_PROVISIONAL_NOT_ACCEPTED_SES",
        "GATE_A_NOT_ESTABLISHED",
        "HUMAN_FAMILY_VALIDITY_NOT_ESTABLISHED",
    } <= set(report["execution_authorization_reasons"])
    assert all(value is False for value in report["claims"].values())
    assert report["bundle_provenance_firewall"]["status"] == "PASS"
    assert report["runtime_leakage_classifier"]["status"] == (
        "NOT_RUN_EXECUTION_UNAUTHORIZED"
    )
    assert report["runner_attestation"]["status"] == (
        "REPAIR_NOT_ATTESTED"
    )


def test_plan_has_exact_rows_arms_mechanisms_and_prefix_pairs() -> None:
    plan = RUNNER.build_plan(ROOT)
    assert plan["assignment_count"] == 640
    assert {
        row["system_id"] for row in plan["assignments"]
    } == set(RUNNER.SYSTEMS)
    assert {row["arm"] for row in plan["assignments"]} == set(
        RUNNER.ARMS
    )
    assert {
        row["mechanism"] for row in plan["assignments"]
    } == set(RUNNER.MECHANISMS)
    groups: dict[tuple[str, str, str], set[str]] = {}
    for row in plan["assignments"]:
        key = (
            row["family_id"],
            row["mechanism"],
            row["system_id"],
        )
        groups.setdefault(key, set()).add(row["arm"])
        assert row["checkpoint_action_index_zero_based"] == 4
        assert row["fixed_budget"] == RUNNER.FIXED_BUDGET
    assert all(arms == set(RUNNER.ARMS) for arms in groups.values())
    sequence_counts: dict[tuple[str, ...], int] = {}
    for key in groups:
        row = next(
            item
            for item in plan["assignments"]
            if (
                item["family_id"],
                item["mechanism"],
                item["system_id"],
            )
            == key
        )
        sequence = tuple(row["order_sequence"])
        sequence_counts[sequence] = (
            sequence_counts.get(sequence, 0) + 1
        )
    assert sorted(sequence_counts.values()) == [40, 40, 40, 40]
    direct_rn = [
        row
        for row in plan["assignments"]
        if row["system_id"] == "direct_long_context"
        and row["arm"] in {"R", "N"}
    ]
    assert all(
        row["assignment_status"]
        == "STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT"
        and row["itt_retained"] is False
        and row["synthetic_outcome_created"] is False
        for row in direct_rn
    )


def test_rn_prefix_is_exact_and_restoration_occurs_after_four_cycles() -> None:
    prefix = RUNNER.run_blocked_prefix(
        MockBackend(arm="R"),
        system_id="single_shot_rag",
    )
    assert [row["action_index"] for row in prefix.events] == [
        0,
        1,
        2,
        3,
    ]
    r_state, n_state, pair = RUNNER.fork_restoration_pair(
        prefix
    )
    assert pair["prefix_hash_r"] == pair["prefix_hash_n"]
    assert pair["prefix_identical"] is True
    assert pair["checkpoint_identical"] is True
    assert pair["event_opportunity_reached"] is True
    assert pair["restoration_applied_r"] is True
    assert pair["restoration_applied_n"] is False
    assert r_state.backend.restored is True
    assert n_state.backend.restored is False
    assert r_state.events == n_state.events
    assert r_state.events[:-1] == prefix.events
    assert r_state.events[-1] == {
        "action_index": 4,
        "event": RUNNER.CHECKPOINT_EVENT,
        "remaining_budget": {
            "remaining_steps": 6,
            "remaining_cost": 7.0,
        },
    }
    assert pair["prefix_byte_length_r"] == pair[
        "prefix_byte_length_n"
    ]


def test_no_trigger_stays_blocked_after_checkpoint() -> None:
    prefix = RUNNER.run_blocked_prefix(
        MockBackend(arm="R"),
        system_id="single_shot_rag",
    )
    r_state, n_state, _ = RUNNER.fork_restoration_pair(prefix)
    pointer_id = next(iter(prefix.pointers))
    assert r_state.backend.observe(pointer_id)["status"] == "ok"
    assert n_state.backend.observe(pointer_id)["status"] in {
        "access_failure",
        "unavailable",
    }
    assert n_state.backend.triggered is False


def test_silent_and_explicit_mechanisms_are_separate() -> None:
    silent = MockBackend(
        mechanism="SILENT_ROUTE_WITHHOLDING",
        arm="B",
    )
    explicit = MockBackend(
        mechanism="EXPLICIT_CHANNEL_OUTAGE",
        arm="B",
    )
    silent_response = silent.search("vision", "q", 5)
    explicit_response = explicit.search("vision", "q", 5)
    assert silent_response["status"] == "ok"
    assert (
        explicit_response["error"]["code"]
        == "REGISTERED_ROUTE_CHANNEL_UNAVAILABLE"
    )
    aggregate = RUNNER._aggregate(
        [
            {
                "mechanism": mechanism,
                "arm": arm,
                "itt_retained": True,
                "structurally_ineligible": False,
                "completion_status": "COMPLETED_VALID",
                "supported_answer_endpoint": 0.0,
            }
            for mechanism in RUNNER.MECHANISMS
            for arm in ("R", "N")
        ]
    )
    assert aggregate["mechanisms_pooled"] is False
    assert set(aggregate["itt"]) == set(RUNNER.MECHANISMS)


def test_public_surface_is_sanitized_and_blocked_status_is_invariant() -> None:
    prefixes = [
        RUNNER.run_blocked_prefix(
            MockBackend(
                mechanism="EXPLICIT_CHANNEL_OUTAGE",
                arm=arm,
            ),
            system_id="single_shot_rag",
        )
        for arm in ("B", "R", "N")
    ]
    assert prefixes[0].events == prefixes[1].events == prefixes[2].events
    serialized = json.dumps(prefixes[0].events, sort_keys=True)
    for forbidden in (
        "triggered",
        "suppressed_segment_ids",
        "known_pointer_ids",
        "known_observation_ids",
    ):
        assert forbidden not in serialized
    assert all(
        set(event["remaining_budget"])
        == {"remaining_steps", "remaining_cost"}
        for event in prefixes[0].events
    )


def test_c_and_b_early_finalize_is_valid_endpoint_not_checkpoint_failure() -> None:
    for arm in ("C", "B"):
        state = RUNNER.run_blocked_prefix(
            MockBackend(arm=arm),
            system_id="learned_react",
            model=MockModel(actions=[4]),
            checkpoint_required=False,
        )
        assert state.final is not None
        assert state.failure is None
        assert state.terminal is True


def test_no_progress_rounds_are_forwarded_and_force_finalize_menu() -> None:
    model = MockModel(actions=[0, 0, 0])
    state = RUNNER.run_blocked_prefix(
        MockBackend(arm="R", empty_search=True),
        system_id="learned_react",
        model=model,
    )
    controller_payloads = [
        row
        for row in model.payloads
        if row["task"] == "choose_next_action"
    ]
    assert [
        row["no_progress_rounds"] for row in controller_payloads
    ] == [0, 1, 2]
    assert state.terminal is True
    assert state.failure["code"] == (
        "EARLY_TERMINAL_BEFORE_CHECKPOINT"
    )


def test_malformed_controller_attempts_are_retained() -> None:
    state = RUNNER.run_blocked_prefix(
        MockBackend(arm="R"),
        system_id="learned_react",
        model=MockModel(malformed=True),
    )
    assert state.failure["code"] == "MALFORMED_AFTER_REPAIR"
    assert len(state.model_calls) == 2
    assert all(row["raw_text"] for row in state.model_calls)
    assert state.factor_outputs[-1]["status"] == "typed_failure"


def test_direct_context_chronological_modality_round_robin_packing() -> None:
    backend = RUNNER.P23FullTimelineBackendAdapter.__new__(
        RUNNER.P23FullTimelineBackendAdapter
    )
    backend.evidence_rows = [
        {
            "start_us": 2_000_000,
            "end_us": 3_000_000,
            "modality": "vision",
            "record_id": "v2",
            "evidence_handle_id": "eh.v2",
        },
        {
            "start_us": 1_000_000,
            "end_us": 2_000_000,
            "modality": "ambient_audio",
            "record_id": "a1",
            "evidence_handle_id": "eh.a1",
        },
        {
            "start_us": 1_000_000,
            "end_us": 2_000_000,
            "modality": "vision",
            "record_id": "v1",
            "evidence_handle_id": "eh.v1",
        },
    ]
    backend.suppressed = set()
    backend.observation_private = {}
    backend.evidence_by_observation = {}
    backend.scale_index = {
        "modalities": {
            "siglip2_visual": {
                "documents": [
                    {"segment_id": "v1"},
                    {"segment_id": "v2"},
                ]
            },
            "speech": {"documents": []},
            "clap_audio": {
                "documents": [{"segment_id": "a1"}]
            },
        }
    }
    packed = backend.pack_accessible_observations(100)
    assert [
        (row["interval"]["start_s"], row["modality"])
        for row in packed
    ] == [(1.0, "vision"), (1.0, "ambient"), (2.0, "vision")]


def test_single_shot_rrf_is_equal_weight_frozen_and_selects_fused_order() -> None:
    events = [
        {
            "action": {"type": "search", "modality": modality},
            "response": {"results": results},
        }
        for modality, results in (
            (
                "vision",
                [
                    {
                        "pointer_id": "v.shared",
                        "interval": {"start_s": 1, "end_s": 2},
                    },
                    {
                        "pointer_id": "v.only",
                        "interval": {"start_s": 3, "end_s": 4},
                    },
                ],
            ),
            (
                "speech",
                [
                    {
                        "pointer_id": "s.shared",
                        "interval": {"start_s": 1, "end_s": 2},
                    }
                ],
            ),
            (
                "ambient",
                [
                    {
                        "pointer_id": "a.shared",
                        "interval": {"start_s": 1, "end_s": 2},
                    }
                ],
            ),
        )
    ]
    selected, fusion = RUNNER._rrf_selected_pointer_ids(events)
    assert selected[:3] == ["v.shared", "s.shared", "a.shared"]
    assert fusion[0]["modalities"] == [
        "ambient",
        "speech",
        "vision",
    ]
    assert fusion[0]["rrf_score"] == pytest.approx(3 / 61)


def test_early_terminal_and_typed_failure_keep_rn_in_itt() -> None:
    early_model = MockModel(actions=[4])
    prefix = RUNNER.run_blocked_prefix(
        MockBackend(arm="R"),
        system_id="learned_react",
        model=early_model,
    )
    assert prefix.terminal is True
    assert prefix.failure["code"] == (
        "EARLY_TERMINAL_BEFORE_CHECKPOINT"
    )
    r_state, n_state, pair = RUNNER.fork_restoration_pair(
        prefix
    )
    assert pair["early_terminal_copied_to_both"] is True
    assert pair["itt_retained_r"] is True
    assert pair["itt_retained_n"] is True
    assert r_state.failure == n_state.failure

    failed = RUNNER.run_blocked_prefix(
        MockBackend(arm="R", fail_on_search=True),
        system_id="single_shot_rag",
    )
    assert failed.failure["code"] == "TOOL_ACCESS_FAILURE"
    assert failed.failure["positive_endpoint"] == 0.0


def test_citations_require_acquired_observation_ids() -> None:
    observations = {
        "obs.vision": {
            "observation_id": "obs.vision",
            "modality": "vision",
        }
    }
    valid = {
        "asserted_claims": [
            {
                "claim_handle": "slot.c01",
                "text": "claim",
                "citations": ["obs.vision"],
            }
        ],
        "claim_to_citations": {
            "slot.c01": ["obs.vision"]
        },
    }
    invalid = copy.deepcopy(valid)
    invalid["asserted_claims"][0]["citations"] = [
        "ptr.vision"
    ]
    invalid["claim_to_citations"]["slot.c01"] = [
        "ptr.vision"
    ]
    assert RUNNER.validate_citations(
        valid, observations
    )["valid"]
    result = RUNNER.validate_citations(
        invalid, observations
    )
    assert result["valid"] is False
    assert result["unknown_observation_ids"] == [
        "ptr.vision"
    ]


def test_write_outputs_includes_raw_factor_hash_and_failure_files(
    tmp_path: Path,
) -> None:
    assignment = {
        "assignment_id": "a1",
        "family_id": "f1",
        "mechanism": "SILENT_ROUTE_WITHHOLDING",
        "system_id": "single_shot_rag",
        "arm": "R",
        "itt_retained": True,
        "assignment_status": "ASSIGNED_ITT",
        "expected_evidence_handle_ids": ["evidence.vision"],
    }
    state = RUNNER.PrefixState(
        backend=MockBackend(arm="R"),
        start={"question": "q"},
        pointers={},
        observations={},
        events=[],
        model_calls=[],
        factor_outputs=[],
        failure=RUNNER._typed_failure(
            "MODEL_TIMEOUT", phase="controller"
        ),
    )
    trajectory = RUNNER._trajectory(assignment, state)
    metric = RUNNER._metric_record(assignment, state)
    output = tmp_path / "run"
    RUNNER.write_run_outputs(
        output,
        plan={"assignments": [assignment]},
        trajectories=[trajectory],
        model_calls=[
            {
                "assignment_id": "a1",
                "raw_text": "raw",
                "status": "generated",
            }
        ],
        factor_outputs=[
            {
                "assignment_id": "a1",
                "phase": "controller",
                "public_state": {},
            }
        ],
        prefix_pairs=[],
        metric_rows=[metric],
        failures=[
            {
                "assignment_id": "a1",
                "code": "MODEL_TIMEOUT",
                "itt_retained": True,
            }
        ],
        run_manifest={
            "run_id": "test",
            "testing_injection": True,
            "bundle_provenance_firewall": {"status": "PASS"},
            "no_deterministic_answer_substitution": True,
        },
    )
    assert {
        path.name for path in output.iterdir()
    } == set(RUNNER.REQUIRED_OUTPUTS)
    replay = json.loads(
        (output / "replay_manifest.json").read_text()
    )
    assert replay["no_deterministic_answer_substitution"]
    inventory = json.loads(
        (output / "file_inventory.json").read_text()
    )
    assert all(
        row["sha256"].startswith("sha256:")
        for row in inventory["files"]
    )
    failure = json.loads(
        (output / "failure_ledger.jsonl").read_text()
    )
    assert failure["itt_retained"] is True
    assert failure["assignment_id"] == "a1"
    assert failure["failure"]["code"] == "MODEL_TIMEOUT"
    assert metric["supported_answer_endpoint"] == 0.0
    manifest = json.loads(
        (output / "run_manifest.json").read_text()
    )
    assert manifest["assignment_count"] == 1
    assert manifest["completion_ledger_row_count"] == 1
    assert manifest["execution_authorized"] is False
    assert manifest["machine_provisional_non_scientific"] is True
    assert manifest["bundle_provenance_firewall"]["status"] == "PASS"
    assert manifest["runtime_leakage_classifier"]["status"] == (
        "NOT_RUN_TEST_INJECTION"
    )


def test_metric_ready_fields_are_mechanical_not_hardcoded() -> None:
    assignment = {
        "assignment_id": "a-metric",
        "family_id": "f1",
        "mechanism": "SILENT_ROUTE_WITHHOLDING",
        "system_id": "single_shot_rag",
        "arm": "C",
        "itt_retained": True,
        "assignment_status": "ASSIGNED_ITT",
        "expected_evidence_handle_ids": ["evidence.vision"],
    }
    backend = MockBackend(arm="C")
    observation = backend.observe("ptr.vision")["observation"]
    state = RUNNER.PrefixState(
        backend=backend,
        start={"question": "q"},
        pointers={},
        observations={
            observation["observation_id"]: observation
        },
        events=[],
        model_calls=[],
        factor_outputs=[],
        final={
            "verdict": "answer",
            "answer_text": "supported",
            "asserted_claims": [
                {
                    "claim_handle": "slot.c01",
                    "text": "supported",
                    "citations": [observation["observation_id"]],
                }
            ],
            "claim_to_citations": {
                "slot.c01": [observation["observation_id"]]
            },
        },
    )
    metric = RUNNER._metric_record(assignment, state)
    assert metric["supported_answer_endpoint"] == 1.0
    assert metric["acquire"]["evidence_recall"] == 1.0
    assert metric["acquire"]["all_evidence_success"] == 1.0
    assert metric["ground"]["citation_f1"] == 1.0
    assert metric["ground"]["supported_claim_rate"] == 1.0
    assert metric["tool_cost"]["steps_used"] == 1
    assert metric["tool_cost"]["cost_used"] == 2.0


def test_write_outputs_rejects_missing_or_duplicate_terminal_rows(
    tmp_path: Path,
) -> None:
    assignment = {
        "assignment_id": "a1",
        "family_id": "f1",
        "mechanism": "SILENT_ROUTE_WITHHOLDING",
        "system_id": "single_shot_rag",
        "arm": "B",
        "itt_retained": True,
        "assignment_status": "ASSIGNED_ITT",
    }
    with pytest.raises(
        RUNNER.RehearsalError,
        match="INCOMPLETE_ASSIGNMENT_TERMINAL_LEDGER",
    ):
        RUNNER.write_run_outputs(
            tmp_path / "bad",
            plan={"assignments": [assignment]},
            trajectories=[],
            model_calls=[],
            factor_outputs=[],
            prefix_pairs=[],
            metric_rows=[],
            failures=[],
            run_manifest={"run_id": "bad"},
        )


def test_execute_without_injected_mocks_fails_closed() -> None:
    with pytest.raises(
        RUNNER.RehearsalError,
        match="QWEN15_AGENT_COMPETENCE_NOT_READY",
    ) as raised:
        RUNNER.execute_rehearsal(ROOT)
    assert raised.value.code == "EXECUTION_NOT_AUTHORIZED"
