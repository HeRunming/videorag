from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from av_trace_data.download import (
    create_download_plan,
    execute_download_plan,
    validate_execution_approval,
)
from av_trace_data.errors import DownloadPlanError, DownloadRefused
from av_trace_data.io import load_json, sha256_json
from av_trace_data.manifests import draft_acquisition_manifest
from av_trace_data.models import LicenseMetadata, NormalizedCandidate
from av_trace_data.selection import SelectionPolicy, select_candidates

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests_data" / "fixtures"


def candidate():
    return NormalizedCandidate(
        dataset_id="lovr",
        adapter_id="lovr",
        provider="huggingface",
        repository_id="TechNomad-ds/LoVR",
        source_id="lovr-001",
        split="validation",
        duration_s=2400.0,
        canonical_url="https://example.invalid/source/lvs-original-001",
        media_url=(
            "https://huggingface.co/datasets/TechNomad-ds/LoVR/resolve/"
            "4f9b37e1d2a64e879f9236c5ac871d0123456789/videos/lovr-001.mp4"
        ),
        has_video=True,
        has_audio=True,
        has_speech=True,
        has_ambient_audio=False,
        transcript_available=True,
        evidence_available=True,
        revision="4f9b37e1d2a64e879f9236c5ac871d0123456789",
        license_evidence=(
            LicenseMetadata(
                artifact_class="repository_metadata",
                name="CC-BY-4.0",
                version="4.0",
                url="https://creativecommons.org/licenses/by/4.0/",
                scope="Repository metadata only; upstream media unresolved",
                source="repository",
            ),
        ),
        license_resolution_status="consistent",
        technical_access_status="public_ungated",
        access_gate="public",
        payload_state="release_payload_available",
        media_rights_status="asset_reviewed",
        source_family="COMPATIBILITY_ONLY",
        publisher="TechNomad-ds",
        rightsholder_or_status="Synthetic Rights Holder",
        upstream_namespace="longvideobench",
        upstream_asset_id="lvs-original-001",
        identity_resolution_status="resolved",
        byte_size=4000,
        checksum="sha256:" + "1" * 64,
        config="default",
        title="Forty minute candidate",
        retrieval={"etag": '"fixture-etag-001"'},
        source_metadata={
            "repository_url": "https://huggingface.co/datasets/TechNomad-ds/LoVR",
            "license_is_not_rights_approval": True,
        },
    )


def draft_manifest():
    return draft_acquisition_manifest(
        candidate(),
        created_by="fixture_adapter",
        created_at="2026-09-07T00:00:00Z",
    )


def approved_manifest():
    manifest = load_json(ROOT / "docs/data/fixtures/positive_acquisition_manifest.json")
    item = candidate()
    manifest["asset_id"] = "lovr:lovr-001"
    manifest["dataset_id"] = item.dataset_id
    manifest["source"]["canonical_url"] = item.canonical_url
    manifest["source"]["source_identifier"] = item.upstream_id
    manifest["source"]["source_revision"] = item.revision
    manifest["source"]["publisher"] = item.publisher
    manifest["source"]["source_family"] = "COMPATIBILITY_ONLY"
    manifest["media"]["duration_s"] = item.duration_s
    manifest["integrity"]["content_sha256"] = item.checksum
    manifest["integrity"]["byte_size"] = item.byte_size
    manifest["audit"]["gate_status"] = "acquisition_approved"
    return manifest


def manifest_map(manifest):
    return {"lovr:lovr-001": manifest}


def selection(item=None):
    item = item or candidate()
    return select_candidates(
        [item],
        SelectionPolicy(
            max_item_bytes=10_000,
            max_total_bytes=10_000,
            require_known_size=False,
            require_media_url=True,
        ),
        source_snapshots={
            f"{item.provider}:{item.repository_id}@{item.revision}":
            "sha256:" + "a" * 64
        },
    )


def approval(plan):
    return {
        "approval_version": "1.0",
        "action": "approve_download_execution",
        "plan_sha256": plan["plan_sha256"],
        "approved_by": "reviewer1",
        "approved_role": "acquisition_reviewer",
        "approved_at": "2026-09-07T01:00:00Z",
        "approved_asset_ids": ["lovr:lovr-001"],
        "attestation": "I approve acquisition of the exact assets in this frozen plan."
    }


APPROVAL_KWARGS = {
    "authorized_signers": {"reviewer1": ["acquisition_reviewer"]},
    "authorization_time": datetime(2026, 9, 7, 2, 0, tzinfo=timezone.utc),
    "approved_staging_roots": ["/approved/staging"],
}


