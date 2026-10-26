from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/p23_102_query_authoring_v2_canary2.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("canary2", TOOL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def family(
    key: str,
    private_id: str,
    clips: list[tuple[str, int, int]],
) -> dict:
    return {
        "family_key": key,
        "private_family_id": private_id,
        "shape": (
            "one_component" if len(clips) == 1 else "two_component_ordered"
        ),
        "slot_names": ["OPAQUE_SLOT"],
        "private_template_hashes": {"question_template": "sha256:opaque"},
        "intervals": [
            {
                "clip_key": clip,
                "start_us": start,
                "end_us": end,
                "private_evidence_handle_ids": [f"{key}-{clip}-a", f"{key}-{clip}-b"],
            }
            for clip, start, end in clips
        ],
    }


def synthetic_inputs(tool):
    families = [
        family("local-a", "private-local-a", [("clip-1", 0, 10)]),
        family("local-b", "private-local-b", [("clip-2", 10, 20)]),
        family(
            "far-vocal",
            "private-far-vocal",
            [("clip-3", 20, 30), ("clip-4", 100, 110)],
        ),
        family(
            "far-continuity",
            "private-far-continuity",
            [("clip-5", 200, 210), ("clip-6", 500, 510)],
        ),
        family(
            "far-low",
            "private-far-low",
            [("clip-7", 600, 610), ("clip-8", 700, 710)],
        ),
    ]
    targets = [
        {
            "clip_key": f"clip-{index}",
            "start_us": (index - 1) * 10,
            "end_us": index * 10,
            "duration_us": 10,
            "family_keys": [
                row["family_key"]
                for row in families
                if any(
                    interval["clip_key"] == f"clip-{index}"
                    for interval in row["intervals"]
                )
            ],
        }
        for index in range(1, 9)
    ]
    structural = {
        "file_hashes": {
            name: f"sha256:{index:064x}"
            for index, name in enumerate(
                sorted(tool.parent.ALLOWED_BUNDLE_FILES), 1
            )
        },
        "families": families,
        "targets": targets,
    }
    machine_rows = {
        "private-far-vocal": {
            "structural_scores": {
                "visual_continuity": 0.80,
                "audio_continuity": 0.79,
            },
            "temporal_structure": {
                "evidence_center_separation_seconds": 80.0
            },
        },
        "private-far-continuity": {
            "structural_scores": {
                "visual_continuity": 0.98,
                "audio_continuity": 0.97,
            },
            "temporal_structure": {
                "evidence_center_separation_seconds": 300.0
            },
        },
        "private-far-low": {
            "structural_scores": {
                "visual_continuity": 0.70,
                "audio_continuity": 0.69,
            },
            "temporal_structure": {
                "evidence_center_separation_seconds": 100.0
            },
        },
    }
    speech_rows = [
        {
            "chunk_id": "speech-vocal",
            "start_us": 20,
            "end_us": 30,
            "text": "Oh",
            "quality_flags": [
                "TOO_FEW_LEXICAL_TOKENS",
                "LOW_GENERATED_TOKEN_LOGPROB",
            ],
            "routing": "inventory_only",
            "mean_generated_token_log_probability": -3.0,
        }
    ]
    return structural, machine_rows, speech_rows


def test_synthetic_selection_uses_exact_three_structural_roles() -> None:
    tool = load_tool()
    structural, machine_rows, speech_rows = synthetic_inputs(tool)
    local_hash = tool._family_hash(structural["families"][0])
    first = tool.select_canary_families(
        structural,
        machine_family_rows=machine_rows,
        speech_rows=speech_rows,
        v15_local_hash=local_hash,
    )
    structural["families"].reverse()
    second = tool.select_canary_families(
        structural,
        machine_family_rows=machine_rows,
        speech_rows=speech_rows,
        v15_local_hash=local_hash,
    )
    assert first == second
    assert first["selected_family_keys"] == {
        "local_v15_structure": "local-a",
        "far_vocalization_asr_ambiguity": "far-vocal",
        "far_continuity_anaphora": "far-continuity",
    }
    assert first["retrieval_score_fields_read"] is False
    assert first["manual_semantic_labels_read"] is False
    assert first["unique_clip_count"] == 5
    subset = tool.build_subset_structural(structural, first)
    assert subset["counts"] == {
        "families": 3,
        "local_families": 1,
        "far_families": 2,
        "target_clips": 5,
        "queries": 13,
    }


def _real_exposure(tool, structural: dict) -> dict:
    del structural
    return deepcopy(tool._load_private_governance_ledger(ROOT)["exposure"])


def test_canary2_factorized_budget_is_exactly_five_plus_five_plus_three() -> None:
    tool = load_tool()
    structural, machine_rows, speech_rows = synthetic_inputs(tool)
    selection = tool.select_canary_families(
        structural,
        machine_family_rows=machine_rows,
        speech_rows=speech_rows,
        v15_local_hash=tool._family_hash(structural["families"][0]),
    )
    subset = tool.build_subset_structural(structural, selection)
    manifest = tool.parent.build_prompt_manifest(subset)
    assert manifest["visual_prompt_count"] == 5
    assert manifest["ambient_prompt_count"] == 5
    assert manifest["composition_prompt_count"] == 3
    assert manifest["prompt_count"] == 13
    assert tool.EXPECTED_INITIAL_FACTORS == 13
    assert tool.EXPECTED_INITIAL_FACTORS == (
        tool.EXPECTED_VISUAL_FACTORS
        + tool.EXPECTED_AMBIENT_FACTORS
        + tool.EXPECTED_COMPOSITION_FACTORS
    )
    specs = tool.parent.derive_expected_factor_specs(subset, manifest)
    assert len(specs) == 13
    assert sum(
        row["factor_kind"] == "visual" for row in specs.values()
    ) == 5
    assert sum(
        row["factor_kind"] == "ambient" for row in specs.values()
    ) == 5
    assert sum(
        row["factor_kind"] == "family_composition"
        for row in specs.values()
    ) == 3


def test_r22a_canary2_inherits_same_family_tuple_duplicate_stop() -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    manifest_path = (
        ROOT
        / ledger["r21_failure_evidence_path"]
        / "accepted_factor_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = tool.parent.ambient_semantic_tuple_duplicate_audit(
        manifest, scope="canary2_r21_regression"
    )
    assert audit["status"] == "FAIL_CLOSED"
    assert any(row["same_family_keys"] for row in audit["blocking_findings"])
    assert audit["global_duplicate_findings"]
    assert audit["collision_ledger"]
    assert audit["automatic_rewrite_permitted"] is False
    assert audit["authoring_retry_permitted"] is False


def test_r12_canary2_real_authoring_tracks_omni_authoring_failure_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    subset = {
        "families": [
            {
                "family_key": "family-r12",
                "shape": "one_component",
                "intervals": [{"clip_key": "clip-r12"}],
            }
        ],
        "targets": [
            {
                "clip_key": "clip-r12",
                "start_us": 0,
                "end_us": 1_000_000,
            }
        ],
        "counts": {},
    }
    staging = tmp_path / "staging"
    staging.mkdir()
    stage_times: dict[str, float] = {}
    stage_tracker = {"current": "canary_setup"}
    monkeypatch.setattr(
        tool.parent,
        "_extract_exact_clips",
        lambda *args, **kwargs: (
            {"clip-r12": object()},
            [
                {
                    "clip_key": "clip-r12",
                    "start_us": 0,
                    "end_us": 1_000_000,
                    "duration_us": 1_000_000,
                    "video_sha256": "sha256:video",
                    "audio_sha256": "sha256:audio",
                }
            ],
        ),
    )
    monkeypatch.setattr(
        tool.parent,
        "_load_omni",
        lambda root: (object(), object(), object()),
    )
    monkeypatch.setattr(
        tool.parent,
        "_decode_av",
        lambda asset: (object(), object()),
    )

    def fail_authoring(*args, **kwargs):
        del args, kwargs
        raise tool.parent.AuthoringError(
            "MODEL_AMBIENT_QUERY_DESCRIPTION_IDENTITY"
        )

    monkeypatch.setattr(tool.parent, "author_one_family", fail_authoring)
    contract = {
        "input_fingerprints": {"media_sha256": "sha256:media"},
        "model_identities": {"authoring": {"repo_id": "mock"}},
    }
    with pytest.raises(
        tool.parent.AuthoringError,
        match="MODEL_AMBIENT_QUERY_DESCRIPTION_IDENTITY",
    ):
        tool._run_real_authoring(
            tmp_path,
            media=Path("media.mp4"),
            staging=staging,
            subset=subset,
            contract=contract,
            stage_times=stage_times,
            stage_tracker=stage_tracker,
        )
    assert stage_tracker["current"] == "omni_authoring"
    assert "omni_authoring_partial_seconds" in stage_times
    assert "query_collision_audits_partial_seconds" not in stage_times


def test_real_selection_is_bound_to_v15_and_machine_index() -> None:
    tool = load_tool()
    structural = tool.parent.load_structural_bundle(ROOT)
    selection, inputs = tool._selection_context(ROOT, structural)
    ledger = tool._load_private_governance_ledger(ROOT)
    expected = {
        role: row["family_key"]
        for role, row in ledger["selection"]["selected_identities"].items()
    }
    assert selection["selected_family_keys"] == expected
    assert selection["unique_clip_count"] == 5
    assert selection["unique_clip_keys"] == sorted(
        {
            clip
            for row in ledger["selection"]["selected_identities"].values()
            for clip in row["clip_keys"]
        }
    )
    assert len(set(selection["selected_family_keys"].values())) == 3
    assert inputs["v15_local_family_structural_sha256"] == (
        selection["selected_family_hashes"]["local_v15_structure"]
    )
    assert inputs["private_governance_ledger_sha256"].startswith("sha256:")
    assert inputs["public_selection_commitment_sha256"].startswith("sha256:")


def test_r22b_exact_exposure_filtering_and_role_priority() -> None:
    tool = load_tool()
    structural = tool.parent.load_structural_bundle(ROOT)
    diagnostics = tool._load_machine_diagnostics(ROOT)
    reference = tool._load_v15_local_reference(ROOT)
    rows = structural["documents"]["family_registry.json"]["families"]
    selection = tool.select_canary_families(
        structural,
        machine_family_rows={row["family_id"]: row for row in rows},
        speech_rows=diagnostics["speech_rows"],
        v15_local_hash=reference["local_family_structural_sha256"],
        exposure=_real_exposure(tool, structural),
    )
    assert selection["role_priority"] == [
        "far_vocalization_asr_ambiguity",
        "far_continuity_anaphora",
    ]
    ledger = tool._load_private_governance_ledger(ROOT)
    assert selection["selected_family_keys"] == {
        role: row["family_key"]
        for role, row in ledger["selection"]["selected_identities"].items()
    }
    proof = selection["private_selection_proof"]
    by_key = {
        row["family_key"]: row
        for row in proof["vocalization_ranking"]
    }
    assert set(by_key) == {
        row["family_key"]
        for row in ledger["selection"]["complete_ranking"]
    }
    for row in ledger["selection"]["complete_ranking"]:
        assert by_key[row["family_key"]]["exclusion_reasons"] == row[
            "exclusion_reasons"
        ]
    selected_by_role = {
        row["family_role"]: row for row in selection["families"]
    }
    ranking_by_key = {
        row["family_key"]: row
        for row in ledger["selection"]["complete_ranking"]
    }
    for role, risk_field in (
        ("far_vocalization_asr_ambiguity", "vocalization_risk_tuple"),
        ("far_continuity_anaphora", "continuity_risk_tuple"),
    ):
        selected = selected_by_role[role]
        assert selected["risk_diagnostics"]["risk_tuple"] == ranking_by_key[
            selected["family_key"]
        ][risk_field]


def test_r22c_private_ledger_and_public_surface_are_bound_and_nonleaking(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    ledger_path = ROOT / tool.PRIVATE_GOVERNANCE_LEDGER
    assert oct(ledger_path.stat().st_mode & 0o777) == "0o600"
    ledger = tool._load_private_governance_ledger(ROOT)
    bindings = tool._public_commitment_hashes(ROOT)
    assert bindings["private_governance_commitment_sha256"] == ledger[
        "canonical_commitment_sha256"
    ]
    scan = tool.scan_public_surface_for_private_leakage(ROOT, ledger=ledger)
    assert scan["status"] == "PASS"
    assert scan["scan_scope"] == "repo_root_recursive_all_regular_files"
    assert scan["scan_policy_sha256"] == (
        tool._public_surface_scan_policy_sha256()
    )
    assert scan["private_token_values_reported"] is False
    assert ledger["governance_limits"]["runtime_fallback_permitted"] is False
    assert ledger["governance_limits"][
        "fallback_after_output_permitted"
    ] is False
    assert ledger["governance_limits"][
        "redraw_after_output_permitted"
    ] is False

    copied = tmp_path / tool.PRIVATE_GOVERNANCE_LEDGER
    copied.parent.mkdir(parents=True)
    copied.write_bytes(ledger_path.read_bytes())
    os.chmod(copied, 0o600)
    tampered = json.loads(copied.read_text(encoding="utf-8"))
    tampered["governance_limits"]["run_attempt_limit"] = 2
    copied.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(tool.CanaryError):
        tool._load_private_governance_ledger(tmp_path)


@pytest.mark.parametrize(
    "relative",
    [
        Path("tests_public/test_injected.py"),
        Path("scripts/injected.sh"),
        Path("src/injected/module.py"),
        Path("mvp/new_public_surface/notes.md"),
    ],
)
def test_r22d_repo_wide_public_scan_rejects_new_public_directory_token(
    tmp_path: Path, relative: Path
) -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    forbidden = next(
        record["token"]
        for record in tool._private_token_records(ledger)
        if record["classification"]
        in {"r22_fresh_selected", "r22_unselected_reserve"}
    )
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(f"public injection: {forbidden}\n", encoding="utf-8")
    with pytest.raises(
        tool.CanaryError,
        match="PUBLIC_SURFACE_PRIVATE_LEAKAGE",
    ):
        tool.scan_public_surface_for_private_leakage(
            tmp_path, ledger=ledger
        )


def test_r22f_public_scan_excludes_restricted_and_cache_but_scans_binary(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    forbidden = next(
        record["token"]
        for record in tool._private_token_records(ledger)
        if record["classification"]
        in {"r22_fresh_selected", "r22_unselected_reserve"}
    )
    restricted = tmp_path / "data/restricted/private.json"
    restricted.parent.mkdir(parents=True)
    restricted.write_text(forbidden, encoding="utf-8")
    cache = tmp_path / ".pytest_cache/private.txt"
    cache.parent.mkdir(parents=True)
    cache.write_text(forbidden, encoding="utf-8")
    result = tool.scan_public_surface_for_private_leakage(
        tmp_path, ledger=ledger
    )
    assert result["status"] == "PASS"
    assert result["counts"]["all_regular"] == 2
    assert result["counts"]["restricted_excluded"] == 1
    assert result["counts"]["policy_excluded"] == 1
    assert result["counts"]["raw_scanned"] == 0


def _forbidden_public_token(tool, ledger: dict) -> str:
    return next(
        record["token"]
        for record in tool._private_token_records(ledger)
        if record["classification"]
        in {"r22_fresh_selected", "r22_unselected_reserve"}
    )


def test_r22e_invalid_utf8_with_private_token_reports_both_failures(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    forbidden = _forbidden_public_token(tool, ledger).encode("utf-8")
    path = tmp_path / "future_public/invalid.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xffprivate=" + forbidden)
    with pytest.raises(tool.CanaryError) as exc_info:
        tool.scan_public_surface_for_private_leakage(
            tmp_path, ledger=ledger
        )
    error = str(exc_info.value)
    assert "PUBLIC_SURFACE_PRIVATE_LEAKAGE:future_public/invalid.md" in error
    assert "PUBLIC_SURFACE_UNDECODABLE_TEXT:future_public/invalid.md" in error
    assert forbidden.decode("utf-8") not in error


def test_r22e_invalid_utf8_without_private_token_fails_closed(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    path = tmp_path / "future_public/invalid.txt"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"ordinary public text\x80")
    with pytest.raises(
        tool.CanaryError,
        match=(
            "PUBLIC_SURFACE_UNDECODABLE_TEXT:"
            "future_public/invalid.txt"
        ),
    ):
        tool.scan_public_surface_for_private_leakage(
            tmp_path, ledger=ledger
        )


def test_r22e_text_suffix_binary_prefix_with_private_token_fails_closed(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    forbidden = _forbidden_public_token(tool, ledger).encode("utf-8")
    path = tmp_path / "future_public/mixed.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\x00\xffBINARY-PREFIX\n" + forbidden)
    with pytest.raises(tool.CanaryError) as exc_info:
        tool.scan_public_surface_for_private_leakage(
            tmp_path, ledger=ledger
        )
    error = str(exc_info.value)
    assert "PUBLIC_SURFACE_PRIVATE_LEAKAGE:future_public/mixed.json" in error
    assert "PUBLIC_SURFACE_UNDECODABLE_TEXT:future_public/mixed.json" in error


def test_r22e_normal_utf8_public_text_passes(tmp_path: Path) -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    path = tmp_path / "future_public/normal.md"
    path.parent.mkdir(parents=True)
    path.write_text("normal UTF-8: 声音与视频\n", encoding="utf-8")
    result = tool.scan_public_surface_for_private_leakage(
        tmp_path, ledger=ledger
    )
    assert result["status"] == "PASS"
    assert result["counts"]["all_regular"] == 1
    assert result["counts"]["raw_scanned"] == 1
    assert result["counts"]["utf8_validated"] == 1
    assert result["raw_bytes_private_token_scan"] is True
    assert result["strict_utf8_decoding"] is True


def test_r22e_restricted_invalid_utf8_does_not_affect_scan(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    forbidden = _forbidden_public_token(tool, ledger).encode("utf-8")
    path = tmp_path / "data/restricted/private.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff" + forbidden)
    result = tool.scan_public_surface_for_private_leakage(
        tmp_path, ledger=ledger
    )
    assert result["status"] == "PASS"
    assert result["counts"]["all_regular"] == 1
    assert result["counts"]["restricted_excluded"] == 1
    assert result["counts"]["raw_scanned"] == 0


def test_r22f_unknown_suffix_utf8_with_token_is_rejected(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    forbidden = _forbidden_public_token(tool, ledger)
    path = tmp_path / "future_public/no_known_suffix.weird"
    path.parent.mkdir(parents=True)
    path.write_text(f"ordinary prefix {forbidden}\n", encoding="utf-8")
    with pytest.raises(
        tool.CanaryError,
        match="PUBLIC_SURFACE_PRIVATE_LEAKAGE",
    ):
        tool.scan_public_surface_for_private_leakage(
            tmp_path, ledger=ledger
        )


def test_r22f_over_8mib_json_tail_token_is_rejected(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    forbidden = _forbidden_public_token(tool, ledger)
    path = tmp_path / "future_public/large.json"
    path.parent.mkdir(parents=True)
    with path.open("w", encoding="utf-8") as stream:
        stream.write('{"padding":"')
        stream.write("a" * (8 * 1024 * 1024 + 4096))
        stream.write(f'","tail":"{forbidden}"}}\n')
    with pytest.raises(
        tool.CanaryError,
        match="PUBLIC_SURFACE_PRIVATE_LEAKAGE",
    ):
        tool.scan_public_surface_for_private_leakage(
            tmp_path, ledger=ledger
        )


def test_r22f_large_clean_unknown_suffix_passes(tmp_path: Path) -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    path = tmp_path / "future_public/large.cleantext"
    path.parent.mkdir(parents=True)
    with path.open("w", encoding="utf-8") as stream:
        for _ in range(9):
            stream.write("x" * 1024 * 1024)
        stream.write("\n")
    result = tool.scan_public_surface_for_private_leakage(
        tmp_path, ledger=ledger
    )
    assert result["status"] == "PASS"
    assert result["counts"]["raw_scanned"] == 1
    assert result["counts"]["utf8_validated"] == 1
    assert result["size_based_skip_permitted"] is False


@pytest.mark.parametrize("payload", [b"valid\x00utf8", b"valid\x01utf8"])
def test_r22f_valid_utf8_binary_controls_are_rejected(
    tmp_path: Path, payload: bytes
) -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    path = tmp_path / "future_public/control.unknown"
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    with pytest.raises(
        tool.CanaryError,
        match="PUBLIC_SURFACE_BINARY_CONTROL_BYTES",
    ):
        tool.scan_public_surface_for_private_leakage(
            tmp_path, ledger=ledger
        )


def test_r22f_binary_without_token_ignores_decode_but_token_fails(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    path = tmp_path / "future_public/blob.bin"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\x00\xffclean")
    result = tool.scan_public_surface_for_private_leakage(
        tmp_path, ledger=ledger
    )
    assert result["status"] == "PASS"
    assert result["counts"]["binary_excluded"] == 1
    assert result["counts"]["raw_scanned"] == 1
    assert result["counts"]["utf8_validated"] == 0

    forbidden = _forbidden_public_token(tool, ledger).encode("utf-8")
    path.write_bytes(b"\x00\xff" + forbidden)
    with pytest.raises(
        tool.CanaryError,
        match="PUBLIC_SURFACE_PRIVATE_LEAKAGE",
    ):
        tool.scan_public_surface_for_private_leakage(
            tmp_path, ledger=ledger
        )


@pytest.mark.parametrize(
    ("fault", "failure_code"),
    [
        ("stat", "PUBLIC_SURFACE_STAT_ERROR"),
        ("open", "PUBLIC_SURFACE_OPEN_ERROR"),
        ("read", "PUBLIC_SURFACE_READ_ERROR"),
    ],
)
def test_r22f_stat_open_read_faults_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    failure_code: str,
) -> None:
    tool = load_tool()
    ledger = tool._load_private_governance_ledger(ROOT)
    path = tmp_path / "future_public/fault.txt"
    path.parent.mkdir(parents=True)
    path.write_text("clean\n", encoding="utf-8")

    if fault == "stat":
        original = tool._public_surface_stat

        def broken_stat(candidate: Path):
            if candidate == path:
                raise OSError(errno.EIO, "synthetic stat failure")
            return original(candidate)

        monkeypatch.setattr(tool, "_public_surface_stat", broken_stat)
    elif fault == "open":
        original = tool._public_surface_open

        def broken_open(candidate: Path):
            if candidate == path:
                raise OSError(errno.EIO, "synthetic open failure")
            return original(candidate)

        monkeypatch.setattr(tool, "_public_surface_open", broken_open)
    else:
        monkeypatch.setattr(
            tool,
            "_public_surface_read",
            lambda stream: (_ for _ in ()).throw(
                OSError(errno.EIO, "synthetic read failure")
            ),
        )
    with pytest.raises(tool.CanaryError, match=failure_code):
        tool.scan_public_surface_for_private_leakage(
            tmp_path, ledger=ledger
        )


def test_r22d_public_scan_path_allowlist_is_narrow_and_tested() -> None:
    tool = load_tool()
    assert (
        tool._public_surface_path_classification(
            Path(
                "data/rehearsal_plan/"
                "external_gateway_strong_agent_smoke_run_v1/run/private.json"
            )
        )
        == "allowlisted_generated_private_output"
    )
    assert (
        tool._public_surface_path_classification(
            Path(
                "data/rehearsal_plan/"
                "external_gateway_strong_agent_smoke_run_v2/private.json"
            )
        )
        is None
    )
    assert (
        tool._public_surface_path_classification(
            Path("orchestration/results/private.txt")
        )
        == "allowlisted_generated_private_output"
    )
    assert (
        tool._public_surface_path_classification(
            Path("orchestration/new_results/private.txt")
        )
        is None
    )
    assert (
        tool._public_surface_path_classification(
            Path("mvp/generated/full/media/large.mp4")
        )
        == "binary"
    )
    assert (
        tool._public_surface_path_classification(
            Path("mvp/generated/full/not_media/large.unknown")
        )
        is None
    )


def test_plan_status_exposes_pipeline_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = load_tool()
    plan = tool.validate_plan(ROOT)
    assert plan["schema_version"].endswith("/27.0")
    assert "accepted_factor_manifest.json" in plan[
        "artifacts_for_future_authorized_run"
    ]
    assert set(plan["artifacts_for_future_authorized_run"]) == {
        *tool.OUTPUT_FILES,
        "seal.json",
        "attempt marker (external governance evidence)",
    }
    status = tool.plan_status(ROOT)
    assert status["status"] == tool.READY
    assert isinstance(
        status["historical_plan_pipeline_hash_current"], bool
    )
    assert status["current"] is True
    assert status["old_authorization_receipts_valid"] is False
    assert status["model_calls"] == 0
    assert status["media_decodes"] == 0
    monkeypatch.setattr(
        tool, "_parent_tool_hash", lambda root: "sha256:simulated-drift"
    )
    with pytest.raises(
        tool.CanaryError,
        match="CANARY_PLAN_EMBEDDED_AUTHORIZATION_INVALID",
    ):
        tool.plan_status(ROOT)


def test_r21_plan_rejects_stale_embedded_authorization_hashes(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    plan = json.loads(
        (
            ROOT
            / "data/rehearsal_plan/"
            "p23_102_query_authoring_v2_canary2.json"
        ).read_text(encoding="utf-8")
    )
    plan["authorization"]["main_pipeline_sha256"] = "sha256:" + "0" * 64
    plan["plan_payload_sha256"] = tool.parent.semantic_hash(
        {
            key: value
            for key, value in plan.items()
            if key != "plan_payload_sha256"
        }
    )
    path = tmp_path / "stale-embedded-authorization.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(
        tool.CanaryError,
        match="CANARY_PLAN_EMBEDDED_AUTHORIZATION_INVALID",
    ):
        tool.validate_plan(ROOT, path)


def test_r22b_plan_rejects_old_selection_contract(tmp_path: Path) -> None:
    tool = load_tool()
    plan = json.loads(
        (ROOT / tool.DEFAULT_PLAN).read_text(encoding="utf-8")
    )
    plan["selection"]["algorithm"] = (
        "v15_local_structural_hash_plus_machine_diagnostic_"
        "lexicographic_risk_with_structural_hash_ties"
    )
    plan["plan_payload_sha256"] = tool.parent.semantic_hash(
        {
            key: value
            for key, value in plan.items()
            if key != "plan_payload_sha256"
        }
    )
    path = tmp_path / "old-selection-plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(
        tool.CanaryError,
        match="CANARY_PLAN_SELECTION_CONTRACT_INVALID",
    ):
        tool.validate_plan(ROOT, path)


def test_canary2_inherits_r6_local_clause_and_component_gates() -> None:
    tool = load_tool()
    exact_local = {
        "visual_description": (
            "A person is crumpling a plastic bag on a table."
        ),
        "visual_query": "person crumpling a plastic bag on a table",
        "ambient_description": (
            "The sound of crumpling plastic is heard."
        ),
        "ambient_query": "sound of crumpling plastic",
    }
    family = {
        "family_key": "family-r6-local",
        "shape": "one_component",
        "intervals": [{"clip_key": "clip-r6-local"}],
    }
    assembled = tool.parent.assemble_family_factors(
        family,
        [
            {
                key: exact_local[key]
                for key in tool.parent.VISUAL_OUTPUT_SCHEMA
            }
        ],
        [
            tool.parent.validate_ambient_factor_output(
                {
                    "event_kind": "crinkle",
                    "acoustic_properties": {
                        "timbre": "crisp",
                        "loudness": "soft",
                        "temporal_pattern": "repeated",
                    },
                }
            )
        ],
        {"relation_kind": "local_cooccurrence"},
    )
    assert tool.parent.validate_component_local_composition(
        family, assembled["components"], assembled
    )["status"] == "PASS"

    cross_component = {
        "visual_description": (
            "A hand aligns a bracket beside another component."
        ),
        "visual_query": "hand aligning a bracket beside a fitting",
        "ambient_description": "A brief metallic tap marks the alignment.",
        "ambient_query": "brief metallic tap during bracket alignment",
    }
    causal = {
        **cross_component,
        "visual_description": "A hand aligns a bracket beside a fitting.",
        "ambient_description": (
            "The bracket movement triggers a brief metallic tap."
        ),
    }
    with pytest.raises(
        tool.parent.AuthoringError,
        match="MODEL_COMPONENT_CROSS_REFERENCE_FORBIDDEN",
    ):
        tool.parent.validate_component_factor_output(cross_component)
    with pytest.raises(
        tool.parent.AuthoringError,
        match="MODEL_CAUSAL_LANGUAGE_FORBIDDEN",
    ):
        tool.parent.validate_component_factor_output(causal)
    assert tool.parent._component_local_continuity_evidence(
        "The same person continues the action again."
    )["unsupported"] is True


def test_canary2_inherits_r18_source_hint_rejection_and_acoustic_pass() -> None:
    tool = load_tool()
    source_free = {
        "event_kind": "crinkle",
        "acoustic_properties": {
            "timbre": "crisp",
            "loudness": "soft",
            "temporal_pattern": "repeated",
        },
    }
    with pytest.raises(
        tool.parent.AuthoringError,
        match="MODEL_AMBIENT_SOURCE_HINT_FIELD_FORBIDDEN",
    ):
        tool.parent.validate_ambient_factor_output(
            {**source_free, "source_hint": "paper"}
        )
    accepted = tool.parent.validate_ambient_factor_output(source_free)
    assert accepted["ambient_description"] == (
        "A soft repeated crisp crinkle is audible."
    )
    assert accepted["ambient_query"] == (
        "Find the audible crinkle event matching crisp, repeated, soft."
    )


def test_r7_parent_local_coreference_and_throat_clearing_regressions() -> None:
    tool = load_tool()
    parent = tool.parent
    exact_ambient = (
        "A person clears their throat and then places a pot lid on the counter."
    )
    local = parent._component_local_continuity_evidence(exact_ambient)
    assert local["unsupported"] is False
    assert local["continuity_reference_terms"] == []
    assert local["local_possessive_coreference_exemptions"][0]["term"] == (
        "their"
    )
    assert parent._acoustic_concepts(exact_ambient) == {"throat-clearing"}
    assert parent._specific_acoustic_terms(exact_ambient) == [
        "throat-clearing"
    ]
    for rejected in (
        "Their throat clearing is audible.",
        "The same person clears their throat again.",
    ):
        assert parent._component_local_continuity_evidence(rejected)[
            "unsupported"
        ] is True
    cross_component = parent._unsupported_continuity_evidence(
        (
            "A person clears their throat, then their hand places a pot lid "
            "on the counter."
        ),
        reject_agent_terms=False,
        reject_reused_entities=False,
    )
    assert cross_component["unsupported"] is True
    policy = parent._human_vocalization_policy(
        "A person clears their throat and speaks several words."
    )
    assert policy["clearly_nonlexical_non_speech"] is False
    assert policy["lexical_speech_terms"]


@pytest.mark.parametrize(
    "text",
    [
        "color choice impacts appearance",
        "person taps a button",
        "clicks a menu button",
        "hand scratches a label",
        "sound menu button click",
    ],
)
def test_r9_canary2_inherits_ambiguous_action_fail_closed(
    text: str,
) -> None:
    tool = load_tool()
    assert tool.parent._specific_acoustic_terms(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "a sharp tap is heard",
        "metallic clicking sounds",
        "scraping noise",
        "a knock echoes",
        "a metallic clank",
        "a faint hiss",
        "throat clearing",
    ],
)
def test_r9_canary2_inherits_valid_acoustic_context(text: str) -> None:
    tool = load_tool()
    assert tool.parent._specific_acoustic_terms(text)


@pytest.mark.parametrize(
    ("text", "accepted"),
    [
        ("scraping noise", True),
        ("throat clearing", True),
        ("sound of a button click", True),
        ("audible clicking", True),
        ("a knock echoes", True),
        ("an echo is heard", True),
        ("the design echoes a theme", False),
        ("echo button", False),
        ("a beep sounds while the design echoes a theme", False),
        ("sound quiet", False),
        ("a beep sounds while a person taps a button", False),
        ("color choice impacts sound quality", False),
        ("click sound menu button", False),
        ("a beep sounds while a person asks a question", False),
        ("single beep", True),
        ("ready beep", True),
    ],
)
def test_r10_canary2_inherits_end_to_end_ambient_validation(
    text: str, accepted: bool
) -> None:
    tool = load_tool()
    context = (
        nullcontext()
        if accepted
        else pytest.raises(tool.parent.AuthoringError)
    )
    with context:
        tool.parent.validate_legacy_ambient_factor_output(
            {
                "ambient_description": text,
                "ambient_query": f"which {text} is audible",
            }
        )


def test_r11_canary2_inherits_controlled_echo_marker_end_to_end() -> None:
    tool = load_tool()
    assert tool.parent.validate_legacy_ambient_factor_output(
        {
            "ambient_description": "a knock echoes",
            "ambient_query": "which knock echoes",
        }
    )


def test_r15_canary2_inherits_visual_by_fail_closed_end_to_end() -> None:
    tool = load_tool()
    description = "A hand lifts a metal bowl from a counter."
    for query in (
        "Which metal bowl is a hand lifting from the counter?",
        "Which metal bowl is being lifted from the counter?",
        "metal bowl lifting from the counter",
    ):
        value = {
            "visual_description": description,
            "visual_query": query,
        }
        assert tool.parent.validate_visual_factor_output(value) == value
    for query in (
        "Which metal bowl is lifted by the hand from the counter?",
        "Which metal bowl is lifted by a worker from the counter?",
        "Which metal bowl rests by the hand on the counter?",
    ):
        with pytest.raises(
            tool.parent.AuthoringError,
            match="MODEL_VISUAL_QUERY_SEMANTIC_ADDITION:by",
        ):
            tool.parent.validate_visual_factor_output(
                {
                    "visual_description": description,
                    "visual_query": query,
                }
            )
    nearby_value = {
        "visual_description": (
            "A hand lifts a nearby metal bowl from a counter."
        ),
        "visual_query": (
            "Which nearby metal bowl is a hand lifting from the counter?"
        ),
    }
    assert (
        tool.parent.validate_visual_factor_output(nearby_value)
        == nearby_value
    )
    for description, query in (
        (
            "A worker and a sealed box stand nearby.",
            "Which sealed box is sealed by the worker?",
        ),
        (
            "A covered bowl sits while a hand rests nearby.",
            "Which covered bowl is covered by the hand?",
        ),
        (
            "A red bowl sits while a hand rests nearby.",
            "Which red bowl is red by the hand?",
        ),
    ):
        with pytest.raises(
            tool.parent.AuthoringError,
            match="MODEL_VISUAL_QUERY_SEMANTIC_ADDITION:by",
        ):
            tool.parent.validate_visual_factor_output(
                {
                    "visual_description": description,
                    "visual_query": query,
                }
            )


def test_r13_canary2_inherits_postposed_auditory_marker_end_to_end() -> None:
    tool = load_tool()
    value = {
        "ambient_description": "A bell rings audibly.",
        "ambient_query": "Which bell rings audibly?",
    }
    assert tool.parent.validate_legacy_ambient_factor_output(value) == value
    with pytest.raises(
        tool.parent.AuthoringError,
        match="MODEL_AMBIENT_AMBIGUOUS_ACOUSTIC_CONTEXT_INVALID:"
        "ambient_description",
    ):
        tool.parent.validate_legacy_ambient_factor_output(
            {
                "ambient_description": (
                    "A bell rings while a person audibly taps a button."
                ),
                "ambient_query": "Which bell rings audibly?",
            }
        )


def test_authorization_is_exact_and_fail_closed(tmp_path: Path) -> None:
    tool = load_tool()
    fingerprints = {
        "canary_config_sha256": "sha256:config",
        "selected_family_hashes": {"role": "sha256:family"},
        "selection_algorithm": tool.SELECTION_ALGORITHM,
        "selection_version": tool.SELECTION_VERSION,
        "private_governance_ledger_sha256": "sha256:private-ledger",
        "private_governance_commitment_sha256": "sha256:private-commitment",
        "public_selection_commitment_sha256": "sha256:public-commitment",
        "main_pipeline_sha256": "sha256:main",
        "canary_pipeline_sha256": "sha256:canary2",
        "bundle_file_hashes": {"family_registry.json": "sha256:bundle"},
        "selection_input_hashes": {"machine_index": "sha256:index"},
        "model_hashes": {"authoring": {"sha256": "sha256:model"}},
        "media_sha256": "sha256:media",
        "subset_payload_sha256": "sha256:subset",
        "prompt_manifest_expected_hashes": {
            "base_prompt_manifest_sha256": "sha256:prompts"
        },
    }
    receipt = {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary2-authorization/3.0"
        ),
        "canary_id": tool.CANARY_ID,
        "decision": "AUTHORIZED",
        "authorization_id": "synthetic-one-run",
        "authorized_at": "2026-10-15T00:00:00Z",
        "single_local_run": True,
        **fingerprints,
        "output_path": tool.DEFAULT_OUTPUT.as_posix(),
    }
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert tool.validate_authorization(
        tmp_path,
        path,
        fingerprints=fingerprints,
        output=tool.DEFAULT_OUTPUT,
    )["authorization_id"] == "synthetic-one-run"
    old_receipt = dict(receipt)
    old_receipt["schema_version"] = (
        "av-trace.p23-102-query-authoring-v2-canary2-authorization/2.0"
    )
    path.write_text(json.dumps(old_receipt), encoding="utf-8")
    with pytest.raises(
        tool.CanaryError,
        match="CANARY_EXECUTION_AUTHORIZATION_SCOPE_MISMATCH",
    ):
        tool.validate_authorization(
            tmp_path,
            path,
            fingerprints=fingerprints,
            output=tool.DEFAULT_OUTPUT,
        )
    for field in (
        "main_pipeline_sha256",
        "canary_pipeline_sha256",
        "selection_input_hashes",
        "selected_family_hashes",
        "selection_algorithm",
        "private_governance_ledger_sha256",
        "public_selection_commitment_sha256",
        "output_path",
    ):
        invalid = dict(receipt)
        invalid[field] = "tampered"
        path.write_text(json.dumps(invalid), encoding="utf-8")
        with pytest.raises(
            tool.CanaryError,
            match="CANARY_EXECUTION_AUTHORIZATION_SCOPE_MISMATCH",
        ):
            tool.validate_authorization(
                tmp_path,
                path,
                fingerprints=fingerprints,
                output=tool.DEFAULT_OUTPUT,
            )


def test_exact_parent_gate_outcomes_are_captured() -> None:
    tool = load_tool()
    parent = tool.parent
    queries = [
        {
            "query_key": "ambient-good",
            "query_kind": "ambient",
            "query_scope": "handle",
            "family_key": "f",
            "clip_key": "c",
            "query_text": "What sharp clanking sound occurs near a metal pan?",
        },
        {
            "query_key": "visual-bad-reference",
            "query_kind": "visual",
            "query_scope": "handle",
            "family_key": "f",
            "clip_key": "c",
            "query_text": "The person moves it there.",
        },
    ]
    descriptions = [
        {
            "description_key": "ambient-description",
            "description_kind": "ambient",
            "family_key": "f",
            "clip_key": "c",
            "description_text": "A brief metallic clank rings out.",
        }
    ]
    ambient = parent.ambient_acoustic_grounding_audit(
        queries,
        descriptions,
        embed_ambient=parent._synthetic_embed,
    )
    standalone = parent.standalone_reference_audit(queries)
    quarantine = parent.asr_vocalization_quarantine_audit(
        [
            {
                **queries[0],
                "query_key": "ambient-vocal",
                "query_text": "A person speaks softly.",
            }
        ],
        [],
        transcripts_by_clip={"c": "Oh"},
    )
    assert ambient["status"] == "PASS"
    assert standalone["status"] == "FAIL"
    assert standalone["findings"][0]["kind"] == "unresolved_handle_reference"
    assert quarantine["status"] == "FAIL"
    assert quarantine["findings"][0]["kind"] == "lexical_speech_forbidden"


def test_failure_accounting_is_written_before_capsule(tmp_path: Path) -> None:
    tool = load_tool()
    staging = tmp_path / "staging"
    staging.mkdir()
    error = tool.CanaryError("MODEL_OUTPUT_CONSTRAINED_JSON_INVALID_SEQUENCE")
    tool._write_exception_accounting(staging, error)
    accounting = json.loads(
        (staging / "failure_accounting.json").read_text(encoding="utf-8")
    )
    gates = json.loads(
        (staging / "gate_findings.json").read_text(encoding="utf-8")
    )
    assert accounting["status"] == "FAIL_CLOSED"
    assert accounting["constrained_json_failures"] == 1
    assert accounting["failure_capsule_required"] is True
    assert gates["status"] == "NOT_REACHED"


def _media_contract(media_present: bool) -> dict:
    return {
        "media_present": media_present,
        "video_placeholders": 1 if media_present else 0,
        "audio_placeholders": 0,
        "video_tensors": 1 if media_present else 0,
        "audio_tensors": 1 if media_present else 0,
        "video_placeholder_tokens": 1 if media_present else 0,
        "audio_placeholder_tokens": 1 if media_present else 0,
        "media_feature_keys": (
            [
                "feature_attention_mask",
                "input_features",
                "pixel_values_videos",
                "video_grid_thw",
            ]
            if media_present
            else []
        ),
        "use_audio_in_video": True if media_present else None,
        "assistant_prefill": "{",
        "assistant_prefill_tokens": 1,
    }


def _attempt_row(
    tool,
    *,
    prompt: dict,
    factor_key: str,
    family_key: str,
    factor_kind: str,
    component_ordinal: int | None,
    raw: str,
    parsed: dict,
    clip_record: dict | None,
) -> dict:
    media_present = factor_kind in {"visual", "ambient"}
    conversation = tool.parent._model_conversation(prompt)
    rendered = json.dumps(conversation, sort_keys=True)
    if factor_kind == "visual":
        media_contract = {
            **_media_contract(True),
            "media_mode": "video_only",
            "audio_placeholders": 0,
            "audio_tensors": 0,
            "audio_placeholder_tokens": 0,
            "media_feature_keys": [
                "pixel_values_videos",
                "video_grid_thw",
            ],
            "use_audio_in_video": False,
        }
    elif factor_kind == "ambient":
        media_contract = {
            **_media_contract(True),
            "media_mode": "audio_only",
            "video_placeholders": 0,
            "audio_placeholders": 1,
            "video_tensors": 0,
            "video_placeholder_tokens": 0,
            "media_feature_keys": [
                "feature_attention_mask",
                "input_features",
            ],
            "use_audio_in_video": None,
        }
    else:
        media_contract = {
            **_media_contract(False),
            "media_mode": "text_only",
        }
    raw_bytes = raw.encode("utf-8")
    return {
        "family_key": family_key,
        "factor_key": factor_key,
        "factor_kind": factor_kind,
        "component_ordinal": component_ordinal,
        "attempt": 1,
        "attempt_kind": "initial",
        "raw_output": raw,
        "raw_output_bytes": len(raw_bytes),
        "raw_output_base64": __import__("base64").b64encode(
            raw_bytes
        ).decode("ascii"),
        "raw_output_sha256": (
            "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
        ),
        "parsed_output_sha256": (
            tool.parent._parsed_output_binding_hash(
                factor_kind,
                (
                    tool.parent._accepted_ambient_factor(parsed)
                    if factor_kind == "ambient"
                    else parsed
                ),
            )
        ),
        "parser_error": None,
        "prior_parser_error": None,
        "prior_raw_output_sha256": None,
        "exact_conversation": conversation,
        "exact_conversation_sha256": tool.parent.semantic_hash(conversation),
        "rendered_prompt": rendered,
        "rendered_prompt_sha256": (
            "sha256:" + hashlib.sha256(rendered.encode()).hexdigest()
        ),
        "rendered_prompt_bytes": len(rendered.encode()),
        "system_prompt_sha256": prompt["system_prompt_sha256"],
        "user_payload_sha256": prompt["user_payload_sha256"],
        "combined_prompt_sha256": prompt["combined_prompt_sha256"],
        "media_modality": (
            factor_kind
            if factor_kind in {"visual", "ambient"}
            else None
        ),
        "clip_keys": [clip_record["clip_key"]] if clip_record else [],
        "clip_manifest_hashes": (
            [
                {
                    "clip_key": clip_record["clip_key"],
                    "start_us": clip_record["start_us"],
                    "end_us": clip_record["end_us"],
                    "duration_us": clip_record["duration_us"],
                    (
                        "video_sha256"
                        if factor_kind == "visual"
                        else "audio_sha256"
                    ): clip_record[
                        (
                            "video_sha256"
                            if factor_kind == "visual"
                            else "audio_sha256"
                        )
                    ],
                }
            ]
            if clip_record
            else []
        ),
        "model_identity": tool._model_identities()["authoring"],
        "media_present": media_present,
        "media_contract": media_contract,
        "media_contract_sha256": tool.parent.semantic_hash(media_contract),
        "schema_only_repair": False,
        "semantic_repair_used": False,
        "retry_used": False,
        **json.loads(
            json.dumps(
                tool.parent.trusted_ambient_constraint_context()[
                    "attempt_constraint"
                    if factor_kind == "ambient"
                    else "json_boundary_constraint"
                ]
            )
        ),
    }


def _sealed_synthetic_output(
    tool, tmp_path: Path, *, content_variant: int = 0
) -> Path:
    parent = tool.parent
    structural, machine_rows, speech_rows = synthetic_inputs(tool)
    selection = tool.select_canary_families(
        structural,
        machine_family_rows=machine_rows,
        speech_rows=speech_rows,
        v15_local_hash=tool._family_hash(structural["families"][0]),
    )
    subset = tool.build_subset_structural(structural, selection)
    prompt_manifest = parent.build_prompt_manifest(subset)
    visual_prompt_by_key = {
        (
            f"{row['family_key']}:component:"
            f"{row['component_ordinal']}:visual"
        ): row
        for row in prompt_manifest["visual_prompts"]
    }
    ambient_prompt_by_key = {
        (
            f"{row['family_key']}:component:"
            f"{row['component_ordinal']}:ambient"
        ): row
        for row in prompt_manifest["ambient_prompts"]
    }
    target_records = [
        {
            **row,
            "video_sha256": f"sha256:video:{row['clip_key']}",
            "audio_sha256": f"sha256:audio:{row['clip_key']}",
        }
        for row in subset["targets"]
    ]
    target_by_key = {row["clip_key"]: row for row in target_records}
    parsed = {}
    attempts = []
    vocabulary = [
        {
            "nouns": ["ladle", "tray", "cup", "plate", "spoon"],
            "sounds": ["clank", "tap", "scrape", "click", "thud"],
            "surfaces": ["zone1", "zone2", "zone3", "zone4", "zone5"],
            "actions": ["rises", "rotates", "slides", "tilts", "lowers"],
            "prepositions": ["above", "under", "across", "inside", "outside"],
        },
        {
            "nouns": ["kettle", "bowl", "fork", "pan", "mug"],
            "sounds": ["ring", "knock", "rattle", "chime", "clang"],
            "surfaces": ["rack1", "rack2", "rack3", "rack4", "rack5"],
            "actions": ["shifts", "turns", "glides", "tips", "drops"],
            "prepositions": ["over", "beneath", "along", "within", "beyond"],
        },
    ][content_variant]
    nouns = vocabulary["nouns"]
    sounds = vocabulary["sounds"]
    component_index = 0
    for family_row in subset["families"]:
        components = []
        clauses = []
        for ordinal, _interval in enumerate(family_row["intervals"], 1):
            noun = nouns[component_index]
            sound = sounds[component_index]
            surface = vocabulary["surfaces"][component_index]
            action = vocabulary["actions"][component_index]
            preposition = vocabulary["prepositions"][component_index]
            component_index += 1
            ambient = parent._accepted_ambient_factor(
                {
                    "event_kind": sound,
                    "acoustic_properties": {
                        "timbre": (
                            "metallic"
                            if component_index % 2
                            else "crisp"
                        ),
                        "loudness": (
                            "soft" if ordinal == 1 else "loud"
                        ),
                        "temporal_pattern": (
                            "brief" if ordinal == 1 else "repeated"
                        ),
                    },
                }
            )
            component = {
                "visual_description": (
                    f"A {noun} {action} {preposition} {surface}."
                ),
                "visual_query": (
                    f"{noun} {action} {preposition} {surface}"
                ),
                **ambient,
            }
            components.append({"ordinal": ordinal, **component})
            clauses.append(
                {
                    "visual_summary": component["visual_description"],
                    "ambient_summary": component["ambient_description"],
                }
            )
            clip_record = target_by_key[
                family_row["intervals"][ordinal - 1]["clip_key"]
            ]
            for factor_kind, prompts in (
                ("visual", visual_prompt_by_key),
                ("ambient", ambient_prompt_by_key),
            ):
                factor_key = (
                    f"{family_row['family_key']}:component:"
                    f"{ordinal}:{factor_kind}"
                )
                factor = (
                    {
                        key: component[key]
                        for key in parent.VISUAL_OUTPUT_SCHEMA
                    }
                    if factor_kind == "visual"
                    else component["ambient_semantics"]
                )
                raw = json.dumps(factor, sort_keys=True)
                attempts.append(
                    _attempt_row(
                        tool,
                        prompt=prompts[factor_key],
                        factor_key=factor_key,
                        family_key=family_row["family_key"],
                        factor_kind=factor_kind,
                        component_ordinal=ordinal,
                        raw=raw,
                        parsed=factor,
                        clip_record=clip_record,
                    )
                )
        composition = {
            "relation_kind": (
                "local_cooccurrence"
                if len(components) == 1
                else "ordered_1_then_2"
            )
        }
        parsed[family_row["family_key"]] = {
            "components": components,
            **composition,
            **parent._mechanical_composition_texts(
                components,
                composition,
                family_shape=family_row["shape"],
            ),
        }
        raw = json.dumps(composition, sort_keys=True)
        composition_prompt = parent._resolved_composition_prompt(
            family_row,
            [
                {
                    key: value
                    for key, value in component.items()
                    if key != "ordinal"
                }
                for component in components
            ],
        )
        prompt_manifest["resolved_composition_prompts"].append(
            composition_prompt
        )
        contract_row = next(
            row
            for row in prompt_manifest["composition_contracts"]
            if row["family_key"] == family_row["family_key"]
        )
        contract_row["resolved"] = True
        contract_row["resolved_user_payload_sha256"] = composition_prompt[
            "user_payload_sha256"
        ]
        contract_row["resolved_combined_prompt_sha256"] = (
            composition_prompt["combined_prompt_sha256"]
        )
        attempts.append(
            _attempt_row(
                tool,
                prompt=composition_prompt,
                factor_key=(
                    f"{family_row['family_key']}:family_composition"
                ),
                family_key=family_row["family_key"],
                factor_kind="family_composition",
                component_ordinal=None,
                raw=raw,
                parsed=composition,
                clip_record=None,
            )
        )
    accepted = parent.build_accepted_factor_manifest(
        subset, parsed, attempts
    )
    with tool._parent_subset_counts():
        queries, descriptions = parent.materialize_query_records(
            subset, parsed, accepted
        )
        asr_inventory = {
            "schema_version": "synthetic-asr/1.0",
            "rows": [
                {
                    "clip_key": row["clip_key"],
                    "normalized_transcript": "",
                    "normalized_transcript_sha256": parent.semantic_hash(""),
                }
                for row in subset["targets"]
            ],
        }
        audits = parent.audit_authored_content(
            subset,
            queries,
            descriptions,
            transcripts_by_clip={
                row["clip_key"]: "" for row in subset["targets"]
            },
            embed_visual=parent._synthetic_embed,
            embed_ambient=parent._synthetic_embed,
        )
    assert audits["status"] == "PASS"
    audits["input_digest"] = parent._audit_input_digest(
        subset, queries, descriptions, asr_inventory
    )
    audits["input_hashes"] = {
        "prompt_manifest": parent.semantic_hash(prompt_manifest),
        "accepted_factor_manifest": accepted["manifest_payload_sha256"],
        "asr_inventory": parent.semantic_hash(asr_inventory),
        "queries": parent.semantic_hash(queries),
        "descriptions": parent.semantic_hash(descriptions),
    }
    audits["canary_scope"] = {
        "families": tool.EXPECTED_FAMILIES,
        "queries": tool.EXPECTED_QUERY_COUNT,
        "retrieval_vectors_read": False,
        "retrieval_scoring_executed": False,
    }
    output = tmp_path / tool.DEFAULT_OUTPUT
    output.mkdir(parents=True)
    synthetic_fingerprints = {
        "selection_algorithm": selection["algorithm"],
        "selection_version": selection.get(
            "version", tool.SELECTION_VERSION
        ),
        "private_governance_ledger_sha256": "sha256:private-ledger",
        "private_governance_commitment_sha256": "sha256:private-commitment",
        "public_selection_commitment_sha256": "sha256:public-commitment",
    }
    contract = {
        "schema_version": tool.CONTRACT_SCHEMA_VERSION,
        "canary_id": tool.CANARY_ID,
        "subset_payload_sha256": subset["subset_payload_sha256"],
        "input_fingerprints": synthetic_fingerprints,
        "selection_governance_bindings": {
            **synthetic_fingerprints,
            "replacement_generation": 1,
            "maximum_replacements": 2,
            "run_attempt_limit": 1,
            "redraw_after_output_permitted": False,
            "runtime_fallback_permitted": False,
        },
        "factorization": {
            **parent.ambient_derivation_contract(),
        },
    }
    target_manifest = {
        "schema_version": "synthetic-targets/1.0",
        "target_count": len(subset["targets"]),
        "source_media": {
            "path": "synthetic-media.mp4",
            "sha256": "sha256:synthetic-media",
        },
        "targets": target_records,
    }
    authored = {
        "schema_version": tool.AUTHORED_QUERIES_SCHEMA_VERSION,
        "canary_id": tool.CANARY_ID,
        "status": "MACHINE_AUTHORED_CANARY_AUDITED_NOT_SCORED",
        "query_count": len(queries),
        "description_count": len(descriptions),
        "accepted_factor_manifest_sha256": (
            accepted["manifest_payload_sha256"]
        ),
        "prompt_manifest_sha256": parent.semantic_hash(prompt_manifest),
        "audits_input_digest": audits["input_digest"],
        "audits_payload_sha256": parent.semantic_hash(audits),
        "queries": queries,
        "descriptions": descriptions,
        "retrieval_results": [],
        "scoring_results": [],
        "scientific_claims": [],
    }
    runtime = {
        "schema_version": tool.RUNTIME_SCHEMA_VERSION,
        "canary_id": tool.CANARY_ID,
        "wall_seconds": 1.0,
        "peak_rss_bytes": 1,
        "initial_authoring_calls": 13,
        "visual_initial_authoring_calls": 5,
        "ambient_initial_authoring_calls": 5,
        "composition_initial_authoring_calls": 3,
        "schema_only_repair_calls": 0,
        "authoring_model_calls": 13,
        "ambient_constraint": parent.ambient_constraint_contract(),
        "retrieval_scoring_executed": False,
    }
    parent.atomic_json(output / "canary2_contract.json", contract)
    parent.atomic_json(output / "canary2_subset_bundle.json", subset)
    parent.atomic_json(output / "target_manifest.json", target_manifest)
    parent.atomic_json(output / "prompt_manifest.json", prompt_manifest)
    parent.atomic_jsonl(output / "raw_attempts.jsonl", attempts)
    parent.atomic_json(output / "accepted_factor_manifest.json", accepted)
    parent.atomic_json(
        output / "ambient_semantic_tuple_collisions.json",
        parent.ambient_semantic_tuple_duplicate_audit(
            accepted,
            queries,
            scope="canary2",
        ),
    )
    parent.atomic_json(output / "asr_audit_inventory.json", asr_inventory)
    parent.atomic_json(output / "authored_queries.json", authored)
    parent.atomic_json(output / "audits.json", audits)
    tool._write_gate_artifacts(output, audits)
    parent.atomic_json(output / "resource_runtime.json", runtime)
    tool._seal_output(output)
    return output


@pytest.mark.parametrize(
    "tamper_kind",
    ["query", "description", "audits", "runtime", "raw_attempt"],
)
def test_canary2_sealed_validator_rejects_resealed_tampering(
    tmp_path: Path, tamper_kind: str
) -> None:
    tool = load_tool()
    output = _sealed_synthetic_output(tool, tmp_path)
    validated = tool.validate_output_integrity_only(tmp_path)
    assert validated["passed"] is True
    assert validated["input_authorization_verified"] is False
    assert validated["execution_attested"] is False
    assert validated["externally_attested"] is False
    with pytest.raises(
        tool.CanaryError,
        match="CANARY_OUTPUT_EXTERNAL_AUTHORIZATION_PATH_MISSING",
    ):
        tool.validate_output(tmp_path)
    for path in output.iterdir():
        os.chmod(path, 0o600)
    (output / "seal.json").unlink()
    if tamper_kind in {"query", "description"}:
        authored = tool.parent.load_json(output / "authored_queries.json")
        collection = (
            authored["queries"]
            if tamper_kind == "query"
            else authored["descriptions"]
        )
        text_key = (
            "query_text"
            if tamper_kind == "query"
            else "description_text"
        )
        collection[0][text_key] += " tampered"
        tool.parent.atomic_json(output / "authored_queries.json", authored)
    elif tamper_kind == "audits":
        audits = tool.parent.load_json(output / "audits.json")
        audits["failures"] = ["tampered"]
        tool.parent.atomic_json(output / "audits.json", audits)
    elif tamper_kind == "runtime":
        runtime = tool.parent.load_json(output / "resource_runtime.json")
        runtime["authoring_model_calls"] = 99
        tool.parent.atomic_json(output / "resource_runtime.json", runtime)
    else:
        rows = [
            json.loads(line)
            for line in (output / "raw_attempts.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        rows[0]["component_ordinal"] = 99
        tool.parent.atomic_jsonl(output / "raw_attempts.jsonl", rows)
    tool._seal_output(output)
    with pytest.raises(tool.CanaryError):
        tool.validate_output_integrity_only(tmp_path)


def _trusted_input_authorized_fixture(tool, tmp_path: Path, monkeypatch):
    output = _sealed_synthetic_output(tool, tmp_path)
    for path in output.iterdir():
        os.chmod(path, 0o600)
    (output / "seal.json").unlink()
    subset = tool.parent.load_json(output / "canary2_subset_bundle.json")
    selection = subset["selection"]
    selection_inputs = {"synthetic_selection": "sha256:trusted"}
    fingerprints = {
        "canary_config_sha256": "sha256:trusted-config",
        "selected_family_hashes": selection["selected_family_hashes"],
        "selection_algorithm": selection["algorithm"],
        "selection_version": selection.get(
            "version", tool.SELECTION_VERSION
        ),
        "private_governance_ledger_sha256": "sha256:private-ledger",
        "private_governance_commitment_sha256": "sha256:private-commitment",
        "public_selection_commitment_sha256": "sha256:public-commitment",
        "main_pipeline_sha256": "sha256:trusted-main",
        "canary_pipeline_sha256": "sha256:trusted-canary",
        "bundle_file_hashes": subset["source_bundle_file_hashes"],
        "selection_input_hashes": selection_inputs,
        "model_hashes": {"synthetic": {"sha256": "sha256:model"}},
        "media_sha256": "sha256:synthetic-media",
        "subset_payload_sha256": tool._subset_body_hash(subset),
        "prompt_manifest_expected_hashes": (
            tool._prompt_manifest_expected_hashes(subset)
        ),
    }
    receipt = {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary2-authorization/3.0"
        ),
        "canary_id": tool.CANARY_ID,
        "decision": "AUTHORIZED",
        "authorization_id": "synthetic-input-authorized-run",
        "authorized_at": "2026-10-15T00:00:00Z",
        "single_local_run": True,
        **fingerprints,
        "output_path": tool.DEFAULT_OUTPUT.as_posix(),
    }
    receipt_path = tmp_path / "trusted" / "authorization.json"
    receipt_path.parent.mkdir()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    marker_path = tool.attempt_marker_path(
        tmp_path / tool.DEFAULT_OUTPUT, receipt["authorization_id"]
    )
    marker = tool._create_attempt_marker(
        root=tmp_path,
        marker_path=marker_path,
        authorization_path=receipt_path,
        authorization_value=receipt,
        fingerprints=fingerprints,
    )
    contract = tool._contract_value(
        root=tmp_path,
        authorization_path=receipt_path,
        authorization_value=receipt,
        fingerprints=fingerprints,
        selection=selection,
        selection_inputs=selection_inputs,
        subset=subset,
        attempt_marker_path_value=marker_path,
        attempt_marker=marker,
    )
    tool.parent.atomic_json(output / "canary2_contract.json", contract)
    tool._seal_output(output)
    structural = {
        "file_hashes": subset["source_bundle_file_hashes"],
        "families": subset["families"],
        "targets": subset["targets"],
    }
    monkeypatch.setattr(
        tool,
        "_trusted_validation_context",
        lambda root, *, bundle, media: (
            structural,
            selection,
            selection_inputs,
            {"subset": subset, "fingerprints": fingerprints},
        ),
    )
    return output, receipt_path, subset, fingerprints


def _reseal(tool, output: Path) -> None:
    for path in output.iterdir():
        os.chmod(path, 0o600)
    (output / "seal.json").unlink(missing_ok=True)
    tool._seal_output(output)


def _sealed_target_records(tool, output: Path) -> list[dict]:
    return tool.parent.load_json(output / "target_manifest.json")["targets"]


def _stub_current_media_decode(
    tool, monkeypatch: pytest.MonkeyPatch, output: Path
) -> None:
    monkeypatch.setattr(
        tool,
        "_recompute_trusted_target_records",
        lambda root, *, media, expected_subset: _sealed_target_records(
            tool, output
        ),
    )


def test_validator_reports_input_authorization_without_execution_attestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    output, receipt, _, _ = _trusted_input_authorized_fixture(
        tool, tmp_path, monkeypatch
    )
    _stub_current_media_decode(tool, monkeypatch, output)
    validated = tool.validate_output(tmp_path, authorization=receipt)
    assert validated["passed"] is True
    assert validated["input_authorization_verified"] is True
    assert validated["execution_attested"] is False
    assert validated["externally_attested"] is False
    assert validated["validation_level"] == (
        "INTEGRITY_PLUS_CURRENT_INPUT_AUTHORIZATION_"
        "NOT_EXECUTION_ATTESTED"
    )


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "receipt_path",
        "receipt_hash",
        "old_receipt_code_drift",
        "subset_body",
        "prompt_binding",
        "model_binding",
        "media_binding",
    ],
)
def test_input_authorized_validator_rejects_binding_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper_kind: str,
) -> None:
    tool = load_tool()
    output, receipt, subset, fingerprints = _trusted_input_authorized_fixture(
        tool, tmp_path, monkeypatch
    )
    _stub_current_media_decode(tool, monkeypatch, output)
    contract = tool.parent.load_json(output / "canary2_contract.json")
    if tamper_kind == "receipt_path":
        contract["authorization_receipt_path"] = (
            tool.DEFAULT_OUTPUT / "authorization.json"
        ).as_posix()
        tool.parent.atomic_json(output / "canary2_contract.json", contract)
    elif tamper_kind == "receipt_hash":
        contract["authorization_receipt_sha256"] = "sha256:wrong"
        tool.parent.atomic_json(output / "canary2_contract.json", contract)
    elif tamper_kind == "old_receipt_code_drift":
        drifted = deepcopy(fingerprints)
        drifted["main_pipeline_sha256"] = "sha256:current-code-drift"
        monkeypatch.setattr(
            tool,
            "_trusted_validation_context",
            lambda root, *, bundle, media: (
                {},
                subset["selection"],
                contract["selection_input_hashes"],
                {"subset": subset, "fingerprints": drifted},
            ),
        )
    elif tamper_kind == "subset_body":
        changed = tool.parent.load_json(
            output / "canary2_subset_bundle.json"
        )
        changed["targets"][0]["start_us"] += 1
        changed["subset_payload_sha256"] = tool._subset_body_hash(changed)
        contract["subset_payload_sha256"] = changed[
            "subset_payload_sha256"
        ]
        contract["input_fingerprints"]["subset_payload_sha256"] = changed[
            "subset_payload_sha256"
        ]
        tool.parent.atomic_json(
            output / "canary2_subset_bundle.json", changed
        )
        tool.parent.atomic_json(output / "canary2_contract.json", contract)
    elif tamper_kind == "prompt_binding":
        attempts = [
            json.loads(line)
            for line in (output / "raw_attempts.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        attempts[0]["combined_prompt_sha256"] = "sha256:wrong"
        tool.parent.atomic_jsonl(output / "raw_attempts.jsonl", attempts)
    elif tamper_kind == "model_binding":
        attempts = [
            json.loads(line)
            for line in (output / "raw_attempts.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        attempts[0]["model_identity"]["revision"] = "wrong"
        tool.parent.atomic_jsonl(output / "raw_attempts.jsonl", attempts)
    else:
        attempts = [
            json.loads(line)
            for line in (output / "raw_attempts.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        attempts[0]["clip_manifest_hashes"][0]["video_sha256"] = (
            "sha256:wrong"
        )
        tool.parent.atomic_jsonl(output / "raw_attempts.jsonl", attempts)
    _reseal(tool, output)
    with pytest.raises(tool.CanaryError):
        tool.validate_output(tmp_path, authorization=receipt)


def test_noncoherent_reseal_is_rejected_by_integrity_and_input_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    output, receipt, subset, _ = _trusted_input_authorized_fixture(
        tool, tmp_path, monkeypatch
    )
    _stub_current_media_decode(tool, monkeypatch, output)
    attempts = [
        json.loads(line)
        for line in (output / "raw_attempts.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    attempts[0]["model_identity"]["revision"] = "attacker-resealed"
    tool.parent.atomic_jsonl(output / "raw_attempts.jsonl", attempts)
    contract = tool.parent.load_json(output / "canary2_contract.json")
    contract["model_identities"]["authoring"]["revision"] = (
        "attacker-resealed"
    )
    contract["authorization"]["main_pipeline_sha256"] = (
        "sha256:attacker-resealed"
    )
    contract["input_fingerprints"]["main_pipeline_sha256"] = (
        "sha256:attacker-resealed"
    )
    tool.parent.atomic_json(output / "canary2_contract.json", contract)
    authored = tool.parent.load_json(output / "authored_queries.json")
    authored["queries"][0]["query_text"] += " coordinated rewrite"
    tool.parent.atomic_json(output / "authored_queries.json", authored)
    audits = tool.parent.load_json(output / "audits.json")
    audits["input_digest"] = tool.parent._audit_input_digest(
        subset,
        authored["queries"],
        authored["descriptions"],
        tool.parent.load_json(output / "asr_audit_inventory.json"),
    )
    authored["audits_input_digest"] = audits["input_digest"]
    authored["audits_payload_sha256"] = tool.parent.semantic_hash(audits)
    tool.parent.atomic_json(output / "audits.json", audits)
    tool.parent.atomic_json(output / "authored_queries.json", authored)
    _reseal(tool, output)
    with pytest.raises(tool.CanaryError):
        tool.validate_output(tmp_path, authorization=receipt)


def test_complete_coherent_replacement_is_never_execution_attested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fully coordinated synthetic output can satisfy deterministic gates.

    The fixture is generated entirely inside this test rather than by a model
    execution.  Passing validation therefore proves only integrity plus exact
    current-input authorization, not an execution transcript.
    """

    tool = load_tool()
    output, receipt, _, _ = _trusted_input_authorized_fixture(
        tool, tmp_path, monkeypatch
    )
    contract = tool.parent.load_json(output / "canary2_contract.json")
    for path in output.iterdir():
        os.chmod(path, 0o600)
    shutil.rmtree(output)
    replacement = _sealed_synthetic_output(
        tool, tmp_path, content_variant=1
    )
    for path in replacement.iterdir():
        os.chmod(path, 0o600)
    (replacement / "seal.json").unlink()
    tool.parent.atomic_json(
        replacement / "canary2_contract.json", contract
    )
    tool._seal_output(replacement)
    _stub_current_media_decode(tool, monkeypatch, replacement)

    validated = tool.validate_output(tmp_path, authorization=receipt)

    assert validated["passed"] is True
    assert validated["input_authorization_verified"] is True
    assert validated["execution_attested"] is False
    assert validated["externally_attested"] is False
    assert validated["validation_level"] == (
        "INTEGRITY_PLUS_CURRENT_INPUT_AUTHORIZATION_"
        "NOT_EXECUTION_ATTESTED"
    )


def test_execute_without_authorization_never_runs_model(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--execute",
            "--repo-root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert (
        "CANARY_EXECUTION_REQUIRES_SEPARATE_AUTHORIZATION_RECEIPT"
        in completed.stderr
    )
    assert not (tmp_path / "data/restricted").exists()


def _synthetic_execution_context(tool, tmp_path: Path, auth_id: str):
    structural, machine_rows, speech_rows = synthetic_inputs(tool)
    selection = tool.select_canary_families(
        structural,
        machine_family_rows=machine_rows,
        speech_rows=speech_rows,
        v15_local_hash=tool._family_hash(structural["families"][0]),
    )
    subset = tool.build_subset_structural(structural, selection)
    selection_inputs = {
        "private_governance_ledger_sha256": "sha256:opaque-ledger",
        "private_governance_commitment_sha256": "sha256:opaque-private",
        "public_selection_commitment_sha256": "sha256:opaque-public",
    }
    fingerprints = {
        "canary_config_sha256": "sha256:opaque-config",
        "selected_family_hashes": selection["selected_family_hashes"],
        "selection_algorithm": selection["algorithm"],
        "selection_version": selection["version"],
        **selection_inputs,
        "main_pipeline_sha256": "sha256:opaque-main",
        "canary_pipeline_sha256": "sha256:opaque-canary",
        "bundle_file_hashes": structural["file_hashes"],
        "selection_input_hashes": selection_inputs,
        "model_hashes": {"opaque": {"sha256": "sha256:opaque-model"}},
        "media_sha256": "sha256:opaque-media",
        "subset_payload_sha256": tool._subset_body_hash(subset),
        "prompt_manifest_expected_hashes": (
            tool._prompt_manifest_expected_hashes(subset)
        ),
    }
    receipt = {
        "schema_version": tool.AUTHORIZATION_SCHEMA_VERSION,
        "canary_id": tool.CANARY_ID,
        "decision": "AUTHORIZED",
        "authorization_id": auth_id,
        "authorized_at": "2026-10-22T00:00:00Z",
        "single_local_run": True,
        **fingerprints,
        "output_path": tool.DEFAULT_OUTPUT.as_posix(),
    }
    receipt_path = tmp_path / "restricted" / "authorization.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return (
        structural,
        selection,
        subset,
        selection_inputs,
        fingerprints,
        receipt,
        receipt_path,
    )


def _patch_synthetic_execute(
    tool,
    monkeypatch: pytest.MonkeyPatch,
    context,
) -> None:
    (
        structural,
        selection,
        subset,
        selection_inputs,
        fingerprints,
        receipt,
        receipt_path,
    ) = context
    tmp_path = receipt_path.parents[1]
    monkeypatch.setattr(
        tool.parent,
        "load_structural_bundle",
        lambda root, bundle=None: structural,
    )
    monkeypatch.setattr(
        tool,
        "_selection_context",
        lambda root, current: (selection, selection_inputs),
    )
    monkeypatch.setattr(
        tool,
        "build_subset_structural",
        lambda current, selected: subset,
    )
    monkeypatch.setattr(
        tool,
        "_input_fingerprints",
        lambda *args, **kwargs: fingerprints,
    )
    monkeypatch.setattr(
        tool,
        "validate_authorization",
        lambda *args, **kwargs: receipt,
    )
    monkeypatch.setattr(
        tool.parent,
        "preflight",
        lambda *args, **kwargs: {"status": "READY", "failures": []},
    )
    monkeypatch.setattr(
        tool,
        "_contract_value",
        lambda **kwargs: {
            "authorization": dict(receipt),
            "attempt_marker": dict(kwargs["attempt_marker"]),
            "attempt_marker_path": tool._relative_repo_path(
                tmp_path, kwargs["attempt_marker_path_value"]
            ),
            "attempt_marker_sha256": (
                "sha256:"
                + tool.parent.file_sha256(
                    kwargs["attempt_marker_path_value"]
                )
            ),
        },
    )


def _minimal_success_stage(tool):
    def run(root, *, staging, **kwargs):
        del root, kwargs
        tool.parent.atomic_json(
            staging / "audits.json",
            {
                "status": "PASS",
                "semantic_authoring_gates": {
                    name: {
                        "status": "PASS",
                        "findings": [],
                        "field_results": {},
                    }
                    for name in tool.parent.SEMANTIC_GATE_NAMES
                },
            },
        )
        return {}

    return run


def test_r22c_existing_capsule_rejects_before_preflight_or_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    context = _synthetic_execution_context(tool, tmp_path, "opaque-capsule")
    _patch_synthetic_execute(tool, monkeypatch, context)
    receipt_path = context[-1]
    output = tmp_path / tool.DEFAULT_OUTPUT
    capsule = tool.parent.failure_capsule_path(
        output, context[-2]["authorization_id"]
    )
    capsule.mkdir(parents=True)
    calls = {"preflight": 0, "stage": 0}
    monkeypatch.setattr(
        tool.parent,
        "preflight",
        lambda *args, **kwargs: calls.__setitem__(
            "preflight", calls["preflight"] + 1
        ),
    )

    def stage(*args, **kwargs):
        calls["stage"] += 1
        raise AssertionError("stage must not run")

    with pytest.raises(
        tool.CanaryError,
        match="CANARY_ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED",
    ):
        tool.execute(
            tmp_path,
            authorization=receipt_path,
            stage_runner=stage,
        )
    assert calls == {"preflight": 0, "stage": 0}


def test_r22c_existing_marker_rejects_before_preflight_or_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    context = _synthetic_execution_context(tool, tmp_path, "opaque-marker")
    _patch_synthetic_execute(tool, monkeypatch, context)
    receipt_path = context[-1]
    output = tmp_path / tool.DEFAULT_OUTPUT
    marker = tool.attempt_marker_path(
        output, context[-2]["authorization_id"]
    )
    marker.parent.mkdir(parents=True)
    marker.write_text("{}\n", encoding="utf-8")
    os.chmod(marker, 0o600)
    calls = {"preflight": 0}
    monkeypatch.setattr(
        tool.parent,
        "preflight",
        lambda *args, **kwargs: calls.__setitem__(
            "preflight", calls["preflight"] + 1
        ),
    )
    with pytest.raises(
        tool.CanaryError,
        match="CANARY_ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED",
    ):
        tool.execute(
            tmp_path,
            authorization=receipt_path,
            stage_runner=lambda *args, **kwargs: {},
        )
    assert calls["preflight"] == 0


def test_r22c_atomic_marker_allows_only_one_concurrent_creator(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    context = _synthetic_execution_context(tool, tmp_path, "opaque-race")
    fingerprints, receipt, receipt_path = context[-3:]
    marker = tool.attempt_marker_path(
        tmp_path / tool.DEFAULT_OUTPUT, receipt["authorization_id"]
    )
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def create() -> None:
        barrier.wait()
        try:
            tool._create_attempt_marker(
                root=tmp_path,
                marker_path=marker,
                authorization_path=receipt_path,
                authorization_value=receipt,
                fingerprints=fingerprints,
            )
            outcomes.append("created")
        except tool.CanaryError as exc:
            outcomes.append(str(exc))

    threads = [threading.Thread(target=create) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == [
        "CANARY_ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED",
        "created",
    ]
    assert oct(marker.stat().st_mode & 0o777) == "0o600"


@pytest.mark.parametrize(
    "fault",
    ["write", "flush", "fsync", "chmod", "dirfsync"],
)
def test_r22d_marker_persistence_fault_consumes_receipt_fail_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    tool = load_tool()
    context = _synthetic_execution_context(
        tool, tmp_path, f"opaque-{fault}-failure"
    )
    _patch_synthetic_execute(tool, monkeypatch, context)
    receipt_path = context[-1]
    output = tmp_path / tool.DEFAULT_OUTPUT
    marker = tool.attempt_marker_path(
        output, context[-2]["authorization_id"]
    )
    calls = {"preflight": 0, "stage": 0}
    monkeypatch.setattr(
        tool.parent,
        "preflight",
        lambda *args, **kwargs: calls.__setitem__(
            "preflight", calls["preflight"] + 1
        ),
    )

    def fail(*args, **kwargs):
        del args, kwargs
        raise OSError(f"synthetic marker {fault} failure")

    target = {
        "write": "_marker_write",
        "flush": "_marker_flush",
        "fsync": "_marker_file_fsync",
        "chmod": "_marker_chmod",
        "dirfsync": "_marker_parent_directory_fsync",
    }[fault]
    monkeypatch.setattr(tool, target, fail)

    def stage(*args, **kwargs):
        del args, kwargs
        calls["stage"] += 1
        raise AssertionError("stage must not run")

    with pytest.raises(
        tool.CanaryError,
        match="CANARY_ATTEMPT_MARKER_PERSISTENCE_FAILED",
    ):
        tool.execute(
            tmp_path,
            authorization=receipt_path,
            stage_runner=stage,
        )
    assert marker.exists()
    assert calls == {"preflight": 0, "stage": 0}

    monkeypatch.undo()
    _patch_synthetic_execute(tool, monkeypatch, context)
    calls = {"preflight": 0, "stage": 0}
    monkeypatch.setattr(
        tool.parent,
        "preflight",
        lambda *args, **kwargs: calls.__setitem__(
            "preflight", calls["preflight"] + 1
        ),
    )
    with pytest.raises(
        tool.CanaryError,
        match="CANARY_ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED",
    ):
        tool.execute(
            tmp_path,
            authorization=receipt_path,
            stage_runner=stage,
        )
    assert calls == {"preflight": 0, "stage": 0}


def test_r22d_partial_marker_fails_validation_but_consumes_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    output, receipt, _, fingerprints = _trusted_input_authorized_fixture(
        tool, tmp_path, monkeypatch
    )
    _stub_current_media_decode(tool, monkeypatch, output)
    contract = tool.parent.load_json(output / "canary2_contract.json")
    marker = tmp_path / contract["attempt_marker_path"]
    marker.write_bytes(b'{"schema_version":')
    os.chmod(marker, 0o600)
    with pytest.raises(
        tool.CanaryError,
        match="CANARY_ATTEMPT_MARKER_INVALID",
    ):
        tool.validate_output(tmp_path, authorization=receipt)

    receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
    with pytest.raises(
        tool.CanaryError,
        match="CANARY_ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED",
    ):
        tool._create_attempt_marker(
            root=tmp_path,
            marker_path=marker,
            authorization_path=receipt,
            authorization_value=receipt_value,
            fingerprints=fingerprints,
        )


def test_r22c_first_synthetic_success_then_second_execute_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    context = _synthetic_execution_context(tool, tmp_path, "opaque-success")
    _patch_synthetic_execute(tool, monkeypatch, context)
    monkeypatch.setattr(
        tool,
        "_seal_output",
        lambda output_dir: {"status": "SYNTHETIC_SEALED"},
    )
    receipt_path = context[-1]
    output = tmp_path / tool.DEFAULT_OUTPUT
    result = tool.execute(
        tmp_path,
        authorization=receipt_path,
        stage_runner=_minimal_success_stage(tool),
    )
    assert result["status"] == "SYNTHETIC_SEALED"
    assert output.is_dir()
    assert tool.attempt_marker_path(
        output, context[-2]["authorization_id"]
    ).is_file()
    with pytest.raises(
        tool.CanaryError,
        match="CANARY_ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED",
    ):
        tool.execute(
            tmp_path,
            authorization=receipt_path,
            stage_runner=_minimal_success_stage(tool),
        )


def test_r22c_failure_retains_marker_and_second_execute_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    context = _synthetic_execution_context(tool, tmp_path, "opaque-failure")
    _patch_synthetic_execute(tool, monkeypatch, context)
    receipt_path = context[-1]
    output = tmp_path / tool.DEFAULT_OUTPUT

    def fail(*args, **kwargs):
        del args, kwargs
        raise tool.CanaryError("SYNTHETIC_STAGE_FAILURE")

    with pytest.raises(tool.CanaryError, match="SYNTHETIC_STAGE_FAILURE"):
        tool.execute(
            tmp_path,
            authorization=receipt_path,
            stage_runner=fail,
        )
    assert tool.attempt_marker_path(
        output, context[-2]["authorization_id"]
    ).is_file()
    assert tool.parent.failure_capsule_path(
        output, context[-2]["authorization_id"]
    ).is_dir()
    with pytest.raises(
        tool.CanaryError,
        match="CANARY_ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED",
    ):
        tool.execute(
            tmp_path,
            authorization=receipt_path,
            stage_runner=fail,
        )


def test_r22c_marker_tamper_fails_output_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    output, receipt, _, _ = _trusted_input_authorized_fixture(
        tool, tmp_path, monkeypatch
    )
    _stub_current_media_decode(tool, monkeypatch, output)
    contract = tool.parent.load_json(output / "canary2_contract.json")
    marker = tmp_path / contract["attempt_marker_path"]
    marker_value = tool.parent.load_json(marker)
    marker_value["started_at"] = ""
    marker.write_text(json.dumps(marker_value), encoding="utf-8")
    os.chmod(marker, 0o600)
    with pytest.raises(tool.CanaryError):
        tool.validate_output(tmp_path, authorization=receipt)
