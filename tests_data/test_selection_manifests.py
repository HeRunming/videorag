from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path

from av_trace.schemas import SchemaRegistry
from av_trace_data.adapters import adapter_for_config
from av_trace_data.configs import get_adapter_config
from av_trace_data.errors import ManifestDraftError, SelectionError
from av_trace_data.manifests import draft_acquisition_manifest
from av_trace_data.models import LicenseEvidence, NormalizedCandidate
from av_trace_data.selection import SelectionPolicy, select_candidates

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests_data" / "fixtures"


def synthetic_candidates() -> list[NormalizedCandidate]:
    hf = adapter_for_config(get_adapter_config("video_mme")).inspect_fixture(
        FIXTURES / "hf_synthetic_av_snapshot.json"
    )
    traceav = adapter_for_config(get_adapter_config("traceav_bench")).inspect_fixture(
        FIXTURES / "hf_synthetic_traceav_snapshot.json"
    )
    return list(hf.candidates + traceav.candidates)


def changed(candidate: NormalizedCandidate, **updates: object) -> NormalizedCandidate:
    value = candidate.to_dict()
    value.update(updates)
    return NormalizedCandidate.from_dict(value)


def lineage_candidate(
    *,
    dataset_id: str,
    source_id: str,
    namespace: str,
    asset_id: str,
    parent_namespace: str | None = None,
    parent_asset_id: str | None = None,
    relation: str | None = None,
) -> NormalizedCandidate:
    base = synthetic_candidates()[0]
    return changed(
        base,
        dataset_id=dataset_id,
        adapter_id=dataset_id,
        repository_id=f"synthetic/{dataset_id}",
        source_id=source_id,
        upstream_namespace=namespace,
        upstream_asset_id=asset_id,
        identity_resolution_status="resolved",
        parent_dataset_id=None,
        parent_upstream_namespace=parent_namespace,
        parent_upstream_asset_id=parent_asset_id,
        lineage_relation=relation,
        checksum=None,
        fingerprint=None,
        byte_size=1000,
    )


