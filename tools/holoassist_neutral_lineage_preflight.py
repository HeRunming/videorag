#!/usr/bin/env python3
"""Bounded official-metadata-only lineage preflight for HoloAssist.

The tool deliberately separates two modes:

* ``--plan-only`` validates the frozen safety contract without networking.
* ``--live`` requests only a small allowlist of official project, GitHub, and
  license metadata pages.  Bodies are bounded, hashed, parsed only for
  technical identity/access/license facts, and are never persisted.

``--live --stop-network`` is the fail-closed finalization path used after a
user stop.  It records the already completed/aborted request ledger without
making any additional network request.

The preflight never downloads media, annotations, transcripts, labels, task
titles/descriptions, or candidate content.  It never selects test groups,
mines candidates, ranks sessions, or assigns semantic yield.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "av-trace.holoassist-neutral-lineage-preflight/1.0"
READY = "HOLOASSIST_NEUTRAL_LINEAGE_PREFLIGHT_READY"
REPAIR = "HOLOASSIST_NEUTRAL_LINEAGE_PREFLIGHT_REPAIR"
NO_GO = "HOLOASSIST_NEUTRAL_LINEAGE_PREFLIGHT_NO_GO"

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "data/rehearsal_plan/holoassist_neutral_lineage_preflight_v1.json"
)

PROJECT_URL = "https://holoassist.github.io/"
DATA_LINKS_URL = "https://holoassist.github.io/data_links/README.md"
GITHUB_REPO_URL = "https://github.com/holoAssist/holoassist.github.io"
GITHUB_API_URL = (
    "https://api.github.com/repos/holoAssist/holoassist.github.io"
)
MSR_PUBLICATION_URL = (
    "https://www.microsoft.com/en-us/research/publication/"
    "holoassist-an-egocentric-human-interaction-dataset-for-interactive-"
    "ai-assistants-in-the-real-world/"
)
CDLA_LICENSE_URL = "https://cdla.dev/permissive-2-0/"

OFFICIAL_HOSTS = {
    "api.github.com",
    "cdla.dev",
    "github.com",
    "holoassist.github.io",
    "www.microsoft.com",
}
DEFAULT_PROXIES = (
    "https://proxy.example.invalid:3128",
    "https://proxy.example.invalid:3128",
)
MAX_RESPONSE_BYTES = 512 * 1024
MAX_AGGREGATE_BYTES = 2 * 1024 * 1024
MIN_ELIGIBLE_GROUPS = 6

FORBIDDEN_URL_TERMS = {
    "annotation",
    "caption",
    "label",
    "narration",
    "task_description",
    "task_title",
    "transcript",
}
FORBIDDEN_SEMANTIC_KEYS = {
    "action",
    "description",
    "instruction",
    "label",
    "narration",
    "object",
    "prompt",
    "step",
    "task",
    "task_description",
    "task_title",
    "title",
    "transcript",
}
ALLOWED_GROUP_KEYS = {
    "audio_codec",
    "audio_stream_count",
    "bytes",
    "duration_seconds",
    "file_id",
    "group_id",
    "hash",
    "hash_algorithm",
    "pair_id",
    "participant_id",
    "recording_id",
    "rendition_id",
    "session_id",
}


class PreflightError(RuntimeError):
    """Stable preflight failure with no credential-bearing detail."""


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def redact_proxy(proxy: str | None) -> str:
    if not proxy:
        return "DIRECT"
    parsed = urllib.parse.urlsplit(proxy)
    return parsed.netloc or "INVALID_PROXY"


def validate_official_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
        raise PreflightError("NON_OFFICIAL_URL_BLOCKED")
    lowered_path = parsed.path.lower()
    if any(term in lowered_path for term in FORBIDDEN_URL_TERMS):
        raise PreflightError("SEMANTIC_ENDPOINT_BLOCKED")


def validate_opaque_group(group: Mapping[str, Any]) -> None:
    keys = {str(key).lower() for key in group}
    forbidden = keys & FORBIDDEN_SEMANTIC_KEYS
    if forbidden:
        raise PreflightError(
            "SEMANTIC_GROUP_FIELD_BLOCKED:" + ",".join(sorted(forbidden))
        )
    unknown = keys - ALLOWED_GROUP_KEYS
    if unknown:
        raise PreflightError(
            "NONTECHNICAL_GROUP_FIELD_BLOCKED:" + ",".join(sorted(unknown))
        )
    if not group.get("group_id") or not group.get("session_id"):
        raise PreflightError("GROUP_ID_OR_SESSION_ID_MISSING")


def eligible_universe(groups: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return exact opaque groups only when every required closure field exists."""
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        validate_opaque_group(group)
        group_id = str(group["group_id"])
        if group_id in seen:
            raise PreflightError("DUPLICATE_GROUP_ID")
        seen.add(group_id)
        required = (
            "participant_id",
            "pair_id",
            "session_id",
            "recording_id",
            "file_id",
            "rendition_id",
            "bytes",
            "hash_algorithm",
            "hash",
            "duration_seconds",
            "audio_stream_count",
            "audio_codec",
        )
        if any(group.get(key) in (None, "") for key in required):
            return []
        if int(group["bytes"]) <= 0 or float(group["duration_seconds"]) <= 0:
            return []
        if int(group["audio_stream_count"]) <= 0:
            return []
        normalized.append({key: group[key] for key in sorted(group)})
    return sorted(normalized, key=lambda item: str(item["group_id"]))


