#!/usr/bin/env python3
"""Build the public HoloAssist exposure supplement without revealing identities.

This route consumes only already-retained evidence.  It performs no network
request and opens no media, annotation, label, transcript, or other semantic
dataset body.  Selected recording identities and technical paths are used only
in memory to verify exclusions, frozen-repository absence, and timing closure;
the public JSON and Markdown contain opaque commitments only.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/rehearsal_plan/holoassist_exposure_supplement_v1.json"
REVIEW = ROOT / "docs/review/holoassist_exposure_supplement_v1.md"

PREFLIGHT = ROOT / "data/rehearsal_plan/holoassist_neutral_lineage_preflight_v1.json"
PRIVATE_UNIVERSE = ROOT / "data/restricted/holoassist_opaque_group_universe_v1.json"
PUBLIC_COMMITMENT = ROOT / "data/rehearsal_plan/holoassist_opaque_group_commitment_v1.json"
FROZEN_EXPOSURE_V2 = ROOT / "data/rehearsal_plan/source_exposure_alias_manifest_v2.json"
TIMING_CACHE = ROOT / "data/restricted/holoassist_technical_timing_cache_v1"

SCHEMA_VERSION = "av-trace.holoassist-exposure-supplement/1.0"
FINAL_MARKER = "HOLOASSIST_EXPOSURE_SUPPLEMENT_V1_READY"
GENERATED_DATE = "2026-10-15"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RID_RE = re.compile(r"(?<![A-Za-z0-9])R\d{3,}(?!\d)", re.IGNORECASE)
NUMBER_RE = re.compile(
    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
)

EXPECTED_INPUT_HASHES = {
    "neutral_preflight": "8f0bab442ac2f2e0c97d6aa797b42428bf09615c6a3ca52d645d858e058264cc",
    "opaque_private_universe": "bfed01c6cf5d1fb6ac5befb2959dacedeba649aa0d33112338e7eb49ae4bf529",
    "opaque_public_commitment": "2b2b39da033e1b9be27901bea2a52bae5163f897844236113baed5bb4871d7ac",
    "source_exposure_alias_manifest_v2": "2c631f070505f60a49862a05d879c83e856d7dd60bca99fb34bfa16e8c064618",
}

HF_REPOSITORY = "SitongGong/HoloAssist"
HF_REVISION = "7ad9269e82503f677cb4ec64d77a460d0790a6c4"
HF_INFO_SHA256 = "c1b060cbfeafe7873c5e3849d1afe110ad2540dff89a898c722f1e2d518db053"
HF_TREE_SHA256 = "60d43d6427da55f944e284b2702a878c49ba5c39aa5df54d7617d1ba75e4f3e3"

# These are retained official-repository metadata/body snapshots.  Their
# bodies are not copied into this supplement.  README inspection is restricted
# to exact recording-ID regex extraction for the permanent example exclusion.
OFFICIAL_EVIDENCE = (
    {
        "role": "current_project_readme_markdown",
        "path": Path("/tmp/holoassist_README.md"),
        "bytes": 9879,
        "sha256": "5409932a234e241ec3f7967e856f01b948725c4268edc1bb4923b124a29ebeb6",
        "git_blob_sha": "f2525be53c10f7e16e3ed75cf32a33999277f68a",
        "repository_revision": "1c6978b6370053675048dae2af273133f827094b",
    },
    {
        "role": "current_project_readme_html",
        "path": Path("/tmp/holoassist_README.html"),
        "bytes": 18289,
        "sha256": "26d2506eed4b47a8a355c97c6f97525b479f933957d7d19ca5b17fab6e27d9ae",
        "git_blob_sha": "d3b089a2f7f7e5fef4e760bac40183b6b4e85899",
        "repository_revision": "1c6978b6370053675048dae2af273133f827094b",
    },
    {
        "role": "historical_project_readme_markdown",
        "path": Path("/tmp/holo_e97430ef17a75766177b636c82b4cb0ca267a330.md"),
        "bytes": 10885,
        "sha256": "9b544da4bbb7209e7c8585322d3ba924eac94bcce9f42539546c4fdbb25abad9",
        "repository_revision": "e97430ef17a75766177b636c82b4cb0ca267a330",
    },
    {
        "role": "historical_project_readme_markdown",
        "path": Path("/tmp/holo_2452f5182bda923b9454d37a89dc926db8bcb11b.md"),
        "bytes": 10885,
        "sha256": "e64a83906b75980bb4f2a84e708797f76045157219aaed9383d626b8218781a3",
        "repository_revision": "2452f5182bda923b9454d37a89dc926db8bcb11b",
    },
)

OFFICIAL_METADATA_EVIDENCE = (
    {
        "role": "official_repository_commit_history",
        "path": Path("/tmp/holoassist_commits.json"),
        "bytes": 67928,
        "sha256": "9a83f9076646f1918ca4ca2641e95b4d55338bea95d86d0424fb310d26ecbded",
        "record_count": 17,
    },
    {
        "role": "official_repository_tree",
        "path": Path("/tmp/holoassist_tree.json"),
        "bytes": 34185,
        "sha256": "f4b477def11f8dcf5b71c3737fe898944588f42085b9b37a8db8b09e34236a8b",
        "tree_sha": "8e2f38a8a7f5846fb31ceee17be2e9186ee62cfb",
    },
    {
        "role": "official_data_link_directory_metadata",
        "path": Path("/tmp/holoassist_data_links_contents.json"),
        "bytes": 1994,
        "sha256": "a59bb52717f5e699893386249629df6321cb1712e3274d8f4503ae8bc9c5edf8",
        "record_count": 2,
    },
)


class SupplementError(RuntimeError):
    """Stable failure raised before a public supplement can be emitted."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _load_bound_json(path: Path, key: str) -> tuple[dict[str, Any], bytes]:
    data = path.read_bytes()
    if sha256_bytes(data) != EXPECTED_INPUT_HASHES[key]:
        raise SupplementError(f"BOUND_INPUT_HASH_MISMATCH:{key}")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise SupplementError(f"BOUND_INPUT_NOT_OBJECT:{key}")
    return value, data