class SelectionAndManifestTests(unittest.TestCase):
    def test_selection_binds_available_source_snapshot_hashes(self) -> None:
        snapshots = {
            (
                "huggingface:lmms-lab/Video-MME@"
                "3f70174ae54164dec63098b23704e2858d40169a"
            ): "sha256:" + "b" * 64,
            (
                "huggingface:Heinz217/TraceAV-Bench@"
                "cc96f31000000000000000000000000000000000"
            ): "sha256:" + "c" * 64,
        }
        selection = select_candidates(
            synthetic_candidates(),
            SelectionPolicy(limit=10),
            source_snapshots=snapshots,
        )
        self.assertEqual(selection["source_snapshots"], snapshots)
        self.assertTrue(selection["freezeable"])
        self.assertTrue(selection["executable"])
        self.assertEqual(selection["selection_state"], "freeze_ready_candidate")

    def test_empty_snapshot_selection_is_explicitly_non_freezeable(self) -> None:
        selection = select_candidates(
            synthetic_candidates(), SelectionPolicy(limit=10), source_snapshots={}
        )
        self.assertFalse(selection["freezeable"])
        self.assertFalse(selection["executable"])
        self.assertEqual(
            selection["selection_state"], "exploratory_non_freezeable_candidate"
        )
        self.assertEqual(
            selection["non_freezeable_reasons"],
            ["missing_source_snapshot_bindings"],
        )

    def test_promotion_rejects_mutable_short_and_compound_revisions(self) -> None:
        base = synthetic_candidates()[0]
        for revision in ("main", "abcdef1", "a" * 40 + " (main)", "HEAD"):
            with self.subTest(revision=revision):
                with self.assertRaisesRegex(SelectionError, "no candidates"):
                    select_candidates(
                        [changed(base, revision=revision)],
                        SelectionPolicy(),
                        source_snapshots={
                            (
                                "huggingface:lmms-lab/Video-MME@"
                                "3f70174ae54164dec63098b23704e2858d40169a"
                            ): "sha256:" + "b" * 64
                        },
                    )

    def test_selection_rejects_malformed_source_snapshot_hash(self) -> None:
        with self.assertRaisesRegex(SelectionError, "SHA-256"):
            select_candidates(
                synthetic_candidates(),
                SelectionPolicy(limit=10),
                source_snapshots={"synthetic": "not-a-hash"},
            )

    def test_selection_is_deterministic_and_deduplicated(self) -> None:
        candidates = synthetic_candidates()
        policy = SelectionPolicy(limit=10)
        forward = select_candidates(candidates, policy)
        reverse = select_candidates(reversed(candidates), policy)
        self.assertEqual(forward["selection_sha256"], reverse["selection_sha256"])
        selected = forward["selected"]
        self.assertEqual(
            [item["upstream_id"] for item in selected],
            [
                "video-mme:synthetic-video-mme-001",
                "traceav:synthetic-traceav-video-77",
            ],
        )
        rejected_reasons = {
            reason for item in forward["rejected"] for reason in item["reasons"]
        }
        self.assertIn("duplicate_lineage_identity", rejected_reasons)
        self.assertIn("outside_duration_range", rejected_reasons)
        self.assertIn("audio_unavailable", rejected_reasons)

    def test_unknown_audio_and_identity_are_retained_but_not_selected(self) -> None:
        lovr = adapter_for_config(get_adapter_config("lovr")).inspect_fixture(
            FIXTURES / "hf_lovr_snapshot.json"
        )
        with self.assertRaisesRegex(SelectionError, "no candidates"):
            select_candidates(lovr.candidates, SelectionPolicy())
        base = synthetic_candidates()[0]
        selection = select_candidates(
            [base, changed(base, source_id="unknown-audio", has_audio=None)],
            SelectionPolicy(),
        )
        reasons = {
            reason for item in selection["rejected"] for reason in item["reasons"]
        }
        self.assertIn("audio_unknown", reasons)

    def test_selection_honors_range_and_total_size_caps(self) -> None:
        selection = select_candidates(
            synthetic_candidates(),
            SelectionPolicy(
                limit=10,
                max_item_bytes=5000,
                max_total_bytes=4500,
                require_known_size=True,
            ),
        )
        self.assertEqual(selection["summary"]["selected_count"], 1)
        self.assertEqual(selection["selected"][0]["source_id"], "synthetic-av-001")

    def test_flare_and_video_mme_deduplicate_by_parent_lineage(self) -> None:
        direct = lineage_candidate(
            dataset_id="video_mme",
            source_id="direct",
            namespace="video-mme",
            asset_id="vmme-42",
        )
        flare = lineage_candidate(
            dataset_id="flare",
            source_id="clip",
            namespace="flare",
            asset_id="flare-clip-8",
            parent_namespace="video-mme",
            parent_asset_id="vmme-42",
            relation="excerpt_of",
        )
        result = select_candidates([direct, flare], SelectionPolicy())
        self.assertEqual(result["summary"]["selected_count"], 1)
        self.assertIn(
            "duplicate_lineage_identity",
            {reason for row in result["rejected"] for reason in row["reasons"]},
        )

    def test_longvidsearch_lovr_longvideobench_chain_deduplicates(self) -> None:
        candidates = [
            lineage_candidate(
                dataset_id="longvideobench",
                source_id="lvb",
                namespace="longvideobench",
                asset_id="lvb-7",
            ),
            lineage_candidate(
                dataset_id="lovr",
                source_id="lovr",
                namespace="lovr",
                asset_id="lovr-7",
                parent_namespace="longvideobench",
                parent_asset_id="lvb-7",
                relation="reconstruction_of",
            ),
            lineage_candidate(
                dataset_id="longvidsearch",
                source_id="lvs",
                namespace="longvidsearch",
                asset_id="lvs-7",
                parent_namespace="lovr",
                parent_asset_id="lovr-7",
                relation="derived_from",
            ),
        ]
        result = select_candidates(candidates, SelectionPolicy())
        self.assertEqual(result["summary"]["selected_count"], 1)
        self.assertEqual(result["summary"]["rejected_count"], 2)

    def test_traceav_deduplicates_only_when_mapping_is_resolved(self) -> None:
        direct = lineage_candidate(
            dataset_id="omnivideobench",
            source_id="omni",
            namespace="omnivideobench",
            asset_id="omni-9",
        )
        mapped = lineage_candidate(
            dataset_id="traceav_bench",
            source_id="trace",
            namespace="traceav",
            asset_id="trace-9",
            parent_namespace="omnivideobench",
            parent_asset_id="omni-9",
            relation="mapped_from",
        )
        unresolved = changed(
            mapped,
            source_id="trace-unresolved",
            upstream_namespace=None,
            upstream_asset_id=None,
            identity_resolution_status="unresolved",
            parent_upstream_namespace=None,
            parent_upstream_asset_id=None,
            lineage_relation=None,
        )
        result = select_candidates([direct, mapped, unresolved], SelectionPolicy())
        reasons = {
            reason for row in result["rejected"] for reason in row["reasons"]
        }
        self.assertEqual(result["summary"]["selected_count"], 1)
        self.assertIn("duplicate_lineage_identity", reasons)
        self.assertIn("identity_unresolved", reasons)

    def test_fingerprint_dedup_requires_reviewed_same_asset_status(self) -> None:
        first = changed(
            synthetic_candidates()[0],
            source_id="fingerprint-a",
            upstream_asset_id="fingerprint-a",
            checksum=None,
            fingerprint="shared-fingerprint",
            source_metadata={"fingerprint_identity_status": "unreviewed"},
        )
        second = changed(
            first,
            source_id="fingerprint-b",
            upstream_asset_id="fingerprint-b",
        )
        result = select_candidates([first, second], SelectionPolicy())
        self.assertEqual(result["summary"]["selected_count"], 2)

        reviewed_first = changed(
            first,
            source_metadata={"fingerprint_identity_status": "verified_same_asset"},
        )
        reviewed_second = changed(
            second,
            source_metadata={"fingerprint_identity_status": "verified_same_asset"},
        )
        reviewed = select_candidates(
            [reviewed_first, reviewed_second], SelectionPolicy()
        )
        self.assertEqual(reviewed["summary"]["selected_count"], 1)
        self.assertIn(
            "duplicate_fingerprint",
            {
                reason
                for row in reviewed["rejected"]
                for reason in row["reasons"]
            },
        )

    def test_draft_is_schema_valid_but_never_claims_release_license_as_grant(self) -> None:
        candidate = synthetic_candidates()[0]
        manifest = draft_acquisition_manifest(
            candidate,
            created_by="fixture_adapter",
            created_at="2026-09-07T00:00:00Z",
        )
        report = SchemaRegistry(ROOT).validate("acquisition-manifest", manifest)
        self.assertTrue(report.ok, report.to_dict())
        self.assertEqual(manifest["audit"]["gate_status"], "metadata_only")
        self.assertEqual(manifest["rights"]["acquisition_authority"], "unknown_hold")
        self.assertEqual(
            manifest["rights"]["license_or_grant"]["name"],
            "UNRESOLVED_RECONNAISSANCE_EVIDENCE",
        )
        self.assertNotEqual(
            manifest["rights"]["license_or_grant"]["name"],
            candidate.license_evidence[0].name,
        )

    def test_manifest_refuses_any_unknown_media_assertion(self) -> None:
        base = synthetic_candidates()[0]
        for field in (
            "has_video",
            "has_audio",
            "has_speech",
            "has_ambient_audio",
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ManifestDraftError, "unknown metadata"):
                    draft_acquisition_manifest(
                        changed(base, **{field: None}),
                        created_by="fixture_adapter",
                    )

    def test_manifest_allows_zero_or_conflicting_license_evidence_without_approval(self) -> None:
        base = synthetic_candidates()[0]
        no_evidence = changed(
            base,
            license_evidence=[],
            license_resolution_status="unresolved",
        )
        conflict = changed(
            base,
            license_evidence=[
                LicenseEvidence(
                    source="header",
                    artifact_class="annotations",
                    name="License A",
                ).to_dict(),
                LicenseEvidence(
                    source="readme",
                    artifact_class="annotations",
                    name="License B",
                ).to_dict(),
            ],
            license_resolution_status="conflicting",
        )
        for candidate in (no_evidence, conflict):
            manifest = draft_acquisition_manifest(
                candidate,
                created_by="fixture_adapter",
                created_at="2026-09-07T00:00:00Z",
            )
            self.assertEqual(manifest["acquisition"]["status"], "unknown_hold")
            self.assertEqual(
                manifest["rights"]["license_or_grant"]["name"],
                "UNRESOLVED_RECONNAISSANCE_EVIDENCE",
            )

    def test_legacy_candidate_read_does_not_guess_namespace_or_rights(self) -> None:
        legacy = deepcopy(synthetic_candidates()[0].to_dict())
        legacy.pop("license_evidence")
        legacy["license"] = {
            "name": "MIT",
            "version": "unversioned",
            "url": "https://example.invalid/license",
            "scope": "repository",
            "source": "repository",
        }
        legacy.pop("license_resolution_status")
        legacy.pop("upstream_namespace")
        legacy.pop("upstream_asset_id")
        legacy.pop("identity_resolution_status")
        legacy["upstream_id"] = "old-local-looking-id"
        legacy.pop("technical_access_status")
        legacy["access_mode"] = "downloadable_annotation_only"
        read = NormalizedCandidate.from_dict(legacy)
        self.assertEqual(read.identity_resolution_status, "unresolved")
        self.assertIsNone(read.upstream_id)
        self.assertEqual(read.license_resolution_status, "unresolved")
        self.assertTrue(read.technical_access_status.startswith("legacy_unresolved"))


if __name__ == "__main__":
    unittest.main()
