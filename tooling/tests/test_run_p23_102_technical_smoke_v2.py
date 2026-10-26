from __future__ import annotations

import contextlib
import copy
import datetime as dt
import importlib.util
import inspect
import json
import shutil
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/run_p23_102_technical_smoke_v2.py"
SPEC = importlib.util.spec_from_file_location(
    "p23_102_technical_smoke_v2_runner", RUNNER_PATH
)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)

AUTHORITY_PATH = ROOT / "tools/p23_102_smoke_authority.py"
AUTHORITY_SPEC = importlib.util.spec_from_file_location(
    "p23_102_smoke_authority_for_runner_tests", AUTHORITY_PATH
)
assert AUTHORITY_SPEC and AUTHORITY_SPEC.loader
AUTHORITY = importlib.util.module_from_spec(AUTHORITY_SPEC)
sys.modules[AUTHORITY_SPEC.name] = AUTHORITY
AUTHORITY_SPEC.loader.exec_module(AUTHORITY)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


class FakeBackend:
    def __init__(self, assignment: Mapping[str, Any]) -> None:
        self.assignment = dict(assignment)
        self.arm = str(assignment["arm"])
        self.budget = {"max_steps": 10, "cost_limit": 12.0}
        self.costs = {
            "search_visual": 1.0,
            "search_speech": 1.0,
            "search_ambient_audio": 1.0,
            "inspect_clip": 2.0,
            "read_transcript": 1.0,
            "get_channel_status": 0.25,
            "finalize": 0.0,
        }
        self.steps_used = 0
        self.cost_used = 0.0
        self.triggered = False
        self.suppressed = (
            {"record.route"} if self.arm in {"B", "R", "N"} else set()
        )
        self.events: list[dict[str, Any]] = []
        self.pointer_private: dict[str, dict[str, Any]] = {}
        self.observation_private: dict[str, dict[str, Any]] = {}
        self.evidence_by_observation: dict[str, list[str]] = {}

    def clone(self) -> FakeBackend:
        return copy.deepcopy(self)

    def apply_exogenous_restoration(self) -> None:
        self.suppressed.clear()
        self.triggered = True

    def public_start(self) -> dict[str, Any]:
        return {
            "question": "What happened in the source?",
            "claim_slots": [
                {
                    "claim_handle": "claim.public",
                    "description": "A public smoke-only claim slot.",
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
            "video_duration_s": 60.0,
        }

    def _charge(self, tool: str) -> None:
        self.steps_used += 1
        self.cost_used += self.costs[tool]

    def search(
        self, modality: str, query: str, top_k: int
    ) -> dict[str, Any]:
        tool = {
            "vision": "search_visual",
            "speech": "search_speech",
            "ambient": "search_ambient_audio",
        }[modality]
        self._charge(tool)
        pointer_id = f"ptr.{modality}.{self.steps_used}"
        self.pointer_private[pointer_id] = {
            "record_id": f"record.{modality}.{self.steps_used}",
            "modality": modality,
            "query": query,
        }
        return {
            "status": "ok",
            "results": [
                {
                    "pointer_id": pointer_id,
                    "modality": modality,
                    "interval": {
                        "start_s": float(self.steps_used),
                        "end_s": float(self.steps_used + 1),
                    },
                    "preview": "public candidate",
                }
            ][:top_k],
        }

    def observe(self, pointer_id: str) -> dict[str, Any]:
        pointer = self.pointer_private[pointer_id]
        modality = str(pointer["modality"])
        self._charge(
            "read_transcript" if modality == "speech" else "inspect_clip"
        )
        observation_id = f"obs.{len(self.observation_private) + 1}"
        observation = {
            "observation_id": observation_id,
            "modality": modality,
            "interval": {"start_s": 1.0, "end_s": 2.0},
            "content": "public smoke observation",
            "citable": True,
        }
        self.observation_private[observation_id] = {
            **observation,
            "record_id": pointer["record_id"],
        }
        self.evidence_by_observation[observation_id] = [
            "private.evidence.handle"
        ]
        return {"status": "ok", "observation": observation}

    def status(self, modalities: list[str]) -> dict[str, Any]:
        self._charge("get_channel_status")
        return {
            "status": "ok",
            "channels": {
                modality: {"status": "available", "retryable": False}
                for modality in modalities
            },
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "remaining_steps": self.budget["max_steps"] - self.steps_used,
            "remaining_cost": round(
                self.budget["cost_limit"] - self.cost_used, 6
            ),
            "triggered": self.triggered,
            "suppressed_segment_ids": sorted(self.suppressed),
            "known_pointer_ids": sorted(self.pointer_private),
            "known_observation_ids": sorted(self.observation_private),
        }

    def finalize(self, final: Mapping[str, Any]) -> dict[str, Any]:
        self._charge("finalize")
        return {"status": "finalized", "verdict": final["verdict"]}

    def pack_accessible_observations(
        self, token_cap: int
    ) -> list[dict[str, Any]]:
        del token_cap
        return []


@dataclass(frozen=True)
class FakeAttestation:
    label: str
    ordinal: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": f"session-{self.ordinal}",
            "cache_namespace": f"cache-{self.ordinal}",
            "continuation_label": self.label,
            "pid": 10_000 + self.ordinal,
            "process_group_id": 20_000 + self.ordinal,
            "runtime_namespace": f"/tmp/fake-{self.ordinal}",
            "network_namespace_denied": True,
            "offline_environment": True,
            "fresh_process": True,
            "shared_conversation_state": False,
            "shared_kv_state": False,
        }


class FakeWorker:
    def __init__(
        self,
        label: str,
        ordinal: int,
        *,
        malformed: bool = False,
    ) -> None:
        self.label = label
        self.ordinal = ordinal
        self.malformed = malformed
        self.closed = False
        self.calls = 0

    def isolation_attestation(self) -> FakeAttestation:
        return FakeAttestation(self.label, self.ordinal)

    def close(self) -> None:
        self.closed = True

    def generate(
        self,
        *,
        system: str,
        payload: Mapping[str, Any],
        max_new_tokens: int,
    ) -> dict[str, Any]:
        del system, max_new_tokens
        self.calls += 1
        if self.malformed:
            return {
                "raw_text": "{raw malformed",
                "parsed": {"wrong": "shape"},
                "parse_error": None,
                "prompt_tokens": 4,
                "generated_tokens": 3,
                "latency_seconds": 0.01,
                "peak_rss_kib": 10,
                "peak_rss_bytes": 10_240,
            }
        if payload["task"] == "choose_next_action":
            menu = payload["output_schema"]["action_menu"]
            if int(payload["turn"]) >= 4:
                action_index = len(menu) - 1
            else:
                action_index = next(
                    (
                        index
                        for index, item in enumerate(menu)
                        if item["action"]["type"] != "finalize"
                    ),
                    len(menu) - 1,
                )
            parsed: dict[str, Any] = {
                "public_state": {
                    "p_sufficient": 0.2,
                    "covered_claim_handles": [],
                    "missing_modalities": ["vision"],
                    "missing_hops": ["event_detection"],
                    "missingness_cause": (
                        "evidence_accessible_but_not_found"
                    ),
                    "recovery_intent": "Continue the public smoke.",
                },
                "action_index": action_index,
            }
        else:
            observations = list(payload["citable_observations"])
            if observations:
                observation_id = observations[0]["observation_id"]
                claim = payload["public_claim_slots"][0]["claim_handle"]
                parsed = {
                    "verdict": "answer",
                    "answer_text": "Smoke-only output.",
                    "asserted_claims": [
                        {
                            "claim_handle": claim,
                            "text": "Smoke-only output.",
                            "citations": [observation_id],
                        }
                    ],
                    "claim_to_citations": {claim: [observation_id]},
                    "missing_modalities": [],
                    "missing_hops": [],
                    "missingness_cause": "not_missing",
                    "p_sufficient": 0.8,
                    "recovery_intent": "No recovery.",
                    "stop_rationale": "Public observation was acquired.",
                }
            else:
                parsed = {
                    "verdict": "insufficient",
                    "answer_text": "",
                    "asserted_claims": [],
                    "claim_to_citations": {},
                    "missing_modalities": ["vision"],
                    "missing_hops": ["event_detection"],
                    "missingness_cause": "uncertain",
                    "p_sufficient": 0.1,
                    "recovery_intent": "No additional smoke action.",
                    "stop_rationale": "No public observation was acquired.",
                }
        raw = json.dumps(parsed, sort_keys=True)
        return {
            "raw_text": raw,
            "parsed": parsed,
            "parse_error": None,
            "prompt_tokens": 10,
            "generated_tokens": 10,
            "latency_seconds": 0.01,
            "peak_rss_kib": 10,
            "peak_rss_bytes": 10_240,
        }


class FakeProcessFactory:
    def __init__(self, *, malformed_label: str | None = None) -> None:
        self.malformed_label = malformed_label
        self.created: list[FakeWorker] = []

    def create(self, label: str) -> FakeWorker:
        worker = FakeWorker(
            label,
            len(self.created) + 1,
            malformed=label == self.malformed_label,
        )
        self.created.append(worker)
        return worker

    @contextlib.contextmanager
    def continuations(
        self,
        *,
        restored_label: str,
        no_trigger_label: str,
    ) -> Iterator[Any]:
        restored = self.create(restored_label)
        no_trigger = self.create(no_trigger_label)
        pair = type(
            "Pair",
            (),
            {"restored": restored, "no_trigger": no_trigger},
        )()
        try:
            yield pair
        finally:
            restored.close()
            no_trigger.close()


@dataclass(frozen=True)
class EphemeralAuthorityVerifier:
    registry_path: Path

    def verify_overlay(
        self,
        *,
        overlay_path: Path,
        registry_path: Path,
        now: dt.datetime,
    ) -> Mapping[str, Any]:
        del registry_path
        return AUTHORITY.verify_overlay_file(
            overlay_path,
            registry_path=self.registry_path,
            now=now,
        )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _signed_authorization_overlay(
    path: Path,
    *,
    output_root: Path,
    plan: Mapping[str, Any],
    validation: Mapping[str, Any],
    overlay_issued_offset: dt.timedelta = dt.timedelta(minutes=-2),
) -> tuple[dict[str, Any], EphemeralAuthorityVerifier]:
    now = RUNNER._utc_now()
    authority_root = path.parent / f"{path.stem}-authority"
    authority_root.mkdir(mode=0o700)
    registry_path = authority_root / "authority_registry.json"
    authorities_root = authority_root / "authorities"
    AUTHORITY.initialize_authorities(
        registry_path=registry_path,
        authorities_root=authorities_root,
        now=now,
    )
    bound_execution = {
        "bindings": RUNNER._authorization_expected_hashes(
            ROOT,
            output_root=output_root.resolve(),
            plan=plan,
            validation=validation,
        ),
        "one_run_nonce": "n" * 32,
        "declarations": {
            "technical_smoke_only": True,
            "no_scientific_interpretation": True,
            "no_competence_or_performance_interpretation": True,
            "single_run_only": True,
            "immutable_freeze_remains_unauthorized": True,
        },
        "review_decision": "GO",
    }
    receipts: dict[str, dict[str, Any]] = {}
    receipt_issued = now - dt.timedelta(minutes=1)
    receipt_expires = now + dt.timedelta(minutes=5)
    for role in AUTHORITY.ROLES:
        request = {
            "schema_version": AUTHORITY.RECEIPT_REQUEST_SCHEMA,
            "receipt_id": f"receipt.{role}.ephemeral-test",
            "issued_at_utc": AUTHORITY.utc_text(receipt_issued),
            "expires_at_utc": AUTHORITY.utc_text(receipt_expires),
            "bound_execution": bound_execution,
        }
        request_path = path.parent / f"{path.stem}-{role}-request.json"
        receipt_path = path.parent / f"{path.stem}-{role}-receipt.json"
        _write_json(request_path, request)
        receipts[role] = AUTHORITY.sign_receipt(
            role,
            payload_path=request_path,
            output_path=receipt_path,
            registry_path=registry_path,
            authorities_root=authorities_root,
            now=now,
        )
    overlay = {
        "schema_version": RUNNER.AUTHORIZATION_SCHEMA,
        "authorization_id": "authorization.p23-smoke-v2.ephemeral-test",
        "issued_at_utc": RUNNER._utc_text(now + overlay_issued_offset),
        "expires_at_utc": RUNNER._utc_text(
            now + dt.timedelta(minutes=6)
        ),
        "bound_execution": bound_execution,
        "approvals": {
            "live_wiring_reviewer": receipts["live_wiring_reviewer"],
            "red_team_reviewer": receipts["red_team_reviewer"],
        },
    }
    _write_json(path, overlay)
    return overlay, EphemeralAuthorityVerifier(registry_path)


def _execute(
    tmp_path: Path,
    *,
    malformed_label: str | None = None,
) -> tuple[dict[str, Any], Path, FakeProcessFactory]:
    output = tmp_path / "run"
    factory = FakeProcessFactory(malformed_label=malformed_label)
    report = RUNNER._execute_technical_smoke_for_test(
        ROOT,
        output_dir=output,
        backend_factory=lambda assignment: FakeBackend(assignment),
        process_factory=factory,
    )
    return report, output, factory


@pytest.fixture(scope="module")
def authorization_context() -> tuple[dict[str, Any], dict[str, Any]]:
    return RUNNER.build_plan(ROOT), RUNNER.validate_repository(ROOT)


@pytest.fixture(scope="module")
def completed_run(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, Any], Path, FakeProcessFactory]:
    return _execute(tmp_path_factory.mktemp("completed-smoke"))


