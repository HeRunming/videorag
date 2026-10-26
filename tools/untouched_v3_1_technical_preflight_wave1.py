#!/usr/bin/env python3
"""Custodian-private technical preflight for one frozen v3.1 group per lineage.

The selector sees only dataset-lineage labels and the public v3.1 commitment
IDs.  After selection, the custodian opens the sealed private mapping and
performs bounded technical checks against exact official routes.  No semantic
annotation body, transcript, label, title, description, media sample, or full
media object is opened or retained.

Live media probes are HEAD/range only, use at most 16 MiB of aggregate response
payload, keep response bytes in memory, and release them after each candidate.
HoloAssist uses retained exact timing-text evidence; it may additionally use
HEAD/range only if an exact video object is discoverable from the technical
repository listing.  This wave never changes or replaces the frozen roster.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from tools import hf_audio_stream_preflight as core
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    _core_path = Path(__file__).with_name("hf_audio_stream_preflight.py")
    _core_spec = importlib.util.spec_from_file_location(
        "hf_audio_stream_preflight", _core_path
    )
    if _core_spec is None or _core_spec.loader is None:
        raise
    core = importlib.util.module_from_spec(_core_spec)
    sys.modules[_core_spec.name] = core
    _core_spec.loader.exec_module(core)


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_LEDGER = (
    ROOT / "data/restricted/untouched_test_group_ledger_v3_1_private.json"
)
PUBLIC_LEDGER = (
    ROOT
    / "data/rehearsal_plan/"
    "untouched_test_group_ledger_v3_1_public_commitment.json"
)
PRIVATE_OUTPUT = (
    ROOT
    / "data/restricted/"
    "untouched_v3_1_technical_preflight_wave1_private.json"
)
PUBLIC_OUTPUT = (
    ROOT
    / "data/rehearsal_plan/"
    "untouched_v3_1_technical_preflight_wave1_public.json"
)
REVIEW_OUTPUT = (
    ROOT / "docs/review/untouched_v3_1_technical_preflight_wave1.md"
)

ASSEMBLY_AUTH_REGISTRY = (
    ROOT / "data/rehearsal_plan/assembly101_authenticated_registry_v1.json"
)
ASSEMBLY_INVENTORY = (
    ROOT
    / "data/hf_recon/assembly101_authenticated_v1/derived/"
    "nonsemantic_session_inventory.json"
)
ASSEMBLY_CARD = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/metadata/"
    "assembly101/hf_README.md"
)
ACCESS_REGISTRY = (
    ROOT / "data/rehearsal_plan/assembly_epic_access_registry_v2.json"
)
EPIC_MANIFEST = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/derived/"
    "epic_video_manifest.csv"
)
EPIC_MD5 = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/metadata/epic/md5.csv"
)
EPIC_README = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/metadata/epic/"
    "data_bris_readme.txt"
)
HOLO_SUPPLEMENT = (
    ROOT / "data/rehearsal_plan/holoassist_exposure_supplement_v1.json"
)
HOLO_TIMING_CACHE = (
    ROOT / "data/restricted/holoassist_technical_timing_cache_v1"
)

SCHEMA_PRIVATE = "av-trace.untouched-v3.1-technical-preflight-private/1.0"
SCHEMA_PUBLIC = "av-trace.untouched-v3.1-technical-preflight-public/1.0"
PREFLIGHT_ID = "UNTOUCHED_V3_1_TECHNICAL_PREFLIGHT_WAVE1"
GENERATED_DATE = "2026-10-15"
READY = "UNTOUCHED_V3_1_TECHNICAL_PREFLIGHT_WAVE1_READY"
REPAIR = "UNTOUCHED_V3_1_TECHNICAL_PREFLIGHT_WAVE1_REPAIR"

LINEAGES = ("ASSEMBLY101", "EPIC", "HOLOASSIST")
DECISIONS = ("TECH_READY", "REPAIR", "NO_GO")
SELECTION_FIELD = "v3_1_group_commitment_sha256"
DEFAULT_PROXIES = (
    "https://proxy.example.invalid:3128",
    "https://proxy.example.invalid:3128",
)

ASSEMBLY_REPO = "cvml-nus/assembly101"
ASSEMBLY_REVISION = "bfc15ea5e3f0bc8f8c232af6c1b45aa137a9d967"
ASSEMBLY_LICENSE = "CC-BY-NC-4.0"
ASSEMBLY_VIEW = "C10095_rgb.mp4"

EPIC_55_BASE = "https://data.bris.ac.uk/datasets/3h91syskeag572hl6tvuovwv4d"
EPIC_LICENSE = "CC-BY-NC-4.0"

HOLO_REPO = "SitongGong/HoloAssist"
HOLO_REVISION = "7ad9269e82503f677cb4ec64d77a460d0790a6c4"
HOLO_LICENSE = "CDLA-Permissive-2.0"
HOLO_INFO_PATH = Path("/tmp/holo_hf_info.json")

WINDOW_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_CANDIDATE_BYTES = 8 * 1024 * 1024
MAX_AGGREGATE_BYTES = 16 * 1024 * 1024
PRIVATE_FILE_MODE = 0o600
PUBLIC_FILE_MODE = 0o644

EXPECTED_HASHES = {
    PRIVATE_LEDGER: (
        "11f87b1d3d39c5ca12859b7cb5385eaae923add03075a0bd0984155cf403a149"
    ),
    PUBLIC_LEDGER: (
        "0e5b98ef6ec19d8ac5124cce53035eccab3f75955f38e7fe0999ab850ef40f15"
    ),
    ASSEMBLY_AUTH_REGISTRY: (
        "72d2a22ed041fe86da49a0b837c1056dd3a16ff94151de83c9ec6da8d003dc71"
    ),
    ASSEMBLY_INVENTORY: (
        "4a819fcd19ae4674f75f699db9a88fd92721d22f05763187a5d1975ca5756754"
    ),
    ACCESS_REGISTRY: (
        "22f1c3a5a59f60e94e5b8d61b3ded4f71558805502f25ac9295e8007204ef9b1"
    ),
    EPIC_MANIFEST: (
        "5324968444483c49bce5ca107398b6c81faab275b218678493242f42b6b2acac"
    ),
    EPIC_MD5: (
        "3f9c31899ff5807c8f0fed5d26a8fe62300f3f4c40dc3eea767345212c2e83c7"
    ),
    HOLO_SUPPLEMENT: (
        "47060b97dbf80e84c9ec4c5f7db07e2e2f841269293e402954321e825c85e890"
    ),
}

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IDENTITY_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])R\d{3,}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])Z\d{3,}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])P\d{2}_\d{2,3}(?!\d)"),
    re.compile(r"nusar-[A-Za-z0-9_-]+", re.IGNORECASE),
)
FORBIDDEN_PUBLIC_KEYS = {
    "identity",
    "identity_and_evidence",
    "exact_object",
    "exact_object_or_session_id",
    "object_path",
    "recording_root",
    "session_id",
    "source_url",
    "technical_path",
    "timing_path",
}
FORBIDDEN_PUBLIC_TEXT = (
    "extracted_videos/",
    "VideoMp4Timing",
    "Pose_sync",
    "recordings/",
    "data.bris.ac.uk/datasets/",
)


class PreflightError(RuntimeError):
    """Stable failure without credentials, signed URLs, or private identities."""


@dataclass(frozen=True)
class SelectedGroup:
    dataset_lineage: str
    commitment_id: str
    slot: str
    source_commitment_sha256: str
    private_group: Mapping[str, Any]


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PreflightError(f"JSON_OBJECT_REQUIRED:{path.name}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def validate_bound_inputs() -> None:
    for path, expected in EXPECTED_HASHES.items():
        if not path.is_file():
            raise PreflightError(f"BOUND_INPUT_MISSING:{path.name}")
        if sha256_path(path) != expected:
            raise PreflightError(f"BOUND_INPUT_HASH_MISMATCH:{path.name}")


def git_lfs_pointer_blob_id(sha256: str, size_bytes: int) -> str:
    pointer = (
        "version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{sha256}\n"
        f"size {size_bytes}\n"
    ).encode()
    return hashlib.sha1(
        f"blob {len(pointer)}\0".encode() + pointer
    ).hexdigest()


def select_public_minima(
    public_groups: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    """Select exactly one commitment per lineage without private fields."""
    allowed = {
        "dataset_lineage",
        "v3_1_group_commitment_sha256",
    }
    by_lineage: dict[str, list[str]] = {lineage: [] for lineage in LINEAGES}
    for row in public_groups:
        if not isinstance(row, Mapping):
            raise PreflightError("PUBLIC_GROUP_ROW_NOT_OBJECT")
        if not set(row).issuperset(allowed):
            raise PreflightError("PUBLIC_GROUP_SELECTION_FIELDS_MISSING")
        lineage = row.get("dataset_lineage")
        commitment = row.get(SELECTION_FIELD)
        if lineage not in by_lineage:
            raise PreflightError("UNEXPECTED_DATASET_LINEAGE")
        if not isinstance(commitment, str) or not SHA256_RE.fullmatch(commitment):
            raise PreflightError("INVALID_PUBLIC_COMMITMENT")
        by_lineage[str(lineage)].append(commitment)
    if any(not values for values in by_lineage.values()):
        raise PreflightError("LINEAGE_WITHOUT_COMMITMENT")
    if any(len(values) != len(set(values)) for values in by_lineage.values()):
        raise PreflightError("DUPLICATE_LINEAGE_COMMITMENT")
    return {
        lineage: min(by_lineage[lineage])
        for lineage in LINEAGES
    }


def reveal_selected_groups(
    private: Mapping[str, Any],
    selected: Mapping[str, str],
) -> list[SelectedGroup]:
    groups = private.get("selected_groups")
    if not isinstance(groups, list):
        raise PreflightError("PRIVATE_SELECTED_GROUPS_MISSING")
    by_commitment: dict[str, Mapping[str, Any]] = {}
    for row in groups:
        if isinstance(row, Mapping):
            commitment = row.get(SELECTION_FIELD)
            if isinstance(commitment, str):
                by_commitment[commitment] = row
    result: list[SelectedGroup] = []
    for lineage in LINEAGES:
        commitment = selected[lineage]
        row = by_commitment.get(commitment)
        if row is None or row.get("dataset_lineage") != lineage:
            raise PreflightError("PRIVATE_COMMITMENT_MAPPING_MISMATCH")
        result.append(
            SelectedGroup(
                dataset_lineage=lineage,
                commitment_id=commitment,
                slot=str(row["slot"]),
                source_commitment_sha256=str(
                    row["source_commitment_sha256"]
                ),
                private_group=row,
            )
        )
    return result


def select_groups(root: Path = ROOT) -> list[SelectedGroup]:
    public = load_json(
        root
        / "data/rehearsal_plan/"
        "untouched_test_group_ledger_v3_1_public_commitment.json"
    )
    private = load_json(
        root / "data/restricted/untouched_test_group_ledger_v3_1_private.json"
    )
    if private.get("locks", {}).get("test_construction_locked") is not True:
        raise PreflightError("ROSTER_LOCK_NOT_INTACT")
    if private.get("locks", {}).get("distribution_locked") is not True:
        raise PreflightError("DISTRIBUTION_LOCK_NOT_INTACT")
    selected = select_public_minima(public.get("group_commitments", []))
    return reveal_selected_groups(private, selected)


def _assembly_candidate(
    selected: SelectedGroup,
) -> tuple[core.Candidate, dict[str, Any]]:
    evidence = selected.private_group["identity_and_evidence"]
    session_id = str(evidence["exact_object_or_session_id"])
    inventory = load_json(ASSEMBLY_INVENTORY)
    sessions = inventory.get("sessions")
    if not isinstance(sessions, list):
        raise PreflightError("ASSEMBLY_INVENTORY_MISSING")
    row = next(
        (
            item
            for item in sessions
            if isinstance(item, Mapping)
            and item.get("session_id") == session_id
        ),
        None,
    )
    if row is None:
        raise PreflightError("ASSEMBLY_EXACT_SESSION_MISSING")
    path = str(row["lexicographic_representative_mp4"])
    expected = f"recordings/{session_id}/{ASSEMBLY_VIEW}"
    if path != expected:
        raise PreflightError("ASSEMBLY_EXACT_PATH_MISMATCH")
    size = int(row["lexicographic_representative_size_bytes"])
    digest = str(row["lexicographic_representative_lfs_sha256"])
    candidate = core.Candidate.from_mapping(
        {
            "candidate_id": "wave1-assembly101",
            "repo_id": ASSEMBLY_REPO,
            "revision": ASSEMBLY_REVISION,
            "path": path,
            "size_bytes": size,
            "hash_algorithm": "sha256",
            "hash": digest,
            "blob_id": git_lfs_pointer_blob_id(digest, size),
        }
    )
    technical = {
        "session_id": session_id,
        "participant_id": str(row["participant_id"]),
        "object_path": path,
        "size_bytes": size,
        "lfs_sha256": digest,
        "view_file_count": int(row["view_file_count"]),
        "fixed_view_file_count": int(row["fixed_view_file_count"]),
        "egocentric_view_file_count": int(
            row["egocentric_view_file_count"]
        ),
        "view_complete_12": row["view_complete_12"] is True,
        "session_total_mp4_bytes": int(row["total_mp4_bytes"]),
    }
    return candidate, technical


def _epic_object_url(object_path: str) -> str:
    return f"{EPIC_55_BASE}/{object_path}"


def _epic_spec(selected: SelectedGroup) -> dict[str, Any]:
    evidence = selected.private_group["identity_and_evidence"]
    video_id = str(evidence["exact_object_or_session_id"])
    manifest = next(
        (row for row in read_csv(EPIC_MANIFEST) if row["video_id"] == video_id),
        None,
    )
    if manifest is None:
        raise PreflightError("EPIC_VIDEO_MANIFEST_ROW_MISSING")
    md5_rows = [
        row
        for row in read_csv(EPIC_MD5)
        if row.get("version") == manifest["media_manifest_version"]
        and row.get("md5") == manifest["md5"]
        and row.get("file_remote_path", "").lower().endswith(
            f"/{video_id.lower()}.mp4"
        )
    ]
    if len(md5_rows) != 1:
        raise PreflightError("EPIC_EXACT_OBJECT_PATH_MISSING")
    object_path = md5_rows[0]["file_remote_path"]
    if PurePosixPath(object_path).is_absolute() or ".." in PurePosixPath(
        object_path
    ).parts:
        raise PreflightError("EPIC_OBJECT_PATH_INVALID")
    return {
        "video_id": video_id,
        "participant_id": manifest["participant_id"],
        "object_path": object_path,
        "source_url": _epic_object_url(object_path),
        "manifest_version": manifest["media_manifest_version"],
        "md5": manifest["md5"],
        "duration_seconds": float(manifest["duration_seconds"]),
        "fps": float(manifest["fps"]),
        "resolution": manifest["resolution"],
    }


def _holo_spec(selected: SelectedGroup) -> dict[str, Any]:
    evidence = selected.private_group["identity_and_evidence"]
    group = evidence["opaque_universe_group"]
    variants = group.get("variants")
    if not isinstance(variants, list) or not variants:
        raise PreflightError("HOLO_VARIANTS_MISSING")
    technical_variants: list[dict[str, Any]] = []
    for variant in sorted(variants, key=lambda item: str(item["timing_path"])):
        timing_path = str(variant["timing_path"])
        cache_path = HOLO_TIMING_CACHE / timing_path
        if not cache_path.is_file():
            raise PreflightError("HOLO_TIMING_CACHE_MISSING")
        data = cache_path.read_bytes()
        expected = variant["timing_evidence"]
        if (
            len(data) != int(expected["bytes"])
            or sha256_bytes(data) != expected["sha256"]
            or expected["format_recognized"] is not True
        ):
            raise PreflightError("HOLO_TIMING_EVIDENCE_MISMATCH")
        technical_variants.append(
            {
                "folder": str(variant["folder"]),
                "timing_path": timing_path,
                "timing_bytes": len(data),
                "timing_sha256": sha256_bytes(data),
                "duration_seconds": float(expected["duration_seconds"]),
                "frame_count": int(expected["frame_count"]),
            }
        )
    return {
        "recording_root": str(group["recording_root"]),
        "variants": technical_variants,
        "timing_closed": group.get("timing_closed") is True,
    }


def local_rights_and_routes(
    selected_groups: Sequence[SelectedGroup],
) -> dict[str, dict[str, Any]]:
    auth = load_json(ASSEMBLY_AUTH_REGISTRY)
    access = load_json(ACCESS_REGISTRY)
    supplement = load_json(HOLO_SUPPLEMENT)
    card_text = ASSEMBLY_CARD.read_text(encoding="utf-8")
    epic_rights = EPIC_README.read_text(encoding="utf-8")
    selected_by_lineage = {
        group.dataset_lineage: group for group in selected_groups
    }

    pinned = auth.get("pinned_source", {})
    assembly_candidate, assembly_technical = _assembly_candidate(
        selected_by_lineage["ASSEMBLY101"]
    )
    assembly = {
        "rights_license": (
            pinned.get("license_declared_by_official_hf_card")
            == ASSEMBLY_LICENSE
            and "license: cc-by-nc-4.0" in card_text.lower()
        ),
        "gate_state": (
            "AUTHENTICATED_LOGIN_PRESENT_BUT_MEDIA_AUTHORIZATION_REQUIRES_LIVE_CHECK"
        ),
        "exact_route": True,
        "candidate": assembly_candidate,
        "technical": assembly_technical,
    }

    epic_registry = access.get("epic", {})
    epic_spec = _epic_spec(selected_by_lineage["EPIC"])
    epic = {
        "rights_license": (
            epic_registry.get("license", {}).get("spdx") == EPIC_LICENSE
            and "Creative Commons Attribution-NonCommerial 4.0"
            in epic_rights.replace("\n", " ")
        ),
        "gate_state": (
            "PUBLIC_NO_REGISTRATION"
            if epic_registry.get("access", {}).get(
                "registration_required_for_data_bris_route"
            )
            is False
            else "UNRESOLVED"
        ),
        "exact_route": True,
        "technical": epic_spec,
    }

    holo_spec = _holo_spec(selected_by_lineage["HOLOASSIST"])
    holo = {
        "rights_license": (
            supplement.get("license_discrepancy", {}).get(
                "operative_license_claim"
            )
            == "OFFICIAL_DECLARATION_CONTROLS"
            and supplement.get("license_discrepancy", {}).get(
                "official_declared_license"
            )
            == HOLO_LICENSE
        ),
        "gate_state": (
            "PUBLIC_UNGATED_MIRROR"
            if supplement.get("hugging_face_metadata_evidence", {}).get(
                "gated"
            )
            is False
            else "UNRESOLVED"
        ),
        "exact_route": True,
        "technical": holo_spec,
    }
    return {
        "ASSEMBLY101": assembly,
        "EPIC": epic,
        "HOLOASSIST": holo,
    }


def _safe_live_assembly_metadata(
    candidate: core.Candidate,
    proxies: Sequence[str],
) -> dict[str, Any]:
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return {"status": "FAILED", "error_code": "HUGGINGFACE_HUB_MISSING"}
    token = core.load_hf_token()
    if not token:
        return {"status": "FAILED", "error_code": "HF_TOKEN_NOT_AVAILABLE"}
    attempts: list[dict[str, Any]] = []
    original_http = os.environ.get("HTTP_PROXY")
    original_https = os.environ.get("HTTPS_PROXY")
    try:
        for proxy in proxies:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
            try:
                info = HfApi(endpoint="https://huggingface.co").dataset_info(
                    ASSEMBLY_REPO,
                    revision=ASSEMBLY_REVISION,
                    files_metadata=True,
                    token=token,
                    timeout=60,
                )
            except Exception as exc:  # noqa: BLE001
                attempts.append(
                    {
                        "proxy_route": core.proxy_label(proxy),
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                    }
                )
                continue
            sibling = next(
                (
                    item
                    for item in info.siblings
                    if item.rfilename == candidate.path
                ),
                None,
            )
            lfs = getattr(sibling, "lfs", None) if sibling else None
            return {
                "status": "SUCCEEDED",
                "attempts": attempts
                + [
                    {
                        "proxy_route": core.proxy_label(proxy),
                        "status": "SUCCEEDED",
                    }
                ],
                "repo_id": info.id,
                "revision": info.sha,
                "private": info.private,
                "gated": info.gated,
                "license": (info.card_data or {}).get("license"),
                "exact_file": {
                    "path": candidate.path,
                    "size_bytes": getattr(sibling, "size", None),
                    "blob_id": getattr(sibling, "blob_id", None),
                    "lfs_sha256": getattr(lfs, "sha256", None)
                    if lfs
                    else None,
                },
            }
    finally:
        if original_http is None:
            os.environ.pop("HTTP_PROXY", None)
        else:
            os.environ["HTTP_PROXY"] = original_http
        if original_https is None:
            os.environ.pop("HTTPS_PROXY", None)
        else:
            os.environ["HTTPS_PROXY"] = original_https
    return {"status": "FAILED", "attempts": attempts}


def _probe_assembly(
    candidate: core.Candidate,
    proxies: Sequence[str],
    budget: core.Budget,
) -> dict[str, Any]:
    metadata = _safe_live_assembly_metadata(candidate, proxies)
    token = core.load_hf_token()
    if not token:
        return {
            "metadata": metadata,
            "candidate": None,
            "error_code": "HF_TOKEN_NOT_AVAILABLE",
        }
    with core.SafeHFRangeClient(
        token,
        proxies=proxies,
        budget=budget,
        maximum_candidate_bytes=MAX_CANDIDATE_BYTES,
        user_agent="AV-TRACE-Untouched-v3.1-Wave1/1.0",
    ) as client:
        result = core.run_candidate(
            candidate, client, window_bytes=WINDOW_BYTES
        )
    return {"metadata": metadata, "candidate": result}


def _head_epic(
    spec: Mapping[str, Any],
    proxies: Sequence[str],
    budget: core.Budget,
) -> dict[str, Any]:
    """HEAD the exact EPIC object, then run bounded ranges if identity is exact."""
    if core.httpx is None:
        return {"status": "FAILED", "error_code": "HTTPX_NOT_INSTALLED"}
    url = str(spec["source_url"])
    last_code = "NO_PROXY_ROUTE_SUCCEEDED"
    for proxy in proxies:
        kwargs: dict[str, Any] = {
            "follow_redirects": True,
            "timeout": core.httpx.Timeout(60.0, connect=30.0),
            "headers": {
                "Accept-Encoding": "identity",
                "User-Agent": "AV-TRACE-Untouched-v3.1-Wave1/1.0",
            },
            "trust_env": False,
            "proxy": proxy,
        }
        try:
            with core.httpx.Client(**kwargs) as client:
                response = client.head(url)
        except Exception as exc:  # noqa: BLE001
            last_code = f"HTTP_TRANSPORT_{type(exc).__name__.upper()}"
            continue
        if response.status_code != 200:
            last_code = f"HTTP_STATUS_{response.status_code}"
            continue
        headers = response.headers
        raw_size = headers.get("content-length")
        if raw_size is None or not raw_size.isdigit():
            return {"status": "FAILED", "error_code": "HEAD_SIZE_MISSING"}
        observed_url = core.strip_url_secrets(str(response.url))
        head = {
            "status": "SUCCEEDED",
            "proxy_route": core.proxy_label(proxy),
            "http_status": response.status_code,
            "url": observed_url,
            "content_length": int(raw_size),
            "etag": headers.get("etag"),
            "last_modified": headers.get("last-modified"),
            "content_type": headers.get("content-type"),
            "accept_ranges": headers.get("accept-ranges"),
            "response_body_bytes": 0,
        }
        if (
            not head["etag"]
            or not head["last_modified"]
            or not head["content_type"]
            or (head["accept_ranges"] or "").lower() != "bytes"
        ):
            return {
                "status": "FAILED",
                "head": head,
                "error_code": "HEAD_TECHNICAL_IDENTITY_INCOMPLETE",
            }
        candidate = core.DirectURLCandidate.from_mapping(
            {
                "candidate_id": "wave1-epic",
                "url": url,
                "size_bytes": head["content_length"],
                "etag": head["etag"],
                "last_modified": head["last_modified"],
                "content_type": head["content_type"],
                "accept_ranges": head["accept_ranges"],
            }
        )
        with core.SafeDirectURLRangeClient(
            allowed_host=lambda host: host.lower().rstrip(".")
            == "data.bris.ac.uk",
            proxies=proxies,
            budget=budget,
            maximum_candidate_bytes=MAX_CANDIDATE_BYTES,
            user_agent="AV-TRACE-Untouched-v3.1-Wave1/1.0",
        ) as range_client:
            result = core.run_candidate(
                candidate, range_client, window_bytes=WINDOW_BYTES
            )
        return {"status": "COMPLETED", "head": head, "candidate": result}
    return {"status": "FAILED", "error_code": last_code}


def discover_holo_exact_video(
    technical: Mapping[str, Any],
    info_path: Path = HOLO_INFO_PATH,
) -> dict[str, Any] | None:
    """Return a technical MP4 listing only if an exact selected object exists."""
    if not info_path.is_file():
        return None
    value = json.loads(info_path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        return None
    siblings = value.get("siblings")
    if not isinstance(siblings, list):
        return None
    prefixes = {
        str(item["folder"]).rstrip("/") + "/"
        for item in technical.get("variants", [])
        if isinstance(item, Mapping) and item.get("folder")
    }
    matches: list[dict[str, Any]] = []
    for item in siblings:
        if not isinstance(item, Mapping):
            continue
        path = item.get("rfilename")
        if (
            isinstance(path, str)
            and path.lower().endswith(".mp4")
            and any(path.startswith(prefix) for prefix in prefixes)
        ):
            matches.append(dict(item))
    if not matches:
        return None
    return sorted(matches, key=lambda item: str(item["rfilename"]))[0]


def run_live(
    local: Mapping[str, Mapping[str, Any]],
    proxies: Sequence[str],
) -> dict[str, Any]:
    budget = core.Budget(
        maximum_response_bytes=MAX_RESPONSE_BYTES,
        maximum_total_bytes=MAX_AGGREGATE_BYTES,
    )
    assembly = _probe_assembly(
        local["ASSEMBLY101"]["candidate"], proxies, budget
    )
    epic = _head_epic(local["EPIC"]["technical"], proxies, budget)
    holo_discovery = discover_holo_exact_video(
        local["HOLOASSIST"]["technical"]
    )
    return {
        "ASSEMBLY101": assembly,
        "EPIC": epic,
        "HOLOASSIST": {
            "timing_evidence": "RETAINED_EXACT_TECHNICAL_TEXT",
            "exact_video_discovery": holo_discovery,
            "media_probe": (
                "NOT_RUN_NO_EXACT_VIDEO_OBJECT_DISCOVERED"
                if holo_discovery is None
                else "NOT_RUN_LISTING_LACKS_PINNED_SIZE_AND_HASH"
            ),
        },
        "byte_accounting": {
            "maximum_response_payload_bytes": MAX_RESPONSE_BYTES,
            "maximum_aggregate_response_payload_bytes": MAX_AGGREGATE_BYTES,
            "response_payload_bytes_read": budget.total_bytes,
            "maximum_observed_response_payload_bytes": (
                budget.maximum_observed_response
            ),
            "response_payload_bytes_persisted": 0,
            "media_probe_bytes_deleted_or_released": True,
        },
    }


def _candidate_technical_status(
    result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not result:
        return {
            "head_or_exact_identity": False,
            "range_access": False,
            "duration_metadata": False,
            "video_stream": False,
            "audio_stream": False,
            "native_sync": False,
        }
    return {
        "head_or_exact_identity": result.get("identity_match") is True,
        "range_access": result.get("range_request_count", 0) > 0,
        "duration_metadata": isinstance(
            result.get("duration_seconds"), (int, float)
        ),
        "video_stream": result.get("video_track_count", 0) > 0,
        "audio_stream": result.get("audio_track_count", 0) > 0,
        "native_sync": (
            result.get("av_timeline_relation")
            == "PLAUSIBLY_SYNCHRONIZED"
        ),
    }


def classify_group(
    *,
    lineage: str,
    rights_license: bool,
    gate_state: str,
    exact_route: bool,
    technical: Mapping[str, Any],
    terminal_identity_mismatch: bool = False,
    terminal_no_video: bool = False,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if not rights_license:
        blockers.append("RIGHTS_OR_LICENSE_UNRESOLVED")
    if gate_state == "UNRESOLVED":
        blockers.append("ACCESS_GATE_UNRESOLVED")
    if not exact_route:
        blockers.append("EXACT_OBJECT_OR_SESSION_ROUTE_UNRESOLVED")
    required = (
        "head_or_exact_identity",
        "range_access",
        "duration_metadata",
        "video_stream",
        "audio_stream",
        "native_sync",
    )
    for key in required:
        if technical.get(key) is not True:
            blockers.append(key.upper() + "_UNRESOLVED")
    if not blockers:
        return "TECH_READY", []
    if terminal_identity_mismatch or terminal_no_video:
        return "NO_GO", blockers
    if lineage == "HOLOASSIST" and technical.get("duration_metadata") is True:
        return "REPAIR", blockers
    return "REPAIR", blockers


def _private_group_record(
    selected: SelectedGroup,
    local: Mapping[str, Any],
    live: Mapping[str, Any] | None,
) -> dict[str, Any]:
    lineage = selected.dataset_lineage
    candidate_result: Mapping[str, Any] | None = None
    terminal_identity = False
    terminal_no_video = False
    if lineage == "ASSEMBLY101":
        candidate_result = (
            live.get("candidate")
            if isinstance(live, Mapping)
            and isinstance(live.get("candidate"), Mapping)
            else None
        )
        metadata = live.get("metadata", {}) if isinstance(live, Mapping) else {}
        gate = (
            "AUTHENTICATED_AND_MEDIA_ACCESS_CONFIRMED"
            if candidate_result
            and candidate_result.get("identity_match") is True
            else local["gate_state"]
        )
        exact_evidence = local["technical"]
    elif lineage == "EPIC":
        candidate_result = (
            live.get("candidate")
            if isinstance(live, Mapping)
            and isinstance(live.get("candidate"), Mapping)
            else None
        )
        metadata = live.get("head", {}) if isinstance(live, Mapping) else {}
        gate = local["gate_state"]
        exact_evidence = local["technical"]
    else:
        metadata = {}
        gate = local["gate_state"]
        exact_evidence = local["technical"]

    status = _candidate_technical_status(candidate_result)
    if lineage == "HOLOASSIST":
        variants = exact_evidence["variants"]
        status["duration_metadata"] = (
            exact_evidence.get("timing_closed") is True
            and bool(variants)
            and all(
                isinstance(item.get("duration_seconds"), (int, float))
                for item in variants
            )
        )
        status["head_or_exact_identity"] = False
        status["range_access"] = False
        status["video_stream"] = False
        status["audio_stream"] = False
        status["native_sync"] = False
    if candidate_result is None and lineage != "HOLOASSIST":
        status["duration_metadata"] = isinstance(
            exact_evidence.get("duration_seconds"), (int, float)
        )
    if candidate_result:
        terminal_identity = bool(
            candidate_result.get("head_identity") is not None
            and candidate_result.get("identity_match") is not True
            and candidate_result.get("limitations")
            == ["HEAD_IDENTITY_MISMATCH"]
        )
        terminal_no_video = bool(
            candidate_result.get("container_parse_status")
            == "PARSED_ISO_BMFF"
            and candidate_result.get("video_track_count") == 0
        )
    decision, blockers = classify_group(
        lineage=lineage,
        rights_license=bool(local["rights_license"]),
        gate_state=gate,
        exact_route=bool(local["exact_route"]),
        technical=status,
        terminal_identity_mismatch=terminal_identity,
        terminal_no_video=terminal_no_video,
    )
    return {
        "commitment_id": selected.commitment_id,
        "dataset_lineage": lineage,
        "slot": selected.slot,
        "source_commitment_sha256": selected.source_commitment_sha256,
        "decision": decision,
        "blockers": blockers,
        "rights_license_gate": {
            "rights_license_established": bool(local["rights_license"]),
            "access_gate_state": gate,
        },
        "private_identity_and_exact_evidence": exact_evidence,
        "live_metadata_or_head": metadata,
        "bounded_container_probe": candidate_result,
        "technical_status": status,
        "exposure": {
            "classification": "METADATA_ACCESS_ONLY",
            "semantic_content_accessed": False,
            "media_content_inspected": False,
            "identity_publication": False,
        },
    }


def build_reports(
    *,
    mode: str,
    selected_groups: Sequence[SelectedGroup],
    local: Mapping[str, Mapping[str, Any]],
    live: Mapping[str, Any] | None,
    generated_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    live = live or {}
    private_groups = [
        _private_group_record(
            selected,
            local[selected.dataset_lineage],
            live.get(selected.dataset_lineage)
            if isinstance(live, Mapping)
            else None,
        )
        for selected in selected_groups
    ]
    private_groups.sort(key=lambda item: item["dataset_lineage"])
    byte_accounting = (
        dict(live.get("byte_accounting", {}))
        if isinstance(live, Mapping)
        else {}
    )
    byte_accounting.setdefault(
        "maximum_response_payload_bytes", MAX_RESPONSE_BYTES
    )
    byte_accounting.setdefault(
        "maximum_aggregate_response_payload_bytes", MAX_AGGREGATE_BYTES
    )
    byte_accounting.setdefault("response_payload_bytes_read", 0)
    byte_accounting.setdefault("maximum_observed_response_payload_bytes", 0)
    byte_accounting.setdefault("response_payload_bytes_persisted", 0)
    byte_accounting.setdefault("media_probe_bytes_deleted_or_released", True)
    if (
        int(byte_accounting["response_payload_bytes_read"])
        > MAX_AGGREGATE_BYTES
        or int(byte_accounting["maximum_observed_response_payload_bytes"])
        > MAX_RESPONSE_BYTES
        or int(byte_accounting["response_payload_bytes_persisted"]) != 0
    ):
        raise PreflightError("BYTE_ACCOUNTING_LIMIT_VIOLATION")

    all_ready = all(
        item["decision"] == "TECH_READY" for item in private_groups
    )
    final_marker = READY if all_ready else REPAIR
    decision_counts = {
        decision: sum(
            item["decision"] == decision for item in private_groups
        )
        for decision in DECISIONS
    }
    common = {
        "preflight_id": PREFLIGHT_ID,
        "generated_date": GENERATED_DATE,
        "generated_at": generated_at or utc_now(),
        "mode": mode,
        "selection": {
            "rule": (
                "Exactly one frozen group per dataset lineage, selected by "
                "lexicographically minimum public v3.1 group commitment."
            ),
            "selection_field": SELECTION_FIELD,
            "lineage_count": len(LINEAGES),
            "selected_group_count": len(private_groups),
            "identity_fields_used_for_selection": False,
        },
        "locks": {
            "roster_remained_locked": True,
            "replacement_executed": False,
            "test_construction_remained_locked": True,
            "distribution_remained_locked": True,
        },
        "scope": {
            "technical_only": True,
            "semantic_annotations_opened": False,
            "labels_opened": False,
            "task_titles_or_descriptions_opened": False,
            "transcripts_or_captions_opened": False,
            "candidate_yield_estimated": False,
            "full_media_downloads": 0,
            "media_payload_bytes_persisted": 0,
            "exposure_classification": "METADATA_ACCESS_ONLY",
        },
        "byte_accounting": byte_accounting,
        "decision_counts": decision_counts,
        "final_marker": final_marker,
    }
    private = {
        "schema_version": SCHEMA_PRIVATE,
        **common,
        "artifact_classification": "CUSTODIAN_PRIVATE",
        "source_bindings": {
            path.relative_to(ROOT).as_posix(): sha256_path(path)
            for path in EXPECTED_HASHES
        },
        "groups": private_groups,
    }
    public_groups = [
        {
            "commitment_id": item["commitment_id"],
            "dataset_lineage": item["dataset_lineage"],
            "decision": item["decision"],
            "technical_status": dict(item["technical_status"]),
            "exposure": "METADATA_ACCESS_ONLY",
        }
        for item in private_groups
    ]
    public = {
        "schema_version": SCHEMA_PUBLIC,
        **common,
        "artifact_classification": "PUBLIC_COMMITMENT_STATUS_ONLY",
        "groups": public_groups,
        "private_report_sha256": sha256_bytes(canonical_bytes(private)),
    }
    validate_public_non_disclosure(
        public,
        private_groups=private_groups,
        review_text=None,
    )
    return private, public


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key).lower())
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def _private_identity_strings(
    private_groups: Sequence[Mapping[str, Any]],
) -> set[str]:
    values: set[str] = set()
    for group in private_groups:
        evidence = group.get("private_identity_and_exact_evidence", {})
        if not isinstance(evidence, Mapping):
            continue
        for key in (
            "session_id",
            "participant_id",
            "object_path",
            "source_url",
            "video_id",
            "recording_root",
        ):
            value = evidence.get(key)
            if isinstance(value, str) and value:
                values.add(value)
        for variant in evidence.get("variants", []):
            if isinstance(variant, Mapping):
                for key in ("folder", "timing_path"):
                    value = variant.get(key)
                    if isinstance(value, str) and value:
                        values.add(value)
    return values


def validate_public_non_disclosure(
    public: Mapping[str, Any],
    *,
    private_groups: Sequence[Mapping[str, Any]],
    review_text: str | None,
) -> None:
    keys = _walk_keys(public)
    forbidden_keys = keys & FORBIDDEN_PUBLIC_KEYS
    if forbidden_keys:
        raise PreflightError(
            "PUBLIC_PRIVATE_KEY_LEAK:" + ",".join(sorted(forbidden_keys))
        )
    raw = canonical_bytes(public).decode("utf-8")
    combined = raw + ("\n" + review_text if review_text else "")
    for identity in _private_identity_strings(private_groups):
        if identity in combined:
            raise PreflightError("PUBLIC_IDENTITY_LEAK")
    if any(pattern.search(combined) for pattern in IDENTITY_PATTERNS):
        raise PreflightError("PUBLIC_IDENTITY_PATTERN_LEAK")
    if any(token in combined for token in FORBIDDEN_PUBLIC_TEXT):
        raise PreflightError("PUBLIC_TECHNICAL_PATH_LEAK")


def render_review(public: Mapping[str, Any]) -> str:
    lines = [
        "# Untouched v3.1 technical preflight wave 1",
        "",
        f"**Final marker: `{public['final_marker']}`**",
        "",
        "Finalized on **October 15, 2026**. The frozen roster remained locked;",
        "this wave executed no replacement and made no source-suitability or",
        "semantic-yield claim.",
        "",
        "## Selection and privacy boundary",
        "",
        "- Exactly one group per dataset lineage was selected by the minimum",
        "  public v3.1 group commitment ID.",
        "- Selection did not use identities, labels, titles, descriptions,",
        "  transcripts, annotations, media content, or candidate yields.",
        "- Public artifacts expose commitment IDs, lineage labels, technical",
        "  status booleans, blocker codes, and decisions only.",
        "- Exposure is classified as **metadata/access only**.",
        "",
        "## Technical decisions",
        "",
        "| Dataset lineage | Commitment ID | Decision | Exact identity | Range | Duration | Video | Audio | Native sync |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for group in public["groups"]:
        status = group["technical_status"]
        lines.append(
            "| {dataset_lineage} | `{commitment_id}` | **{decision}** | "
            "{head_or_exact_identity} | {range_access} | {duration_metadata} | "
            "{video_stream} | {audio_stream} | {native_sync} |".format(
                **group,
                **{
                    key: "yes" if value else "no"
                    for key, value in status.items()
                },
            )
        )
    accounting = public["byte_accounting"]
    lines.extend(
        [
            "",
            "## Bounded-access accounting",
            "",
            f"- Aggregate response-payload cap: **{accounting['maximum_aggregate_response_payload_bytes']} bytes**.",
            f"- Response payload read: **{accounting['response_payload_bytes_read']} bytes**.",
            "- Persisted media response payload: **0 bytes**.",
            "- In-memory media probe bytes were released after classification.",
            "- Full media downloads: **0**.",
            "",
            "## Interpretation",
            "",
            "A `TECH_READY` decision means the bounded technical gates closed for",
            "that commitment. `REPAIR` preserves the locked roster while listing",
            "technical evidence still needed. `NO_GO` is reserved for a terminal",
            "identity or media-structure conflict; it does not trigger replacement",
            "in this wave.",
            "",
            f"**{public['final_marker']}**",
            "",
        ]
    )
    return "\n".join(lines)


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_artifacts(
    private: Mapping[str, Any],
    public: Mapping[str, Any],
    review: str,
    *,
    private_path: Path = PRIVATE_OUTPUT,
    public_path: Path = PUBLIC_OUTPUT,
    review_path: Path = REVIEW_OUTPUT,
) -> None:
    validate_public_non_disclosure(
        public,
        private_groups=private["groups"],
        review_text=review,
    )
    atomic_write(private_path, canonical_bytes(private), PRIVATE_FILE_MODE)
    atomic_write(public_path, canonical_bytes(public), PUBLIC_FILE_MODE)
    atomic_write(review_path, review.encode("utf-8"), PUBLIC_FILE_MODE)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("plan-only", "live"),
        default="plan-only",
    )
    parser.add_argument(
        "--proxy",
        action="append",
        dest="proxies",
        default=[],
        help="Existing official-route proxy; repeat for fallback.",
    )
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_bound_inputs()
        selected = select_groups()
        local = local_rights_and_routes(selected)
        live = (
            run_live(local, tuple(args.proxies) or DEFAULT_PROXIES)
            if args.mode == "live"
            else None
        )
        private, public = build_reports(
            mode=args.mode,
            selected_groups=selected,
            local=local,
            live=live,
        )
        review = render_review(public)
        if not args.no_write:
            write_artifacts(private, public, review)
    except PreflightError as exc:
        print(f"{REPAIR}:{exc}", file=sys.stderr)
        return 2
    print(public["final_marker"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
