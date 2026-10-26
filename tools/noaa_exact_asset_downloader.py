#!/usr/bin/env python3
"""Fail-closed downloader for the five frozen NOAA Ocean Today MP4 objects.

The default mode is an offline, read-only validation.  Execute mode downloads
only the exact URL identities in the canonical plan, in bounded HTTP Range
requests, into ``data/restricted/noaa01/``.  It performs no decoding,
annotation, media derivation, redistribution, or public release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Protocol, Sequence, TextIO
from urllib.parse import urlsplit

try:
    import httpx
except ImportError:  # pragma: no cover - checked before network execution
    httpx = None  # type: ignore[assignment]


SCHEMA_VERSION = "1.0"
PLAN_ID = "NOAA01-EXACT-FIVE-RESTRICTED-ACQUISITION"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 0
EXPECTED_TOTAL_BYTES = 1_955_298_193
EXPECTED_PREFLIGHT_BODY_BYTES = 25_494_606
EXPECTED_PREFLIGHT_OBJECTS = 8

PREFLIGHT_PLAN_REL = Path(
    "data/acquisition_preflight/noaa_webinar_stream_preflight_plan.json"
)
PREFLIGHT_RESULT_REL = Path(
    "data/acquisition_preflight/noaa_webinar_stream_preflight_result.json"
)
PLAN_REL = Path("data/acquisition_plan/noaa01_exact_asset_plan.json")
AUTHORIZATION_REL = Path(
    "data/access_review/noaa01_acquisition_authorization.json"
)
STAGING_REL = Path("data/restricted/noaa01")
RAW_REL = Path("raw")
MANIFEST_REL = Path("manifests/noaa01_acquisition_manifest.json")
LOCK_REL = Path("manifests/.noaa_exact_asset_downloader.lock")

PREFLIGHT_PLAN_INTEGRITY = {
    "bytes": 32_686,
    "sha256": "9b38cbea1c294ca341806cbfef0f4ecdd3cc1120f9951f022274156a2cedc5a7",
}
PREFLIGHT_RESULT_INTEGRITY = {
    "bytes": 73_757,
    "sha256": "a519a20761e16aac9a1eaac600f6c612ec8ed9fd64589546655c710f6f525fbf",
}

ALLOWED_HOSTS = frozenset(
    {
        "oceantoday.noaa.gov",
        "cdn.oceanservice.noaa.gov",
    }
)
CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})

# Ordered to match the five scientific/benchmark roles in the task.
FROZEN_SELECTION: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "cand-045",
        "selection_role": "short_education_webinar",
        "title": "Exploring Ocean Today Education Resources",
        "stable_source_id": "NOAA-OceanToday-webinar1",
        "url": (
            "https://cdn.oceanservice.noaa.gov/oceantodayprod/media/"
            "deeperdive/webinars/oceantodaywebinar_040720-lg.mp4"
        ),
        "size_bytes": 58_576_631,
        "etag": "0x8DC750FFEBB6FC3",
        "last_modified": "Wed, 15 May 2024 18:51:13 GMT",
        "duration_seconds": 1772.44,
        "video_track_count": 1,
        "audio_track_count": 1,
    },
    {
        "candidate_id": "cand-047",
        "selection_role": "ocean_exploration_watch_party",
        "title": "Deep Ocean Full Moon Watch Party",
        "stable_source_id": "NOAA-OceanToday-webinar3",
        "url": (
            "https://cdn.oceanservice.noaa.gov/oceantodayprod/media/"
            "deeperdive/webinars/oceantoday-watchparty-050720b-sm.mp4"
        ),
        "size_bytes": 284_515_787,
        "etag": "0x8DC7510025A05A8",
        "last_modified": "Wed, 15 May 2024 18:51:19 GMT",
        "duration_seconds": 1983.8506666666667,
        "video_track_count": 1,
        "audio_track_count": 1,
    },
    {
        "candidate_id": "cand-049",
        "selection_role": "safety_field_oriented_program",
        "title": "Beach and Bay Safe",
        "stable_source_id": "NOAA-OceanToday-webinar5",
        "url": (
            "https://cdn.oceanservice.noaa.gov/oceantodayprod/media/"
            "deeperdive/webinars/05_archive_070620_sm.mp4"
        ),
        "size_bytes": 491_943_858,
        "etag": "0x8DC751001B8FB3B",
        "last_modified": "Wed, 15 May 2024 18:51:18 GMT",
        "duration_seconds": 2465.365333333333,
        "video_track_count": 1,
        "audio_track_count": 1,
    },
    {
        "candidate_id": "cand-051",
        "selection_role": "marine_debris_conservation_program",
        "title": "Trash Talk",
        "stable_source_id": "NOAA-OceanToday-webinar7",
        "url": (
            "https://cdn.oceanservice.noaa.gov/oceantodayprod/media/"
            "deeperdive/webinars/07_trashtalk_archive_0902_smc.mp4"
        ),
        "size_bytes": 558_522_234,
        "etag": "0x8DC7510021E50C0",
        "last_modified": "Wed, 15 May 2024 18:51:19 GMT",
        "duration_seconds": 3718.634666666667,
        "video_track_count": 1,
        "audio_track_count": 1,
    },
    {
        "candidate_id": "cand-052",
        "selection_role": "weather_climate_program",
        "title": "Climate Alive! Wild Weather",
        "stable_source_id": "NOAA-OceanToday-webinar8",
        "url": (
            "https://cdn.oceanservice.noaa.gov/oceantodayprod/media/"
            "deeperdive/webinars/08_climatealive_archive_1001_smc.mp4"
        ),
        "size_bytes": 561_739_683,
        "etag": "0x8DC750FF6150259",
        "last_modified": "Wed, 15 May 2024 18:50:59 GMT",
        "duration_seconds": 3781.184,
        "video_track_count": 1,
        "audio_track_count": 1,
    },
)

ALLOWLIST = tuple(
    PurePosixPath(urlsplit(item["url"]).path).name for item in FROZEN_SELECTION
)


class DownloaderError(RuntimeError):
    """Fixed-code downloader failure."""


class ConfigurationError(DownloaderError):
    pass


class SafetyError(DownloaderError):
    pass


class ContentValidationError(DownloaderError):
    pass


@dataclass(frozen=True)
class ObservedIdentity:
    url: str
    size_bytes: int
    etag: str
    last_modified: str
    content_type: str
    accept_ranges: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "size_bytes": self.size_bytes,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "content_type": self.content_type,
            "accept_ranges": self.accept_ranges,
        }


@dataclass(frozen=True)
class RangeResponse:
    body: bytes
    observed_etag: str
    observed_last_modified: str


@dataclass
class WireBudget:
    maximum_response_bytes: int = MAX_RESPONSE_BYTES
    maximum_total_bytes: int = EXPECTED_TOTAL_BYTES
    total_bytes: int = 0
    maximum_observed: int = 0

    def preflight(self, count: int) -> None:
        if count <= 0:
            raise SafetyError("INVALID_RESPONSE_SIZE")
        if count > self.maximum_response_bytes:
            raise SafetyError("RESPONSE_BODY_LIMIT_EXCEEDED")
        if self.total_bytes + count > self.maximum_total_bytes:
            raise SafetyError("WIRE_TRANSFER_BUDGET_EXCEEDED")

    def account(self, count: int) -> None:
        self.preflight(count)
        self.total_bytes += count
        self.maximum_observed = max(self.maximum_observed, count)


class ExactFetcher(Protocol):
    def validate_identity(self, asset: Mapping[str, Any]) -> ObservedIdentity: ...

    def fetch_range(
        self, asset: Mapping[str, Any], start: int, end: int
    ) -> RangeResponse: ...


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, *, chunk_bytes: int = 1024 * 1024) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as handle:
        while block := handle.read(chunk_bytes):
            count += len(block)
            digest.update(block)
    return count, digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ConfigurationError(
            f"INVALID_JSON_{path.name.upper().replace('.', '_')}"
        ) from None


def _input_integrity(path: Path, expected: Mapping[str, Any]) -> dict[str, Any]:
    raw = path.read_bytes()
    actual = {"bytes": len(raw), "sha256": sha256_bytes(raw)}
    if actual != dict(expected):
        raise ConfigurationError("AUDIT_INPUT_INTEGRITY_MISMATCH")
    return actual


def _validate_exact_asset_url(url: str) -> str:
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError:
        raise ConfigurationError("INVALID_URL_PORT") from None
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme.lower() != "https"
        or host not in ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or not parsed.path.lower().endswith(".mp4")
    ):
        raise ConfigurationError("INVALID_EXACT_NOAA_ASSET_URL")
    return host


def _audit_result(repo_root: Path) -> dict[str, Any]:
    plan_path = repo_root / PREFLIGHT_PLAN_REL
    result_path = repo_root / PREFLIGHT_RESULT_REL
    _input_integrity(plan_path, PREFLIGHT_PLAN_INTEGRITY)
    _input_integrity(result_path, PREFLIGHT_RESULT_INTEGRITY)
    source_plan = load_json(plan_path)
    result = load_json(result_path)

    if (
        source_plan.get("status") != "READY_FOR_BOUNDED_NOAA_STREAM_PREFLIGHT"
        or result.get("mode")
        != "live_bounded_noaa_direct_url_stream_preflight"
        or result.get("object_count") != EXPECTED_PREFLIGHT_OBJECTS
        or result.get("candidate_count") != EXPECTED_PREFLIGHT_OBJECTS
        or result.get("aggregate", {}).get("response_body_bytes")
        != EXPECTED_PREFLIGHT_BODY_BYTES
        or result.get("aggregate", {}).get("decision_counts")
        != {
            "GO_STREAM_DECLARED_AUDIO_AND_DURATION_PASS": 8,
            "NO_GO_DURATION_OUT_OF_RANGE": 0,
            "NO_GO_IDENTITY_OR_TRANSFER_VALIDATION": 0,
            "NO_GO_NO_AUDIO_TRACK": 0,
            "NO_GO_UNSUPPORTED_OR_INCOMPLETE_CONTAINER": 0,
        }
    ):
        raise ConfigurationError("PREFLIGHT_RESULT_SUMMARY_MISMATCH")

    plan_objects = {
        item["candidate_id"]: item for item in source_plan.get("objects", [])
    }
    result_objects = {
        item["candidate_id"]: item for item in result.get("objects", [])
    }
    if len(plan_objects) != 8 or set(plan_objects) != set(result_objects):
        raise ConfigurationError("PREFLIGHT_OBJECT_SET_MISMATCH")

    for candidate_id, item in result_objects.items():
        if (
            item.get("decision")
            != "GO_STREAM_DECLARED_AUDIO_AND_DURATION_PASS"
            or item.get("identity_match") is not True
            or item.get("container_parse_status") != "PARSED_ISO_BMFF"
            or item.get("duration_gate") != "PASS"
            or item.get("video_track_count") != 1
            or item.get("audio_track_count") != 1
            or item.get("av_timeline_relation") != "PLAUSIBLY_SYNCHRONIZED"
            or item.get("identity")
            != {
                key: plan_objects[candidate_id][key]
                for key in (
                    "accept_ranges",
                    "candidate_id",
                    "content_type",
                    "etag",
                    "last_modified",
                    "size_bytes",
                    "url",
                )
            }
        ):
            raise ConfigurationError("PREFLIGHT_OBJECT_AUDIT_MISMATCH")
    return result


def derive_frozen_plan(repo_root: Path) -> dict[str, Any]:
    result = _audit_result(repo_root)
    result_objects = {
        item["candidate_id"]: item for item in result["objects"]
    }
    assets: list[dict[str, Any]] = []
    for frozen in FROZEN_SELECTION:
        observed = result_objects.get(frozen["candidate_id"])
        if observed is None:
            raise ConfigurationError("SELECTED_OBJECT_MISSING_FROM_PREFLIGHT")
        identity = observed["identity"]
        expected_identity = {
            key: frozen[key]
            for key in ("candidate_id", "url", "size_bytes", "etag", "last_modified")
        }
        if {key: identity[key] for key in expected_identity} != expected_identity:
            raise ConfigurationError("SELECTED_OBJECT_IDENTITY_MISMATCH")
        for key in (
            "duration_seconds",
            "video_track_count",
            "audio_track_count",
        ):
            if observed.get(key) != frozen[key]:
                raise ConfigurationError("SELECTED_OBJECT_STREAM_FACT_MISMATCH")
        provenance = observed["noaa_provenance"]
        if (
            provenance.get("page_title") != frozen["title"]
            or provenance.get("stable_source_id") != frozen["stable_source_id"]
        ):
            raise ConfigurationError("SELECTED_OBJECT_PROVENANCE_MISMATCH")

        basename = PurePosixPath(urlsplit(frozen["url"]).path).name
        _validate_exact_asset_url(frozen["url"])
        assets.append(
            {
                "candidate_id": frozen["candidate_id"],
                "selection_role": frozen["selection_role"],
                "title": frozen["title"],
                "stable_source_id": frozen["stable_source_id"],
                "url": frozen["url"],
                "size_bytes": frozen["size_bytes"],
                "etag": frozen["etag"],
                "last_modified": frozen["last_modified"],
                "content_type": "video/mp4",
                "accept_ranges": "bytes",
                "basename": basename,
                "destination": (RAW_REL / basename).as_posix(),
                "technical_audit": {
                    "decision": observed["decision"],
                    "container_parse_status": observed[
                        "container_parse_status"
                    ],
                    "duration_seconds": observed["duration_seconds"],
                    "duration_gate": observed["duration_gate"],
                    "video_track_count": observed["video_track_count"],
                    "container_declared_audio_track_count": observed[
                        "audio_track_count"
                    ],
                    "av_timeline_relation": observed[
                        "av_timeline_relation"
                    ],
                    "local_audio_decode_checked": False,
                    "speech_or_ambient_semantics_checked": False,
                },
            }
        )

    if (
        len(assets) != 5
        or tuple(item["basename"] for item in assets) != ALLOWLIST
        or sum(item["size_bytes"] for item in assets) != EXPECTED_TOTAL_BYTES
        or len({item["url"] for item in assets}) != 5
    ):
        raise ConfigurationError("FROZEN_SELECTION_TOTAL_OR_COUNT_MISMATCH")

    return {
        "schema_version": SCHEMA_VERSION,
        "plan_id": PLAN_ID,
        "frozen_date": "2026-09-09",
        "status": "AUTHORIZED_FOR_EXACT_RESTRICTED_DOWNLOAD_ONLY",
        "source_audit": {
            PREFLIGHT_PLAN_REL.as_posix(): PREFLIGHT_PLAN_INTEGRITY,
            PREFLIGHT_RESULT_REL.as_posix(): PREFLIGHT_RESULT_INTEGRITY,
            "result_decision": "8/8 GO_STREAM_DECLARED_AUDIO_AND_DURATION_PASS",
            "result_response_body_bytes": EXPECTED_PREFLIGHT_BODY_BYTES,
        },
        "selection": {
            "selected_count": 5,
            "candidate_ids": [
                item["candidate_id"] for item in FROZEN_SELECTION
            ],
            "excluded_candidate_ids": ["cand-046", "cand-048", "cand-054"],
            "selection_basis": (
                "Five nonredundant topic roles, using passed official "
                "renditions and preferring small/low-resolution objects."
            ),
        },
        "allowed_hosts": sorted(ALLOWED_HOSTS),
        "staging_root": STAGING_REL.as_posix(),
        "transfer_policy": {
            "methods": ["HEAD", "GET"],
            "get_requires_exact_range": True,
            "redirects_allowed": MAX_REDIRECTS,
            "maximum_response_body_bytes": MAX_RESPONSE_BYTES,
            "chunk_bytes": MAX_RESPONSE_BYTES,
            "expected_total_payload_bytes": EXPECTED_TOTAL_BYTES,
            "exact_final_size_required": True,
            "etag_and_last_modified_required": True,
            "bearer_tokens_prohibited": True,
            "cookies_prohibited": True,
            "whole_file_sha256_after_download": "OPTIONAL_OPERATOR_FLAG",
        },
        "authorization_boundary": {
            "restricted_internal_storage_only": True,
            "processing_authorized": False,
            "annotation_authorized": False,
            "public_release_authorized": False,
            "derived_media_authorized": False,
        },
        "assets": assets,
    }


def validate_frozen_plan(repo_root: Path) -> tuple[dict[str, Any], str]:
    path = repo_root / PLAN_REL
    raw = path.read_bytes()
    persisted = load_json(path)
    expected = derive_frozen_plan(repo_root)
    if persisted != expected or raw != canonical_json_bytes(expected):
        raise ConfigurationError("FROZEN_PLAN_DRIFT")
    return expected, sha256_bytes(raw)


def expected_authorization(plan_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_id": "NOAA-01",
        "authorization_status": "AUTHORIZED_EXACT_FIVE_RESTRICTED_DOWNLOADS",
        "authorization_source": (
            "TASK_76_RECORD_OF_PRIOR_USER_AUTHORIZATION_AFTER_AUDIT"
        ),
        "recorded_date": "2026-09-09",
        "authorized_scope": {
            "plan": PLAN_REL.as_posix(),
            "plan_sha256": plan_sha256,
            "candidate_ids": [
                item["candidate_id"] for item in FROZEN_SELECTION
            ],
            "exact_urls": [item["url"] for item in FROZEN_SELECTION],
            "exact_sizes": [
                item["size_bytes"] for item in FROZEN_SELECTION
            ],
            "exact_etags": [item["etag"] for item in FROZEN_SELECTION],
            "exact_last_modified": [
                item["last_modified"] for item in FROZEN_SELECTION
            ],
            "expected_total_payload_bytes": EXPECTED_TOTAL_BYTES,
            "maximum_single_response_body_bytes": MAX_RESPONSE_BYTES,
            "destination_root": STAGING_REL.as_posix(),
            "storage_class": "RESTRICTED_INTERNAL_ONLY",
        },
        "audit_basis": {
            "result": PREFLIGHT_RESULT_REL.as_posix(),
            "result_sha256": PREFLIGHT_RESULT_INTEGRITY["sha256"],
            "passed_objects": 8,
            "selected_objects": 5,
            "technical_acquisition_eligibility": "PASS",
            "container_declared_audio_tracks": "ONE_PER_SELECTED_OBJECT",
            "local_decoded_audio_checked": False,
            "speech_or_ambient_semantics_checked": False,
            "rights_and_public_redistribution": "HELD_NOT_AUTHORIZED",
        },
        "credential_controls": {
            "hf_token_lookup": False,
            "authorization_header": "PROHIBITED",
            "cookie_header": "PROHIBITED",
        },
        "not_authorized": {
            "unlisted_url_or_candidate": True,
            "wildcard_or_page_level_download": True,
            "processing_or_decoding": True,
            "annotation": True,
            "derived_media": True,
            "public_release_or_redistribution": True,
        },
        "implementation": "tools/noaa_exact_asset_downloader.py",
        "selection_memo": "docs/review/noaa_final_selection.md",
    }


def validate_authorization(
    repo_root: Path, plan: Mapping[str, Any], plan_sha256: str
) -> dict[str, Any]:
    path = repo_root / AUTHORIZATION_REL
    raw = path.read_bytes()
    authorization = load_json(path)
    expected = expected_authorization(plan_sha256)
    if authorization != expected or raw != canonical_json_bytes(expected):
        raise ConfigurationError("AUTHORIZATION_DRIFT")
    if plan["selection"]["candidate_ids"] != authorization[
        "authorized_scope"
    ]["candidate_ids"]:
        raise ConfigurationError("PLAN_AUTHORIZATION_SCOPE_MISMATCH")
    return authorization


def validate_local_configuration(
    repo_root: Path,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    plan, plan_sha256 = validate_frozen_plan(repo_root)
    authorization = validate_authorization(repo_root, plan, plan_sha256)
    return plan, plan_sha256, authorization


def _header_content_type(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def _expected_identity(asset: Mapping[str, Any]) -> ObservedIdentity:
    return ObservedIdentity(
        url=str(asset["url"]),
        size_bytes=int(asset["size_bytes"]),
        etag=str(asset["etag"]),
        last_modified=str(asset["last_modified"]),
        content_type=str(asset["content_type"]),
        accept_ranges=str(asset["accept_ranges"]),
    )


class SafeExactRangeClient:
    """No-credential client for exact NOAA objects with strict Range checks."""

    def __init__(
        self,
        *,
        proxy: str | None = None,
        client: Any | None = None,
        budget: WireBudget | None = None,
    ) -> None:
        if httpx is None:
            raise ConfigurationError("HTTPX_NOT_INSTALLED")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            follow_redirects=False,
            trust_env=True,
            proxy=proxy,
            timeout=httpx.Timeout(120.0, connect=30.0),
            headers={
                "User-Agent": "AV-TRACE-noaa-exact-asset-downloader/1.0"
            },
        )
        self.budget = budget or WireBudget()

    def __enter__(self) -> "SafeExactRangeClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    @staticmethod
    def _validate_request_asset(asset: Mapping[str, Any]) -> None:
        url = str(asset.get("url", ""))
        _validate_exact_asset_url(url)
        frozen = next(
            (
                item
                for item in FROZEN_SELECTION
                if item["candidate_id"] == asset.get("candidate_id")
            ),
            None,
        )
        if frozen is None or any(
            asset.get(key) != frozen[key]
            for key in ("url", "size_bytes", "etag", "last_modified")
        ):
            raise SafetyError("REQUEST_ASSET_NOT_FROZEN")

    @staticmethod
    def _reject_sensitive_headers(headers: Mapping[str, str]) -> None:
        lowered = {key.lower() for key in headers}
        if "authorization" in lowered or "cookie" in lowered:
            raise SafetyError("CREDENTIAL_HEADER_PROHIBITED")

    @staticmethod
    def _observed_identity(
        asset: Mapping[str, Any], response: Any
    ) -> ObservedIdentity:
        try:
            size = int(response.headers["content-length"])
        except (KeyError, TypeError, ValueError):
            raise SafetyError("MISSING_OR_INVALID_CONTENT_LENGTH") from None
        return ObservedIdentity(
            url=str(response.url),
            size_bytes=size,
            etag=response.headers.get("etag", ""),
            last_modified=response.headers.get("last-modified", ""),
            content_type=_header_content_type(
                response.headers.get("content-type", "")
            ),
            accept_ranges=response.headers.get("accept-ranges", "").lower(),
        )

    def validate_identity(self, asset: Mapping[str, Any]) -> ObservedIdentity:
        self._validate_request_asset(asset)
        headers = {"Accept-Encoding": "identity"}
        self._reject_sensitive_headers(headers)
        try:
            with self._client.stream(
                "HEAD", str(asset["url"]), headers=headers
            ) as response:
                if response.status_code in REDIRECT_CODES:
                    raise SafetyError("REDIRECT_PROHIBITED")
                if response.status_code != 200:
                    raise SafetyError("UNEXPECTED_HEAD_STATUS")
                observed = self._observed_identity(asset, response)
                if observed != _expected_identity(asset):
                    raise SafetyError("HEAD_IDENTITY_MISMATCH")
                if any(True for _ in response.iter_bytes()):
                    raise SafetyError("UNEXPECTED_HEAD_RESPONSE_BODY")
                return observed
        except DownloaderError:
            raise
        except Exception as exc:
            raise DownloaderError(
                f"HTTP_TRANSPORT_{type(exc).__name__.upper()}"
            ) from None

    def fetch_range(
        self, asset: Mapping[str, Any], start: int, end: int
    ) -> RangeResponse:
        self._validate_request_asset(asset)
        size = int(asset["size_bytes"])
        if start < 0 or end < start or end >= size:
            raise SafetyError("RANGE_OUTSIDE_FROZEN_OBJECT")
        expected_body = end - start + 1
        if expected_body > MAX_RESPONSE_BYTES:
            raise SafetyError("REQUEST_EXCEEDS_8_MIB")
        self.budget.preflight(expected_body)
        # Do not send If-Range: this exact CDN serves a full-object 200 for
        # that construction. Identity remains fail-closed via the required
        # HEAD above and exact ETag/Last-Modified checks on every 206 below.
        headers = {
            "Range": f"bytes={start}-{end}",
            "Accept-Encoding": "identity",
        }
        self._reject_sensitive_headers(headers)
        try:
            with self._client.stream(
                "GET", str(asset["url"]), headers=headers
            ) as response:
                if response.status_code in REDIRECT_CODES:
                    raise SafetyError("REDIRECT_PROHIBITED")
                if response.status_code == 200:
                    raise SafetyError("RANGE_IGNORED_FULL_OBJECT_200")
                if response.status_code != 206:
                    raise SafetyError("UNEXPECTED_RANGE_STATUS")
                if str(response.url) != asset["url"]:
                    raise SafetyError("RANGE_EFFECTIVE_URL_MISMATCH")
                if (
                    response.headers.get("content-encoding", "identity").lower()
                    != "identity"
                ):
                    raise SafetyError("UNEXPECTED_RANGE_CONTENT_ENCODING")
                try:
                    content_length = int(response.headers["content-length"])
                except (KeyError, TypeError, ValueError):
                    raise SafetyError(
                        "MISSING_OR_INVALID_CONTENT_LENGTH"
                    ) from None
                if content_length != expected_body:
                    raise SafetyError("MISMATCHED_CONTENT_LENGTH")
                match = CONTENT_RANGE_RE.fullmatch(
                    response.headers.get("content-range", "").strip()
                )
                if not match or tuple(map(int, match.groups())) != (
                    start,
                    end,
                    size,
                ):
                    raise SafetyError("MISMATCHED_CONTENT_RANGE")
                if _header_content_type(
                    response.headers.get("content-type", "")
                ) != asset["content_type"]:
                    raise SafetyError("RANGE_CONTENT_TYPE_MISMATCH")
                observed_etag = response.headers.get("etag", "")
                observed_last_modified = response.headers.get(
                    "last-modified", ""
                )
                if (
                    observed_etag != asset["etag"]
                    or observed_last_modified != asset["last_modified"]
                ):
                    raise SafetyError("RANGE_IDENTITY_MISMATCH")
                body = bytearray()
                for block in response.iter_bytes():
                    if len(body) + len(block) > expected_body:
                        raise SafetyError("RANGE_RESPONSE_EXCESS_BYTES")
                    body.extend(block)
                if len(body) != expected_body:
                    raise SafetyError("RANGE_RESPONSE_TRUNCATED")
                self.budget.account(len(body))
                return RangeResponse(
                    body=bytes(body),
                    observed_etag=observed_etag,
                    observed_last_modified=observed_last_modified,
                )
        except DownloaderError:
            raise
        except Exception as exc:
            raise DownloaderError(
                f"HTTP_TRANSPORT_{type(exc).__name__.upper()}"
            ) from None


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _reject_symlink_components(path: Path, stop: Path) -> None:
    current = path
    while True:
        if current.exists() and current.is_symlink():
            raise SafetyError("SYMLINK_IN_DESTINATION_PATH")
        if current == stop:
            return
        if stop not in current.parents:
            raise SafetyError("DESTINATION_OUTSIDE_REPOSITORY")
        current = current.parent


def ensure_secure_directory(
    path: Path, *, repo_root: Path, managed: bool = True
) -> None:
    _reject_symlink_components(path, repo_root)
    if path.exists():
        if not path.is_dir():
            raise SafetyError("DESTINATION_COMPONENT_NOT_DIRECTORY")
        mode = _mode(path)
        if managed and mode != 0o700:
            raise SafetyError("PERMISSIVE_MANAGED_DIRECTORY")
        if mode & 0o022:
            raise SafetyError("WRITABLE_DESTINATION_PARENT")
        return
    path.mkdir(mode=0o700, parents=False)
    if _mode(path) != 0o700:
        raise SafetyError("SECURE_DIRECTORY_MODE_NOT_ESTABLISHED")


def ensure_staging_tree(repo_root: Path) -> Path:
    data = repo_root / "data"
    restricted = data / "restricted"
    for parent in (data, restricted):
        ensure_secure_directory(parent, repo_root=repo_root, managed=False)
    staging = repo_root / STAGING_REL
    ensure_secure_directory(staging, repo_root=repo_root)
    ensure_secure_directory(staging / RAW_REL, repo_root=repo_root)
    ensure_secure_directory(
        (staging / MANIFEST_REL).parent, repo_root=repo_root
    )
    return staging


def _assert_secure_file(path: Path) -> None:
    if path.is_symlink():
        raise SafetyError("SYMLINK_FILE_PROHIBITED")
    if not path.is_file():
        raise SafetyError("EXPECTED_REGULAR_FILE")
    if _mode(path) != 0o600:
        raise SafetyError("PERMISSIVE_FILE_PROHIBITED")


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_json(
    path: Path, value: Any, *, replace: bool = True
) -> None:
    if path.exists():
        _assert_secure_file(path)
    data = canonical_json_bytes(value)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if not replace and path.exists():
            raise SafetyError("REFUSING_TO_OVERWRITE_SIDECAR")
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_mp4_prefix(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        prefix = handle.read(4096)
    if len(prefix) < 16:
        raise ContentValidationError("MP4_PREFIX_TOO_SHORT")
    box_size = int.from_bytes(prefix[0:4], "big")
    if (
        prefix[4:8] != b"ftyp"
        or box_size < 16
        or box_size > len(prefix)
        or box_size % 4
    ):
        raise ContentValidationError("MP4_FTYP_PREFIX_INVALID")
    major_brand = prefix[8:12]
    compatible_brands = [
        prefix[index : index + 4] for index in range(16, box_size, 4)
    ]
    if not all(
        len(brand) == 4 and all(32 <= byte <= 126 for byte in brand)
        for brand in [major_brand, *compatible_brands]
    ):
        raise ContentValidationError("MP4_BRAND_BYTES_INVALID")
    return {
        "first_box_type": "ftyp",
        "first_box_size": box_size,
        "major_brand": major_brand.decode("ascii"),
        "compatible_brands": [
            brand.decode("ascii") for brand in compatible_brands
        ],
    }


def _asset_binding(
    asset: Mapping[str, Any], plan_sha256: str, chunk_bytes: int
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "plan_id": PLAN_ID,
        "plan_sha256": plan_sha256,
        "candidate_id": asset["candidate_id"],
        "url": asset["url"],
        "size_bytes": asset["size_bytes"],
        "etag": asset["etag"],
        "last_modified": asset["last_modified"],
        "content_type": asset["content_type"],
        "accept_ranges": asset["accept_ranges"],
        "basename": asset["basename"],
        "destination": asset["destination"],
        "chunk_bytes": chunk_bytes,
    }


class Acquirer:
    def __init__(
        self,
        repo_root: Path,
        plan: Mapping[str, Any],
        plan_sha256: str,
        fetcher: ExactFetcher,
        *,
        compute_whole_file_sha256: bool = False,
        chunk_bytes: int | None = None,
        progress_stream: TextIO | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.plan = plan
        self.plan_sha256 = plan_sha256
        self.fetcher = fetcher
        self.compute_whole_file_sha256 = compute_whole_file_sha256
        self.chunk_bytes = chunk_bytes or int(
            plan["transfer_policy"]["chunk_bytes"]
        )
        if self.chunk_bytes <= 0 or self.chunk_bytes > MAX_RESPONSE_BYTES:
            raise ConfigurationError("INVALID_CHUNK_SIZE")
        self.progress_stream = progress_stream or sys.stderr
        self.staging_root = repo_root / STAGING_REL
        self.payload_bytes_received = 0

    def _paths(
        self, asset: Mapping[str, Any]
    ) -> tuple[Path, Path, Path, Path]:
        raw_destination = PurePosixPath(str(asset["destination"]))
        if (
            raw_destination.is_absolute()
            or ".." in raw_destination.parts
            or raw_destination.parts
            != ("raw", str(asset["basename"]))
            or asset["basename"] not in ALLOWLIST
        ):
            raise SafetyError("DESTINATION_PATH_NOT_EXACT")
        destination = self.staging_root / Path(*raw_destination.parts)
        if destination.parent != self.staging_root / RAW_REL:
            raise SafetyError("DESTINATION_OUTSIDE_FROZEN_RAW_DIRECTORY")
        return (
            destination,
            destination.with_name(destination.name + ".partial"),
            destination.with_name(destination.name + ".partial.json"),
            destination.with_name(destination.name + ".metadata.json"),
        )

    @staticmethod
    def _existing(path: Path) -> bool:
        if path.is_symlink():
            raise SafetyError("SYMLINK_FILE_PROHIBITED")
        if path.exists():
            _assert_secure_file(path)
            return True
        return False

    def _load_or_create_partial(
        self, asset: Mapping[str, Any], partial: Path, state_path: Path
    ) -> tuple[int, hashlib._Hash]:
        partial_exists = self._existing(partial)
        state_exists = self._existing(state_path)
        if partial_exists != state_exists:
            raise SafetyError("PARTIAL_AND_STATE_MUST_EXIST_TOGETHER")
        binding = _asset_binding(asset, self.plan_sha256, self.chunk_bytes)
        if not partial_exists:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(partial, flags, 0o600)
            os.close(descriptor)
            initial = dict(binding)
            initial.update(
                {
                    "completed_bytes": 0,
                    "prefix_sha256": hashlib.sha256().hexdigest(),
                }
            )
            atomic_write_json(state_path, initial, replace=False)
            return 0, hashlib.sha256()

        state_value = load_json(state_path)
        if any(
            state_value.get(key) != value for key, value in binding.items()
        ):
            raise SafetyError("PARTIAL_STATE_BINDING_MISMATCH")
        size, digest = sha256_file(partial)
        if size > asset["size_bytes"]:
            raise SafetyError("PARTIAL_LARGER_THAN_TARGET")
        if size != asset["size_bytes"] and size % self.chunk_bytes:
            raise SafetyError("PARTIAL_NOT_ON_EXACT_CHUNK_BOUNDARY")
        if (
            state_value.get("completed_bytes") != size
            or state_value.get("prefix_sha256") != digest
        ):
            raise SafetyError("PARTIAL_STATE_SIZE_OR_HASH_MISMATCH")
        hasher = hashlib.sha256()
        with partial.open("rb") as handle:
            while block := handle.read(1024 * 1024):
                hasher.update(block)
        return size, hasher

    def _verify_completed(
        self,
        asset: Mapping[str, Any],
        destination: Path,
        metadata_path: Path,
    ) -> dict[str, Any]:
        if not self._existing(metadata_path):
            raise SafetyError("EXISTING_TARGET_WITHOUT_METADATA")
        metadata = load_json(metadata_path)
        binding = _asset_binding(asset, self.plan_sha256, self.chunk_bytes)
        if any(metadata.get(key) != value for key, value in binding.items()):
            raise SafetyError("COMPLETED_METADATA_BINDING_MISMATCH")
        size, digest = sha256_file(destination)
        if (
            size != asset["size_bytes"]
            or metadata.get("final_size_bytes") != size
            or metadata.get("transfer_sha256") != digest
        ):
            raise SafetyError("COMPLETED_TARGET_SIZE_OR_HASH_MISMATCH")
        if self.compute_whole_file_sha256 and metadata.get(
            "whole_file_sha256"
        ) != digest:
            metadata["whole_file_sha256"] = digest
            metadata["whole_file_sha256_computed_locally"] = True
            metadata["whole_file_sha256_computed_at_utc"] = utc_now()
            atomic_write_json(metadata_path, metadata)
        return {
            "status": "skipped_verified",
            "size": size,
            "sha256": digest,
        }

    def acquire_asset(
        self, asset: Mapping[str, Any], index: int, total: int
    ) -> dict[str, Any]:
        destination, partial, state_path, metadata_path = self._paths(asset)
        for path in (destination, partial, state_path, metadata_path):
            if path.is_symlink():
                raise SafetyError("SYMLINK_FILE_PROHIBITED")
        if self._existing(destination):
            if partial.exists() or state_path.exists():
                raise SafetyError("COMPLETED_AND_PARTIAL_TARGET_CONFLICT")
            result = self._verify_completed(
                asset, destination, metadata_path
            )
            print(
                f"[{index}/{total}] verified existing {asset['basename']}",
                file=self.progress_stream,
                flush=True,
            )
            return result
        if metadata_path.exists():
            raise SafetyError("METADATA_WITHOUT_COMPLETED_TARGET")

        completed, hasher = self._load_or_create_partial(
            asset, partial, state_path
        )
        # A complete-looking partial is still untrusted until the live exact
        # object identity is revalidated; never finalize solely from local
        # resumable state.
        observed_head: ObservedIdentity | None = self.fetcher.validate_identity(
            asset
        )
        observed_range_identity: dict[str, str] | None = None
        request_count = 0
        if completed < asset["size_bytes"]:
            print(
                f"[{index}/{total}] identity verified {asset['basename']} "
                f"resume_bytes={completed}",
                file=self.progress_stream,
                flush=True,
            )
            flags = os.O_WRONLY | os.O_APPEND
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(partial, flags)
            with os.fdopen(descriptor, "wb", buffering=0) as handle:
                while completed < asset["size_bytes"]:
                    length = min(
                        self.chunk_bytes, asset["size_bytes"] - completed
                    )
                    response = self.fetcher.fetch_range(
                        asset, completed, completed + length - 1
                    )
                    if len(response.body) != length:
                        raise SafetyError(
                            "FETCHER_RETURNED_UNEXPECTED_BYTE_COUNT"
                        )
                    current_identity = {
                        "etag": response.observed_etag,
                        "last_modified": response.observed_last_modified,
                    }
                    if observed_range_identity not in (
                        None,
                        current_identity,
                    ):
                        raise SafetyError("RANGE_IDENTITY_CHANGED_DURING_RUN")
                    observed_range_identity = current_identity
                    view = memoryview(response.body)
                    while view:
                        written = handle.write(view)
                        if not written:
                            raise SafetyError("PARTIAL_WRITE_FAILED")
                        view = view[written:]
                    handle.flush()
                    os.fsync(handle.fileno())
                    hasher.update(response.body)
                    completed += length
                    request_count += 1
                    self.payload_bytes_received += length
                    if self.payload_bytes_received > EXPECTED_TOTAL_BYTES:
                        raise SafetyError(
                            "RUN_PAYLOAD_EXCEEDS_FROZEN_TOTAL"
                        )
                    state_value = _asset_binding(
                        asset, self.plan_sha256, self.chunk_bytes
                    )
                    state_value.update(
                        {
                            "completed_bytes": completed,
                            "prefix_sha256": hasher.hexdigest(),
                        }
                    )
                    atomic_write_json(state_path, state_value)
                    print(
                        f"[{index}/{total}] {asset['basename']} "
                        f"bytes={completed}/{asset['size_bytes']}",
                        file=self.progress_stream,
                        flush=True,
                    )

        final_size = partial.stat().st_size
        transfer_sha256 = hasher.hexdigest()
        if final_size != asset["size_bytes"]:
            raise SafetyError("FINAL_SIZE_MISMATCH")
        content_validation = validate_mp4_prefix(partial)
        whole_file_sha256: str | None = None
        if self.compute_whole_file_sha256:
            recomputed_size, whole_file_sha256 = sha256_file(partial)
            if (
                recomputed_size != final_size
                or whole_file_sha256 != transfer_sha256
            ):
                raise SafetyError("WHOLE_FILE_SHA256_RECOMPUTE_MISMATCH")

        metadata = _asset_binding(
            asset, self.plan_sha256, self.chunk_bytes
        )
        metadata.update(
            {
                "final_size_bytes": final_size,
                "transfer_sha256": transfer_sha256,
                "whole_file_sha256": whole_file_sha256,
                "whole_file_sha256_computed_locally": (
                    self.compute_whole_file_sha256
                ),
                "expected_identity": _expected_identity(asset).as_dict(),
                "observed_head_identity": (
                    observed_head.as_dict() if observed_head else None
                ),
                "observed_range_identity": observed_range_identity,
                "range_request_count_this_run": request_count,
                "content_validation": content_validation,
                "completed_at_utc": utc_now(),
                "authorization_boundary": {
                    "restricted_internal_storage_only": True,
                    "processing_or_decoding_authorized": False,
                    "annotation_authorized": False,
                    "derived_media_authorized": False,
                    "public_release_or_redistribution_authorized": False,
                },
            }
        )
        metadata_temporary = metadata_path.with_name(
            metadata_path.name + ".partial"
        )
        if metadata_temporary.exists() or metadata_temporary.is_symlink():
            raise SafetyError("METADATA_TEMPORARY_ALREADY_EXISTS")
        atomic_write_json(metadata_temporary, metadata, replace=False)
        if destination.exists() or metadata_path.exists():
            raise SafetyError("REFUSING_TO_OVERWRITE_COMPLETED_TARGET")
        os.replace(partial, destination)
        fsync_directory(destination.parent)
        os.replace(metadata_temporary, metadata_path)
        fsync_directory(destination.parent)
        state_path.unlink()
        fsync_directory(destination.parent)
        _assert_secure_file(destination)
        _assert_secure_file(metadata_path)
        return {
            "status": "downloaded",
            "size": final_size,
            "sha256": transfer_sha256,
        }

    def run(self) -> dict[str, Any]:
        assets = list(self.plan["assets"])
        if (
            len(assets) != 5
            or tuple(item["basename"] for item in assets) != ALLOWLIST
        ):
            raise SafetyError("PLAN_ASSET_ORDER_OR_ALLOWLIST_MISMATCH")
        results = [
            self.acquire_asset(asset, index, len(assets))
            for index, asset in enumerate(assets, 1)
        ]
        verified_total = sum(item["size"] for item in results)
        if verified_total != EXPECTED_TOTAL_BYTES:
            raise SafetyError("VERIFIED_AGGREGATE_SIZE_MISMATCH")
        return {
            "schema_version": SCHEMA_VERSION,
            "plan_id": PLAN_ID,
            "plan_sha256": self.plan_sha256,
            "completed_at_utc": utc_now(),
            "expected_total_payload_bytes": EXPECTED_TOTAL_BYTES,
            "verified_total_payload_bytes": verified_total,
            "payload_bytes_received_this_run": self.payload_bytes_received,
            "whole_file_sha256_requested": self.compute_whole_file_sha256,
            "authorization_boundary": {
                "restricted_internal_storage_only": True,
                "processing_or_decoding_authorized": False,
                "annotation_authorized": False,
                "derived_media_authorized": False,
                "public_release_or_redistribution_authorized": False,
            },
            "assets": [
                {
                    "candidate_id": asset["candidate_id"],
                    "basename": asset["basename"],
                    "size_bytes": result["size"],
                    "sha256": result["sha256"],
                    "status": result["status"],
                    "metadata_sidecar": (
                        Path(asset["destination"]).with_name(
                            Path(asset["destination"]).name
                            + ".metadata.json"
                        )
                    ).as_posix(),
                }
                for asset, result in zip(assets, results, strict=True)
            ],
        }


def dry_run(repo_root: Path) -> dict[str, Any]:
    plan, plan_sha256, _ = validate_local_configuration(repo_root)
    return {
        "mode": "dry-run",
        "status": "GO_EXACT_RESTRICTED_DOWNLOAD",
        "plan": PLAN_REL.as_posix(),
        "plan_sha256": plan_sha256,
        "authorization": AUTHORIZATION_REL.as_posix(),
        "candidate_ids": plan["selection"]["candidate_ids"],
        "asset_count": len(plan["assets"]),
        "expected_total_payload_bytes": EXPECTED_TOTAL_BYTES,
        "maximum_response_body_bytes": MAX_RESPONSE_BYTES,
        "network_attempted": False,
        "credentials_read": False,
        "outputs_written": False,
        "processing_authorized": False,
        "annotation_authorized": False,
        "public_release_authorized": False,
    }


def _acquire_lock(staging_root: Path) -> tuple[int, Path]:
    lock_path = staging_root / LOCK_REL
    if lock_path.exists() or lock_path.is_symlink():
        raise SafetyError("ACQUISITION_LOCK_ALREADY_EXISTS")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
    os.fsync(descriptor)
    return descriptor, lock_path


def run_execute(
    repo_root: Path,
    *,
    proxy: str | None = None,
    compute_whole_file_sha256: bool = False,
    client_factory: Callable[[], ExactFetcher] | None = None,
    progress_stream: TextIO | None = None,
) -> dict[str, Any]:
    plan, plan_sha256, _ = validate_local_configuration(repo_root)
    staging_root = ensure_staging_tree(repo_root)
    lock_fd, lock_path = _acquire_lock(staging_root)
    fetcher: ExactFetcher | None = None
    try:
        fetcher = (
            client_factory()
            if client_factory
            else SafeExactRangeClient(proxy=proxy)
        )
        result = Acquirer(
            repo_root,
            plan,
            plan_sha256,
            fetcher,
            compute_whole_file_sha256=compute_whole_file_sha256,
            progress_stream=progress_stream,
        ).run()
        if isinstance(fetcher, SafeExactRangeClient):
            result["wire_response_bytes_this_run"] = (
                fetcher.budget.total_bytes
            )
            result["maximum_response_body_observed"] = (
                fetcher.budget.maximum_observed
            )
        manifest_path = staging_root / MANIFEST_REL
        atomic_write_json(manifest_path, result)
        return {
            "mode": "execute",
            "status": "COMPLETE",
            "manifest": manifest_path.relative_to(repo_root).as_posix(),
            "asset_count": len(result["assets"]),
            "expected_total_payload_bytes": EXPECTED_TOTAL_BYTES,
            "payload_bytes_received_this_run": result[
                "payload_bytes_received_this_run"
            ],
        }
    finally:
        close = getattr(fetcher, "close", None)
        if callable(close):
            close()
        os.close(lock_fd)
        if lock_path.exists():
            lock_path.unlink()
            fsync_directory(lock_path.parent)


def find_repo_root(script_path: Path) -> Path:
    root = script_path.resolve().parents[1]
    if not (root / "pyproject.toml").is_file():
        raise ConfigurationError("REPOSITORY_ROOT_NOT_FOUND")
    return root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="validate frozen plan and authorization without network or writes",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="download only the five authorized exact objects",
    )
    parser.add_argument(
        "--proxy",
        help="Optional explicit HTTP(S) proxy used only for exact NOAA requests",
    )
    parser.add_argument(
        "--sha256",
        action="store_true",
        help="re-read each completed local file and record whole-file SHA-256",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo_root = find_repo_root(Path(__file__))
        result = (
            dry_run(repo_root)
            if args.dry_run
            else run_execute(
                repo_root,
                proxy=args.proxy,
                compute_whole_file_sha256=args.sha256,
            )
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except DownloaderError as exc:
        print(
            f"noaa exact asset downloader failed: {exc}", file=sys.stderr
        )
        return 2
    except Exception as exc:
        print(
            "noaa exact asset downloader failed: "
            f"INTERNAL_{type(exc).__name__.upper()}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