def test_plan_is_deterministic_and_execute_is_fail_closed() -> None:
    first = RUNNER.build_plan(ROOT)
    second = RUNNER.build_plan(ROOT)
    assert first == second
    assert first["assignment_count"] == 32
    assert first["execution_authorized"] is False
    assert [row["ordinal"] for row in first["assignments"]] == list(
        range(1, 33)
    )
    assert {
        row["assignment_id"] for row in first["assignments"]
    } == {
        row["assignment_id"]
        for row in json.loads(
            (ROOT / RUNNER.CONFIG_REL).read_text(encoding="utf-8")
        )["assignment_plan"]["assignments"]
    }
    with pytest.raises(RUNNER.TechnicalSmokeError) as caught:
        RUNNER.execute_technical_smoke(ROOT)
    assert caught.value.code == "EXECUTION_NOT_AUTHORIZED"


def test_production_api_exposes_no_injected_execution_surface(
    tmp_path: Path,
) -> None:
    parameters = inspect.signature(
        RUNNER.execute_technical_smoke
    ).parameters
    assert set(parameters) == {
        "repo_root",
        "output_dir",
        "authorization_overlay",
    }
    rejected = {
        "backend_factory": lambda assignment: FakeBackend(assignment),
        "process_factory": FakeProcessFactory(),
        "authority_verifier": object(),
        "testing": True,
        "provider_terminal_hook": lambda _: None,
        "pre_completion_hook": lambda _: None,
        "assignment_deadline_seconds": 0.01,
    }
    for name, value in rejected.items():
        with pytest.raises(TypeError):
            RUNNER.execute_technical_smoke(
                ROOT,
                output_dir=tmp_path / name,
                **{name: value},
            )
    with pytest.raises(RUNNER.TechnicalSmokeError) as caught:
        RUNNER._execute_technical_smoke_core(
            ROOT,
            output_dir=tmp_path / "forged-core",
            authorization_overlay=None,
            backend_factory=lambda assignment: FakeBackend(assignment),
            process_factory=FakeProcessFactory(),
            capability=True,
        )
    assert caught.value.code == "PRODUCTION_INJECTION_REJECTED"


