from __future__ import annotations

import unittest

from av_trace.semantic import validate_family
from av_trace.schemas import SchemaRegistry
from av_trace.util import load_json

from tests.helpers import ROOT, alternative_ses_family, channel_outage_family, positive_family, positive_manifest


class SemanticFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SchemaRegistry(ROOT)

    def codes(self, family: dict) -> set[str]:
        return {
            issue.code
            for issue in validate_family(
                family,
                positive_manifest(),
                self.registry,
                media_mode="synthetic_testing",
            ).issues
        }

    def test_normative_positive_family_passes(self) -> None:
        self.assertTrue(
            validate_family(
                positive_family(),
                positive_manifest(),
                self.registry,
                media_mode="synthetic_testing",
            ).ok
        )

    def test_alternative_ses_is_supported_without_unique_clip_assumption(self) -> None:
        family = alternative_ses_family()
        report = validate_family(
            family,
            positive_manifest(),
            self.registry,
            media_mode="synthetic_testing",
        )
        self.assertTrue(report.ok, report.to_dict())

    def test_alternative_ses_surviving_block_is_rejected(self) -> None:
        family = alternative_ses_family()
        family["episodes"][1]["initial_state"]["accessible_evidence_ids"] = ["e2", "e3"]
        family["episodes"][2]["initial_state"]["accessible_evidence_ids"] = ["e2", "e3"]
        self.assertIn("INT-004", self.codes(family))

    def test_invalid_necessity_group_is_rejected(self) -> None:
        family = alternative_ses_family()
        family["claim_evidence_graph"]["necessity_groups"][0]["member_evidence_ids"] = ["e1"]
        family["episodes"][1]["interventions"][0]["affected_evidence_ids"] = ["e1"]
        family["episodes"][2]["interventions"][0]["affected_evidence_ids"] = ["e1"]
        family["episodes"][2]["interventions"][1]["affected_evidence_ids"] = ["e1"]
        self.assertIn("NEC-002", self.codes(family))

    def test_non_minimal_ses_is_rejected(self) -> None:
        family = positive_family()
        redundant = dict(family["claim_evidence_graph"]["accepted_sufficient_sets"][0])
        redundant["set_id"] = "ses_redundant"
        redundant["evidence_ids"] = ["e1", "e2"]
        # Make the original a one-unit complete direct derivation, so redundant is a strict superset.
        family["claim_evidence_graph"]["support_edges"].append(
            {"edge_id": "direct1", "relation": "direct_support", "from_ids": ["e1"], "to_id": "c1"}
        )
        family["claim_evidence_graph"]["accepted_sufficient_sets"][0]["evidence_ids"] = ["e1"]
        family["claim_evidence_graph"]["accepted_sufficient_sets"][0]["hop_ids"] = []
        family["claim_evidence_graph"]["accepted_sufficient_sets"].append(redundant)
        self.assertTrue({"SES-004", "SES-005"} & self.codes(family))

    def test_non_isolated_budget_change_is_rejected(self) -> None:
        family = positive_family()
        family["episodes"][2]["budget"]["cost_limit"] = 20.0
        codes = self.codes(family)
        self.assertIn("FAM-002", codes)

    def test_non_isolated_extra_evidence_removal_is_rejected(self) -> None:
        family = positive_family()
        family["episodes"][1]["initial_state"]["accessible_evidence_ids"] = []
        family["episodes"][2]["initial_state"]["accessible_evidence_ids"] = []
        self.assertIn("INT-002", self.codes(family))

    def test_blocked_cannot_add_previously_inaccessible_evidence(self) -> None:
        family = positive_family()
        clean, blocked, restored = family["episodes"]
        clean["initial_state"]["accessible_evidence_ids"] = ["e1"]
        blocked["initial_state"]["accessible_evidence_ids"] = ["e2"]
        restored["initial_state"]["accessible_evidence_ids"] = ["e2"]
        self.assertIn("INT-001", self.codes(family))

    def test_public_core_duration_must_be_within_pilot_range(self) -> None:
        family = positive_family()
        family["source"]["duration_s"] = 600.0
        manifest = positive_manifest()
        manifest["media"]["duration_s"] = 600.0
        report = validate_family(
            family, manifest, self.registry, media_mode="synthetic_testing"
        )
        self.assertIn("FAM-008", {issue.code for issue in report.issues})

    def test_fixed_call_restoration_requires_trigger_value(self) -> None:
        family = positive_family()
        family["episodes"][2]["interventions"][1]["restoration"]["trigger_type"] = "fixed_call_index"
        self.assertIn("REST-002", self.codes(family))

    def test_replay_seed_must_be_identical_across_family(self) -> None:
        family = positive_family()
        family["episodes"][2]["replay"]["seed"] = 1
        self.assertIn("FAM-002", self.codes(family))

    def test_annotation_roles_must_be_independent(self) -> None:
        family = positive_family()
        family["annotation"]["authors"] = ["validator_a"]
        self.assertIn("SES-006", self.codes(family))

    def test_ses_validators_must_be_registered(self) -> None:
        family = positive_family()
        family["claim_evidence_graph"]["accepted_sufficient_sets"][0]["validator_ids"] = ["outsider1", "outsider2"]
        self.assertIn("SES-006", self.codes(family))

    def test_necessity_group_removal_must_break_each_target_claim(self) -> None:
        family = positive_family()
        graph = family["claim_evidence_graph"]
        graph["claims"].append({
            "claim_id": "c2",
            "proposition": "The valve was closed.",
            "requirement": "required",
            "answer_value": "closed",
            "accepted_aliases": [],
            "contradiction_claim_ids": [],
        })
        family["answer_spec"]["required_claim_ids"].append("c2")
        graph["support_edges"].append(
            {"edge_id": "direct2", "relation": "direct_support", "from_ids": ["e2"], "to_id": "c2"}
        )
        graph["accepted_sufficient_sets"][0]["claim_ids"].append("c2")
        graph["necessity_groups"][0]["claim_ids"].append("c2")
        self.assertIn("NEC-003", self.codes(family))

    def test_accepted_family_requires_completed_alternative_search(self) -> None:
        family = positive_family()
        family["annotation"]["alternative_search_completed"] = False
        self.assertIn("SES-003", self.codes(family))

    def test_fixed_call_trigger_must_be_within_max_steps(self) -> None:
        family = positive_family()
        restoration = family["episodes"][2]["interventions"][1]["restoration"]
        restoration["trigger_type"] = "fixed_call_index"
        restoration["trigger_value"] = family["episodes"][2]["budget"]["max_steps"]
        self.assertIn("REST-004", self.codes(family))

    def test_required_hops_must_match_broken_alternative_routes(self) -> None:
        family = alternative_ses_family()
        family["claim_evidence_graph"]["necessity_groups"][0]["required_hop_ids"] = ["h1"]
        self.assertIn("NEC-005", self.codes(family))

    def test_blocked_oracle_must_match_broken_hops(self) -> None:
        family = alternative_ses_family()
        family["episodes"][1]["oracle"]["gold_missing_hop_ids"] = ["h1"]
        self.assertIn("NEC-005", self.codes(family))

    def test_frozen_family_cannot_receive_partial_certification_pass(self) -> None:
        family = positive_family()
        family["annotation"]["status"] = "frozen"
        self.assertIn("CERT-001", self.codes(family))

    def test_incorrect_restoration_is_rejected(self) -> None:
        family = positive_family()
        family["episodes"][2]["interventions"][1]["affected_evidence_ids"] = ["e2"]
        self.assertIn("REST-003", self.codes(family))

    def test_model_dependent_restoration_is_structurally_rejected(self) -> None:
        family = positive_family()
        family["episodes"][2]["interventions"][1]["restoration"]["trigger_type"] = "when_answer_is_wrong"
        report = validate_family(
            family,
            positive_manifest(),
            self.registry,
            media_mode="synthetic_testing",
        )
        self.assertFalse(report.ok)
        self.assertIn("SCHEMA-VALIDATION", {issue.code for issue in report.issues})

    def test_provenance_mismatch_is_rejected(self) -> None:
        family = positive_family()
        family["source"]["manifest_asset_id"] = "asset_other"
        self.assertIn("PROV-001", self.codes(family))

    def test_missing_manifest_fails_closed(self) -> None:
        report = validate_family(
            positive_family(), None, self.registry, media_mode="synthetic_testing"
        )
        self.assertFalse(report.ok)
        self.assertIn("PROV-000", {issue.code for issue in report.issues})

    def test_malformed_manifest_returns_validation_report(self) -> None:
        report = validate_family(
            positive_family(),
            {"asset_id": "broken"},
            self.registry,
            media_mode="synthetic_testing",
        )
        self.assertFalse(report.ok)
        self.assertIn("SCHEMA-VALIDATION", {issue.code for issue in report.issues})

    def test_channel_outage_family_passes(self) -> None:
        family = channel_outage_family()
        report = validate_family(
            family,
            positive_manifest(),
            self.registry,
            media_mode="synthetic_testing",
        )
        self.assertTrue(report.ok, report.to_dict())

    def test_channel_outage_cannot_remove_extra_channel(self) -> None:
        family = channel_outage_family()
        family["episodes"][1]["initial_state"]["enabled_channels"].remove("ambient")
        family["episodes"][2]["initial_state"]["enabled_channels"].remove("ambient")
        self.assertIn("INT-003", self.codes(family))

    def test_public_core_accepts_annotation_status_when_six_decisions_are_allowed(self) -> None:
        manifest = positive_manifest()
        manifest["audit"]["gate_status"] = "annotation_approved"
        report = validate_family(
            positive_family(),
            manifest,
            self.registry,
            media_mode="synthetic_testing",
        )
        self.assertTrue(report.ok, report.to_dict())

    def test_verified_asset_bridge_rejects_episode_stream_tampering(self) -> None:
        family = positive_family()
        family["source"]["streams"][0]["hash"] = "sha256:" + "a" * 64
        verified_asset = load_json(
            ROOT / "tests_data/fixtures/positive_verified_asset.json"
        )
        report = validate_family(
            family,
            positive_manifest(),
            self.registry,
            verified_asset=verified_asset,
        )
        self.assertTrue(
            {"PROV-002", "TIME-003"} & {issue.code for issue in report.issues}
        )


if __name__ == "__main__":
    unittest.main()