class DownloadTests(unittest.TestCase):
    def test_plan_is_metadata_only_and_carries_resume_range_and_revision(self) -> None:
        item = candidate()
        manifest = draft_manifest()
        plan = create_download_plan(
            selection(item),
            manifest_map(manifest),
            output_root="/approved/staging",
            max_item_bytes=2000,
            max_total_bytes=2000,
            range_start=1000,
            range_end=1999,
        )
        self.assertFalse(plan["network_access_performed"])
        self.assertEqual(plan["state"], "planned_not_authorized")
        self.assertEqual(plan["items"][0]["source_revision"], item.revision)
        self.assertEqual(plan["items"][0]["planned_transfer_bytes"], 1000)
        self.assertEqual(plan["items"][0]["resume"]["initial_offset"], 1000)
        self.assertFalse(plan["items"][0]["resume"]["verify_final_sha256"])
        self.assertEqual(plan["plan_id"], plan["plan_sha256"])

    def test_plan_rejects_item_size_cap(self) -> None:
        with self.assertRaisesRegex(DownloadPlanError, "item size cap"):
            create_download_plan(
                selection(),
                manifest_map(draft_manifest()),
                output_root="/approved/staging",
                max_item_bytes=3999,
            )

    def test_plan_refuses_unknown_size_when_a_cap_must_be_enforced(self) -> None:
        item = candidate()
        item_dict = item.to_dict()
        item_dict["byte_size"] = None
        unknown_size = NormalizedCandidate.from_dict(item_dict)
        manifest = draft_acquisition_manifest(
            unknown_size,
            created_by="fixture_adapter",
            created_at="2026-09-07T00:00:00Z",
        )
        with self.assertRaisesRegex(DownloadPlanError, "transfer size is unknown"):
            create_download_plan(
                selection(unknown_size),
                {"lovr:lovr-001": manifest},
                output_root="/approved/staging",
                max_total_bytes=10000,
            )

    def test_execute_refuses_metadata_only_manifest(self) -> None:
        manifest = draft_manifest()
        plan = create_download_plan(
            selection(), manifest_map(manifest), output_root="/approved/staging"
        )
        with self.assertRaisesRegex(DownloadRefused, "not exactly acquisition_approved"):
            validate_execution_approval(
                plan, manifest_map(manifest), approval(plan), **APPROVAL_KWARGS
            )

    def test_execute_refuses_missing_or_wrong_explicit_approval(self) -> None:
        manifest = approved_manifest()
        plan = create_download_plan(
            selection(), manifest_map(manifest), output_root="/approved/staging"
        )
        bad = approval(plan)
        bad["plan_sha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(DownloadRefused, "does not bind"):
            validate_execution_approval(
                plan, manifest_map(manifest), bad, **APPROVAL_KWARGS
            )

    def test_execute_refuses_tampered_plan(self) -> None:
        manifest = approved_manifest()
        plan = create_download_plan(
            selection(), manifest_map(manifest), output_root="/approved/staging"
        )
        tampered = deepcopy(plan)
        tampered["items"][0]["url"] = "https://example.invalid/changed"
        with self.assertRaisesRegex(DownloadRefused, "hash does not match"):
            validate_execution_approval(
                tampered, manifest_map(manifest), approval(plan), **APPROVAL_KWARGS
            )

    def test_approved_execute_still_performs_no_transfer_without_backend(self) -> None:
        manifest = approved_manifest()
        plan = create_download_plan(
            selection(), manifest_map(manifest), output_root="/approved/staging"
        )
        result = execute_download_plan(
            plan,
            manifest_map(manifest),
            approval(plan),
            backend=None,
            **APPROVAL_KWARGS,
        )
        self.assertEqual(result["status"], "validated_not_authorized")
        self.assertFalse(result["approval_signature_verified"])
        self.assertFalse(result["network_access_performed"])

    def test_manifest_change_after_planning_is_refused(self) -> None:
        manifest = approved_manifest()
        plan = create_download_plan(
            selection(), manifest_map(manifest), output_root="/approved/staging"
        )
        changed = deepcopy(manifest)
        changed["audit"]["record_updated_at"] = "2026-09-07T02:00:00Z"
        with self.assertRaisesRegex(DownloadRefused, "changed after planning"):
            validate_execution_approval(
                plan, manifest_map(changed), approval(plan), **APPROVAL_KWARGS
            )

    def test_plan_hash_is_canonical_body_hash(self) -> None:
        manifest = approved_manifest()
        plan = create_download_plan(
            selection(), manifest_map(manifest), output_root="/approved/staging"
        )
        body = dict(plan)
        body.pop("plan_id")
        body.pop("plan_sha256")
        self.assertEqual(plan["plan_sha256"], sha256_json(body))


if __name__ == "__main__":
    unittest.main()