def classify(
    *,
    identity_established: bool,
    license_established: bool,
    access_mechanism_exact: bool,
    groups: Sequence[Mapping[str, Any]],
    incompatible_license: bool = False,
) -> tuple[str, list[str]]:
    if incompatible_license:
        return NO_GO, ["The operative official license is incompatible."]

    universe = eligible_universe(groups)
    blockers: list[str] = []
    if not identity_established:
        blockers.append("Official dataset identity is not byte-auditable.")
    if not license_established:
        blockers.append(
            "The exact operative CDLA-Permissive-2.0 text was not archived."
        )
    if not access_mechanism_exact:
        blockers.append(
            "The first-party package index was identified, but exact backing "
            "object URLs and access behavior were not retained."
        )
    if len(universe) < MIN_ELIGIBLE_GROUPS:
        blockers.append(
            "Fewer than six exact opaque groups have participant/pair/session/"
            "recording/file lineage, bytes/hash/duration, and native audio "
            "metadata closed without semantic fields."
        )
    if blockers:
        return REPAIR, blockers
    return READY, []


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_github_repository(data: bytes) -> dict[str, Any]:
    value = json.loads(data)
    if not isinstance(value, Mapping):
        raise PreflightError("GITHUB_REPOSITORY_NOT_OBJECT")
    if value.get("full_name") != "holoAssist/holoassist.github.io":
        raise PreflightError("GITHUB_REPOSITORY_IDENTITY_MISMATCH")
    return {
        "full_name": value["full_name"],
        "default_branch": value.get("default_branch"),
        "archived": value.get("archived"),
        "license_spdx_id": (
            value.get("license", {}).get("spdx_id")
            if isinstance(value.get("license"), Mapping)
            else None
        ),
    }


def parse_project_page(data: bytes) -> dict[str, Any]:
    text = data.decode("utf-8", errors="replace")
    compact = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    if "HoloAssist" not in compact:
        raise PreflightError("PROJECT_IDENTITY_MISSING")
    lowered = compact.lower()
    return {
        "dataset_name_present": True,
        "cdla_permissive_2_0_declared": (
            "cdla-permissive-2.0" in lowered
            or "cdla permissive 2.0" in lowered
        ),
        "data_links_route_present": "data_links" in text,
    }


def parse_data_links_page(data: bytes) -> dict[str, Any]:
    """Parse only route mechanics; never return link names or path semantics."""
    text = data.decode("utf-8", errors="replace")
    urls = re.findall(r"https://[^\s<>()\"']+", text)
    hosts = sorted(
        {
            urllib.parse.urlsplit(url.rstrip(".,;")).hostname
            for url in urls
            if urllib.parse.urlsplit(url.rstrip(".,;")).hostname
        }
    )
    return {
        "https_url_count": len(urls),
        "backing_hosts": hosts,
        "body_contains_recording_ids": bool(
            re.search(
                r"\b(?:recording|session)[_-]?[0-9]{2,}\b",
                text,
                re.IGNORECASE,
            )
        ),
        "semantic_link_text_retained": False,
    }


def parse_cdla_page(data: bytes) -> dict[str, Any]:
    text = re.sub(
        r"\s+",
        " ",
        re.sub(r"<[^>]+>", " ", data.decode("utf-8", errors="replace")),
    )
    lowered = text.lower()
    required = (
        "community data license agreement",
        "permissive",
        "2.0",
    )
    if not all(term in lowered for term in required):
        raise PreflightError("CDLA_IDENTITY_MISSING")
    return {
        "license_id": "CDLA-Permissive-2.0",
        "official_standard_text_obtained": True,
        "terms_interpretation": {
            "use_modify_share": "PERMITTED_SUBJECT_TO_LICENSE",
            "license_copy_with_substantial_distribution": "REQUIRED",
            "source_designations": "MUST_NOT_BE_REMOVED_OR_MODIFIED",
            "warranty": "DISCLAIMED",
            "patent_license": "NOT_EXPRESSLY_GRANTED",
        },
    }


