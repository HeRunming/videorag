from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/source_exposure_alias_manifest_v2.py"
MANIFEST_PATH = (
    ROOT / "data/rehearsal_plan/source_exposure_alias_manifest_v2.json"
)
REVIEW_PATH = ROOT / "docs/review/source_exposure_alias_manifest_v2.md"
LEDGER_PATH = ROOT / "data/rehearsal_plan/untouched_test_group_ledger_v2.json"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "source_exposure_alias_manifest_v2", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def component(manifest: dict, alias: str) -> dict:
    for row in manifest["alias_graph"]["components"]:
        if alias in row["aliases"]:
            return row
    raise AssertionError(f"missing alias: {alias}")


def events_for(manifest: dict, closure_root: str) -> list[dict]:
    return [
        row
        for row in manifest["contamination_events"]
        if row["closure_root"] == closure_root
    ]


def test_all_twelve_v2_ledger_closures_are_contaminated() -> None:
    manifest = load(MANIFEST_PATH)
    ledger = load(LEDGER_PATH)
    roots = {row["closure_root"] for row in ledger["test_groups"]}
    contaminated = {
        row["closure_root"] for row in manifest["contaminated_closures"]
    }

    assert len(roots) == 12
    assert roots <= contaminated
    assert manifest["ledger_v2_audit"]["all_contaminated"] is True
    for root in roots:
        assert events_for(manifest, root)


def test_cand_042_alias_closure_is_exact() -> None:
    row = component(load(MANIFEST_PATH), "cand-042")
    assert row["closure_root"] == "EC-NARA-CITY-UNDER-ICE"
    assert {
        "cand-042",
        "EC-NARA-CITY-UNDER-ICE",
        "NAID:2569752",
    } <= set(row["aliases"])
    assert row["supporting_edges"]


def test_p23_closes_all_participant_derivatives() -> None:
    manifest = load(MANIFEST_PATH)
    row = component(manifest, "P23_102")
    assert row["closure_root"] == "EPIC:P23"
    assert {"EPIC:P23", "P23", "P23_101", "P23_102", "P23_103"} <= set(
        row["aliases"]
    )
    assert events_for(manifest, "EPIC:P23")


def test_candidate_route_pool_propagates_epic_cc4d_and_assembly() -> None:
    manifest = load(MANIFEST_PATH)

    epic = events_for(manifest, "EPIC:P35")
    assert any(
        row["event_type"] == "candidate_route"
        and "source_ids_or_pool" in row["evidence"]["locator"]
        for row in epic
    )

    cc4d = events_for(manifest, "CC4D:P04")
    assert any(row["event_type"] == "candidate_route" for row in cc4d)
    assert component(manifest, "25_1")["closure_root"] == "CC4D:P04"

    assembly = events_for(manifest, "ASSEMBLY101:9056")
    assert any(
        row["event_type"] == "candidate_route"
        and row["propagation"].startswith("RESOLVED_NAMED_POOL")
        for row in assembly
    )


def test_assembly_frozen_primary_pool_contaminates_members() -> None:
    manifest = load(MANIFEST_PATH)
    for root in ("ASSEMBLY101:9051", "ASSEMBLY101:9056", "ASSEMBLY101:9083"):
        assert any(
            row["event_type"] == "frozen_primary_pool"
            and row["evidence"]["path"].endswith(
                "assembly101_authenticated_registry_v1.json"
            )
            for row in events_for(manifest, root)
        )


def test_mit_and_yale_course_and_title_aliases_close() -> None:
    manifest = load(MANIFEST_PATH)
    mit = component(manifest, "repl-mit-2-003j-lecture-1")
    yale = component(manifest, "repl-yale-hist-202-lecture-1")

    assert mit["closure_root"] == "SG-MIT-2-003J-L01"
    assert {
        "2.003J Dynamics and Control I",
        "2.003J Dynamics and Control I: Lecture 1",
    } <= set(mit["aliases"])
    assert yale["closure_root"] == "SG-YALE-HIST202-L01"
    assert {
        "HIST-202 European Civilization, 1648-1945",
        "HIST-202 Lecture 1",
    } <= set(yale["aliases"])


def test_events_are_nonempty_exact_and_cover_strict_categories() -> None:
    manifest = load(MANIFEST_PATH)
    events = manifest["contamination_events"]
    assert events
    assert {
        "frozen_primary_pool",
        "candidate_pool_member",
        "candidate_route",
        "candidate_selection_rank",
        "selection_rationale",
        "semantic_prompt",
        "candidate_queue_review_or_mining",
        "media_acquired",
        "media_indexed",
    } <= {row["event_type"] for row in events}
    for row in events:
        evidence = row["evidence"]
        assert evidence["path"]
        assert evidence["locator"]
        assert evidence["detail"]
        assert len(evidence["sha256"]) == 64
        assert row["eligibility_effect"] == "CONTAMINATED"


def test_candidate_universe_is_derived_neutral_only_and_not_hardcoded() -> None:
    manifest = load(MANIFEST_PATH)
    universe = manifest["candidate_universe"]
    contaminated = {
        row["closure_root"] for row in manifest["contaminated_closures"]
    }

    assert universe
    assert {"EPIC", "ASSEMBLY101"} <= {row["family"] for row in universe}
    for row in universe:
        assert row["closure_root"] not in contaminated
        assert row["semantic_routing_event_count"] == 0
        assert "official" in row["derivation_rule"].lower()
        assert row["neutral_evidence"]["path"]
        assert len(row["neutral_evidence"]["sha256"]) == 64


def test_pinned_inventory_is_deterministic_and_supplemental_is_non_authoritative() -> None:
    tool = load_tool()
    manifest = load(MANIFEST_PATH)
    freeze = manifest["scan_freeze"]

    assert freeze["pinned_files"]
    assert freeze["pinned_file_count"] == len(freeze["pinned_files"])
    assert freeze["pinned_inventory_sha256"] == tool.sha256_value(
        freeze["pinned_files"]
    )
    assert freeze["pinned_files"] == sorted(
        freeze["pinned_files"], key=lambda row: row["path"]
    )
    assert "do not contribute" in freeze["freeze_rule"]

    rebuilt = tool.build_manifest(ROOT)
    assert rebuilt["scan_freeze"]["pinned_files"] == freeze["pinned_files"]
    assert MANIFEST_PATH.read_text(encoding="utf-8") == (
        json.dumps(rebuilt, indent=2, sort_keys=True) + "\n"
    )
    assert REVIEW_PATH.read_text(encoding="utf-8") == tool.render_markdown(
        rebuilt
    )


def test_check_cli_prints_ready_marker(capsys) -> None:
    tool = load_tool()
    assert tool.main(["--root", str(ROOT), "--check"]) == 0
    assert capsys.readouterr().out.strip() == tool.FINAL_READY