def test_fake_execution_delivers_all_checkpoints_and_isolates_sessions(
    completed_run: tuple[dict[str, Any], Path, FakeProcessFactory],
) -> None:
    report, output, factory = completed_run
    assert report["status"] == "TECHNICAL_SMOKE_COMPLETE"
    checkpoint = json.loads(
        (output / "checkpoint_delivery.json").read_text(encoding="utf-8")
    )
    assert checkpoint["pair_count"] == 12
    assert checkpoint["all_prefixes_identical"] is True
    assert checkpoint["all_checkpoints_identical"] is True
    assert all(
        row["checkpoint_delivered_r"]
        and row["checkpoint_delivered_n"]
        and row["event_opportunity_reached"]
        for row in checkpoint["pairs"]
    )
    isolation = json.loads(
        (output / "process_session_isolation.json").read_text(
            encoding="utf-8"
        )
    )
    assert isolation["status"] == "PASS"
    assert isolation["fresh_process_per_assignment"] is True
    assert isolation["dedicated_prefix_process_count"] == 8
    assert len(isolation["attestations"]) == 40
    assert len(
        {row["session_id"] for row in isolation["attestations"]}
    ) == 40
    assert len(
        {row["pid"] for row in isolation["attestations"]}
    ) == 40
    assert len(factory.created) == 40
    assert all(worker.closed for worker in factory.created)
    prefix_workers = [
        worker for worker in factory.created if worker.label.endswith(":prefix")
    ]
    assert len(prefix_workers) == 8
    assert all(worker.closed for worker in prefix_workers)
    pre_spawn = json.loads(
        (output / "model_inventory_pre_spawn.json").read_text(
            encoding="utf-8"
        )
    )
    assert pre_spawn["equals_initial_validation"] is True
    assert pre_spawn["equals_signed_overlay"] is None
    assert pre_spawn["worker_spawned_before_check"] is False