class BoundedClient:
    def __init__(self, proxies: Sequence[str]) -> None:
        self.proxies = tuple(proxies) or (None,)
        self.total_bytes = 0
        self.requests: list[dict[str, Any]] = []

    def get(self, url: str) -> bytes | None:
        validate_official_url(url)
        for proxy in self.proxies:
            handlers: list[Any] = []
            if proxy:
                handlers.append(
                    urllib.request.ProxyHandler(
                        {"http": proxy, "https": proxy}
                    )
                )
            else:
                handlers.append(urllib.request.ProxyHandler({}))
            opener = urllib.request.build_opener(*handlers)
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json,text/html,text/plain;q=0.9",
                    "User-Agent": "AV-TRACE-HoloAssist-Metadata-Preflight/1.0",
                },
            )
            record: dict[str, Any] = {
                "url": url,
                "method": "GET",
                "route": redact_proxy(proxy),
                "maximum_body_bytes": MAX_RESPONSE_BYTES,
                "body_bytes": 0,
                "body_persisted_bytes": 0,
            }
            try:
                with opener.open(request, timeout=30) as response:
                    effective = response.geturl()
                    validate_official_url(effective)
                    body = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise PreflightError("RESPONSE_BYTE_LIMIT_EXCEEDED")
                    if self.total_bytes + len(body) > MAX_AGGREGATE_BYTES:
                        raise PreflightError("AGGREGATE_BYTE_LIMIT_EXCEEDED")
                    self.total_bytes += len(body)
                    record.update(
                        {
                            "status": "SUCCEEDED",
                            "http_status": response.status,
                            "effective_url": effective,
                            "body_bytes": len(body),
                            "sha256": _sha256(body),
                            "content_type": response.headers.get(
                                "Content-Type"
                            ),
                        }
                    )
                    self.requests.append(record)
                    return body
            except (
                OSError,
                PreflightError,
                urllib.error.URLError,
            ) as exc:
                record.update(
                    {
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                    }
                )
                self.requests.append(record)
        return None


def run_live(proxies: Sequence[str]) -> dict[str, Any]:
    client = BoundedClient(proxies)
    parsed: dict[str, Any] = {}
    for name, url, parser in (
        ("project", PROJECT_URL, parse_project_page),
        ("github_repository", GITHUB_API_URL, parse_github_repository),
        ("data_links", DATA_LINKS_URL, parse_data_links_page),
        ("cdla", CDLA_LICENSE_URL, parse_cdla_page),
    ):
        body = client.get(url)
        if body is not None:
            try:
                parsed[name] = parser(body)
            except (PreflightError, ValueError, json.JSONDecodeError) as exc:
                parsed[name] = {
                    "parse_status": "FAILED",
                    "error_type": type(exc).__name__,
                }
    return {
        "network_requests": len(client.requests),
        "response_body_bytes_read": client.total_bytes,
        "response_body_bytes_persisted": 0,
        "requests": client.requests,
        "parsed": parsed,
    }


def stopped_request_ledger() -> list[dict[str, Any]]:
    """Exact retained request ledger at the October 14, 2026 user stop."""
    api_attempts = [
        ("https://proxy.example.invalid:3128", "FAILED_PROXY_DNS", "CurlExit5"),
        ("https://proxy.example.invalid:3128", "FAILED_PROXY_DNS", "CurlExit5"),
        (
            "INHERITED_star-https://proxy.example.invalid:3128",
            "FAILED_PROXY_DNS",
            "CurlExit5",
        ),
        ("DIRECT", "FAILED_HOST_DNS", "CurlExit6"),
        ("https://proxy.example.invalid:3128", "ABORTED_BY_USER", "UserStop"),
    ]
    ledger = [
        {
            "url": GITHUB_API_URL,
            "method": "GET",
            "route": route,
            "status": status,
            "error_type": error,
            "response_header_bytes": 0,
            "response_body_bytes": 0,
            "persisted_body_bytes": 0,
        }
        for route, status, error in api_attempts
    ]
    for url in (
        "https://ghfast.top",
        "https://ghproxy.net",
        "https://github.moeyy.xyz",
    ):
        ledger.append(
            {
                "url": url,
                "method": "HEAD",
                "route": "DIRECT",
                "status": "FAILED_HOST_DNS",
                "error_type": "CurlExit6",
                "response_header_bytes": 0,
                "response_body_bytes": 0,
                "persisted_body_bytes": 0,
                "accepted_as_source_evidence": False,
            }
        )
    return ledger


