#!/usr/bin/env python3
"""Independent, redaction-safe integrity and decode audit for NOAA-01.

The tool is intentionally read-only with respect to acquired media. It writes
only the requested audit JSON, never persists decoded frames/audio, never
starts a downloader, and runs every media subprocess with an explicit timeout.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence


PLAN_REL = Path("data/acquisition_plan/noaa01_exact_asset_plan.json")
ACQUISITION_AUTH_REL = Path("data/access_review/noaa01_acquisition_authorization.json")
PROCESSING_AUTH_REL = Path("data/access_review/noaa01_processing_audit_authorization.json")
MANIFEST_REL = Path("data/restricted/noaa01/manifests/noaa01_acquisition_manifest.json")
AUDIT_REL = Path("data/restricted/noaa01/manifests/noaa01_media_audit.json")
RESTRICTED_REL = Path("data/restricted/noaa01")
LOCK_REL = RESTRICTED_REL / "manifests/.noaa_exact_asset_downloader.lock"

EXPECTED_CANDIDATES = ("cand-045", "cand-047", "cand-049", "cand-051", "cand-052")
EXPECTED_PAYLOAD_BYTES = 1_955_298_193
EXPECTED_PAYLOAD_COUNT = 5
EXPECTED_PLAN_SHA256 = "241a476b503a198eafe208485206385f755cd57756f924e769ce8a37d1d1f6fd"
FFPROBE_TIMEOUT_SECONDS = 120
DECODE_TIMEOUT_SECONDS = 180
DECODE_POSITION_TOLERANCE_SECONDS = 2.0

SIGNED_QUERY_RE = re.compile(
    r"(x-amz-(?:signature|credential|security-token|algorithm)|"
    r"x-goog-(?:signature|credential|algorithm)|"
    r"(?:^|[?&])(signature|sig|token|access_token|expires|policy|key-pair-id)=)",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
SENSITIVE_LEAF_KEY_RE = re.compile(
    r"^(password|passwd|secret|access[_-]?token|refresh[_-]?token|"
    r"bearer(?:[_-]?token)?|cookie(?:[_-]?header)?|credential|private[_-]?key|"
    r"client[_-]?secret|access[_-]?key|api[_-]?key|"
    r"authorization(?:[_-]?header)?)$",
    re.IGNORECASE,
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class AuditError(RuntimeError):
    """Expected fail-closed audit error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"INVALID_JSON:{path.as_posix()}") from exc


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        path.chmod(0o600)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def sha256_file(path: Path, *, chunk_size: int = 4 * 1024 * 1024) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while block := handle.read(chunk_size):
                size += len(block)
                digest.update(block)
    except OSError as exc:
        raise AuditError(f"PAYLOAD_READ_FAILED:{path.as_posix()}") from exc
    return size, digest.hexdigest()


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def finite_float(value: Any, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError
    return result


def optional_finite_float(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return finite_float(value)
    except (TypeError, ValueError):
        return None


def parse_fraction(value: Any) -> float | None:
    if value in (None, "", "N/A", "0/0"):
        return None
    try:
        result = float(Fraction(str(value)))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return result if math.isfinite(result) else None


def path_safety(path: Path, restricted_root: Path, repo_root: Path) -> dict[str, Any]:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        resolved = path.resolve(strict=False)
    mode = stat.S_IMODE(path.lstat().st_mode)
    return {
        "path": path.relative_to(repo_root).as_posix(),
        "lexically_under_restricted_root": is_relative_to(
            path.absolute(), restricted_root.absolute()
        ),
        "resolved_under_restricted_root": is_relative_to(
            resolved, restricted_root.resolve(strict=True)
        ),
        "is_regular_file": path.is_file(),
        "is_symlink": path.is_symlink(),
        "mode_octal": f"{mode:04o}",
        "group_or_other_permission_bits": f"{mode & 0o077:03o}",
        "restricted_permissions": (mode & 0o077) == 0,
    }


def _inert_sensitive_value(value: Any) -> bool:
    if value is None or value is False:
        return True
    if isinstance(value, str):
        return value.strip().upper() in {
            "",
            "NONE",
            "NULL",
            "FALSE",
            "NO",
            "PROHIBITED",
            "DISABLED",
            "NOT_USED",
            "NOT PRESENT",
        }
    return False


def scan_sensitive_value(parsed: Any, *, path_label: str, raw: str = "") -> dict[str, Any]:
    """Report only finding kinds/locations, never values."""
    findings: set[tuple[str, str]] = set()

    def walk(value: Any, location: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                key_text = str(key)
                child_location = f"{location}.{key_text}" if location else key_text
                prohibition_control = (
                    ("prohibited" in key_text.lower() or "disabled" in key_text.lower())
                    and child is True
                )
                if (
                    SENSITIVE_LEAF_KEY_RE.search(key_text)
                    and not prohibition_control
                    and not _inert_sensitive_value(child)
                ):
                    findings.add(("non_inert_sensitive_field", child_location))
                walk(child, child_location)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{location}[{index}]")
        elif isinstance(value, str):
            if URL_RE.search(value):
                authority = value.partition("://")[2].partition("/")[0]
                if "@" in authority:
                    findings.add(("url_userinfo", location))
                if SIGNED_QUERY_RE.search(value):
                    findings.add(("signed_url_or_token_query", location))

    walk(parsed, "")
    if SIGNED_QUERY_RE.search(raw):
        findings.add(("raw_signed_url_or_token_indicator", "$"))
    ordered = sorted(findings)
    return {
        "path": path_label,
        "passed": not ordered,
        "finding_count": len(ordered),
        "findings": [{"kind": kind, "location": location} for kind, location in ordered],
        "values_disclosed": False,
    }


def scan_sensitive_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"INVALID_JSON:{path.as_posix()}") from exc
    return scan_sensitive_value(parsed, path_label=path.as_posix(), raw=raw)


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AuditError(f"MALFORMED_{label}")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise AuditError(f"MALFORMED_{label}")
    return value


def validate_inputs(
    plan: Any,
    manifest: Any,
    acquisition_auth: Any,
    processing_auth: Any,
    plan_sha256: str,
) -> tuple[list[Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    plan = _require_mapping(plan, "PLAN")
    manifest = _require_mapping(manifest, "MANIFEST")
    acquisition_auth = _require_mapping(
        acquisition_auth, "ACQUISITION_AUTHORIZATION"
    )
    processing_auth = _require_mapping(processing_auth, "PROCESSING_AUTHORIZATION")
    if plan_sha256 != EXPECTED_PLAN_SHA256:
        raise AuditError("FROZEN_PLAN_SHA256_MISMATCH")
    if plan.get("schema_version") != "1.0":
        raise AuditError("UNSUPPORTED_PLAN_SCHEMA")
    if manifest.get("schema_version") != "1.0":
        raise AuditError("UNSUPPORTED_MANIFEST_SCHEMA")
    if acquisition_auth.get("schema_version") != "1.0":
        raise AuditError("UNSUPPORTED_ACQUISITION_AUTHORIZATION_SCHEMA")
    if processing_auth.get("schema_version") != "1.1":
        raise AuditError("UNSUPPORTED_PROCESSING_AUTHORIZATION_SCHEMA")
    if plan.get("status") != "AUTHORIZED_FOR_EXACT_RESTRICTED_DOWNLOAD_ONLY":
        raise AuditError("FROZEN_PLAN_STATUS_MISMATCH")
    if plan.get("staging_root") != RESTRICTED_REL.as_posix():
        raise AuditError("FROZEN_PLAN_RESTRICTED_ROOT_MISMATCH")

    assets_raw = _require_list(plan.get("assets"), "PLAN_ASSETS")
    manifest_raw = _require_list(manifest.get("assets"), "MANIFEST_ASSETS")
    if len(assets_raw) != EXPECTED_PAYLOAD_COUNT or len(manifest_raw) != EXPECTED_PAYLOAD_COUNT:
        raise AuditError("UNEXPECTED_ASSET_COUNT")
    assets = []
    seen_candidates: set[str] = set()
    seen_basenames: set[str] = set()
    seen_destinations: set[str] = set()
    for raw in assets_raw:
        asset = _require_mapping(raw, "PLAN_ASSET")
        candidate = str(asset.get("candidate_id", ""))
        basename = str(asset.get("basename", ""))
        destination = str(asset.get("destination", ""))
        if not candidate or not basename or not destination:
            raise AuditError("MALFORMED_PLAN_ASSET")
        if candidate in seen_candidates or basename in seen_basenames or destination in seen_destinations:
            raise AuditError("DUPLICATE_PLAN_ASSET_IDENTITY")
        if Path(destination).is_absolute() or ".." in Path(destination).parts:
            raise AuditError("PLAN_PATH_ESCAPE")
        if Path(destination).name != basename or not destination.startswith("raw/"):
            raise AuditError("PLAN_DESTINATION_MISMATCH")
        try:
            size = int(asset.get("size_bytes"))
            duration = finite_float(
                _require_mapping(asset.get("technical_audit"), "TECHNICAL_AUDIT").get(
                    "duration_seconds"
                ),
                positive=True,
            )
        except (TypeError, ValueError) as exc:
            raise AuditError("INVALID_PLAN_NUMERIC_METADATA") from exc
        if size <= 0 or duration <= 0:
            raise AuditError("INVALID_PLAN_NUMERIC_METADATA")
        if asset.get("content_type") != "video/mp4":
            raise AuditError("UNEXPECTED_PLAN_CONTENT_TYPE")
        assets.append(asset)
        seen_candidates.add(candidate)
        seen_basenames.add(basename)
        seen_destinations.add(destination)
    if tuple(sorted(seen_candidates)) != EXPECTED_CANDIDATES:
        raise AuditError("UNEXPECTED_CANDIDATE_SELECTION")
    selection = _require_mapping(plan.get("selection"), "PLAN_SELECTION")
    if tuple(sorted(str(x) for x in _require_list(
        selection.get("candidate_ids"), "PLAN_SELECTION_IDS"
    ))) != EXPECTED_CANDIDATES:
        raise AuditError("PLAN_SELECTION_MISMATCH")
    if sum(int(asset["size_bytes"]) for asset in assets) != EXPECTED_PAYLOAD_BYTES:
        raise AuditError("PLAN_AGGREGATE_SIZE_MISMATCH")

    manifest_by_basename: dict[str, Mapping[str, Any]] = {}
    for raw in manifest_raw:
        item = _require_mapping(raw, "MANIFEST_ASSET")
        basename = str(item.get("basename", ""))
        if not basename or basename in manifest_by_basename:
            raise AuditError("DUPLICATE_MANIFEST_BASENAME")
        manifest_by_basename[basename] = item
    if set(manifest_by_basename) != seen_basenames:
        raise AuditError("MANIFEST_PLAN_BASENAME_MISMATCH")
    if manifest.get("plan_sha256") != plan_sha256:
        raise AuditError("MANIFEST_PLAN_SHA256_MISMATCH")
    if manifest.get("plan_id") != plan.get("plan_id"):
        raise AuditError("MANIFEST_PLAN_ID_MISMATCH")
    if manifest.get("expected_total_payload_bytes") != EXPECTED_PAYLOAD_BYTES:
        raise AuditError("MANIFEST_EXPECTED_SIZE_MISMATCH")
    if manifest.get("verified_total_payload_bytes") != EXPECTED_PAYLOAD_BYTES:
        raise AuditError("MANIFEST_VERIFIED_SIZE_MISMATCH")
    if manifest.get("whole_file_sha256_requested") is not True:
        raise AuditError("MANIFEST_WHOLE_FILE_SHA256_NOT_RECORDED")
    manifest_boundary = _require_mapping(
        manifest.get("authorization_boundary"), "MANIFEST_AUTHORIZATION_BOUNDARY"
    )
    if (
        manifest_boundary.get("restricted_internal_storage_only") is not True
        or manifest_boundary.get("public_release_or_redistribution_authorized")
        is not False
        or manifest_boundary.get("annotation_authorized") is not False
        or manifest_boundary.get("derived_media_authorized") is not False
    ):
        raise AuditError("MANIFEST_AUTHORIZATION_BOUNDARY_MISMATCH")

    acquisition_scope = _require_mapping(
        acquisition_auth.get("authorized_scope"), "ACQUISITION_AUTHORIZED_SCOPE"
    )
    acquisition_candidates = tuple(
        sorted(
            str(x)
            for x in _require_list(
                acquisition_scope.get("candidate_ids"), "ACQUISITION_AUTHORIZED_IDS"
            )
        )
    )
    if acquisition_candidates != EXPECTED_CANDIDATES:
        raise AuditError("ACQUISITION_AUTHORIZATION_SELECTION_MISMATCH")
    if acquisition_scope.get("plan") != PLAN_REL.as_posix():
        raise AuditError("ACQUISITION_AUTHORIZATION_PLAN_MISMATCH")
    if acquisition_scope.get("plan_sha256") != plan_sha256:
        raise AuditError("ACQUISITION_AUTHORIZATION_PLAN_SHA256_MISMATCH")
    if acquisition_scope.get("destination_root") != RESTRICTED_REL.as_posix():
        raise AuditError("ACQUISITION_AUTHORIZATION_DESTINATION_MISMATCH")
    if acquisition_scope.get("expected_total_payload_bytes") != EXPECTED_PAYLOAD_BYTES:
        raise AuditError("ACQUISITION_AUTHORIZATION_SIZE_MISMATCH")
    for field, asset_field in (
        ("exact_urls", "url"),
        ("exact_etags", "etag"),
        ("exact_last_modified", "last_modified"),
        ("exact_sizes", "size_bytes"),
    ):
        authorized_values = _require_list(
            acquisition_scope.get(field), f"ACQUISITION_AUTHORIZED_{field.upper()}"
        )
        if sorted(authorized_values, key=str) != sorted(
            (asset.get(asset_field) for asset in assets), key=str
        ):
            raise AuditError(f"ACQUISITION_AUTHORIZATION_{field.upper()}_MISMATCH")
    acquisition_not_authorized = _require_mapping(
        acquisition_auth.get("not_authorized"), "ACQUISITION_NOT_AUTHORIZED"
    )
    if not all(
        acquisition_not_authorized.get(key) is True
        for key in (
            "annotation",
            "derived_media",
            "public_release_or_redistribution",
            "unlisted_url_or_candidate",
        )
    ):
        raise AuditError("ACQUISITION_AUTHORIZATION_PROHIBITION_MISSING")

    scope = _require_mapping(processing_auth.get("authorized_scope"), "PROCESSING_SCOPE")
    authorized_candidates = tuple(
        sorted(str(x) for x in _require_list(scope.get("candidate_ids"), "AUTHORIZED_IDS"))
    )
    if authorized_candidates != EXPECTED_CANDIDATES:
        raise AuditError("PROCESSING_AUTHORIZATION_SELECTION_MISMATCH")
    authorized_assets = tuple(
        sorted(
            str(x)
            for x in _require_list(scope.get("exact_assets"), "AUTHORIZED_ASSETS")
        )
    )
    expected_assets = tuple(
        sorted((RESTRICTED_REL / str(asset["destination"])).as_posix() for asset in assets)
    )
    if authorized_assets != expected_assets:
        raise AuditError("PROCESSING_AUTHORIZATION_ASSET_PATH_MISMATCH")
    required_operations = {
        "read-only integrity and provenance verification",
        "bounded container and stream inspection",
        "bounded in-memory video and audio decoding",
        "non-semantic technical audio statistics",
        "redaction-safe technical reporting",
    }
    operations = set(
        str(x) for x in _require_list(scope.get("operations"), "AUTHORIZED_OPERATIONS")
    )
    if operations != required_operations:
        raise AuditError("PROCESSING_AUTHORIZATION_OPERATION_MISMATCH")
    if scope.get("storage_class") not in {
        "restricted internal",
        "RESTRICTED_INTERNAL_ONLY",
    }:
        raise AuditError("PROCESSING_AUTHORIZATION_STORAGE_MISMATCH")
    if scope.get("persistent_media_outputs_allowed", False) is not False:
        raise AuditError("PROCESSING_AUTHORIZATION_PERSISTENCE_MISMATCH")
    if processing_auth.get("activates_only") != (
        "restricted internal technical inspection and decoding"
    ):
        raise AuditError("PROCESSING_AUTHORIZATION_SCOPE_MISMATCH")
    if (
        processing_auth.get("packet_id") != "NOAA-01"
        or processing_auth.get("addendum_id")
        != "NOAA01-RESTRICTED-PROCESSING-AUDIT-AUTHORIZATION"
        or processing_auth.get("authorization_status")
        != "ACTIVE_FOR_NARROW_TECHNICAL_AUDIT_ONLY"
    ):
        raise AuditError("PROCESSING_AUTHORIZATION_IDENTITY_MISMATCH")
    relationship = _require_mapping(
        processing_auth.get("relationship_to_acquisition_authorization"),
        "PROCESSING_AUTHORIZATION_RELATIONSHIP",
    )
    if (
        relationship.get("acquisition_authorization")
        != ACQUISITION_AUTH_REL.as_posix()
        or relationship.get("all_other_acquisition_limits_continue") is not True
        or relationship.get("does_not_establish_ownership_license_or_release_rights")
        is not True
    ):
        raise AuditError("PROCESSING_AUTHORIZATION_RELATIONSHIP_MISMATCH")
    prohibitions = _require_mapping(
        processing_auth.get("continuing_prohibitions"), "PROCESSING_PROHIBITIONS"
    )
    required_prohibitions = {
        "public_release_or_redistribution",
        "benchmark_annotation",
        "semantic_labeling",
        "persistent_extracted_frames_audio_clips_transcripts_or_other_derived_media",
        "access_to_unlisted_object",
    }
    if not all(prohibitions.get(key) is True for key in required_prohibitions):
        raise AuditError("PROCESSING_AUTHORIZATION_PROHIBITION_MISSING")
    plan_control = _require_mapping(
        processing_auth.get("frozen_plan_control"), "PROCESSING_PLAN_CONTROL"
    )
    if (
        plan_control.get("plan") != PLAN_REL.as_posix()
        or plan_control.get("plan_sha256") != plan_sha256
        or plan_control.get("plan_remains_unmodified") is not True
        or plan_control.get("acquisition_scope_not_expanded") is not True
    ):
        raise AuditError("PROCESSING_AUTHORIZATION_PLAN_CONTROL_MISMATCH")
    scientific_limits = _require_mapping(
        processing_auth.get("semantic_and_scientific_limits"),
        "PROCESSING_SCIENTIFIC_LIMITS",
    )
    if not all(
        scientific_limits.get(key) is True
        for key in (
            "speech_intelligibility_not_authorized_or_assessed",
            "ambient_audio_usefulness_not_authorized_or_assessed",
            "minimal_modality_necessity_not_authorized_or_assessed",
            "scientific_episode_suitability_not_authorized_or_assessed",
            "release_rights_not_established",
        )
    ):
        raise AuditError("PROCESSING_AUTHORIZATION_SCIENTIFIC_LIMIT_MISSING")
    return assets, manifest_by_basename


def check_execution_gate(repo_root: Path) -> dict[str, Any]:
    lock = repo_root / LOCK_REL
    manifest = repo_root / MANIFEST_REL
    partials = sorted(
        p.relative_to(repo_root).as_posix()
        for p in (repo_root / RESTRICTED_REL).rglob("*")
        if (p.is_file() or p.is_symlink()) and ".partial" in p.name.lower()
    )
    mp4s = sorted(
        p.relative_to(repo_root).as_posix()
        for p in (repo_root / RESTRICTED_REL / "raw").glob("*.mp4")
        if p.is_file()
    )
    state = {
        "lock_path": LOCK_REL.as_posix(),
        "lock_present": lock.exists() or lock.is_symlink(),
        "completed_manifest_path": MANIFEST_REL.as_posix(),
        "completed_manifest_present": manifest.is_file() and not manifest.is_symlink(),
        "partial_files": partials,
        "final_mp4_count": len(mp4s),
        "required_final_mp4_count": EXPECTED_PAYLOAD_COUNT,
        "passed": False,
    }
    state["passed"] = (
        not state["lock_present"]
        and state["completed_manifest_present"]
        and not partials
        and len(mp4s) == EXPECTED_PAYLOAD_COUNT
    )
    if state["lock_present"]:
        raise AuditError("DOWNLOADER_LOCK_PRESENT")
    if not state["completed_manifest_present"]:
        raise AuditError("COMPLETED_ACQUISITION_MANIFEST_ABSENT")
    if partials:
        raise AuditError("PARTIAL_FILES_PRESENT")
    if len(mp4s) != EXPECTED_PAYLOAD_COUNT:
        raise AuditError(f"FINAL_MP4_COUNT_{len(mp4s)}")
    return state


def inventory_tree(
    restricted_root: Path,
    expected_payload_paths: set[Path],
    expected_sidecar_paths: set[Path],
    allowed_manifest_paths: set[Path],
    repo_root: Path,
) -> dict[str, Any]:
    symlinks: list[str] = []
    partials: list[str] = []
    locks: list[str] = []
    orphan_sidecars: list[str] = []
    orphan_state_files: list[str] = []
    unexpected_payloads: list[str] = []
    all_files: list[Path] = []
    payload_like: list[Path] = []

    for root, directories, names in os.walk(restricted_root, followlinks=False):
        root_path = Path(root)
        for name in [*directories, *names]:
            path = root_path / name
            if path.is_symlink():
                symlinks.append(path.relative_to(repo_root).as_posix())
        for name in names:
            path = root_path / name
            all_files.append(path)
            lower = name.lower()
            if ".partial" in lower:
                partials.append(path.relative_to(repo_root).as_posix())
            if lower.endswith(".lock") or lower.startswith(".lock"):
                locks.append(path.relative_to(repo_root).as_posix())
            if lower.endswith(
                (
                    ".state",
                    ".state.json",
                    ".resume",
                    ".resume.json",
                    ".partial.json",
                )
            ):
                orphan_state_files.append(path.relative_to(repo_root).as_posix())
            if path.suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv", ".webm"}:
                payload_like.append(path)
                if path not in expected_payload_paths:
                    unexpected_payloads.append(path.relative_to(repo_root).as_posix())
            if name.endswith(".metadata.json"):
                payload = path.with_name(name[: -len(".metadata.json")])
                if path not in expected_sidecar_paths or payload not in expected_payload_paths:
                    orphan_sidecars.append(path.relative_to(repo_root).as_posix())

    duplicate_basenames = sorted(
        name for name, count in Counter(p.name for p in payload_like).items() if count > 1
    )
    expected_all = expected_payload_paths | expected_sidecar_paths | allowed_manifest_paths
    unexpected_files = sorted(
        path.relative_to(repo_root).as_posix()
        for path in all_files
        if path not in expected_all
    )
    directory_permissions = []
    file_permissions = []
    for path in all_files:
        mode = stat.S_IMODE(path.lstat().st_mode)
        try:
            resolved_under_root = is_relative_to(
                path.resolve(strict=True), restricted_root.resolve(strict=True)
            )
        except OSError:
            resolved_under_root = False
        file_permissions.append(
            {
                "path": path.relative_to(repo_root).as_posix(),
                "mode_octal": f"{mode:04o}",
                "is_regular_file": path.is_file(),
                "is_symlink": path.is_symlink(),
                "resolved_under_restricted_root": resolved_under_root,
                "group_or_other_permission_bits": f"{mode & 0o077:03o}",
                "restricted_permissions": (mode & 0o077) == 0,
            }
        )
    for path in [restricted_root, restricted_root / "raw", restricted_root / "manifests"]:
        if path.exists():
            mode = stat.S_IMODE(path.lstat().st_mode)
            directory_permissions.append(
                {
                    "path": path.relative_to(repo_root).as_posix(),
                    "mode_octal": f"{mode:04o}",
                    "is_symlink": path.is_symlink(),
                    "resolved_under_restricted_root": is_relative_to(
                        path.resolve(strict=True), restricted_root.resolve(strict=True)
                    ),
                    "group_or_other_write_bits": f"{mode & 0o022:03o}",
                    "group_or_other_permission_bits": f"{mode & 0o077:03o}",
                    "not_group_or_other_writable": (mode & 0o022) == 0,
                    "restricted_permissions": (mode & 0o077) == 0,
                }
            )
    hazards = [
        symlinks,
        partials,
        locks,
        orphan_sidecars,
        orphan_state_files,
        unexpected_payloads,
        duplicate_basenames,
        unexpected_files,
    ]
    return {
        "symlinks": sorted(symlinks),
        "partial_files": sorted(partials),
        "stale_locks": sorted(locks),
        "orphan_sidecars": sorted(orphan_sidecars),
        "orphan_state_files": sorted(orphan_state_files),
        "duplicate_payload_basenames": duplicate_basenames,
        "unexpected_payload_files": sorted(unexpected_payloads),
        "unexpected_files": unexpected_files,
        "directory_permissions": directory_permissions,
        "file_permissions": file_permissions,
        "passed": not any(hazards)
        and all(
            item["restricted_permissions"]
            and item["resolved_under_restricted_root"]
            and not item["is_symlink"]
            for item in directory_permissions
        )
        and all(
            item["restricted_permissions"]
            and item["resolved_under_restricted_root"]
            and item["is_regular_file"]
            and not item["is_symlink"]
            for item in file_permissions
        ),
    }


def audit_integrity(
    repo_root: Path,
    assets: list[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    manifest_by_basename: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    restricted_root = repo_root / RESTRICTED_REL
    expected_payload_paths: set[Path] = set()
    expected_sidecar_paths: set[Path] = set()
    entries: list[dict[str, Any]] = []
    aggregate = 0

    for asset in assets:
        basename = str(asset["basename"])
        payload = restricted_root / str(asset["destination"])
        manifest_asset = manifest_by_basename[basename]
        sidecar_rel = str(manifest_asset.get("metadata_sidecar", ""))
        if Path(sidecar_rel).is_absolute() or ".." in Path(sidecar_rel).parts:
            raise AuditError("MANIFEST_SIDECAR_PATH_ESCAPE")
        sidecar = restricted_root / sidecar_rel
        expected_payload_paths.add(payload)
        expected_sidecar_paths.add(sidecar)
        if not payload.exists() or not sidecar.exists():
            raise AuditError(f"MISSING_PAYLOAD_OR_SIDECAR:{basename}")
        sidecar_data = _require_mapping(load_json(sidecar), "SIDECAR")
        actual_size, actual_sha256 = sha256_file(payload)
        aggregate += actual_size
        matches = {
            "plan_basename": payload.name == basename,
            "plan_destination": payload.relative_to(restricted_root).as_posix()
            == asset.get("destination"),
            "plan_candidate_id": asset.get("candidate_id")
            == manifest_asset.get("candidate_id")
            == sidecar_data.get("candidate_id"),
            "plan_size": actual_size == asset.get("size_bytes"),
            "manifest_basename": manifest_asset.get("basename") == basename,
            "manifest_size": actual_size == manifest_asset.get("size_bytes"),
            "manifest_sha256": actual_sha256 == manifest_asset.get("sha256"),
            "manifest_status_complete": manifest_asset.get("status") == "downloaded",
            "manifest_sidecar_path": sidecar.relative_to(restricted_root).as_posix()
            == sidecar_rel,
            "sidecar_basename": sidecar_data.get("basename") == basename,
            "sidecar_destination": sidecar_data.get("destination") == asset.get("destination"),
            "sidecar_size": actual_size
            == sidecar_data.get("size_bytes")
            == sidecar_data.get("final_size_bytes"),
            "sidecar_sha256": actual_sha256
            == sidecar_data.get("whole_file_sha256")
            == sidecar_data.get("transfer_sha256"),
            "sidecar_whole_file_sha256_computed": sidecar_data.get(
                "whole_file_sha256_computed_locally"
            )
            is True,
            "sidecar_plan_id": sidecar_data.get("plan_id") == manifest.get("plan_id"),
            "sidecar_plan_sha256": sidecar_data.get("plan_sha256")
            == manifest.get("plan_sha256"),
            "sidecar_source_identity": all(
                sidecar_data.get(key) == asset.get(key)
                for key in ("url", "etag", "last_modified", "content_type", "accept_ranges")
            ),
            "sidecar_expected_source_identity": all(
                _require_mapping(
                    sidecar_data.get("expected_identity"), "SIDECAR_EXPECTED_IDENTITY"
                ).get(key)
                == asset.get(key)
                for key in (
                    "url",
                    "etag",
                    "last_modified",
                    "content_type",
                    "accept_ranges",
                    "size_bytes",
                )
            ),
            "sidecar_observed_head_identity": all(
                _require_mapping(
                    sidecar_data.get("observed_head_identity"),
                    "SIDECAR_OBSERVED_HEAD_IDENTITY",
                ).get(key)
                == asset.get(key)
                for key in (
                    "url",
                    "etag",
                    "last_modified",
                    "content_type",
                    "accept_ranges",
                    "size_bytes",
                )
            ),
            "sidecar_observed_range_identity": all(
                _require_mapping(
                    sidecar_data.get("observed_range_identity"),
                    "SIDECAR_OBSERVED_RANGE_IDENTITY",
                ).get(key)
                == asset.get(key)
                for key in ("etag", "last_modified")
            ),
        }
        payload_safety = path_safety(payload, restricted_root, repo_root)
        sidecar_safety = path_safety(sidecar, restricted_root, repo_root)
        safety_passed = all(
            (
                payload_safety["lexically_under_restricted_root"],
                payload_safety["resolved_under_restricted_root"],
                payload_safety["is_regular_file"],
                not payload_safety["is_symlink"],
                payload_safety["restricted_permissions"],
                sidecar_safety["lexically_under_restricted_root"],
                sidecar_safety["resolved_under_restricted_root"],
                sidecar_safety["is_regular_file"],
                not sidecar_safety["is_symlink"],
                sidecar_safety["restricted_permissions"],
            )
        )
        entries.append(
            {
                "candidate_id": asset["candidate_id"],
                "basename": basename,
                "path": payload.relative_to(repo_root).as_posix(),
                "metadata_path": sidecar.relative_to(repo_root).as_posix(),
                "actual_size_bytes": actual_size,
                "actual_sha256": actual_sha256,
                "matches": matches,
                "path_safety": payload_safety,
                "sidecar_path_safety": sidecar_safety,
                "passed": all(matches.values()) and safety_passed,
            }
        )

    inventory = inventory_tree(
        restricted_root,
        expected_payload_paths,
        expected_sidecar_paths,
        {repo_root / MANIFEST_REL, repo_root / AUDIT_REL},
        repo_root,
    )
    aggregate_summary = {
        "actual_payload_bytes": aggregate,
        "expected_payload_bytes": EXPECTED_PAYLOAD_BYTES,
        "plan_payload_bytes": sum(int(asset["size_bytes"]) for asset in assets),
        "manifest_expected_payload_bytes": manifest.get("expected_total_payload_bytes"),
        "manifest_verified_payload_bytes": manifest.get("verified_total_payload_bytes"),
        "payload_count": len(entries),
        "expected_payload_count": EXPECTED_PAYLOAD_COUNT,
        "exact_match": aggregate == EXPECTED_PAYLOAD_BYTES
        and len(entries) == EXPECTED_PAYLOAD_COUNT
        and all(entry["passed"] for entry in entries),
    }
    return entries, {"aggregate": aggregate_summary, "inventory": inventory}


def _ffprobe_compact(parsed: Mapping[str, Any], stderr: str, returncode: int) -> dict[str, Any]:
    format_raw = parsed.get("format")
    streams_raw = parsed.get("streams")
    format_info = format_raw if isinstance(format_raw, Mapping) else {}
    streams = streams_raw if isinstance(streams_raw, list) else []
    compact_streams = []
    numeric_invalid = False
    for raw in streams:
        if not isinstance(raw, Mapping):
            continue
        start = optional_finite_float(raw.get("start_time"))
        duration = optional_finite_float(raw.get("duration"))
        if raw.get("start_time") not in (None, "", "N/A") and start is None:
            numeric_invalid = True
        if raw.get("duration") not in (None, "", "N/A") and duration is None:
            numeric_invalid = True
        item: dict[str, Any] = {
            "index": raw.get("index"),
            "codec_type": raw.get("codec_type"),
            "codec_name": raw.get("codec_name"),
            "profile": raw.get("profile"),
            "time_base": raw.get("time_base"),
            "start_time_seconds": start,
            "duration_seconds": duration,
            "bit_rate": raw.get("bit_rate"),
            "dispositions": sorted(
                str(name)
                for name, enabled in (
                    raw.get("disposition", {}).items()
                    if isinstance(raw.get("disposition"), Mapping)
                    else []
                )
                if enabled
            ),
        }
        if raw.get("codec_type") == "video":
            item.update(
                {
                    "pixel_format": raw.get("pix_fmt"),
                    "width": raw.get("width"),
                    "height": raw.get("height"),
                    "real_frame_rate": raw.get("r_frame_rate"),
                    "real_frame_rate_fps": parse_fraction(raw.get("r_frame_rate")),
                    "average_frame_rate": raw.get("avg_frame_rate"),
                    "average_frame_rate_fps": parse_fraction(raw.get("avg_frame_rate")),
                }
            )
        elif raw.get("codec_type") == "audio":
            item.update(
                {
                    "sample_format": raw.get("sample_fmt"),
                    "sample_rate": raw.get("sample_rate"),
                    "channels": raw.get("channels"),
                    "channel_layout": raw.get("channel_layout"),
                }
            )
        compact_streams.append(item)
    duration = optional_finite_float(format_info.get("duration"))
    start = optional_finite_float(format_info.get("start_time"))
    errors = []
    if returncode != 0:
        errors.append(f"FFPROBE_EXIT_{returncode}")
    if numeric_invalid:
        errors.append("FFPROBE_NONFINITE_STREAM_METADATA")
    if stderr.strip():
        errors.append("FFPROBE_WARNING_OR_ERROR_OUTPUT")
    return {
        "tool": "ffprobe",
        "available": True,
        "invoked": True,
        "returncode": returncode,
        "readable_container": (
            returncode == 0
            and bool(format_info)
            and duration is not None
            and duration > 0
            and not numeric_invalid
        ),
        "format": {
            "format_name": format_info.get("format_name"),
            "format_long_name": format_info.get("format_long_name"),
            "start_time_seconds": start,
            "duration_seconds": duration,
            "bit_rate": format_info.get("bit_rate"),
        },
        "streams": compact_streams,
        "warning_or_error_output_present": bool(stderr.strip()),
        "errors": errors,
    }


def run_ffprobe(path: Path, timeout_seconds: int = FFPROBE_TIMEOUT_SECONDS) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    if not executable:
        return {
            "tool": "ffprobe",
            "available": False,
            "invoked": False,
            "readable_container": None,
            "errors": ["FFPROBE_NOT_AVAILABLE"],
        }
    command = [
        executable,
        "-hide_banner",
        "-v",
        "warning",
        "-show_error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, timeout=timeout_seconds, check=False
        )
    except subprocess.TimeoutExpired:
        return {
            "tool": "ffprobe",
            "available": True,
            "invoked": True,
            "readable_container": False,
            "errors": ["FFPROBE_TIMEOUT"],
        }
    except OSError:
        return {
            "tool": "ffprobe",
            "available": True,
            "invoked": True,
            "readable_container": False,
            "errors": ["FFPROBE_EXECUTION_ERROR"],
        }
    try:
        parsed = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed = {}
    return _ffprobe_compact(
        parsed,
        result.stderr.decode("utf-8", errors="replace"),
        result.returncode,
    )


PYAV_CHILD = r"""
import json, math, os, sys
from fractions import Fraction
import av
import numpy as np

path, mode = sys.argv[1], sys.argv[2]
result = {
    "tool": "pyav",
    "tool_version": getattr(av, "__version__", None),
    "available": True,
    "invoked": True,
    "errors": [],
}

def seconds(value, time_base=None):
    if value is None:
        return None
    try:
        output = float(value if time_base is None else value * time_base)
    except Exception:
        return None
    return output if math.isfinite(output) else None

def dispositions(value):
    names = []
    try:
        for flag in type(value):
            if flag.value and value & flag:
                names.append(flag.name)
    except Exception:
        pass
    return sorted(names)

def scalar_audio(frame):
    array = frame.to_ndarray()
    if np.issubdtype(array.dtype, np.integer):
        scale = float(max(abs(np.iinfo(array.dtype).min), np.iinfo(array.dtype).max))
        values = array.astype(np.float64) / scale
    else:
        values = array.astype(np.float64, copy=False)
    finite = bool(np.isfinite(values).all())
    if values.size and finite:
        peak = float(np.max(np.abs(values)))
        rms = float(np.sqrt(np.mean(np.square(values))))
    else:
        peak = None
        rms = None
    return values.size, finite, peak, rms

try:
    with av.open(path, metadata_errors="ignore") as container:
        container_duration = seconds(container.duration, Fraction(1, av.time_base))
        if mode == "probe":
            streams = []
            for stream in container.streams:
                codec = stream.codec_context
                item = {
                    "index": stream.index,
                    "codec_type": stream.type,
                    "codec_name": getattr(codec, "name", None),
                    "profile": getattr(codec, "profile", None),
                    "time_base": str(stream.time_base) if stream.time_base else None,
                    "start_time_seconds": seconds(stream.start_time, stream.time_base),
                    "duration_seconds": seconds(stream.duration, stream.time_base),
                    "frame_count_declared": stream.frames,
                    "dispositions": dispositions(stream.disposition),
                }
                if stream.type == "video":
                    item.update({
                        "pixel_format": getattr(getattr(codec, "format", None), "name", None),
                        "width": getattr(codec, "width", None),
                        "height": getattr(codec, "height", None),
                        "average_frame_rate": str(stream.average_rate) if stream.average_rate else None,
                        "average_frame_rate_fps": seconds(stream.average_rate),
                        "base_frame_rate": str(stream.base_rate) if stream.base_rate else None,
                        "guessed_frame_rate": str(stream.guessed_rate) if stream.guessed_rate else None,
                        "bit_rate": getattr(codec, "bit_rate", None),
                    })
                elif stream.type == "audio":
                    item.update({
                        "sample_format": getattr(getattr(codec, "format", None), "name", None),
                        "sample_rate": getattr(codec, "sample_rate", None),
                        "channels": getattr(codec, "channels", None),
                        "channel_layout": getattr(getattr(codec, "layout", None), "name", None),
                        "bit_rate": getattr(codec, "bit_rate", None),
                    })
                streams.append(item)
            result.update({
                "readable_container": True,
                "format": {
                    "format_name": container.format.name,
                    "format_long_name": container.format.long_name,
                    "start_time_seconds": seconds(container.start_time, Fraction(1, av.time_base)),
                    "duration_seconds": container_duration,
                    "bit_rate": container.bit_rate,
                },
                "streams": streams,
            })
        elif mode == "decode":
            points = json.loads(sys.argv[3])
            observations = []
            for point in points:
                target = float(point["seconds"])
                observation = {"label": point["label"], "target_seconds": target}
                with av.open(path, metadata_errors="ignore") as point_container:
                    video_streams = list(point_container.streams.video)
                    if video_streams:
                        stream = video_streams[0]
                        point_container.seek(
                            max(0, int(target * av.time_base)),
                            backward=True,
                            any_frame=False,
                            stream=None,
                        )
                        selected = None
                        examined = 0
                        for packet in point_container.demux(stream):
                            for frame in packet.decode():
                                examined += 1
                                frame_time = seconds(frame.pts, frame.time_base)
                                if frame_time is not None and frame_time < target - 0.25:
                                    if examined >= 5000:
                                        break
                                    continue
                                selected = frame
                                break
                            if selected is not None or examined >= 5000:
                                break
                        frame_time = (
                            seconds(selected.pts, selected.time_base)
                            if selected is not None
                            else None
                        )
                        observation["video"] = {
                            "decoded": selected is not None,
                            "frame_time_seconds": frame_time,
                            "target_delta_seconds": (
                                frame_time - target if frame_time is not None else None
                            ),
                            "width": selected.width if selected is not None else None,
                            "height": selected.height if selected is not None else None,
                            "pixel_format": selected.format.name if selected is not None else None,
                            "frames_examined": examined,
                        }
                        if selected is None:
                            observation["video"]["error"] = "NO_VIDEO_FRAME_DECODED"
                    else:
                        observation["video"] = {"decoded": False, "error": "NO_VIDEO_STREAM"}

                with av.open(path, metadata_errors="ignore") as point_container:
                    audio_streams = list(point_container.streams.audio)
                    if audio_streams:
                        stream = audio_streams[0]
                        point_container.seek(
                            max(0, int(target * av.time_base)),
                            backward=True,
                            any_frame=False,
                            stream=None,
                        )
                        target_end = target + 1.0
                        frame_count = 0
                        sample_frames = 0
                        scalar_samples = 0
                        finite = True
                        peak = 0.0
                        square_sum = 0.0
                        first_time = None
                        last_end = None
                        examined = 0
                        for packet in point_container.demux(stream):
                            for frame in packet.decode():
                                examined += 1
                                frame_time = seconds(frame.pts, frame.time_base)
                                frame_end = (
                                    None if frame_time is None or not frame.sample_rate
                                    else frame_time + frame.samples / frame.sample_rate
                                )
                                if frame_end is not None and frame_end <= target:
                                    if examined >= 10000:
                                        break
                                    continue
                                count, frame_finite, frame_peak, frame_rms = scalar_audio(frame)
                                if first_time is None:
                                    first_time = frame_time
                                frame_count += 1
                                sample_frames += frame.samples
                                scalar_samples += count
                                finite = finite and frame_finite
                                if frame_peak is not None:
                                    peak = max(peak, frame_peak)
                                if frame_rms is not None:
                                    square_sum += frame_rms * frame_rms * count
                                last_end = frame_end
                                if frame_end is None or frame_end >= target_end or examined >= 10000:
                                    break
                            if frame_count and (
                                last_end is None
                                or last_end >= target_end
                                or examined >= 10000
                            ):
                                break
                        rms = (
                            math.sqrt(square_sum / scalar_samples)
                            if scalar_samples > 0 and finite else None
                        )
                        decoded = frame_count > 0 and sample_frames > 0 and scalar_samples > 0
                        observation["audio"] = {
                            "decoded": decoded,
                            "decoded_samples_exist": decoded,
                            "frame_count": frame_count,
                            "sample_frame_count": sample_frames,
                            "scalar_sample_count": scalar_samples,
                            "finite_values": finite if scalar_samples else None,
                            "peak_absolute_normalized": peak if scalar_samples and finite else None,
                            "rms_normalized": rms,
                            "silent_sampled_window": (
                                bool(decoded and finite and peak <= 1e-8)
                            ),
                            "silence_threshold_peak_absolute_normalized": 1e-8,
                            "first_frame_time_seconds": first_time,
                            "first_frame_target_delta_seconds": (
                                first_time - target if first_time is not None else None
                            ),
                            "last_frame_end_seconds": last_end,
                            "frames_examined": examined,
                        }
                        if not decoded:
                            observation["audio"]["error"] = "NO_AUDIO_WINDOW_DECODED"
                        elif not finite:
                            observation["audio"]["error"] = "NONFINITE_AUDIO_SAMPLES"
                    else:
                        observation["audio"] = {"decoded": False, "error": "NO_AUDIO_STREAM"}
                observations.append(observation)
            result.update(
                {
                    "readable_container": True,
                    "observations": observations,
                    "persistent_outputs_created": False,
                    "child_filesystem_write_api_used": False,
                }
            )
        else:
            raise RuntimeError("invalid mode")
except Exception as exc:
    result["errors"].append("PYAV_" + type(exc).__name__.upper())
    result["readable_container"] = False
print(json.dumps(result, sort_keys=True, allow_nan=False))
"""


def run_pyav_child(
    path: Path,
    mode: str,
    *,
    points: list[dict[str, Any]] | None = None,
    timeout_seconds: int = DECODE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    command = [sys.executable, "-c", PYAV_CHILD, str(path), mode]
    if points is not None:
        command.append(json.dumps(points, separators=(",", ":")))
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            cwd=path.parent,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
    except subprocess.TimeoutExpired:
        return {
            "tool": "pyav",
            "available": True,
            "invoked": True,
            "readable_container": False,
            "errors": [f"PYAV_{mode.upper()}_TIMEOUT"],
        }
    except OSError:
        return {
            "tool": "pyav",
            "available": False,
            "invoked": False,
            "readable_container": False,
            "errors": [f"PYAV_{mode.upper()}_EXECUTION_ERROR"],
        }
    if result.returncode != 0:
        return {
            "tool": "pyav",
            "available": True,
            "invoked": True,
            "readable_container": False,
            "errors": [f"PYAV_{mode.upper()}_EXIT_{result.returncode}"],
            "stderr_present": bool(result.stderr.strip()),
        }
    try:
        parsed = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {
            "tool": "pyav",
            "available": True,
            "invoked": True,
            "readable_container": False,
            "errors": [f"PYAV_{mode.upper()}_INVALID_JSON"],
        }
    parsed["stderr_present"] = bool(result.stderr.strip())
    if result.stderr.strip():
        parsed.setdefault("errors", []).append(f"PYAV_{mode.upper()}_WARNING_OR_ERROR_OUTPUT")
    return parsed


def compare_duration(actual: float | None, expected: float) -> dict[str, Any]:
    if actual is None or not math.isfinite(actual):
        return {
            "frozen_preflight_seconds": expected,
            "actual_seconds": actual,
            "absolute_difference_seconds": None,
            "relative_difference": None,
            "relative_difference_percent": None,
            "within_tolerance": False,
            "tolerance": "max(1.0 second, 0.1%)",
        }
    absolute = abs(actual - expected)
    relative = absolute / expected
    return {
        "frozen_preflight_seconds": expected,
        "actual_seconds": actual,
        "absolute_difference_seconds": absolute,
        "relative_difference": relative,
        "relative_difference_percent": relative * 100.0,
        "within_tolerance": absolute <= max(1.0, expected * 0.001),
        "tolerance": "max(1.0 second, 0.1%)",
    }


def decode_points(duration: float) -> list[dict[str, Any]]:
    if not math.isfinite(duration) or duration <= 0:
        raise AuditError("INVALID_DECODE_DURATION")
    return [
        {"label": "beginning", "seconds": 0.0},
        {"label": "middle", "seconds": duration / 2.0},
        {"label": "near_end", "seconds": max(0.0, duration - min(3.0, duration * 0.02))},
    ]


def summarize_streams(probe: Mapping[str, Any]) -> dict[str, Any]:
    raw = probe.get("streams")
    streams = raw if isinstance(raw, list) else []
    counts = Counter(str(stream.get("codec_type", "unknown")) for stream in streams)
    return {
        "video_stream_count": counts["video"],
        "audio_stream_count": counts["audio"],
        "subtitle_stream_count": counts["subtitle"],
        "data_stream_count": counts["data"],
        "other_stream_count": len(streams)
        - counts["video"]
        - counts["audio"]
        - counts["subtitle"]
        - counts["data"],
        "video_streams": [stream for stream in streams if stream.get("codec_type") == "video"],
        "audio_streams": [stream for stream in streams if stream.get("codec_type") == "audio"],
        "subtitle_streams": [
            stream for stream in streams if stream.get("codec_type") == "subtitle"
        ],
        "data_streams": [stream for stream in streams if stream.get("codec_type") == "data"],
    }


def assess_timeline(streams: Mapping[str, Any]) -> dict[str, Any]:
    videos = streams.get("video_streams", [])
    audios = streams.get("audio_streams", [])
    if not videos or not audios:
        return {
            "assessment": "NOT_PLAUSIBLE_MISSING_DECLARED_AV_STREAM",
            "av_start_offset_seconds": None,
            "av_end_offset_seconds": None,
            "absolute_start_offset_seconds": None,
            "absolute_end_offset_seconds": None,
            "conservative_thresholds": {
                "start_offset_seconds": 2.0,
                "end_offset_seconds": 3.0,
            },
        }
    video = videos[0]
    audio = audios[0]
    video_start = optional_finite_float(video.get("start_time_seconds"))
    audio_start = optional_finite_float(audio.get("start_time_seconds"))
    video_duration = optional_finite_float(video.get("duration_seconds"))
    audio_duration = optional_finite_float(audio.get("duration_seconds"))
    if None in (video_start, audio_start, video_duration, audio_duration):
        return {
            "assessment": "INDETERMINATE_NONFINITE_OR_MISSING_STREAM_TIMELINE",
            "av_start_offset_seconds": None,
            "av_end_offset_seconds": None,
            "absolute_start_offset_seconds": None,
            "absolute_end_offset_seconds": None,
            "conservative_thresholds": {
                "start_offset_seconds": 2.0,
                "end_offset_seconds": 3.0,
            },
        }
    av_start = float(audio_start) - float(video_start)
    av_end = (float(audio_start) + float(audio_duration)) - (
        float(video_start) + float(video_duration)
    )
    plausible = abs(av_start) <= 2.0 and abs(av_end) <= 3.0
    return {
        "assessment": (
            "PLAUSIBLE_AT_CONTAINER_TIMELINE_LEVEL"
            if plausible
            else "CONSERVATIVE_TIMELINE_OFFSET_WARNING"
        ),
        "av_start_offset_seconds": av_start,
        "av_end_offset_seconds": av_end,
        "absolute_start_offset_seconds": abs(av_start),
        "absolute_end_offset_seconds": abs(av_end),
        "video_start_seconds": video_start,
        "audio_start_seconds": audio_start,
        "video_end_seconds": float(video_start) + float(video_duration),
        "audio_end_seconds": float(audio_start) + float(audio_duration),
        "conservative_thresholds": {
            "start_offset_seconds": 2.0,
            "end_offset_seconds": 3.0,
        },
    }


def decode_observation_passes(
    observation: Mapping[str, Any],
    *,
    tolerance_seconds: float = DECODE_POSITION_TOLERANCE_SECONDS,
) -> tuple[bool, bool]:
    target = optional_finite_float(observation.get("target_seconds"))
    video_raw = observation.get("video")
    audio_raw = observation.get("audio")
    video = video_raw if isinstance(video_raw, Mapping) else {}
    audio = audio_raw if isinstance(audio_raw, Mapping) else {}
    video_time = optional_finite_float(video.get("frame_time_seconds"))
    audio_start = optional_finite_float(audio.get("first_frame_time_seconds"))
    audio_end = optional_finite_float(audio.get("last_frame_end_seconds"))
    peak = optional_finite_float(audio.get("peak_absolute_normalized"))
    rms = optional_finite_float(audio.get("rms_normalized"))
    video_at_target = (
        target is not None
        and video_time is not None
        and abs(video_time - target) <= tolerance_seconds
    )
    audio_covers_target = (
        target is not None
        and audio_start is not None
        and audio_end is not None
        and audio_start <= target + tolerance_seconds
        and audio_end >= target - tolerance_seconds
    )
    video_passed = video.get("decoded") is True and video_at_target
    audio_passed = (
        audio.get("decoded") is True
        and audio.get("decoded_samples_exist") is True
        and audio.get("finite_values") is True
        and peak is not None
        and rms is not None
        and 0.0 <= peak <= 1.000001
        and 0.0 <= rms <= 1.000001
        and audio_covers_target
    )
    return video_passed, audio_passed


def audit_media(
    repo_root: Path, assets: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    restricted_root = repo_root / RESTRICTED_REL
    results = []
    for asset in assets:
        path = restricted_root / str(asset["destination"])
        preflight_duration = finite_float(
            _require_mapping(asset["technical_audit"], "TECHNICAL_AUDIT")[
                "duration_seconds"
            ],
            positive=True,
        )
        ffprobe = run_ffprobe(path)
        pyav_probe = run_pyav_child(path, "probe")
        authoritative = (
            ffprobe
            if ffprobe.get("readable_container") is True
            else pyav_probe
        )
        streams = summarize_streams(authoritative)
        format_info = authoritative.get("format")
        if not isinstance(format_info, Mapping):
            format_info = {}
        actual_duration = optional_finite_float(format_info.get("duration_seconds"))
        duration = compare_duration(actual_duration, preflight_duration)
        timeline = assess_timeline(streams)
        smoke = run_pyav_child(
            path, "decode", points=decode_points(actual_duration or preflight_duration)
        )
        observations = smoke.get("observations")
        if not isinstance(observations, list):
            observations = []
        labels = [item.get("label") for item in observations if isinstance(item, Mapping)]
        position_passes = [
            decode_observation_passes(item)
            for item in observations
            if isinstance(item, Mapping)
        ]
        correct_positions = labels == ["beginning", "middle", "near_end"]
        video_decode = (
            len(position_passes) == 3
            and correct_positions
            and all(video for video, _audio in position_passes)
        )
        audio_decode = (
            len(position_passes) == 3
            and correct_positions
            and all(audio for _video, audio in position_passes)
        )
        declared_av = (
            streams["video_stream_count"] >= 1 and streams["audio_stream_count"] >= 1
        )
        av_streams = [
            stream
            for stream in authoritative.get("streams", [])
            if isinstance(stream, Mapping)
            and stream.get("codec_type") in {"video", "audio"}
        ]
        finite_stream_timeline = bool(av_streams) and all(
            optional_finite_float(stream.get("start_time_seconds")) is not None
            and (
                optional_finite_float(stream.get("duration_seconds")) is not None
                and float(stream["duration_seconds"]) > 0
            )
            for stream in av_streams
        )
        warnings = []
        errors = []
        if not ffprobe.get("available"):
            warnings.append("EXTERNAL_FFPROBE_UNAVAILABLE")
        elif ffprobe.get("readable_container") is not True:
            errors.append("EXTERNAL_FFPROBE_FAILED")
        if authoritative.get("readable_container") is not True:
            errors.append("CONTAINER_UNREADABLE")
        if not declared_av:
            errors.append("MISSING_DECLARED_AUDIOVISUAL_STREAM")
        if not finite_stream_timeline:
            errors.append("NONFINITE_OR_MISSING_STREAM_TIMELINE")
        if not duration["within_tolerance"]:
            errors.append("FROZEN_PREFLIGHT_DURATION_MISMATCH")
        if timeline["assessment"] != "PLAUSIBLE_AT_CONTAINER_TIMELINE_LEVEL":
            errors.append("AV_TIMELINE_NOT_PLAUSIBLE")
        if not video_decode:
            errors.append("VIDEO_DECODE_SMOKE_FAILED")
        if not audio_decode:
            errors.append("AUDIO_DECODE_SMOKE_FAILED")
        if pyav_probe.get("errors"):
            errors.append("PYAV_PROBE_ERROR")
        if smoke.get("errors"):
            errors.append("PYAV_DECODE_ERROR")
        if smoke.get("persistent_outputs_created") is not False:
            errors.append("DECODE_PERSISTENCE_STATUS_NOT_FALSE")
        results.append(
            {
                "candidate_id": asset["candidate_id"],
                "basename": asset["basename"],
                "path": path.relative_to(repo_root).as_posix(),
                "frozen_preflight": {
                    "duration_seconds": preflight_duration,
                    "declared_video_track_count": asset["technical_audit"].get(
                        "video_track_count"
                    ),
                    "declared_audio_track_count": asset["technical_audit"].get(
                        "container_declared_audio_track_count"
                    ),
                },
                "external_ffprobe": ffprobe,
                "pyav_probe": pyav_probe,
                "authoritative_probe": (
                    "ffprobe" if authoritative is ffprobe else "pyav_fallback"
                ),
                "container": {
                    "readable": authoritative.get("readable_container"),
                    **dict(format_info),
                },
                "duration_comparison": duration,
                "streams": streams,
                "timeline": timeline,
                "decode_smoke": {
                    "method": "bounded PyAV child process; in-memory sinks only",
                    "timeout_seconds": DECODE_TIMEOUT_SECONDS,
                    "position_tolerance_seconds": DECODE_POSITION_TOLERANCE_SECONDS,
                    "observations": observations,
                    "position_labels_valid": correct_positions,
                    "video_passed": video_decode,
                    "audio_passed": audio_decode,
                    "errors": smoke.get("errors", []),
                    "persistent_outputs_created": smoke.get(
                        "persistent_outputs_created"
                    ),
                    "child_filesystem_write_api_used": smoke.get(
                        "child_filesystem_write_api_used"
                    ),
                },
                "warnings": warnings,
                "errors": sorted(set(errors)),
                "declared_audiovisual_pass": declared_av,
                "actual_decode_pass": video_decode and audio_decode,
                "timeline_plausibility_pass": timeline["assessment"]
                == "PLAUSIBLE_AT_CONTAINER_TIMELINE_LEVEL",
                "technical_audit_pass": not errors,
            }
        )
    return results


def decide(
    gate: Mapping[str, Any],
    integrity_entries: list[Mapping[str, Any]],
    integrity_summary: Mapping[str, Any],
    media: list[Mapping[str, Any]],
    secret_scans: list[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    reasons = []
    hard_fail = False
    if not gate.get("passed"):
        hard_fail = True
        reasons.append("The acquisition execution gate was not complete and clean.")
    if not all(entry.get("passed") for entry in integrity_entries):
        hard_fail = True
        reasons.append("One or more files failed independent size/hash/provenance/path checks.")
    if not integrity_summary.get("aggregate", {}).get("exact_match"):
        hard_fail = True
        reasons.append("The exact aggregate payload size or payload count did not match.")
    if not integrity_summary.get("inventory", {}).get("passed"):
        hard_fail = True
        reasons.append("The restricted tree contains a prohibited or unexpected condition.")
    if not all(scan.get("passed") for scan in secret_scans):
        hard_fail = True
        reasons.append("A scanned JSON file contains a credential or signed-URL indicator.")
    if len(media) != EXPECTED_PAYLOAD_COUNT or not all(
        item.get("technical_audit_pass") for item in media
    ):
        hard_fail = True
        reasons.append("One or more assets failed stream, duration, timeline, or decode checks.")
    if hard_fail:
        return "NO_GO", reasons
    if not all(item.get("external_ffprobe", {}).get("available") for item in media):
        reasons.append(
            "The host has no ffprobe executable; bounded PyAV inspection and decoding passed, "
            "but independent external ffprobe confirmation remains outstanding."
        )
        return "CONDITIONAL_GO", reasons
    return "GO_RESTRICTED_AUDIO_CONTENT_RECON", [
        "All required integrity, declared-stream, decode, and conservative timeline checks passed; "
        "this is a technical stage recommendation, not processing, annotation, or release authorization."
    ]


def restricted_tree_snapshot(restricted_root: Path, repo_root: Path) -> list[dict[str, Any]]:
    snapshot = []
    for path in sorted(restricted_root.rglob("*")):
        metadata = path.lstat()
        snapshot.append(
            {
                "path": path.relative_to(repo_root).as_posix(),
                "kind": (
                    "symlink"
                    if path.is_symlink()
                    else "directory"
                    if path.is_dir()
                    else "file"
                    if path.is_file()
                    else "other"
                ),
                "size_bytes": metadata.st_size,
                "mode_octal": f"{stat.S_IMODE(metadata.st_mode):04o}",
                "mtime_ns": metadata.st_mtime_ns,
            }
        )
    return snapshot


def validate_audit_consistency(audit: Mapping[str, Any]) -> None:
    integrity = _require_mapping(
        audit.get("integrity_and_provenance"), "AUDIT_INTEGRITY"
    )
    entries = _require_list(integrity.get("entries"), "AUDIT_INTEGRITY_ENTRIES")
    media = _require_list(audit.get("media"), "AUDIT_MEDIA")
    aggregate = _require_mapping(integrity.get("aggregate"), "AUDIT_AGGREGATE")
    dimensions = _require_mapping(
        audit.get("decision_dimensions"), "AUDIT_DECISION_DIMENSIONS"
    )
    if len(entries) != EXPECTED_PAYLOAD_COUNT or len(media) != EXPECTED_PAYLOAD_COUNT:
        raise AuditError("AUDIT_INTERNAL_COUNT_MISMATCH")
    if aggregate.get("payload_count") != len(entries):
        raise AuditError("AUDIT_INTERNAL_AGGREGATE_COUNT_MISMATCH")
    if aggregate.get("actual_payload_bytes") != sum(
        int(entry.get("actual_size_bytes", -1)) for entry in entries
    ):
        raise AuditError("AUDIT_INTERNAL_AGGREGATE_SIZE_MISMATCH")
    if dimensions.get("acquisition_integrity") != (
        "PASS" if integrity.get("passed") is True else "FAIL"
    ):
        raise AuditError("AUDIT_INTERNAL_INTEGRITY_DIMENSION_MISMATCH")
    expected_dimensions = {
        "declared_stream_presence": all(
            item.get("declared_audiovisual_pass") is True for item in media
        ),
        "actual_decode_success": all(
            item.get("actual_decode_pass") is True for item in media
        ),
        "timeline_plausibility": all(
            item.get("timeline_plausibility_pass") is True for item in media
        ),
    }
    for key, passed in expected_dimensions.items():
        if dimensions.get(key) != ("PASS" if passed else "FAIL"):
            raise AuditError(f"AUDIT_INTERNAL_{key.upper()}_MISMATCH")
    decision = audit.get("decision")
    if decision not in {
        "GO_RESTRICTED_AUDIO_CONTENT_RECON",
        "CONDITIONAL_GO",
        "NO_GO",
    }:
        raise AuditError("AUDIT_INTERNAL_DECISION_INVALID")
    if decision != "NO_GO" and not all(
        (
            integrity.get("passed") is True,
            all(item.get("technical_audit_pass") is True for item in media),
            audit.get("restricted_tree_unchanged_during_media_inspection") is True,
        )
    ):
        raise AuditError("AUDIT_INTERNAL_NONFAIL_DECISION_INCONSISTENT")
    if scan_sensitive_value(
        audit,
        path_label=AUDIT_REL.as_posix(),
        raw=json.dumps(audit, sort_keys=True, ensure_ascii=False),
    )["passed"] is not True:
        raise AuditError("AUDIT_OUTPUT_REDACTION_SAFETY_FAILED")


def build_audit(repo_root: Path) -> dict[str, Any]:
    gate = check_execution_gate(repo_root)
    paths = {
        "plan": repo_root / PLAN_REL,
        "acquisition_authorization": repo_root / ACQUISITION_AUTH_REL,
        "processing_authorization": repo_root / PROCESSING_AUTH_REL,
        "manifest": repo_root / MANIFEST_REL,
    }
    for label, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise AuditError(f"MISSING_OR_UNSAFE_{label.upper()}")
    plan_size, plan_sha256 = sha256_file(paths["plan"])
    manifest_size, manifest_sha256 = sha256_file(paths["manifest"])
    processing_auth_size, processing_auth_sha256 = sha256_file(
        paths["processing_authorization"]
    )
    plan = load_json(paths["plan"])
    manifest = load_json(paths["manifest"])
    acquisition_auth = load_json(paths["acquisition_authorization"])
    processing_auth = load_json(paths["processing_authorization"])
    assets, manifest_by_basename = validate_inputs(
        plan, manifest, acquisition_auth, processing_auth, plan_sha256
    )
    integrity_entries, integrity_summary = audit_integrity(
        repo_root, assets, manifest, manifest_by_basename
    )
    secret_paths = [
        paths["plan"],
        paths["acquisition_authorization"],
        paths["processing_authorization"],
        paths["manifest"],
        *(repo_root / entry["metadata_path"] for entry in integrity_entries),
    ]
    secret_scans = []
    for path in secret_paths:
        scan = scan_sensitive_json(path)
        scan["path"] = path.relative_to(repo_root).as_posix()
        secret_scans.append(scan)
    before_decode = restricted_tree_snapshot(repo_root / RESTRICTED_REL, repo_root)
    media = audit_media(repo_root, assets)
    after_decode = restricted_tree_snapshot(repo_root / RESTRICTED_REL, repo_root)
    tree_unchanged = before_decode == after_decode
    if not tree_unchanged:
        for item in media:
            item.setdefault("errors", []).append(
                "RESTRICTED_TREE_CHANGED_DURING_MEDIA_INSPECTION"
            )
            item["technical_audit_pass"] = False
    decision, reasons = decide(
        gate, integrity_entries, integrity_summary, media, secret_scans
    )
    pyav_available = importlib.util.find_spec("av") is not None
    audit = {
        "schema_version": "1.0",
        "audit_id": "NOAA-01-DOWNLOAD-MEDIA-AUDIT",
        "generated_at_utc": utc_now(),
        "scope": {
            "authorized_operation": (
                "restricted internal technical inspection and decoding"
            ),
            "candidate_ids": list(EXPECTED_CANDIDATES),
            "restricted_root": RESTRICTED_REL.as_posix(),
            "payloads_modified": False,
            "payloads_renamed_deleted_or_redistributed": False,
            "derived_media_persisted": False,
            "benchmark_annotations_created": False,
            "semantic_labeling_performed": False,
            "content_reconnaissance_performed": False,
        },
        "execution_gate": gate,
        "inputs": {
            "frozen_plan": {
                "path": PLAN_REL.as_posix(),
                "size_bytes": plan_size,
                "sha256": plan_sha256,
            },
            "acquisition_manifest": {
                "path": MANIFEST_REL.as_posix(),
                "size_bytes": manifest_size,
                "sha256": manifest_sha256,
            },
            "processing_authorization": {
                "path": PROCESSING_AUTH_REL.as_posix(),
                "size_bytes": processing_auth_size,
                "sha256": processing_auth_sha256,
            },
        },
        "tool_availability": {
            "ffprobe": shutil.which("ffprobe") is not None,
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "pyav": pyav_available,
            "timeouts_seconds": {
                "ffprobe": FFPROBE_TIMEOUT_SECONDS,
                "pyav_probe_and_decode": DECODE_TIMEOUT_SECONDS,
            },
        },
        "restricted_tree_unchanged_during_media_inspection": tree_unchanged,
        "integrity_and_provenance": {
            "entries": integrity_entries,
            **integrity_summary,
            "secret_and_signed_url_scans": secret_scans,
            "passed": all(entry["passed"] for entry in integrity_entries)
            and integrity_summary["aggregate"]["exact_match"]
            and integrity_summary["inventory"]["passed"]
            and all(scan["passed"] for scan in secret_scans),
        },
        "media": media,
        "decision": decision,
        "decision_reasons": reasons,
        "decision_dimensions": {
            "acquisition_integrity": (
                "PASS"
                if all(entry["passed"] for entry in integrity_entries)
                and integrity_summary["aggregate"]["exact_match"]
                and integrity_summary["inventory"]["passed"]
                else "FAIL"
            ),
            "declared_stream_presence": (
                "PASS" if all(item["declared_audiovisual_pass"] for item in media) else "FAIL"
            ),
            "actual_decode_success": (
                "PASS" if all(item["actual_decode_pass"] for item in media) else "FAIL"
            ),
            "timeline_plausibility": (
                "PASS" if all(item["timeline_plausibility_pass"] for item in media) else "FAIL"
            ),
            "remaining_semantic_and_scientific_unknowns": [
                "speech intelligibility",
                "ambient-audio usefulness",
                "minimal modality necessity",
                "scientific episode suitability",
            ],
            "public_release_and_annotation_hold": "CONTINUES",
            "release_rights": "NOT_ESTABLISHED",
            "next_stage_authorization": "NOT_GRANTED_BY_THIS_AUDIT",
        },
    }
    validate_audit_consistency(audit)
    return audit


def find_repo_root(script_path: Path) -> Path:
    root = script_path.resolve().parents[1]
    if not (root / "pyproject.toml").is_file():
        raise AuditError("REPOSITORY_ROOT_NOT_FOUND")
    return root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=AUDIT_REL.as_posix(),
        help="repository-relative audit JSON path under the NOAA-01 restricted tree",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="run the audit without writing the machine-readable report",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo_root = find_repo_root(Path(__file__))
        audit = build_audit(repo_root)
        if not args.no_write:
            output = repo_root / args.output
            expected_output = repo_root / AUDIT_REL
            if output.absolute() != expected_output.absolute():
                raise AuditError("AUDIT_OUTPUT_PATH_IS_FIXED")
            atomic_write_json(output, audit)
            written = load_json(output)
            validate_audit_consistency(_require_mapping(written, "WRITTEN_AUDIT"))
        print(
            json.dumps(
                {
                    "decision": audit["decision"],
                    "payload_count": audit["integrity_and_provenance"]["aggregate"][
                        "payload_count"
                    ],
                    "payload_bytes": audit["integrity_and_provenance"]["aggregate"][
                        "actual_payload_bytes"
                    ],
                    "declared_av_passes": sum(
                        item["declared_audiovisual_pass"] for item in audit["media"]
                    ),
                    "decode_passes": sum(item["actual_decode_pass"] for item in audit["media"]),
                    "timeline_passes": sum(
                        item["timeline_plausibility_pass"] for item in audit["media"]
                    ),
                    "output_written": not args.no_write,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if audit["decision"] != "NO_GO" else 2
    except AuditError as exc:
        print(f"NOAA-01 media audit failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"NOAA-01 media audit failed: INTERNAL_{type(exc).__name__.upper()}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