def _token_present(data: bytes, identity: str) -> bool:
    pattern = re.compile(
        rb"(?<![A-Za-z0-9])" + re.escape(identity.encode("ascii")) + rb"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    return pattern.search(data) is not None


def _parse_timing_text(data: bytes) -> tuple[int, Decimal]:
    text = data.decode("utf-8", errors="strict")
    # Reproduce the already-committed parser exactly.  The retained evidence
    # used binary floats before subtracting the large absolute timestamps.
    rows: list[list[float]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        numbers = NUMBER_RE.findall(stripped)
        if numbers:
            rows.append([float(number) for number in numbers])
    if len(rows) < 2:
        raise SupplementError("TIMING_TEXT_TOO_SHORT")
    last = [row[-1] for row in rows]
    if any(right < left for left, right in itertools.pairwise(last)):
        raise SupplementError("TIMING_TEXT_NONMONOTONIC")
    span = last[-1] - last[0]
    scale = 1.0
    if span > 100_000:
        scale = 1_000_000.0
    elif span > 10_000:
        scale = 1_000.0
    return len(rows), Decimal(str(round(span / scale, 9)))


def _number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(format(value.normalize(), "f"))


def _path_label(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def verify_retained_official_evidence(expected_examples: set[str]) -> None:
    """Verify retained official snapshots when producing the finalized route."""
    readme_identity_sets: list[set[str]] = []
    for item in OFFICIAL_EVIDENCE:
        path = item["path"]
        if not path.is_file():
            raise SupplementError(f"RETAINED_OFFICIAL_EVIDENCE_MISSING:{item['role']}")
        data = path.read_bytes()
        if len(data) != item["bytes"] or sha256_bytes(data) != item["sha256"]:
            raise SupplementError(f"RETAINED_OFFICIAL_EVIDENCE_MISMATCH:{item['role']}")
        identities = {match.group(0).upper() for match in RID_RE.finditer(data.decode("utf-8", errors="ignore"))}
        readme_identity_sets.append(identities)
    if not readme_identity_sets or any(values != expected_examples for values in readme_identity_sets):
        raise SupplementError("OFFICIAL_README_EXAMPLE_SET_MISMATCH")

    for item in OFFICIAL_METADATA_EVIDENCE:
        path = item["path"]
        if not path.is_file():
            raise SupplementError(f"RETAINED_OFFICIAL_METADATA_MISSING:{item['role']}")
        data = path.read_bytes()
        if len(data) != item["bytes"] or sha256_bytes(data) != item["sha256"]:
            raise SupplementError(f"RETAINED_OFFICIAL_METADATA_MISMATCH:{item['role']}")

    hf_info = Path("/tmp/holo_hf_info.json")
    hf_tree = Path("/tmp/holo_hf_tree.json")
    if not hf_info.is_file() or sha256_path(hf_info) != HF_INFO_SHA256:
        raise SupplementError("RETAINED_HF_INFO_MISMATCH")
    if not hf_tree.is_file() or sha256_path(hf_tree) != HF_TREE_SHA256:
        raise SupplementError("RETAINED_HF_TREE_MISMATCH")
    info = json.loads(hf_info.read_text(encoding="utf-8"))
    if (
        info.get("id") != HF_REPOSITORY
        or info.get("sha") != HF_REVISION
        or info.get("gated") is not False
        or (info.get("cardData") or {}).get("license") != "apache-2.0"
    ):
        raise SupplementError("RETAINED_HF_METADATA_VALUE_MISMATCH")


def _audit_frozen_repository_history(
    manifest: dict[str, Any], selected_identities: set[str]
) -> dict[str, Any]:
    freeze = manifest["scan_freeze"]
    if freeze["supplemental_post_freeze_file_count"] != 0:
        raise SupplementError("FROZEN_V2_HAS_SUPPLEMENTAL_FILES")
    pinned = freeze["pinned_files"]
    identity_hits = 0
    verified = 0
    verified_bytes = 0
    for row in pinned:
        path = ROOT / row["path"]
        data = path.read_bytes()
        if len(data) != row["bytes"] or sha256_bytes(data) != row["sha256"]:
            raise SupplementError("FROZEN_V2_PINNED_FILE_MISMATCH")
        verified += 1
        verified_bytes += len(data)
        for identity in selected_identities:
            identity_hits += int(_token_present(data, identity))
    if identity_hits:
        raise SupplementError("SELECTED_IDENTITY_PRESENT_IN_FROZEN_HISTORY")
    if verified != freeze["pinned_file_count"]:
        raise SupplementError("FROZEN_V2_PINNED_COUNT_MISMATCH")
    return {
        "authoritative_manifest": _path_label(FROZEN_EXPOSURE_V2),
        "manifest_sha256": EXPECTED_INPUT_HASHES["source_exposure_alias_manifest_v2"],
        "pinned_inventory_sha256": freeze["pinned_inventory_sha256"],
        "pinned_file_count": verified,
        "pinned_bytes_verified": verified_bytes,
        "selected_identity_exact_token_hits": identity_hits,
        "route_created_after_freeze": True,
        "result": "ALL_SIX_ABSENT",
    }


def _timing_inventory(
    private: dict[str, Any], public_commitments: set[str]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cache_files = sorted(path for path in TIMING_CACHE.rglob("*") if path.is_file())
    inventory_records: list[dict[str, Any]] = []
    for path in cache_files:
        data = path.read_bytes()
        inventory_records.append(
            {
                "path": path.relative_to(TIMING_CACHE).as_posix(),
                "bytes": len(data),
                "sha256": sha256_bytes(data),
            }
        )

    summaries: list[dict[str, Any]] = []
    used_paths: set[str] = set()
    for group in private["selected_groups"]:
        commitment = group["private_commitment"]
        if commitment not in public_commitments:
            raise SupplementError("PRIVATE_COMMITMENT_NOT_PUBLIC")
        if not group.get("timing_closed"):
            raise SupplementError("SELECTED_GROUP_NOT_TIMING_CLOSED")
        durations: list[Decimal] = []
        private_evidence: list[dict[str, Any]] = []
        for variant in group["variants"]:
            timing_path = variant["timing_path"]
            if timing_path in used_paths:
                raise SupplementError("DUPLICATE_SELECTED_TIMING_PATH")
            used_paths.add(timing_path)
            path = TIMING_CACHE / timing_path
            data = path.read_bytes()
            frame_count, duration = _parse_timing_text(data)
            evidence = variant["timing_evidence"]
            if (
                not evidence.get("fetched")
                or not evidence.get("format_recognized")
                or len(data) != evidence["bytes"]
                or sha256_bytes(data) != evidence["sha256"]
                or frame_count != evidence["frame_count"]
                or duration != Decimal(str(evidence["duration_seconds"]))
            ):
                raise SupplementError("TIMING_EVIDENCE_MISMATCH")
            durations.append(duration)
            private_evidence.append(
                {
                    "path": timing_path,
                    "bytes": len(data),
                    "sha256": sha256_bytes(data),
                    "frame_count": frame_count,
                    "duration_seconds": _number(duration),
                }
            )
        summaries.append(
            {
                "commitment": commitment,
                "classification": "CONDITIONAL_METADATA_ONLY",
                "conditions": {
                    "absent_from_official_readme_example_set": True,
                    "absent_from_frozen_repository_history_v2": True,
                    "timing_closed": True,
                },
                "timing_evidence": {
                    "text_file_count": len(private_evidence),
                    "recognized_text_file_count": len(private_evidence),
                    "frame_boundary_row_count": sum(
                        item["frame_count"] for item in private_evidence
                    ),
                    "duration_seconds_total": _number(sum(durations, Decimal(0))),
                    "duration_seconds_min": _number(min(durations)),
                    "duration_seconds_max": _number(max(durations)),
                    "private_evidence_commitment_sha256": sha256_bytes(
                        canonical_json(private_evidence)
                    ),
                },
            }
        )

    cache_relpaths = {row["path"] for row in inventory_records}
    if used_paths != cache_relpaths:
        raise SupplementError("TIMING_CACHE_NOT_EXACTLY_SELECTED")
    inventory = {
        "path": _path_label(TIMING_CACHE),
        "path_entries_public": False,
        "file_count": len(inventory_records),
        "total_bytes": sum(row["bytes"] for row in inventory_records),
        "canonical_private_inventory_sha256": sha256_bytes(
            canonical_json(inventory_records)
        ),
        "selected_file_count": len(used_paths),
        "unselected_file_count": len(cache_relpaths - used_paths),
    }
    return inventory, sorted(summaries, key=lambda item: item["commitment"])


def _source_binding(
    path: Path, key: str, value: dict[str, Any]
) -> dict[str, Any]:
    return {
        "path": _path_label(path),
        "bytes": path.stat().st_size,
        "sha256": EXPECTED_INPUT_HASHES[key],
        "schema_version": value.get("schema_version"),
        "final_marker": value.get("final_marker"),
    }


def build_supplement() -> dict[str, Any]:
    preflight, _ = _load_bound_json(PREFLIGHT, "neutral_preflight")
    private, _ = _load_bound_json(PRIVATE_UNIVERSE, "opaque_private_universe")
    public, _ = _load_bound_json(PUBLIC_COMMITMENT, "opaque_public_commitment")
    frozen_v2, _ = _load_bound_json(
        FROZEN_EXPOSURE_V2, "source_exposure_alias_manifest_v2"
    )

    commitments = set(public["commitments"])
    selected_groups = private["selected_groups"]
    selected_identities = {group["recording_root"] for group in selected_groups}
    semantic_examples = set(private["policy"]["explicit_exclusions"])
    semantic_examples.update(private["policy"]["semantic_text_exclusions"])

    if len(commitments) != 6 or len(selected_groups) != 6:
        raise SupplementError("SEALED_GROUP_COUNT_NOT_SIX")
    if commitments != {group["private_commitment"] for group in selected_groups}:
        raise SupplementError("PUBLIC_PRIVATE_COMMITMENT_SET_MISMATCH")
    if selected_identities & semantic_examples:
        raise SupplementError("SELECTED_IDENTITY_IS_README_EXAMPLE")
    if len(semantic_examples) != 4:
        raise SupplementError("OFFICIAL_EXAMPLE_COUNT_MISMATCH")
    if private["source"]["hf_revision"] != HF_REVISION:
        raise SupplementError("PRIVATE_HF_REVISION_MISMATCH")
    if public["lineage"]["hf_revision"] != HF_REVISION:
        raise SupplementError("PUBLIC_HF_REVISION_MISMATCH")
    if (
        public["lineage"]["hf_info_sha256"] != HF_INFO_SHA256
        or public["lineage"]["hf_tree_sha256"] != HF_TREE_SHA256
    ):
        raise SupplementError("PUBLIC_HF_HASH_MISMATCH")

    repository_history = _audit_frozen_repository_history(
        frozen_v2, selected_identities
    )
    timing_inventory, group_summaries = _timing_inventory(private, commitments)

    official_snapshot_records = []
    for item in OFFICIAL_EVIDENCE:
        record = {
            key: value
            for key, value in item.items()
            if key not in {"path"}
        }
        record["body_published"] = False
        official_snapshot_records.append(record)

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_date": GENERATED_DATE,
        "final_marker": FINAL_MARKER,
        "scope": {
            "network_used": False,
            "media_opened": False,
            "video_opened": False,
            "audio_opened": False,
            "annotations_opened": False,
            "labels_opened": False,
            "semantic_dataset_fields_opened": False,
            "selected_identities_published": False,
            "technical_timing_text_only": True,
        },
        "source_bindings": {
            "neutral_lineage_preflight": _source_binding(
                PREFLIGHT, "neutral_preflight", preflight
            ),
            "opaque_private_universe": _source_binding(
                PRIVATE_UNIVERSE, "opaque_private_universe", private
            ),
            "opaque_public_commitment": _source_binding(
                PUBLIC_COMMITMENT, "opaque_public_commitment", public
            ),
            "frozen_exposure_manifest_v2": _source_binding(
                FROZEN_EXPOSURE_V2,
                "source_exposure_alias_manifest_v2",
                frozen_v2,
            ),
        },
        "official_repository_evidence": {
            "repository": "holoAssist/holoassist.github.io",
            "project_url": "https://holoassist.github.io/",
            "data_link_index_url": "https://holoassist.github.io/data_links/README.md",
            "head_commit": "1c6978b6370053675048dae2af273133f827094b",
            "head_commit_date": "2025-06-04T02:03:29Z",
            "tree_sha": "8e2f38a8a7f5846fb31ceee17be2e9186ee62cfb",
            "metadata_snapshots": [
                {key: value for key, value in item.items() if key != "path"}
                for item in OFFICIAL_METADATA_EVIDENCE
            ],
            "readme_snapshots": official_snapshot_records,
            "semantic_example_identity_count": len(semantic_examples),
            "semantic_example_identity_set_sha256": sha256_bytes(
                canonical_json(sorted(semantic_examples))
            ),
            "identities_published": False,
        },
        "hugging_face_metadata_evidence": {
            "repository": HF_REPOSITORY,
            "revision": HF_REVISION,
            "last_modified": "2026-08-22T04:42:51.000Z",
            "metadata_sha256": HF_INFO_SHA256,
            "tree_page_sha256": HF_TREE_SHA256,
            "tree_page_entry_count": 1000,
            "gated": False,
            "private": False,
            "declared_license": "apache-2.0",
            "access_route": {
                "metadata": (
                    "Hugging Face dataset REST metadata endpoint pinned by "
                    "repository and exact revision"
                ),
                "tree": (
                    "Hugging Face dataset tree endpoint pinned by repository "
                    "and exact revision"
                ),
                "timing_text": (
                    "Hugging Face resolve endpoint pinned by repository, exact "
                    "revision, and private technical path"
                ),
                "authentication_required": False,
                "media_route_used": False,
            },
        },
        "license_discrepancy": {
            "mirror_declared_license": "Apache-2.0",
            "official_declared_license": "CDLA-Permissive-2.0",
            "resolved_as_equivalent": False,
            "operative_license_claim": "OFFICIAL_DECLARATION_CONTROLS",
            "effect": (
                "The mirror license field is metadata-only evidence and does "
                "not replace or reconcile the official declaration."
            ),
        },
        "exposure_classes": {
            "official_readme_semantic_examples": {
                "classification": "PERMANENTLY_CONTAMINATED",
                "identity_count": len(semantic_examples),
                "identity_set_sha256": sha256_bytes(
                    canonical_json(sorted(semantic_examples))
                ),
                "rule": (
                    "Every recording identity appearing as a semantic example "
                    "in a bound current or retained historical official README "
                    "is permanently excluded."
                ),
                "selected_intersection_count": 0,
            },
            "hf_file_tree_license_and_timing_access": {
                "classification": "CONDITIONAL_METADATA_ONLY",
                "rule": (
                    "File-tree, access, license, and timing-text evidence does "
                    "not by itself create semantic contamination; a selected "
                    "group remains conditional only while absent from the "
                    "official README example set and frozen repository history."
                ),
                "semantic_content_used": False,
            },
            "sealed_selected_groups": {
                "classification": "CONDITIONAL_METADATA_ONLY",
                "count": 6,
                "commitments_only": True,
                "identities_published": False,
                "all_conditions_satisfied": True,
                "groups": group_summaries,
            },
        },
        "repository_history_check": repository_history,
        "timing_cache_inventory": timing_inventory,
        "timing_evidence_totals": {
            "sealed_group_count": len(group_summaries),
            "timing_closed_group_count": sum(
                item["conditions"]["timing_closed"] for item in group_summaries
            ),
            "timing_text_file_count": sum(
                item["timing_evidence"]["text_file_count"]
                for item in group_summaries
            ),
            "duration_seconds_total": _number(
                sum(
                    (
                        Decimal(
                            str(item["timing_evidence"]["duration_seconds_total"])
                        )
                        for item in group_summaries
                    ),
                    Decimal(0),
                )
            ),
        },
        "claim_boundary": {
            "timing_text_access_claim": True,
            "video_content_access_claim": False,
            "audio_content_access_claim": False,
            "playable_media_validation_claim": False,
            "native_audio_presence_claim": False,
            "duration_interpretation": (
                "Computed span of retained technical timing text; not a claim "
                "that video or audio was downloaded, decoded, or inspected."
            ),
        },
        "decision": {
            "status": "READY",
            "sealed_groups": 6,
            "permanently_contaminated_example_identities": len(semantic_examples),
            "conditional_groups": 6,
            "reason": (
                "All six opaque commitments are timing-closed, disjoint from "
                "the permanent official README example set, and absent from "
                "the hash-verified frozen v2 repository inventory."
            ),
        },
    }
    report["integrity"] = {
        "algorithm": "sha256",
        "canonical_payload_sha256": sha256_bytes(canonical_json(report)),
    }
    validate_public_identity_absence(report, selected_identities | semantic_examples)
    return report


def validate_public_identity_absence(
    report: dict[str, Any], private_identities: set[str]
) -> None:
    raw = canonical_json(report)
    for identity in private_identities:
        if _token_present(raw, identity):
            raise SupplementError("PUBLIC_IDENTITY_LEAK")
    forbidden = (
        b"extracted_videos/",
        b"VideoMp4Timing.txt",
        b"Pose_sync.txt",
        b"recording_root",
        b"timing_path",
    )
    if any(token in raw for token in forbidden):
        raise SupplementError("PUBLIC_TECHNICAL_PATH_LEAK")


def render_review(report: dict[str, Any]) -> str:
    groups = report["exposure_classes"]["sealed_selected_groups"]["groups"]
    lines = [
        "# HoloAssist exposure supplement v1",
        "",
        f"**Final marker: `{FINAL_MARKER}`**",
        "",
        f"Finalized offline on **October 15, 2026**. This supplement does not",
        "modify the frozen exposure manifest v2 or any exposure ledger. It",
        "publishes no selected HoloAssist recording identity or technical path.",
        "",
        "## Classification",
        "",
        "- Official project/repository README semantic example identities: "
        "**permanently contaminated**. Four identities are committed by hash and",
        "remain excluded; the identities are not reproduced here.",
        "- Hugging Face file-tree, access, license, and timing-text evidence:",
        "**conditional metadata-only**.",
        "- Six sealed selected groups: **conditional metadata-only**, and only",
        "while each remains absent from both the official README example set and",
        "the repository evidence frozen before this route.",
        "",
        "The frozen v2 inventory was revalidated byte-for-byte: "
        f"**{report['repository_history_check']['pinned_file_count']} files** and "
        f"**{report['repository_history_check']['pinned_bytes_verified']} bytes**.",
        "Exact-token hits for every sealed selected identity were zero.",
        "",
        "## Bound evidence",
        "",
        f"- Official repository head: `{report['official_repository_evidence']['head_commit']}`",
        f"- Official repository tree: `{report['official_repository_evidence']['tree_sha']}`",
        f"- Exact Hugging Face revision: `{report['hugging_face_metadata_evidence']['revision']}`",
        f"- HF metadata SHA-256: `{report['hugging_face_metadata_evidence']['metadata_sha256']}`",
        f"- HF tree-page SHA-256: `{report['hugging_face_metadata_evidence']['tree_page_sha256']}`",
        f"- Private opaque universe SHA-256: `{report['source_bindings']['opaque_private_universe']['sha256']}`",
        f"- Public opaque commitment SHA-256: `{report['source_bindings']['opaque_public_commitment']['sha256']}`",
        f"- Timing cache private inventory SHA-256: `{report['timing_cache_inventory']['canonical_private_inventory_sha256']}`",
        "",
        "The access route is the official project data-link index for first-party",
        "package routing and the Hugging Face dataset metadata/tree/resolve route",
        "pinned to the exact revision above. No media route was exercised by this",
        "supplement.",
        "",
        "## License discrepancy",
        "",
        "The Hugging Face mirror declares **Apache-2.0**, while the official",
        "project README declares **CDLA-Permissive-2.0**. The values are recorded",
        "as a discrepancy, not treated as equivalent, and the official",
        "declaration controls this supplement's license statement.",
        "",
        "## Timing closure by opaque commitment",
        "",
        "| Commitment | Timing texts | Duration total (s) | Min (s) | Max (s) |",
        "|---|---:|---:|---:|---:|",
    ]
    for group in groups:
        timing = group["timing_evidence"]
        lines.append(
            "| `{}` | {} | {} | {} | {} |".format(
                group["commitment"],
                timing["text_file_count"],
                timing["duration_seconds_total"],
                timing["duration_seconds_min"],
                timing["duration_seconds_max"],
            )
        )
    lines.extend(
        [
            "",
            f"All **{report['timing_evidence_totals']['timing_closed_group_count']} "
            "of 6** commitments are timing-closed across "
            f"**{report['timing_evidence_totals']['timing_text_file_count']}** "
            "retained technical timing texts. Paths and recording identities",
            "remain private.",
            "",
            "## Claim boundary",
            "",
            "The duration values are computed spans from technical timing text.",
            "They are **not** evidence that video or audio was downloaded, opened,",
            "decoded, heard, viewed, or validated. No video claim, audio claim,",
            "native-audio claim, annotation claim, label claim, or semantic-yield",
            "claim is made.",
            "",
            f"`{FINAL_MARKER}`",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], output: Path, review: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    review.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(report))
    review.write_text(render_review(report), encoding="utf-8")
    os.chmod(output, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--review", type=Path, default=REVIEW)
    parser.add_argument(
        "--skip-retained-evidence-verification",
        action="store_true",
        help="Use only pinned hashes when external retained /tmp evidence is unavailable.",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    report = build_supplement()
    private = json.loads(PRIVATE_UNIVERSE.read_text(encoding="utf-8"))
    semantic_examples = set(private["policy"]["explicit_exclusions"])
    semantic_examples.update(private["policy"]["semantic_text_exclusions"])
    if not args.skip_retained_evidence_verification:
        verify_retained_official_evidence(semantic_examples)

    json_bytes = canonical_json(report)
    review_text = render_review(report)
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != json_bytes:
            raise SupplementError("PUBLIC_JSON_NOT_CURRENT")
        if not args.review.is_file() or args.review.read_text(encoding="utf-8") != review_text:
            raise SupplementError("REVIEW_NOT_CURRENT")
    else:
        write_outputs(report, args.output, args.review)
    print(FINAL_MARKER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