def test_private_firewall_and_exactly_one_completion_row(
    completed_run: tuple[dict[str, Any], Path, FakeProcessFactory],
) -> None:
    _, output, _ = completed_run
    leakage = json.loads(
        (output / "runtime_leakage_surface.json").read_text(
            encoding="utf-8"
        )
    )
    assert leakage["status"] == "NOT_ESTIMABLE_SINGLE_SOURCE"
    scan = leakage["mechanical_private_surface_scan"]
    assert scan["status"] == "PASS"
    assert scan["leakage_hit_count"] == 0
    public_text = (
        output / "public_trajectories.jsonl"
    ).read_text(encoding="utf-8")
    private_rows = _read_jsonl(
        output / "private_arm_evidence_mappings.jsonl"
    )
    for row in private_rows:
        assert row["arm"] in {"C", "B", "R", "N"}
        assert row["route_group_id"] not in public_text
        for handle in row["expected_evidence_handle_ids"]:
            assert handle not in public_text
    completion = _read_jsonl(output / "completion_ledger.jsonl")
    failures = _read_jsonl(output / "failure_ledger.jsonl")
    assert len(completion) == len(failures) == 32
    assert len({row["assignment_id"] for row in completion}) == 32
    assert all(row["terminal_row_count"] == 1 for row in completion)


def test_raw_malformed_attempts_are_retained(
    tmp_path: Path,
) -> None:
    plan = RUNNER.build_plan(ROOT)
    malformed_assignment = next(
        row
        for row in plan["assignments"]
        if row["pair_id"] is None
    )
    _, output, _ = _execute(
        tmp_path,
        malformed_label=malformed_assignment["assignment_id"],
    )
    raw = _read_jsonl(output / "raw_model_calls.jsonl")
    matching = [
        row
        for row in raw
        if row["process_label"]
        == malformed_assignment["assignment_id"]
    ]
    assert len(matching) == 2
    assert all(
        row["response"]["raw_text"] == "{raw malformed"
        for row in matching
    )
    assert all(
        row["repaired_runner_attempt"]["status"] == "invalid"
        for row in matching
    )
    failures = {
        row["assignment_id"]: row
        for row in _read_jsonl(output / "failure_ledger.jsonl")
    }
    assert failures[malformed_assignment["assignment_id"]]["failure"][
        "code"
    ] == "MALFORMED_AFTER_REPAIR"


