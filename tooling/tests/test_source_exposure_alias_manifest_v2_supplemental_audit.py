from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = (
    ROOT / "tools/source_exposure_alias_manifest_v2_supplemental_audit.py"
)
AUDIT_PATH = (
    ROOT
    / "data/rehearsal_plan/"
    "source_exposure_alias_manifest_v2_supplemental_audit.json"
)
REVIEW_PATH = (
    ROOT
    / "docs/review/"
    "source_exposure_alias_manifest_v2_supplemental_audit.md"
)
MANIFEST_PATH = (
    ROOT / "data/rehearsal_plan/source_exposure_alias_manifest_v2.json"
)
PRIVATE_PATH = (
    ROOT
    / "data/restricted/"
    "untouched_test_group_ledger_v3_1_private.json"
)


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "source_exposure_alias_manifest_v2_supplemental_audit", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_current_supplemental_count_and_zero_selected_hit() -> None:
    tool = load_tool()
    audit = load(AUDIT_PATH)
    assert audit["supplemental_inventory"]["post_freeze_file_count"] == 54
    assert (
        audit["supplemental_inventory"][
            "ignored_governance_artifact_count"
        ]
        == 54
    )
    assert (
        audit["supplemental_inventory"]["strict_contamination_event_count"]
        == 0
    )
    selected = audit["selected_v3_1_private_comparison"]
    assert selected["selected_commitment_count"] == 12
    assert selected["selected_commitment_or_closure_exposure_hit_count"] == 0
    assert selected["status"] == "CLEAR"
    assert audit["final_marker"] == tool.FINAL_PASS


def test_public_outputs_have_no_private_selected_identity_or_commitment() -> None:
    tool = load_tool()
    private = load(PRIVATE_PATH)
    public_json = AUDIT_PATH.read_text(encoding="utf-8")
    public_markdown = REVIEW_PATH.read_text(encoding="utf-8")
    tool.validate_public_non_disclosure(
        private,
        public_json_text=public_json,
        public_markdown_text=public_markdown,
    )
    combined = (public_json + "\n" + public_markdown).casefold()
    for identity in tool.selected_identity_strings(private):
        assert identity.casefold() not in combined
    for group in private["selected_groups"]:
        assert group["v3_1_group_commitment_sha256"] not in combined
        assert group["source_commitment_sha256"] not in combined


def test_frozen_manifest_and_all_pinned_hashes_are_immutable() -> None:
    tool = load_tool()
    audit = load(AUDIT_PATH)
    assert hashlib.sha256(MANIFEST_PATH.read_bytes()).hexdigest() == (
        tool.EXPECTED_MANIFEST_SHA256
    )
    frozen = audit["frozen_input_integrity"]
    assert frozen["frozen_manifest_v2_sha256_matches"] is True
    assert frozen["frozen_ledger_v2_sha256_matches"] is True
    assert frozen["pinned_inventory"]["pinned_file_hashes_unchanged"] is True
    assert frozen["pinned_inventory"]["changed_file_count"] == 0
    assert frozen["pinned_inventory"]["missing_file_count"] == 0


def test_future_semantic_prompt_selected_fixture_triggers_private_hit() -> None:
    tool = load_tool()
    private = load(PRIVATE_PATH)
    v2_tool = tool._load_v2_tool(ROOT)
    manifest = load(MANIFEST_PATH)
    lookup = {
        alias: component["closure_root"]
        for component in manifest["alias_graph"]["components"]
        for alias in component["aliases"]
    }
    (
        selected_aliases,
        _,
        direct_commitments,
        selected_v2_roots,
    ) = tool._selected_groups(private)
    selected_identities = tool.selected_identity_strings(private)
    fixture_identity = sorted(
            identity
            for identity in selected_identities
            if "/" not in identity and len(identity) > 4
    )[0]
    fixture_text = (
        "semantic prompt target for exact source " + fixture_identity + "\n"
    )
    fixture = ROOT / "orchestration/prompts/.future_selected_fixture.prompt"
    try:
        fixture.write_text(fixture_text, encoding="utf-8")
        inventory_row = {
            "bytes": fixture.stat().st_size,
            "path": fixture.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        }
        row, events, selected_hits, _ = tool.classify_added_file(
            root=ROOT,
            inventory_row=inventory_row,
            v2_tool=v2_tool,
            v2_lookup=lookup,
            selected_aliases_by_commitment=selected_aliases,
            direct_commitment_to_group=direct_commitments,
            selected_v2_roots=selected_v2_roots,
            selected_identities=selected_identities,
        )
    finally:
        fixture.unlink(missing_ok=True)
    assert row["classification"] == "SOURCE_EXPOSURE_CONTAMINATION"
    assert events
    assert selected_hits
    assert all(event["selected_v3_1_hit"] for event in events)
    serialized = json.dumps(events, sort_keys=True).casefold()
    assert fixture_identity.casefold() not in serialized


def test_committed_outputs_are_deterministic_and_check_passes(capsys) -> None:
    tool = load_tool()
    fresh = tool.build_audit(ROOT)
    assert AUDIT_PATH.read_text(encoding="utf-8") == (
        json.dumps(fresh, indent=2, sort_keys=True) + "\n"
    )
    assert REVIEW_PATH.read_text(encoding="utf-8") == tool.render_markdown(
        fresh
    )
    assert tool.main(["--root", str(ROOT), "--check"]) == 0
    assert capsys.readouterr().out.strip() == tool.FINAL_PASS