def stopped_live_evidence() -> dict[str, Any]:
    ledger = stopped_request_ledger()
    return {
        "network_requests": len(ledger),
        "response_body_bytes_read": 0,
        "response_body_bytes_persisted": 0,
        "requests": ledger,
        "parsed": {},
        "user_stop_observed": True,
        "requests_after_stop": 0,
        "active_targeted_network_processes_after_stop": 0,
        "web_discovery": [
            {
                "url": PROJECT_URL,
                "tool": "web search/open",
                "status": "COMPLETED_WITHOUT_BYTE_AUDIT_RECORD",
                "bounded_bytes_available_to_report": None,
                "body_persisted_bytes": 0,
            },
            {
                "url": DATA_LINKS_URL,
                "tool": "web open",
                "status": "COMPLETED_WITHOUT_BYTE_AUDIT_RECORD",
                "bounded_bytes_available_to_report": None,
                "body_persisted_bytes": 0,
            },
            {
                "url": MSR_PUBLICATION_URL,
                "tool": "web open",
                "status": "COMPLETED_WITHOUT_BYTE_AUDIT_RECORD",
                "bounded_bytes_available_to_report": None,
                "body_persisted_bytes": 0,
            },
        ],
    }


def build_report(
    *,
    mode: str,
    live: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    parsed = live.get("parsed", {}) if live else {}
    project = (
        parsed.get("project", {}) if isinstance(parsed, Mapping) else {}
    )
    github = (
        parsed.get("github_repository", {})
        if isinstance(parsed, Mapping)
        else {}
    )
    data_links = (
        parsed.get("data_links", {}) if isinstance(parsed, Mapping) else {}
    )
    cdla = parsed.get("cdla", {}) if isinstance(parsed, Mapping) else {}

    identity_established = bool(
        project.get("dataset_name_present")
        and github.get("full_name") == "holoAssist/holoassist.github.io"
    )
    license_established = bool(
        project.get("cdla_permissive_2_0_declared")
        and cdla.get("official_standard_text_obtained")
    )
    access_mechanism_exact = bool(
        project.get("data_links_route_present")
        and data_links.get("https_url_count", 0) > 0
    )
    groups: list[dict[str, Any]] = []
    marker, blockers = classify(
        identity_established=identity_established,
        license_established=license_established,
        access_mechanism_exact=access_mechanism_exact,
        groups=groups,
    )

    stopped = bool(live and live.get("user_stop_observed"))
    if stopped:
        identity_status = "OFFICIAL_ROUTES_IDENTIFIED_NOT_BYTE_AUDITABLE"
        license_status = (
            "CDLA_PERMISSIVE_2_0_DECLARATION_IDENTIFIED_"
            "OPERATIVE_TEXT_NOT_ARCHIVED"
        )
        access_status = "FIRST_PARTY_INDEX_IDENTIFIED_EXACT_OBJECTS_UNRESOLVED"
    else:
        identity_status = (
            "ESTABLISHED" if identity_established else "UNRESOLVED"
        )
        license_status = (
            "ESTABLISHED" if license_established else "UNRESOLVED"
        )
        access_status = (
            "ESTABLISHED" if access_mechanism_exact else "UNRESOLVED"
        )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or utc_now(),
        "mode": mode,
        "final_marker": marker,
        "disposition": marker.rsplit("_", 1)[-1],
        "scope": {
            "official_metadata_only": True,
            "permitted_exposure_class": "METADATA_ACCESS_ONLY",
            "must_be_recorded_later": True,
            "full_media_downloads": 0,
            "media_bytes_read": 0,
            "media_bytes_persisted": 0,
            "annotations_opened": 0,
            "transcripts_opened": 0,
            "labels_opened": 0,
            "task_titles_or_descriptions_opened": 0,
            "semantic_content_inspected": False,
            "semantic_prompts_used": False,
            "candidate_mining_performed": False,
            "candidate_ranking_performed": False,
            "test_groups_selected": 0,
            "semantic_yield_assigned": False,
        },
        "official_identity": {
            "dataset": "HoloAssist",
            "status": identity_status,
            "project_url": PROJECT_URL,
            "official_repository": GITHUB_REPO_URL,
            "official_repository_api": GITHUB_API_URL,
            "microsoft_research_publication": MSR_PUBLICATION_URL,
            "fresh_byte_auditable_identity": identity_established,
        },
        "license": {
            "declared_identifier": "CDLA-Permissive-2.0",
            "status": license_status,
            "official_standard_url": CDLA_LICENSE_URL,
            "operative_dataset_license_file_obtained": False,
            "standard_terms_verified_in_live_body": license_established,
            "terms": (
                cdla.get("terms_interpretation")
                if license_established
                else {
                    "status": "NOT_RESTATED_AS_VERIFIED",
                    "reason": (
                        "The stopped run did not retain the first-party "
                        "dataset license file or official CDLA text body."
                    ),
                }
            ),
        },
        "access_and_download": {
            "status": access_status,
            "first_party_index": DATA_LINKS_URL,
            "mechanism": (
                "First-party project data-link index leading to package URLs."
            ),
            "exact_backing_object_urls_obtained": False,
            "authentication_requirement": "UNRESOLVED",
            "object_listing_or_manifest_obtained": False,
            "full_download_authorized": False,
        },
        "technical_inventory": {
            "official_session_inventory_obtained": False,
            "recording_ids_obtained": 0,
            "participant_ids_obtained": 0,
            "pair_ids_obtained": 0,
            "session_ids_obtained": 0,
            "file_ids_obtained": 0,
            "rendition_ids_obtained": 0,
            "files_with_exact_bytes": 0,
            "files_with_hashes": 0,
            "sessions_with_duration_evidence": 0,
            "sessions_with_native_synchronized_audio_evidence": 0,
            "audio_codec_or_track_metadata_obtained": False,
            "semantic_inventory_fields_opened": False,
        },
        "eligible_universe": {
            "minimum_required": MIN_ELIGIBLE_GROUPS,
            "exact_group_count": 0,
            "exact_session_count": 0,
            "group_ids": [],
            "session_ids": [],
            "status": "NOT_CONSTRUCTED",
            "reason": (
                "No exact official technical inventory closed participant/"
                "pair/session/recording/file lineage plus bytes, hashes, "
                "duration, and native synchronized audio without semantic "
                "fields."
            ),
            "selected_test_groups": [],
            "semantic_yield": None,
        },
        "selection_prohibitions": {
            "semantic_prompts": "PROHIBITED",
            "candidate_mining": "PROHIBITED",
            "candidate_ranking": "PROHIBITED",
            "task_or_action_labels": "SEALED",
            "transcripts_or_narrations": "SEALED",
            "task_titles_or_descriptions": "SEALED",
            "test_group_selection": "NONE",
        },
        "live_run": dict(live or {
            "network_requests": 0,
            "response_body_bytes_read": 0,
            "response_body_bytes_persisted": 0,
            "requests": [],
            "parsed": {},
        }),
        "decision": {
            "blockers": blockers,
            "ready_rule": (
                "READY requires byte-auditable official identity and operative "
                "license, an exact first-party access mechanism, and at least "
                "six opaque lineage-closed groups with exact technical file, "
                "duration, and native synchronized audio metadata."
            ),
            "why_not_no_go": (
                "Official HoloAssist project/repository/data-link routes and a "
                "CDLA-Permissive-2.0 declaration were identified, leaving a "
                "concrete metadata-only repair path."
            ),
        },
        "reproduction": {
            "plan_only": (
                "python tools/holoassist_neutral_lineage_preflight.py "
                "--plan-only"
            ),
            "live": (
                "python tools/holoassist_neutral_lineage_preflight.py --live "
                "--proxy https://proxy.example.invalid:3128 "
                "--proxy https://proxy.example.invalid:3128"
            ),
            "stopped_finalization": (
                "python tools/holoassist_neutral_lineage_preflight.py --live "
                "--stop-network"
            ),
        },
    }
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument(
        "--stop-network",
        action="store_true",
        help="Finalize retained stopped-run evidence; make no network calls.",
    )
    parser.add_argument(
        "--proxy",
        action="append",
        default=[],
        help="Explicit proxy for live official metadata requests.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.stop_network and not args.live:
        raise PreflightError("--stop-network requires --live")

    if args.plan_only:
        mode = "plan-only"
        live = None
    elif args.stop_network:
        mode = "live-stopped-finalization"
        live = stopped_live_evidence()
    else:
        mode = "live"
        live = run_live(args.proxy or DEFAULT_PROXIES)

    generated_at = (
        "2026-10-14T11:10:00Z"
        if mode == "live-stopped-finalization"
        else None
    )
    report = build_report(
        mode=mode,
        live=live,
        generated_at=generated_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(report["final_marker"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PreflightError as exc:
        print(f"HOLOASSIST_PREFLIGHT_ERROR:{exc}", file=sys.stderr)
        raise SystemExit(2) from exc