def test_minimal_or_unknown_authorization_overlay_is_rejected(
    tmp_path: Path,
    authorization_context: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    plan, validation = authorization_context
    output = tmp_path / "authorized-run"
    overlay_path = tmp_path / "overlay.json"
    overlay, verifier = _signed_authorization_overlay(
        overlay_path,
        output_root=output,
        plan=plan,
        validation=validation,
    )
    overlay["unknown"] = True
    _write_json(overlay_path, overlay)
    with pytest.raises(RUNNER.TechnicalSmokeError) as caught:
        RUNNER._validate_authorization_overlay_for_test(
            overlay_path,
            root=ROOT,
            output_root=output.resolve(),
            plan=plan,
            validation=validation,
            authority_verifier=verifier,
        )
    assert caught.value.code == "AUTHORIZATION_SCHEMA_INVALID"


def test_authorization_overlay_with_genuinely_missing_field_is_rejected(
    tmp_path: Path,
    authorization_context: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    plan, validation = authorization_context
    output = tmp_path / "authorized-run"
    overlay_path = tmp_path / "overlay.json"
    overlay, verifier = _signed_authorization_overlay(
        overlay_path,
        output_root=output,
        plan=plan,
        validation=validation,
    )
    del overlay["approvals"]
    _write_json(overlay_path, overlay)
    with pytest.raises(RUNNER.TechnicalSmokeError) as caught:
        RUNNER._validate_authorization_overlay_for_test(
            overlay_path,
            root=ROOT,
            output_root=output.resolve(),
            plan=plan,
            validation=validation,
            authority_verifier=verifier,
        )
    assert caught.value.code == "AUTHORIZATION_SCHEMA_INVALID"


@pytest.mark.parametrize("wrong_name", ["wrong", "nonempty"])
def test_authorization_overlay_is_bound_to_exact_empty_output_root(
    tmp_path: Path,
    authorization_context: tuple[dict[str, Any], dict[str, Any]],
    wrong_name: str,
) -> None:
    plan, validation = authorization_context
    bound = tmp_path / "bound"
    wrong = tmp_path / wrong_name
    if wrong_name == "nonempty":
        wrong.mkdir()
        (wrong / "preexisting.txt").write_text("occupied", encoding="utf-8")
    overlay_path = tmp_path / f"overlay-{wrong_name}.json"
    _, verifier = _signed_authorization_overlay(
        overlay_path,
        output_root=bound,
        plan=plan,
        validation=validation,
    )
    with pytest.raises(RUNNER.TechnicalSmokeError) as caught:
        RUNNER._validate_authorization_overlay_for_test(
            overlay_path,
            root=ROOT,
            output_root=wrong.resolve(),
            plan=plan,
            validation=validation,
            authority_verifier=verifier,
        )
    assert caught.value.code == "AUTHORIZATION_BINDING_MISMATCH"


@pytest.mark.parametrize(
    ("model_name", "repo_id", "revision", "error_prefix"),
    [
        (
            "qwen",
            RUNNER.EXPECTED_QWEN_REPO,
            RUNNER.EXPECTED_QWEN_REVISION,
            "QWEN",
        ),
        (
            "siglip2",
            RUNNER.EXPECTED_SIGLIP2_REPO,
            RUNNER.EXPECTED_SIGLIP2_REVISION,
            "SIGLIP2",
        ),
        (
            "clap",
            RUNNER.EXPECTED_CLAP_REPO,
            RUNNER.EXPECTED_CLAP_REVISION,
            "CLAP",
        ),
    ],
)
def test_same_size_model_tamper_fails_before_process_factory_invocation(
    tmp_path: Path,
    model_name: str,
    repo_id: str,
    revision: str,
    error_prefix: str,
) -> None:
    snapshot = tmp_path / model_name
    snapshot.mkdir()
    model_file = snapshot / "config.json"
    model_file.write_bytes(b"good")
    model = {
        "repo_id": repo_id,
        "revision": revision,
        "snapshot_dir": str(snapshot),
        "files": [
            {
                "path": "config.json",
                "bytes": 4,
                "sha256": RUNNER._sha256(model_file),
            }
        ],
    }
    model_file.write_bytes(b"evil")
    manifest_path = tmp_path / f"{model_name}-manifest.json"
    _write_json(manifest_path, {"model": model})
    identity = RUNNER._local_model_identity(
        tmp_path,
        manifest_path=manifest_path.relative_to(tmp_path),
        model=model,
        expected_repo=repo_id,
        expected_revision=revision,
        error_prefix=error_prefix,
    )
    assert f"{error_prefix}_LOCAL_FILE_HASH:config.json" in identity["errors"]
    process_factory_called = False

    def process_factory(_: Mapping[str, Any]) -> None:
        nonlocal process_factory_called
        process_factory_called = True

    if identity["errors"]:
        with pytest.raises(RUNNER.TechnicalSmokeError) as caught:
            raise RUNNER.TechnicalSmokeError(
                "VALIDATION_NOT_READY", ",".join(identity["errors"])
            )
    else:
        process_factory(identity)
    assert caught.value.code == "VALIDATION_NOT_READY"
    assert process_factory_called is False


@pytest.mark.parametrize(
    ("model_name", "repo_id", "revision", "error_prefix"),
    [
        (
            "qwen",
            RUNNER.EXPECTED_QWEN_REPO,
            RUNNER.EXPECTED_QWEN_REVISION,
            "QWEN",
        ),
        (
            "siglip2",
            RUNNER.EXPECTED_SIGLIP2_REPO,
            RUNNER.EXPECTED_SIGLIP2_REVISION,
            "SIGLIP2",
        ),
        (
            "clap",
            RUNNER.EXPECTED_CLAP_REPO,
            RUNNER.EXPECTED_CLAP_REVISION,
            "CLAP",
        ),
    ],
)
def test_manifest_model_inventory_rejects_unexpected_files(
    tmp_path: Path,
    model_name: str,
    repo_id: str,
    revision: str,
    error_prefix: str,
) -> None:
    snapshot = tmp_path / model_name
    snapshot.mkdir()
    model_file = snapshot / "config.json"
    model_file.write_bytes(b"bound")
    (snapshot / "unexpected.bin").write_bytes(b"not allowed")
    model = {
        "repo_id": repo_id,
        "revision": revision,
        "snapshot_dir": str(snapshot),
        "files": [
            {
                "path": "config.json",
                "bytes": model_file.stat().st_size,
                "sha256": RUNNER._sha256(model_file),
            }
        ],
    }
    manifest_path = tmp_path / f"{model_name}-manifest.json"
    _write_json(manifest_path, {"model": model})
    identity = RUNNER._local_model_identity(
        tmp_path,
        manifest_path=manifest_path.relative_to(tmp_path),
        model=model,
        expected_repo=repo_id,
        expected_revision=revision,
        error_prefix=error_prefix,
    )
    assert (
        f"{error_prefix}_UNEXPECTED_FILE:unexpected.bin"
        in identity["errors"]
    )
    assert {
        row["path"] for row in identity["validated_files"]
    } == {"config.json"}


def test_whisper_inventory_rejects_unexpected_files(
    tmp_path: Path,
) -> None:
    snapshot_rel = Path("whisper")
    snapshot = tmp_path / snapshot_rel
    snapshot.mkdir()
    model_file = snapshot / "config.json"
    model_file.write_bytes(b"bound")
    sums_rel = snapshot_rel / "SHA256SUMS"
    (tmp_path / sums_rel).write_text(
        (
            RUNNER._sha256(model_file).removeprefix("sha256:")
            + f"  {snapshot_rel.as_posix()}/config.json\n"
        ),
        encoding="utf-8",
    )
    (snapshot / "unexpected.bin").write_bytes(b"not allowed")
    identity = RUNNER._sha256sums_model_identity(
        tmp_path,
        snapshot_rel=snapshot_rel,
        sums_rel=sums_rel,
        expected_repo=RUNNER.EXPECTED_WHISPER_REPO,
        expected_revision=RUNNER.EXPECTED_WHISPER_REVISION,
        error_prefix="WHISPER",
    )
    assert "WHISPER_UNEXPECTED_FILE:unexpected.bin" in identity["errors"]
    assert {
        row["path"] for row in identity["validated_files"]
    } == {"config.json", "SHA256SUMS"}


def test_pre_spawn_model_mutation_fails_before_process_factory_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = RUNNER._local_model_identities
    calls = 0

    def drift_on_pre_spawn(
        root: Path,
        qwen_manifest: Mapping[str, Any],
    ) -> dict[str, dict[str, Any]]:
        nonlocal calls
        calls += 1
        identities = original(root, qwen_manifest)
        if calls >= 3:
            identities = copy.deepcopy(identities)
            identities["qwen"]["validated_file_set_sha256"] = (
                "sha256:" + "0" * 64
            )
        return identities

    class NeverCalledFactory(FakeProcessFactory):
        def create(self, label: str) -> FakeWorker:
            raise AssertionError(f"worker spawned unexpectedly: {label}")

    monkeypatch.setattr(
        RUNNER,
        "_local_model_identities",
        drift_on_pre_spawn,
    )
    output = tmp_path / "pre-spawn-drift"
    with pytest.raises(RUNNER.TechnicalSmokeError) as caught:
        RUNNER._execute_technical_smoke_for_test(
            ROOT,
            output_dir=output,
            backend_factory=lambda assignment: FakeBackend(assignment),
            process_factory=NeverCalledFactory(),
        )
    assert caught.value.code == "PRE_SPAWN_MODEL_INVENTORY_DRIFT"
    assert not (output / "model_inventory_pre_spawn.json").exists()


def test_recursive_scan_detects_embedded_private_value_and_classifier_stays_ne(
) -> None:
    private = [{
        "family_id": "mpf.secret-value",
        "intervention_id": "mpi.secret-value",
        "route_group_id": "mpr.secret-value",
        "suppressed_segment_ids_registered": ["P23_102.secret"],
        "expected_evidence_handle_ids": ["eh.secret-value"],
    }]
    report = RUNNER._runtime_leakage_report(
        [{
            "request": {
                "payload": {
                    "nested": [
                        {"text": "prefix eh.secret-value suffix"}
                    ]
                }
            },
            "response": {},
        }],
        [],
        private,
    )
    assert report["status"] == "NOT_ESTIMABLE_SINGLE_SOURCE"
    assert report["mechanical_private_surface_scan"]["status"] == "FAIL"
    assert any(
        hit["kind"] == "embedded_private_value"
        for hit in report["mechanical_private_surface_scan"]["hits"]
    )
    assert (
        report["runtime_leakage_classifier"]["status"]
        == "NOT_ESTIMABLE_SINGLE_SOURCE"
    )
    assert report["runtime_leakage_classifier"]["pass_allowed"] is False


def test_abort_thresholds_use_exact_greater_than_or_equal_semantics() -> None:
    reasons = RUNNER._online_abort_reasons(
        total_calls=352,
        effective_assignment_calls={"a": 11},
        process_failures=2,
        malformed_after_repair=3,
        tool_contract_violations=2,
        provider_latencies=[120.0],
        assignment_elapsed=900.0,
        mechanical_scan_hits=1,
        isolation_collisions=1,
    )
    assert {
        "GLOBAL_MODEL_CALL_THRESHOLD_REACHED",
        "ASSIGNMENT_MODEL_CALL_THRESHOLD_REACHED",
        "PROCESS_FAILURE_THRESHOLD_REACHED",
        "MALFORMED_THRESHOLD_REACHED",
        "TOOL_CONTRACT_THRESHOLD_REACHED",
        "PROVIDER_TIMEOUT_THRESHOLD_REACHED",
        "ASSIGNMENT_TIMEOUT_THRESHOLD_REACHED",
        "PRIVATE_SURFACE_SCAN_FAILURE",
        "PROCESS_ISOLATION_COLLISION",
    } == set(reasons)


def test_interruption_preserves_initial_manifest_abort_and_unstarted_ledgers(
    tmp_path: Path,
) -> None:
    class InterruptingFactory(FakeProcessFactory):
        def create(self, label: str) -> FakeWorker:
            if len(self.created) >= 2:
                raise RuntimeError("simulated interruption")
            return super().create(label)

    output = tmp_path / "interrupted"
    with pytest.raises(RuntimeError, match="simulated interruption"):
        RUNNER._execute_technical_smoke_for_test(
            ROOT,
            output_dir=output,
            backend_factory=lambda assignment: FakeBackend(assignment),
            process_factory=InterruptingFactory(),
        )
    manifest = json.loads(
        (output / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["completion_status"] == "ABORTED"
    assert manifest["started_at_utc"].endswith("Z")
    assert _read_jsonl(output / "abort_ledger.jsonl")
    assert _read_jsonl(output / "unstarted_assignments.jsonl")


def test_second_process_failure_aborts_exactly(
    tmp_path: Path,
) -> None:
    class CrashingWorker(FakeWorker):
        def generate(
            self,
            *,
            system: str,
            payload: Mapping[str, Any],
            max_new_tokens: int,
        ) -> dict[str, Any]:
            del system, payload, max_new_tokens
            raise RuntimeError(f"process failure {self.label}")

    class CrashingFactory(FakeProcessFactory):
        def create(self, label: str) -> FakeWorker:
            worker = CrashingWorker(label, len(self.created) + 1)
            self.created.append(worker)
            return worker

    output = tmp_path / "second-process-failure"
    with pytest.raises(RUNNER.TechnicalSmokeHardAbort) as caught:
        RUNNER._execute_technical_smoke_for_test(
            ROOT,
            output_dir=output,
            backend_factory=lambda assignment: FakeBackend(assignment),
            process_factory=CrashingFactory(),
        )
    assert caught.value.code == "PROCESS_FAILURE_THRESHOLD_REACHED"
    journal = _read_jsonl(output / "provider_call_journal.jsonl")
    terminals = [
        row["payload"] for row in journal if row["event"] == "terminal"
    ]
    assert len(terminals) == 2
    assert all(row["failure"] is not None for row in terminals)
    abort = _read_jsonl(output / "abort_ledger.jsonl")
    assert len(abort) == 1
    assert abort[0]["code"] == "PROCESS_FAILURE_THRESHOLD_REACHED"
    assert abort[0]["raw_journal_terminal_count"] == 2
    manifest = json.loads(
        (output / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["completion_status"] == "ABORTED"
    assert manifest["abort_reasons"] == [
        "PROCESS_FAILURE_THRESHOLD_REACHED"
    ]


def test_interruption_after_durable_raw_before_terminal_artifacts(
    tmp_path: Path,
) -> None:
    output = tmp_path / "durable-raw-interruption"
    interrupted_call_id: str | None = None

    def interrupt_after_terminal(row: Mapping[str, Any]) -> None:
        nonlocal interrupted_call_id
        interrupted_call_id = str(row["call_id"])
        raise KeyboardInterrupt("after durable raw")

    with pytest.raises(KeyboardInterrupt, match="after durable raw"):
        RUNNER._execute_technical_smoke_for_test(
            ROOT,
            output_dir=output,
            backend_factory=lambda assignment: FakeBackend(assignment),
            process_factory=FakeProcessFactory(),
            provider_terminal_hook=interrupt_after_terminal,
        )
    assert interrupted_call_id is not None
    raw = _read_jsonl(output / "raw_model_calls.jsonl")
    assert [row["call_id"] for row in raw] == [interrupted_call_id]
    journal = _read_jsonl(output / "provider_call_journal.jsonl")
    assert [row["event"] for row in journal] == ["request", "terminal"]
    assert not _read_jsonl(output / "completion_ledger.jsonl")
    assert not _read_jsonl(output / "failure_ledger.jsonl")
    abort = _read_jsonl(output / "abort_ledger.jsonl")
    assert abort[0]["raw_journal_request_count"] == 1
    assert abort[0]["raw_journal_terminal_count"] == 1


def test_replay_corruption_is_rejected_with_current_code(
    tmp_path: Path,
    completed_run: tuple[dict[str, Any], Path, FakeProcessFactory],
) -> None:
    _, completed_output, _ = completed_run
    output = tmp_path / "replay-corrupt"
    shutil.copytree(completed_output, output)
    rows = _read_jsonl(output / "public_trajectories.jsonl")
    rows[0]["final_output"]["answer_text"] = "corrupted replay"
    RUNNER._atomic_write_jsonl(output / "public_trajectories.jsonl", rows)
    with pytest.raises(RUNNER.TechnicalSmokeError) as caught:
        RUNNER._write_and_validate_replay_manifest(
            output,
            plan=RUNNER.build_plan(ROOT),
            checkpoints=_read_jsonl(output / "r_n_prefix_pairs.jsonl"),
            write=False,
        )
    assert caught.value.code == "REPLAY_TRAJECTORY_HASH_MISMATCH"


def test_raw_retention_mismatch_is_rejected_with_current_code(
    tmp_path: Path,
    completed_run: tuple[dict[str, Any], Path, FakeProcessFactory],
) -> None:
    _, completed_output, _ = completed_run
    output = tmp_path / "raw-retention-corrupt"
    shutil.copytree(completed_output, output)
    raw = _read_jsonl(output / "raw_model_calls.jsonl")
    raw[0]["response"]["raw_text"] = "tampered raw retention"
    RUNNER._atomic_write_jsonl(output / "raw_model_calls.jsonl", raw)
    with pytest.raises(RUNNER.TechnicalSmokeError) as caught:
        RUNNER._write_and_validate_raw_retention_manifest(output, write=False)
    assert caught.value.code == "RAW_RETENTION_CONTENT_MISMATCH"


def test_signed_approval_provenance_and_output_binding_are_preserved(
    tmp_path: Path,
    authorization_context: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    plan, validation = authorization_context
    output = tmp_path / "bound-output"
    overlay_path = tmp_path / "signed-overlay.json"
    overlay, verifier = _signed_authorization_overlay(
        overlay_path,
        output_root=output,
        plan=plan,
        validation=validation,
    )
    authorization = RUNNER._validate_authorization_overlay_for_test(
        overlay_path,
        root=ROOT,
        output_root=output.resolve(),
        plan=plan,
        validation=validation,
        authority_verifier=verifier,
    )
    verification = authorization["authority_verification"]
    assert verification["authorization_id"] == overlay["authorization_id"]
    assert verification["status"] == "OVERLAY_APPROVALS_VALID"
    assert set(verification["authority_ids"]) == set(AUTHORITY.ROLES)
    assert set(verification["receipt_ids"]) == set(AUTHORITY.ROLES)
    for role in AUTHORITY.ROLES:
        signed = overlay["approvals"][role]["signed_payload"]
        assert verification["authority_ids"][role] == signed["authority_id"]
        assert verification["receipt_ids"][role] == signed["receipt_id"]
        assert signed["issued_at_utc"] >= overlay["issued_at_utc"]
        assert signed["expires_at_utc"] <= overlay["expires_at_utc"]
    expected_output_binding = RUNNER.semantic_hash(str(output.resolve()))
    assert (
        authorization["bindings"]["output_root_sha256"]
        == expected_output_binding
    )
    manifest = RUNNER._manifest_identity_core(
        output_dir=output,
        run_id="provenance-test",
        plan=plan,
        validation=validation,
        authorization=authorization,
        testing_injection=False,
        started_at_utc=RUNNER._utc_text(),
    )
    strict_overlay = manifest["authorization"]["strict_overlay"]
    assert strict_overlay["authorization_id"] == overlay["authorization_id"]
    assert (
        strict_overlay["authority_verification"]["authority_ids"]
        == verification["authority_ids"]
    )
    assert (
        strict_overlay["authority_verification"]["receipt_ids"]
        == verification["receipt_ids"]
    )
    assert manifest["output_root"] == str(output.resolve())


def test_wrong_but_identical_checkpoint_is_rejected() -> None:
    wrong = {
        "event_type": "protocol_checkpoint",
        "event_version": "2.0.0",
        "message": "Wrong checkpoint.",
        "cost": 0.0,
    }
    state = type(
        "State",
        (),
        {"events": [{"action_index": 4, "event": wrong}]},
    )()
    errors = RUNNER._checkpoint_validation(
        {
            "checkpoint_event": wrong,
            "checkpoint_event_hash": RUNNER.semantic_hash(wrong),
            "checkpoint_action_index_zero_based": 4,
            "checkpoint_delivered_r": True,
            "checkpoint_delivered_n": True,
            "checkpoint_identical": True,
        },
        r_state=state,
        n_state=state,
    )
    assert "CHECKPOINT_EVENT_OBJECT_MISMATCH" in errors
    assert "CHECKPOINT_EVENT_HASH_MISMATCH" in errors


def test_process_failure_always_has_canonical_raw_diagnostic_hash() -> None:
    class CrashingWorker:
        def generate(self, **_: Any) -> dict[str, Any]:
            raise RuntimeError("raw process failure")

    calls: list[dict[str, Any]] = []
    model = RUNNER.RecordingModel(
        worker=CrashingWorker(),
        trajectory_id="trajectory",
        process_label="process",
        calls=calls,
    )
    with pytest.raises(RuntimeError, match="raw process failure"):
        model.generate(system="system", payload={}, max_new_tokens=1)
    failure = calls[0]["failure"]
    assert failure["raw_diagnostic_bytes_sha256"].startswith("sha256:")
    assert failure["raw_diagnostic_bytes_length"] > 0
