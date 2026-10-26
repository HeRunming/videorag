#!/usr/bin/env python3
"""Bounded authenticated preflight for Assembly101 participant 9051.

The tool has two modes:

* plan-only validates the frozen route, local authenticated metadata registry,
  participant/session/view lineage, exact object identities, license evidence,
  annotation seal, and byte limits without network access;
* live revalidates the pinned Hugging Face dataset metadata with the existing
  login and performs bounded ISO-BMFF range probes for two exact RGB views.

It never downloads or persists full media, decoded samples, frames, audio,
signed URLs, credentials, or semantic annotation contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from tools import hf_audio_stream_preflight as core
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    import hf_audio_stream_preflight as core  # type: ignore[no-redef]


SCHEMA_VERSION = "av-trace.assembly101-9051-vsa-preflight/1.0"
ROUTE_ID = "ARVSA-R02-ASSEMBLY101-9051"
REPO_ID = "cvml-nus/assembly101"
REVISION = "bfc15ea5e3f0bc8f8c232af6c1b45aa137a9d967"
PARTICIPANT_ID = "9051"
LICENSE_ID = "CC-BY-NC-4.0"

ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = ROOT / "data/rehearsal_plan/audio_rich_vsa_acquisition_routes_v1.json"
AUTH_REGISTRY_PATH = (
    ROOT / "data/rehearsal_plan/assembly101_authenticated_registry_v1.json"
)
INVENTORY_PATH = (
    ROOT
    / "data/hf_recon/assembly101_authenticated_v1/derived/"
    "nonsemantic_session_inventory.json"
)
HF_CARD_PATH = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/metadata/"
    "assembly101/hf_README.md"
)
DEFAULT_OUTPUT = (
    ROOT / "data/rehearsal_plan/assembly101_9051_vsa_preflight_v1.json"
)

DEFAULT_PROXIES = (
    "https://proxy.example.invalid:3128",
    "https://proxy.example.invalid:3128",
)
WINDOW_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_CANDIDATE_BYTES = 8 * 1024 * 1024
MAX_AGGREGATE_BYTES = 16 * 1024 * 1024
LONG_SESSION_MIN_SECONDS = 1200.0
LONG_SESSION_MAX_SECONDS = 5400.0

READY = "ASSEMBLY101_9051_VSA_PREFLIGHT_READY"
REPAIR = "ASSEMBLY101_9051_VSA_PREFLIGHT_REPAIR"
NO_GO = "ASSEMBLY101_9051_VSA_PREFLIGHT_NO_GO"

PRIMARY_SESSION = (
    "nusar-2021_action_both_9051-c08a_9051_user_id_2021-02-22_115717"
)
SECONDARY_SESSION = (
    "nusar-2021_action_both_9051-b03a_9051_user_id_2021-02-22_114140"
)


class PreflightError(RuntimeError):
    """Stable, credential-free preflight failure."""


@dataclass(frozen=True)
class SessionSpec:
    role: str
    session_id: str
    session_total_mp4_bytes: int
    size_bytes: int
    sha256: str

    @property
    def path(self) -> str:
        return f"recordings/{self.session_id}/C10095_rgb.mp4"

    @property
    def candidate_id(self) -> str:
        return f"assembly101-9051-{self.role}"

    @property
    def blob_id(self) -> str:
        return git_lfs_pointer_blob_id(self.sha256, self.size_bytes)

    def candidate(self) -> core.Candidate:
        return core.Candidate.from_mapping(
            {
                "candidate_id": self.candidate_id,
                "repo_id": REPO_ID,
                "revision": REVISION,
                "path": self.path,
                "size_bytes": self.size_bytes,
                "hash_algorithm": "sha256",
                "hash": self.sha256,
                "blob_id": self.blob_id,
            }
        )


SESSION_SPECS = (
    SessionSpec(
        role="primary",
        session_id=PRIMARY_SESSION,
        session_total_mp4_bytes=5_107_229_101,
        size_bytes=595_283_958,
        sha256="5d76b99652b8715d7cae59083d31720798a21817a91540c547663c6357887415",
    ),
    SessionSpec(
        role="secondary",
        session_id=SECONDARY_SESSION,
        session_total_mp4_bytes=4_129_671_985,
        size_bytes=480_774_181,
        sha256="80bad0538f8b13c5eab5182fd24d482c551f9711ff50fa3548016732d59cfb34",
    ),
)


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def git_lfs_pointer_blob_id(sha256: str, size_bytes: int) -> str:
    pointer = (
        "version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{sha256}\n"
        f"size {size_bytes}\n"
    ).encode()
    header = f"blob {len(pointer)}\0".encode()
    return hashlib.sha1(header + pointer).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PreflightError(f"JSON_NOT_OBJECT:{path.relative_to(ROOT)}")
    return value


def find_route(routes: Mapping[str, Any]) -> Mapping[str, Any]:
    for value in routes.values():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping) and item.get("route_id") == ROUTE_ID:
                    return item
    raise PreflightError("FROZEN_ROUTE_NOT_FOUND")


def validate_local_inputs() -> dict[str, Any]:
    route = find_route(load_json(ROUTE_PATH))
    auth = load_json(AUTH_REGISTRY_PATH)
    inventory = load_json(INVENTORY_PATH)
    card_text = HF_CARD_PATH.read_text(encoding="utf-8")

    exact = route.get("exact_ids_or_pool")
    if not isinstance(exact, Mapping):
        raise PreflightError("ROUTE_EXACT_IDS_MISSING")
    expected_route = {
        "repo_id": REPO_ID,
        "revision": REVISION,
        "participant_block_id": PARTICIPANT_ID,
        "session_id": PRIMARY_SESSION,
        "representative_mp4_path": SESSION_SPECS[0].path,
        "representative_mp4_size_bytes": SESSION_SPECS[0].size_bytes,
        "representative_mp4_lfs_sha256": SESSION_SPECS[0].sha256,
        "session_total_mp4_bytes": SESSION_SPECS[0].session_total_mp4_bytes,
        "view_file_count": 12,
    }
    if dict(exact) != expected_route:
        raise PreflightError("FROZEN_ROUTE_IDENTITY_MISMATCH")

    pinned = auth.get("pinned_source")
    if not isinstance(pinned, Mapping):
        raise PreflightError("AUTH_REGISTRY_PIN_MISSING")
    if (
        pinned.get("repo_id") != REPO_ID
        or pinned.get("revision") != REVISION
        or pinned.get("license_declared_by_official_hf_card")
        != "CC-BY-NC-4.0"
    ):
        raise PreflightError("AUTH_REGISTRY_PIN_MISMATCH")

    sessions = inventory.get("sessions")
    if not isinstance(sessions, list):
        raise PreflightError("SESSION_INVENTORY_MISSING")
    participant_sessions = [
        item
        for item in sessions
        if isinstance(item, Mapping)
        and str(item.get("participant_id")) == PARTICIPANT_ID
    ]
    if len(participant_sessions) != 6:
        raise PreflightError("PARTICIPANT_SESSION_COUNT_MISMATCH")
    by_id = {str(item["session_id"]): item for item in participant_sessions}
    for spec in SESSION_SPECS:
        item = by_id.get(spec.session_id)
        if item is None:
            raise PreflightError("SELECTED_SESSION_NOT_IN_INVENTORY")
        expected = {
            "view_file_count": 12,
            "fixed_view_file_count": 8,
            "egocentric_view_file_count": 4,
            "view_complete_12": True,
            "total_mp4_bytes": spec.session_total_mp4_bytes,
            "lexicographic_representative_mp4": spec.path,
            "lexicographic_representative_size_bytes": spec.size_bytes,
            "lexicographic_representative_lfs_sha256": spec.sha256,
        }
        for key, value in expected.items():
            if item.get(key) != value:
                raise PreflightError(f"SESSION_INVENTORY_MISMATCH:{key}")

    if "license: cc-by-nc-4.0" not in card_text.lower():
        raise PreflightError("LOCAL_LICENSE_CARD_MISMATCH")
    if "Creative Commons Attribution-NonCommerial 4.0" not in card_text:
        raise PreflightError("LOCAL_LICENSE_NOTICE_MISSING")

    all_ids = sorted(by_id)
    if PRIMARY_SESSION not in all_ids or SECONDARY_SESSION not in all_ids:
        raise PreflightError("TWO_SESSION_FAMILY_NOT_ESTABLISHED")

    return {
        "route": route,
        "auth_registry": auth,
        "inventory": inventory,
        "participant_sessions": participant_sessions,
        "selected_candidates": [spec.candidate() for spec in SESSION_SPECS],
    }


def session_record(spec: SessionSpec, result: Mapping[str, Any] | None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "role": spec.role,
        "participant_id": PARTICIPANT_ID,
        "session_id": spec.session_id,
        "view_id": "v1",
        "camera_id": "C10095_rgb",
        "exact_file": {
            "repo_id": REPO_ID,
            "revision": REVISION,
            "path": spec.path,
            "size_bytes": spec.size_bytes,
            "lfs_sha256": spec.sha256,
            "git_lfs_pointer_blob_id": spec.blob_id,
        },
        "lineage": {
            "participant_block": PARTICIPANT_ID,
            "session_view_count": 12,
            "fixed_view_count": 8,
            "egocentric_view_count": 4,
            "session_total_mp4_bytes": spec.session_total_mp4_bytes,
            "all_synchronized_views_and_derivatives_remain_in_same_source_group": True,
        },
        "duration_seconds": None,
        "resolution": None,
        "declared_video_track_count": 0,
        "declared_audio_track_count": 0,
        "native_synchronized_audio": "UNRESOLVED",
        "bounded_access": "NOT_RUN",
    }
    if result is None:
        return record
    record["bounded_access"] = (
        "SUCCEEDED" if result.get("identity_match") is True else "FAILED"
    )
    record["duration_seconds"] = result.get("duration_seconds")
    record["declared_video_track_count"] = result.get("video_track_count", 0)
    record["declared_audio_track_count"] = result.get("audio_track_count", 0)
    record["native_synchronized_audio"] = (
        "DECLARED_AUDIO_TRACK_TIMELINE_PLAUSIBLY_SYNCHRONIZED"
        if result.get("audio_track_count", 0) > 0
        and result.get("av_timeline_relation") == "PLAUSIBLY_SYNCHRONIZED"
        else "NOT_EVIDENCED"
    )
    record["container"] = {
        "parse_status": result.get("container_parse_status"),
        "major_brand": result.get("major_brand"),
        "compatible_brands": result.get("compatible_brands"),
        "av_timeline_relation": result.get("av_timeline_relation"),
        "tracks": result.get("tracks", []),
    }
    record["requests"] = result.get("requests", [])
    record["probe_bytes"] = result.get("response_body_bytes", 0)
    record["probe_decision"] = result.get("decision")
    record["probe_limitations"] = result.get("limitations", [])
    return record


def live_metadata(token: str, proxies: Sequence[str]) -> dict[str, Any]:
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:  # pragma: no cover - environment guard
        raise PreflightError("HUGGINGFACE_HUB_NOT_INSTALLED") from exc

    attempts: list[dict[str, Any]] = []
    original_http = os.environ.get("HTTP_PROXY")
    original_https = os.environ.get("HTTPS_PROXY")
    try:
        for proxy in proxies:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
            route = core.proxy_label(proxy)
            try:
                info = HfApi(endpoint="https://huggingface.co").dataset_info(
                    REPO_ID,
                    revision=REVISION,
                    files_metadata=True,
                    token=token,
                    timeout=60,
                )
            except Exception as exc:  # noqa: BLE001
                # Never retain provider exception text; HF may include secrets.
                attempts.append(
                    {
                        "proxy_route": route,
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                    }
                )
                continue
            attempts.append({"proxy_route": route, "status": "SUCCEEDED"})
            siblings = {item.rfilename: item for item in info.siblings}
            selected: list[dict[str, Any]] = []
            for spec in SESSION_SPECS:
                sibling = siblings.get(spec.path)
                if sibling is None:
                    raise PreflightError("LIVE_EXACT_FILE_MISSING")
                lfs = getattr(sibling, "lfs", None)
                selected.append(
                    {
                        "path": spec.path,
                        "size_bytes": getattr(sibling, "size", None),
                        "blob_id": getattr(sibling, "blob_id", None),
                        "lfs_sha256": (
                            getattr(lfs, "sha256", None) if lfs else None
                        ),
                    }
                )
            return {
                "status": "SUCCEEDED",
                "attempts": attempts,
                "repo_id": info.id,
                "revision": info.sha,
                "private": info.private,
                "gated": info.gated,
                "license": (info.card_data or {}).get("license"),
                "sibling_count": len(info.siblings),
                "selected_files": selected,
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


def validate_live_metadata(metadata: Mapping[str, Any]) -> None:
    if metadata.get("status") != "SUCCEEDED":
        raise PreflightError("LIVE_AUTHENTICATED_METADATA_FAILED")
    if (
        metadata.get("repo_id") != REPO_ID
        or metadata.get("revision") != REVISION
        or metadata.get("license") != "cc-by-nc-4.0"
    ):
        raise PreflightError("LIVE_REPOSITORY_IDENTITY_MISMATCH")
    files = metadata.get("selected_files")
    if not isinstance(files, list) or len(files) != len(SESSION_SPECS):
        raise PreflightError("LIVE_SELECTED_FILE_METADATA_MISSING")
    by_path = {item.get("path"): item for item in files if isinstance(item, Mapping)}
    for spec in SESSION_SPECS:
        item = by_path.get(spec.path)
        if item is None:
            raise PreflightError("LIVE_EXACT_FILE_MISSING")
        if (
            item.get("size_bytes") != spec.size_bytes
            or item.get("lfs_sha256") != spec.sha256
            or item.get("blob_id") != spec.blob_id
        ):
            raise PreflightError("LIVE_EXACT_FILE_IDENTITY_MISMATCH")


def classify(
    mode: str,
    metadata: Mapping[str, Any] | None,
    stream: Mapping[str, Any] | None,
) -> tuple[str, list[str]]:
    if mode == "plan-only":
        return REPAIR, [
            "Live authenticated gate/access state was not revalidated.",
            "Long duration, resolution, and native synchronized audio require bounded live container probes.",
        ]
    blockers: list[str] = []
    if metadata is None or metadata.get("status") != "SUCCEEDED":
        attempts = (metadata or {}).get("attempts", [])
        if isinstance(attempts, list) and attempts:
            routes = ", ".join(
                f"{item.get('proxy_route')}={item.get('error_type')}"
                for item in attempts
                if isinstance(item, Mapping)
            )
            blockers.append(
                "Authenticated pinned-revision metadata listing failed before "
                f"HTTP on every live route ({routes})."
            )
        else:
            blockers.append(
                "Authenticated pinned-revision metadata listing failed."
            )
        blockers.append(
            "The most recent retained successful exact-file provider probes, "
            "from 2026-10-02, returned HTTP 403 GatedRepo for the existing "
            "logged-in account."
        )
    if stream is None:
        blockers.append("Bounded exact-asset stream preflight did not run.")
    else:
        candidates = stream.get("candidates", [])
        if not isinstance(candidates, list) or len(candidates) != 2:
            blockers.append("Two exact candidate probe results were not produced.")
        else:
            for result in candidates:
                candidate_id = result.get("candidate_id", "unknown")
                if result.get("identity_match") is not True:
                    blockers.append(
                        f"{candidate_id}: authenticated exact-asset access/identity failed."
                    )
                    continue
                duration = result.get("duration_seconds")
                if not isinstance(duration, (int, float)) or not (
                    LONG_SESSION_MIN_SECONDS
                    <= float(duration)
                    <= LONG_SESSION_MAX_SECONDS
                ):
                    blockers.append(
                        f"{candidate_id}: 20-90 minute duration not evidenced."
                    )
                if result.get("audio_track_count", 0) < 1:
                    blockers.append(
                        f"{candidate_id}: native audio track not evidenced."
                    )
                if (
                    result.get("av_timeline_relation")
                    != "PLAUSIBLY_SYNCHRONIZED"
                ):
                    blockers.append(
                        f"{candidate_id}: synchronized A/V timeline not evidenced."
                    )
    return (READY, []) if not blockers else (REPAIR, blockers)


def build_report(
    *,
    mode: str,
    local: Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
    stream: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    decision, blockers = classify(mode, metadata, stream)
    stream_by_id = {
        item.get("candidate_id"): item
        for item in (stream or {}).get("candidates", [])
        if isinstance(item, Mapping)
    }
    sessions = [
        session_record(spec, stream_by_id.get(spec.candidate_id))
        for spec in SESSION_SPECS
    ]
    participant_sessions = local["participant_sessions"]
    total_probe_bytes = (
        int((stream or {}).get("aggregate", {}).get("response_body_bytes", 0))
    )
    access_succeeded = bool(
        metadata
        and metadata.get("status") == "SUCCEEDED"
        and stream
        and all(item["bounded_access"] == "SUCCEEDED" for item in sessions)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "mode": mode,
        "final_marker": decision,
        "disposition": decision.rsplit("_", 1)[-1],
        "scope": {
            "route_id": ROUTE_ID,
            "participant_id": PARTICIPANT_ID,
            "plan_only_or_live_preflight": True,
            "full_media_downloads": 0,
            "media_bytes_persisted": 0,
            "semantic_annotation_files_opened": 0,
            "human_review_performed": False,
            "ses_or_h_tier_claimed": False,
            "gate_a_claimed": False,
            "v_plus_s_plus_a_claimed": False,
        },
        "source_identity": {
            "dataset": "Assembly101",
            "repo_id": REPO_ID,
            "revision": REVISION,
            "official_hf_gate": (
                metadata.get("gated") if metadata else "NOT_REVALIDATED"
            ),
            "operative_license": LICENSE_ID,
            "license_evidence": {
                "local_official_card": str(HF_CARD_PATH.relative_to(ROOT)),
                "live_card_license": (
                    metadata.get("license") if metadata else "NOT_REVALIDATED"
                ),
                "noncommercial_restriction": True,
                "attribution_required": True,
                "license_is_not_privacy_or_release_clearance": True,
            },
        },
        "authenticated_access": {
            "existing_login_only": True,
            "new_credentials_or_gate_acceptance_created": False,
            "credential_or_identity_recorded": False,
            "proxy_routes": [core.proxy_label(item) for item in DEFAULT_PROXIES],
            "metadata": metadata or {"status": "NOT_RUN"},
            "exact_asset_bounded_access_succeeded": access_succeeded,
            "bounded_probe_bytes_read": total_probe_bytes,
            "bounded_probe_bytes_persisted": 0,
            "retained_prior_authenticated_evidence": {
                "observed_at": "2026-10-02",
                "existing_login_validated": True,
                "pinned_metadata_listing_succeeded": True,
                "exact_mp4_metadata_succeeded": True,
                "exact_media_head_status": 403,
                "exact_media_range_status": 403,
                "provider_error_code": "GatedRepo",
                "media_bytes_read": 0,
                "source": str(AUTH_REGISTRY_PATH.relative_to(ROOT)),
            },
            "limits": {
                "maximum_response_bytes": MAX_RESPONSE_BYTES,
                "maximum_candidate_bytes": MAX_CANDIDATE_BYTES,
                "maximum_aggregate_bytes": MAX_AGGREGATE_BYTES,
                "initial_head_and_tail_window_bytes": WINDOW_BYTES,
                "complete_object_range_prohibited": True,
            },
        },
        "participant_session_view_lineage": {
            "participant_id": PARTICIPANT_ID,
            "participant_session_count": len(participant_sessions),
            "participant_session_ids": sorted(
                str(item["session_id"]) for item in participant_sessions
            ),
            "source_group_definition": (
                "Participant 9051 plus every session, synchronized view, native "
                "audio stream, annotation, clip, encoding, pose, calibration "
                "artifact, and derivative remains one admitted lineage group."
            ),
            "selected_session_rule": {
                "primary": (
                    "The frozen route session from "
                    "audio_rich_vsa_acquisition_routes_v1."
                ),
                "secondary": (
                    "The lexicographically first different complete 12-view "
                    "session for participant 9051."
                ),
                "semantic_labels_used": False,
                "selection_fields": [
                    "participant ID",
                    "session ID",
                    "view completeness",
                    "exact file size",
                    "LFS SHA-256",
                    "pinned revision",
                ],
            },
            "two_defensible_candidate_families_in_same_admitted_source_group": {
                "status": "TECHNICALLY_PLAUSIBLE"
                if len(participant_sessions) >= 2
                else "NOT_ESTABLISHED",
                "basis": (
                    "Six distinct complete synchronized sessions exist for the "
                    "same participant block; two were frozen without reading "
                    "task, action, object, mistake, or timestamp semantics."
                ),
                "scientific_defensibility_requires_later_authorized_review": True,
            },
        },
        "exact_sessions": sessions,
        "timestamp_annotations": {
            "availability": "PRESENT_BUT_SEALED",
            "evidence": (
                "The pinned repository tree and official card identify coarse "
                "and fine temporal annotations for the selected session IDs."
            ),
            "contents_opened_or_used_for_selection": False,
            "timestamp_values_claimed": False,
        },
        "routing_only_plausibility": {
            "speech": "UNKNOWN; an audio track is not evidence of speech.",
            "source_world_ambient": (
                "PLAUSIBLE_ONLY from controlled toy assembly/disassembly capture; "
                "no audible content was decoded or reviewed."
            ),
            "semantic_selection_use": False,
            "vsa_credit": False,
        },
        "technical_limits": {
            "resolution_status": (
                "NOT_AVAILABLE_FROM_CURRENT_BOUNDED_TRACK-PRESENCE_PARSER"
            ),
            "note": (
                "The shared bounded parser establishes container duration and "
                "declared track timing, but not coded width/height. Resolution "
                "therefore remains unresolved unless provider metadata exposes it."
            ),
        },
        "authorization_boundary": {
            "metadata_preflight": "AUTHORIZED_BY_THIS_RUN",
            "bounded_stream_preflight": (
                "AUTHORIZED_BY_THIS_RUN" if mode == "live" else "NOT_RUN"
            ),
            "full_acquisition": "NOT_AUTHORIZED",
            "decoding_or_content_review": "NOT_AUTHORIZED",
            "restricted_annotation_access": "NOT_AUTHORIZED",
            "processing": "NOT_AUTHORIZED",
            "release": "NOT_AUTHORIZED",
        },
        "decision": {
            "go_rule": (
                "READY only if operative rights/access, exact assets, long "
                "duration, and synchronized native audio are evidenced for both "
                "frozen sessions."
            ),
            "blockers": blockers,
            "why_not_no_go": (
                "A concrete repair path remains whenever the pinned repository, "
                "exact files, and existing account remain valid but a gate or "
                "technical property is unresolved."
            )
            if decision == REPAIR
            else None,
        },
        "stop_boundary": {
            "further_network_calls_after_user_stop": 0,
            "finalized_from_retained_evidence_only": True,
            "live_attempt_completed_before_stop": (
                metadata is not None and metadata.get("status") == "FAILED"
            ),
        },
        "reproduction": {
            "plan_only": (
                "python tools/assembly101_9051_vsa_preflight.py --plan-only"
            ),
            "live": (
                "python tools/assembly101_9051_vsa_preflight.py --live "
                "--proxy https://proxy.example.invalid:3128 "
                "--proxy https://proxy.example.invalid:3128"
            ),
        },
    }


def run_live(
    local: Mapping[str, Any], proxies: Sequence[str]
) -> dict[str, Any]:
    token = core.load_hf_token()
    if not token:
        raise PreflightError("EXISTING_HF_LOGIN_NOT_AVAILABLE")
    metadata = live_metadata(token, proxies)
    if metadata.get("status") != "SUCCEEDED":
        return build_report(
            mode="live", local=local, metadata=metadata, stream=None
        )
    validate_live_metadata(metadata)
    budget = core.Budget(
        maximum_response_bytes=MAX_RESPONSE_BYTES,
        maximum_total_bytes=MAX_AGGREGATE_BYTES,
    )
    with core.SafeHFRangeClient(
        token,
        proxies=proxies,
        budget=budget,
        maximum_candidate_bytes=MAX_CANDIDATE_BYTES,
        user_agent="AV-TRACE-assembly101-9051-vsa-preflight/1.0",
    ) as client:
        stream = core.run_preflight(
            local["selected_candidates"],
            client,
            window_bytes=WINDOW_BYTES,
        )
    return build_report(
        mode="live", local=local, metadata=metadata, stream=stream
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--proxy",
        action="append",
        default=[],
        help="Explicit proxy route; repeat for ordered failover.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        local = validate_local_inputs()
        if args.plan_only:
            report = build_report(mode="plan-only", local=local)
        else:
            proxies = tuple(args.proxy) if args.proxy else DEFAULT_PROXIES
            report = run_live(local, proxies)
        core.atomic_write_json(args.output, report)
        print(report["final_marker"])
        return 0
    except (PreflightError, core.PreflightError) as exc:
        print(f"ERROR:{exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(
            f"ERROR:INPUT_OR_OUTPUT_{type(exc).__name__.upper()}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
