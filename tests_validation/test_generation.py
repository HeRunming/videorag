from __future__ import annotations

from av_trace.util import load_json


def test_two_independent_validator_trajectories_per_state(validator_bundle):
    root, index, certificate = validator_bundle
    assert certificate["status"] == "PASS"
    assert index["counts"]["families"] == 8
    assert index["counts"]["trajectories"] == 48
    for family in index["families"]:
        links = [
            load_json(root / "families" / family["family_id"] / "links" / f"{validator}.{state}.json")
            for validator in index["validator_ids"]
            for state in ("clean", "blocked", "restored")
        ]
        assert len(links) == 6
        clean_plans = {
            item["search_plan_id"] for item in links if item["state_role"] == "CLEAN"
        }
        assert clean_plans == {
            "search_then_observe_chronological",
            "direct_observe_reverse_chronological",
        }


def test_clean_restored_acquire_and_blocked_diagnoses(validator_bundle):
    root, index, _certificate = validator_bundle
    for family in index["families"]:
        family_root = root / "families" / family["family_id"]
        blocked = load_json(family_root / "proofs" / "blocked.json")
        restored = load_json(family_root / "proofs" / "restored.json")
        assert blocked["blocked_insufficient"] is True
        assert blocked["reachable_ses_ids"] == []
        assert all(
            item["diagnosed_missingness_cause"]
            == "evidence_in_source_but_inaccessible"
            for item in blocked["validator_results"]
        )
        assert restored["restoration_successful"] is True
        assert all(item["acquired_ses_ids"] for item in restored["validator_results"])


def test_status_and_fixed_call_cases_are_present(validator_bundle):
    root, index, _certificate = validator_bundle
    cases = {item["case_id"]: item for item in index["validator_cases"]}
    assert cases["status-trigger-restoration"]["trigger_type"] == "get_channel_status"
    fixed = cases["fixed-call-restoration"]
    assert fixed["trigger_type"] == "fixed_call_index"
    assert len(fixed["trajectories"]) == 2
    for item in fixed["trajectories"]:
        trajectory = load_json(root / item["trajectory_path"])
        event = trajectory["events"][item["trigger_event_index"]]
        assert event["active_hook_ids"]

