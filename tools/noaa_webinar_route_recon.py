#!/usr/bin/env python3
"""Discover exact small NOAA Ocean Today webinar MP4 routes metadata-only.

The reconciler reads the ten reviewed NOAA rows from the local candidate CSV,
GETs only their official Ocean Today pages (with a strict 2 MiB body cap), and
uses HEAD only for extracted direct MP4 routes.  It never requests an MP4 body.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urljoin, urlsplit, urlunsplit

try:
    import httpx
except ImportError:  # pragma: no cover - checked by CLI
    httpx = None  # type: ignore[assignment]


SCHEMA_VERSION = "1.0.0"
SOURCE_CSV_PATH = Path("data/candidates/source_candidates.csv")
PLAN_PATH = Path(
    "data/acquisition_preflight/noaa_webinar_stream_preflight_plan.json"
)
NOAA_CANDIDATE_IDS = tuple(f"cand-{number:03d}" for number in range(45, 55))
PAGE_HOST = "oceantoday.noaa.gov"
OCEAN_SERVICE_CDN_HOST = "cdn.oceanservice.noaa.gov"
DIRECT_MP4_HOSTS = frozenset((PAGE_HOST, OCEAN_SERVICE_CDN_HOST))
MIN_OBJECTS = 5
MAX_OBJECTS = 8
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 8
MAX_ROUTES_PER_PAGE = 32
REDIRECT_CODES = {301, 302, 303, 307, 308}
MP4_RE = re.compile(
    r"""(?P<url>(?:https://(?:
            oceantoday\.noaa\.gov|
            cdn\.oceanservice\.noaa\.gov
        ))?/?
        [A-Za-z0-9_./%+\-]+\.mp4(?:\#[^"'<> \t\r\n]*)?)""",
    re.IGNORECASE | re.VERBOSE,
)
LENGTH_RE = re.compile(
    r"\bLength\s*:\s*([^<\n\r]{1,80})", re.IGNORECASE
)


class ReconError(RuntimeError):
    """Stable metadata-reconciliation failure code."""


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def noaa_redirect_host_allowed(host: str) -> bool:
    return direct_mp4_host_allowed(host)


def ocean_today_host_allowed(host: str) -> bool:
    return host.lower().rstrip(".") == PAGE_HOST


def direct_mp4_host_allowed(host: str) -> bool:
    return host.lower().rstrip(".") in DIRECT_MP4_HOSTS


def _clean_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.username is not None or parsed.password is not None:
        raise ReconError("URL_USERINFO_PROHIBITED")
    host = (parsed.hostname or "").lower().rstrip(".")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path, "", ""))


def validate_official_url(
    url: str,
    *,
    final_ocean_today_required: bool,
    mp4_required: bool = False,
    transient_query_or_fragment_allowed: bool = False,
) -> None:
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError:
        raise ReconError("INVALID_URL_PORT") from None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or (
            (parsed.query or parsed.fragment)
            and not transient_query_or_fragment_allowed
        )
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ReconError("INVALID_OFFICIAL_HTTPS_URL")
    allowed = (
        ocean_today_host_allowed(parsed.hostname)
        if final_ocean_today_required
        else direct_mp4_host_allowed(parsed.hostname)
    )
    if not allowed:
        raise ReconError("NON_OFFICIAL_NOAA_HOST")
    if mp4_required and not parsed.path.lower().endswith(".mp4"):
        raise ReconError("NON_MP4_ROUTE")


def approx_duration_seconds(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ReconError("INVALID_CSV_DURATION_PRIOR")
    hours, minutes, seconds = map(int, parts)
    if minutes >= 60 or seconds >= 60:
        raise ReconError("INVALID_CSV_DURATION_PRIOR")
    return hours * 3600 + minutes * 60 + seconds


@dataclass(frozen=True)
class CandidatePage:
    candidate_id: str
    title: str
    page_url: str
    stable_source_id: str
    metadata_duration_prior_text: str
    metadata_duration_prior_seconds: int

    @classmethod
    def from_row(cls, row: Mapping[str, str]) -> "CandidatePage":
        candidate = cls(
            candidate_id=row["candidate_id"],
            title=row["title"].strip(),
            page_url=row["canonical_landing_url"].strip(),
            stable_source_id=row["stable_source_id"].strip(),
            metadata_duration_prior_text=row["approx_duration"].strip(),
            metadata_duration_prior_seconds=approx_duration_seconds(
                row["approx_duration"]
            ),
        )
        if candidate.candidate_id not in NOAA_CANDIDATE_IDS:
            raise ReconError("CANDIDATE_OUTSIDE_NOAA_SCOPE")
        validate_official_url(
            candidate.page_url, final_ocean_today_required=True
        )
        return candidate


def load_candidate_pages(path: Path = SOURCE_CSV_PATH) -> list[CandidatePage]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = {
            row["candidate_id"]: row
            for row in csv.DictReader(handle)
            if row.get("candidate_id") in NOAA_CANDIDATE_IDS
        }
    if tuple(sorted(rows)) != NOAA_CANDIDATE_IDS:
        raise ReconError("NOAA_CANDIDATE_ROWS_INCOMPLETE")
    candidates = [CandidatePage.from_row(rows[item]) for item in NOAA_CANDIDATE_IDS]
    if len({item.page_url for item in candidates}) != len(candidates):
        raise ReconError("DUPLICATE_NOAA_PAGE_URL")
    return candidates


@dataclass(frozen=True)
class RouteReference:
    url: str
    label: str
    origin: str

    @property
    def small_hint(self) -> int:
        text = f"{self.url} {self.label}".lower()
        if re.search(
            r"(?:^|[_\-.])(smc?|small|low|360p?|480p?)(?:[_\-.]|$)",
            text,
        ) or re.search(r"\b(?:640|720)\s*x\s*360\b", text):
            return 0
        if re.search(
            r"(?:^|[_\-.])(lgc?|large|high|720p?|1080p?)(?:[_\-.]|$)",
            text,
        ) or re.search(r"\b1280\s*x\s*720\b", text):
            return 2
        return 1


@dataclass
class _Element:
    tag: str
    url: str
    label: str
    text: list[str] = field(default_factory=list)


class _RouteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.routes: list[tuple[str, str, str]] = []
        self.title_parts: list[str] = []
        self.visible_parts: list[str] = []
        self._title_depth = 0
        self._script_depth = 0
        self._element: _Element | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        lowered = tag.lower()
        if lowered == "title":
            self._title_depth += 1
        if lowered == "script":
            self._script_depth += 1
        if lowered in {"source", "video"}:
            url = attributes.get("src", "")
            if url:
                label = " ".join(
                    attributes.get(key, "")
                    for key in ("label", "data-res", "title")
                ).strip()
                self.routes.append((url, label, lowered))
        elif lowered == "a" and attributes.get("href"):
            self._element = _Element(
                tag=lowered,
                url=attributes["href"],
                label=attributes.get("download", ""),
            )

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "title" and self._title_depth:
            self._title_depth -= 1
        if lowered == "script" and self._script_depth:
            self._script_depth -= 1
        if lowered == "a" and self._element is not None:
            label = " ".join(
                [self._element.label, *self._element.text]
            ).strip()
            self.routes.append(
                (self._element.url, label, self._element.tag)
            )
            self._element = None

    def handle_data(self, data: str) -> None:
        if self._title_depth:
            self.title_parts.append(data)
        if self._script_depth:
            for match in MP4_RE.finditer(data):
                self.routes.append((match.group("url"), "", "script"))
            return
        self.visible_parts.append(data)
        if self._element is not None:
            self._element.text.append(data)


def extract_page_routes(
    page_url: str, page_body: bytes
) -> tuple[str | None, str | None, list[RouteReference]]:
    if len(page_body) > MAX_PAGE_BYTES:
        raise ReconError("PAGE_BODY_LIMIT_EXCEEDED")
    text = page_body.decode("utf-8", "replace")
    parser = _RouteParser()
    parser.feed(text)
    visible_text = html.unescape(" ".join(parser.visible_parts))
    page_title = " ".join(" ".join(parser.title_parts).split()) or None
    length_match = LENGTH_RE.search(visible_text)
    page_duration_text = (
        " ".join(length_match.group(1).split()) if length_match else None
    )
    by_url: dict[str, RouteReference] = {}
    for raw_url, label, origin in parser.routes:
        if ".mp4" not in raw_url.lower():
            continue
        joined = urljoin(page_url, html.unescape(raw_url))
        parsed = urlsplit(joined)
        clean = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, "", "")
        )
        try:
            validate_official_url(
                clean,
                final_ocean_today_required=False,
                mp4_required=True,
            )
        except ReconError:
            continue
        candidate = RouteReference(
            url=clean,
            label=" ".join(label.split()),
            origin=origin,
        )
        current = by_url.get(clean)
        if current is None or (
            candidate.small_hint,
            -len(candidate.label),
            candidate.origin,
        ) < (
            current.small_hint,
            -len(current.label),
            current.origin,
        ):
            by_url[clean] = candidate
    routes = sorted(
        by_url.values(),
        key=lambda item: (item.small_hint, item.url),
    )
    if len(routes) > MAX_ROUTES_PER_PAGE:
        raise ReconError("TOO_MANY_MP4_ROUTES_ON_PAGE")
    return page_title, page_duration_text, routes


@dataclass(frozen=True)
class RouteHead:
    requested_url: str
    effective_url: str
    content_length: int
    etag: str
    last_modified: str
    content_type: str
    accept_ranges: str
    redirect_chain: tuple[dict[str, Any], ...]


class MetadataOnlyNOAAClient:
    def __init__(
        self,
        *,
        proxy: str | None = None,
        client: Any | None = None,
    ) -> None:
        if httpx is None:
            raise ReconError("HTTPX_NOT_INSTALLED")
        self._owns_client = client is None
        if client is not None:
            self.client = client
        else:
            kwargs: dict[str, Any] = {
                "follow_redirects": False,
                "timeout": httpx.Timeout(60.0, connect=30.0),
                "headers": {
                    "User-Agent": "AV-TRACE-noaa-route-recon/1.0",
                    "Accept-Encoding": "identity",
                },
            }
            if proxy:
                kwargs.update(proxy=proxy, trust_env=False)
            else:
                kwargs["trust_env"] = True
            self.client = httpx.Client(**kwargs)
        self.records: list[dict[str, Any]] = []

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "MetadataOnlyNOAAClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(
        self, method: str, initial_url: str, *, page_body: bool
    ) -> tuple[str, Mapping[str, str], bytes, list[dict[str, Any]]]:
        url = initial_url
        redirects: list[dict[str, Any]] = []
        for _ in range(MAX_REDIRECTS + 1):
            validate_official_url(
                url,
                final_ocean_today_required=page_body,
                mp4_required=not page_body,
                transient_query_or_fragment_allowed=(
                    not page_body and bool(redirects)
                ),
            )
            parsed = urlsplit(url)
            with self.client.stream(
                method, url, headers={"Accept-Encoding": "identity"}
            ) as response:
                if response.status_code in REDIRECT_CODES:
                    location = response.headers.get("location")
                    if not location:
                        raise ReconError("REDIRECT_WITHOUT_LOCATION")
                    next_url = urljoin(url, location)
                    validate_official_url(
                        next_url,
                        final_ocean_today_required=page_body,
                        mp4_required=not page_body,
                        transient_query_or_fragment_allowed=not page_body,
                    )
                    redirects.append(
                        {
                            "status_code": response.status_code,
                            "from_host": (parsed.hostname or "").lower(),
                            "to_host": (
                                urlsplit(next_url).hostname or ""
                            ).lower(),
                            "location": _clean_url(next_url),
                        }
                    )
                    url = next_url
                    continue
                if response.status_code != 200:
                    raise ReconError(f"UNEXPECTED_HTTP_STATUS_{response.status_code}")
                effective = _clean_url(url)
                validate_official_url(
                    effective,
                    final_ocean_today_required=page_body,
                    mp4_required=not page_body,
                )
                if not page_body:
                    record = {
                        "method": method,
                        "requested_url": _clean_url(initial_url),
                        "effective_url": effective,
                        "status_code": response.status_code,
                        "body_bytes": 0,
                        "redirect_chain": redirects,
                    }
                    self.records.append(record)
                    return effective, response.headers, b"", redirects
                raw_length = response.headers.get("content-length")
                if raw_length and raw_length.isdigit():
                    if int(raw_length) > MAX_PAGE_BYTES:
                        raise ReconError("PAGE_CONTENT_LENGTH_EXCEEDS_LIMIT")
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > MAX_PAGE_BYTES:
                        raise ReconError("PAGE_BODY_LIMIT_EXCEEDED")
                    body.extend(chunk)
                self.records.append(
                    {
                        "method": method,
                        "requested_url": _clean_url(initial_url),
                        "effective_url": effective,
                        "status_code": response.status_code,
                        "body_bytes": len(body),
                        "redirect_chain": redirects,
                    }
                )
                return effective, response.headers, bytes(body), redirects
        raise ReconError("TOO_MANY_REDIRECTS")

    def get_page(self, url: str) -> tuple[str, bytes]:
        effective, headers, body, _ = self._request("GET", url, page_body=True)
        content_type = headers.get("content-type", "").lower()
        if "html" not in content_type:
            raise ReconError("PAGE_CONTENT_TYPE_NOT_HTML")
        return effective, body

    def head_mp4(self, url: str) -> RouteHead:
        effective, headers, _, redirects = self._request(
            "HEAD", url, page_body=False
        )
        raw_length = headers.get("content-length")
        if raw_length is None or not raw_length.isdigit():
            raise ReconError("MP4_CONTENT_LENGTH_MISSING_OR_INVALID")
        content_length = int(raw_length)
        if content_length <= 0:
            raise ReconError("MP4_CONTENT_LENGTH_INVALID")
        etag = headers.get("etag", "").strip()
        last_modified = headers.get("last-modified", "").strip()
        content_type = headers.get("content-type", "").strip()
        accept_ranges = headers.get("accept-ranges", "").strip()
        if not etag:
            raise ReconError("MP4_ETAG_MISSING")
        if not last_modified:
            raise ReconError("MP4_LAST_MODIFIED_MISSING")
        if content_type.split(";", 1)[0].strip().lower() != "video/mp4":
            raise ReconError("MP4_CONTENT_TYPE_INVALID")
        if accept_ranges.lower() != "bytes":
            raise ReconError("MP4_BYTE_RANGES_NOT_ADVERTISED")
        return RouteHead(
            requested_url=_clean_url(url),
            effective_url=effective,
            content_length=content_length,
            etag=etag,
            last_modified=last_modified,
            content_type=content_type,
            accept_ranges=accept_ranges,
            redirect_chain=tuple(redirects),
        )


def _object_from_head(
    candidate: CandidatePage,
    page_title: str | None,
    page_duration_text: str | None,
    reference: RouteReference,
    head: RouteHead,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "stable_source_id": candidate.stable_source_id,
        "page_url": candidate.page_url,
        "page_title": candidate.title,
        "observed_html_title": page_title,
        "metadata_duration_prior": {
            "csv_text": candidate.metadata_duration_prior_text,
            "csv_seconds": candidate.metadata_duration_prior_seconds,
            "page_text": page_duration_text,
            "status": "HYPOTHESIS_ONLY_NOT_CONTAINER_DURATION",
        },
        "route_evidence": {
            "origin": reference.origin,
            "label": reference.label,
            "small_rendition_hint": reference.small_hint == 0,
        },
        "url": head.effective_url,
        "size_bytes": head.content_length,
        "etag": head.etag,
        "last_modified": head.last_modified,
        "content_type": head.content_type,
        "accept_ranges": head.accept_ranges,
        "actual_duration_seconds": None,
        "declared_audio_track": None,
        "stream_facts_status": "UNRESOLVED_PENDING_BOUNDED_PREFLIGHT",
        "full_acquisition_authorized": False,
        "processing_authorized": False,
        "annotation_authorized": False,
        "release_authorized": False,
    }


def reconcile(
    candidates: Sequence[CandidatePage],
    client: MetadataOnlyNOAAClient,
) -> dict[str, Any]:
    available: list[dict[str, Any]] = []
    page_results: list[dict[str, Any]] = []
    for candidate in candidates:
        page_result: dict[str, Any] = {
            "candidate_id": candidate.candidate_id,
            "page_url": candidate.page_url,
            "page_title": candidate.title,
            "status": "UNRESOLVED",
            "route_count": 0,
            "error_codes": [],
        }
        try:
            effective_page_url, body = client.get_page(candidate.page_url)
            if effective_page_url != candidate.page_url:
                raise ReconError("PAGE_EFFECTIVE_URL_CHANGED")
            observed_title, page_duration_text, routes = extract_page_routes(
                candidate.page_url, body
            )
            page_result["observed_html_title"] = observed_title
            page_result["metadata_duration_page_text"] = page_duration_text
            page_result["route_count"] = len(routes)
            resolved: list[
                tuple[RouteReference, RouteHead]
            ] = []
            for route in routes:
                try:
                    resolved.append((route, client.head_mp4(route.url)))
                except ReconError as exc:
                    page_result["error_codes"].append(str(exc))
            if not resolved:
                raise ReconError("NO_EXACT_HEAD_VALIDATED_MP4_ROUTE")
            # Prefer the exact smallest object, then an explicit low-resolution
            # hint, then URL for deterministic selection.
            reference, head = min(
                resolved,
                key=lambda item: (
                    item[1].content_length,
                    item[0].small_hint,
                    item[1].effective_url,
                ),
            )
            page_result["status"] = "EXACT_SMALL_RENDITION_RESOLVED"
            page_result["selected_url"] = head.effective_url
            page_result["selected_size_bytes"] = head.content_length
            available.append(
                _object_from_head(
                    candidate,
                    observed_title,
                    page_duration_text,
                    reference,
                    head,
                )
            )
        except ReconError as exc:
            page_result["status"] = "UNRESOLVED_FAIL_CLOSED"
            page_result["error_codes"].append(str(exc))
        page_results.append(page_result)

    available.sort(key=lambda item: (item["size_bytes"], item["candidate_id"]))
    selected = available[:MAX_OBJECTS]
    status = (
        "READY_FOR_BOUNDED_NOAA_STREAM_PREFLIGHT"
        if len(selected) >= MIN_OBJECTS
        else "BLOCKED_INSUFFICIENT_EXACT_NOAA_ROUTES"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "status": status,
        "purpose": (
            "Exact metadata-only NOAA Ocean Today route reconciliation and "
            "bounded ISO-BMFF preflight plan."
        ),
        "source_identity_file": SOURCE_CSV_PATH.as_posix(),
        "scope": {
            "candidate_ids": list(NOAA_CANDIDATE_IDS),
            "official_page_host": PAGE_HOST,
            "minimum_selected_objects": MIN_OBJECTS,
            "maximum_selected_objects": MAX_OBJECTS,
            "selected_object_count": len(selected),
            "wildcards_allowed": False,
        },
        "route_discovery_policy": {
            "page_get_body_limit_bytes": MAX_PAGE_BYTES,
            "mp4_methods_allowed": ["HEAD"],
            "mp4_body_requests_performed": 0,
            "official_ocean_today_final_host_required": False,
            "official_ocean_today_landing_host_required": True,
            "official_mp4_final_hosts": sorted(DIRECT_MP4_HOSTS),
            "noaa_only_redirects": True,
            "exact_redirect_hosts_only": True,
            "prefer_small_low_resolution_rendition": True,
        },
        "transfer_policy": {
            "per_request_body_bytes": 8 * 1024 * 1024,
            "per_candidate_body_bytes": 12 * 1024 * 1024,
            "aggregate_body_bytes": 96 * 1024 * 1024,
            "maximum_object_count": MAX_OBJECTS,
            "head_and_bounded_range_get_only": True,
            "complete_object_range_prohibited": True,
            "full_object_get_prohibited": True,
            "media_byte_persistence_prohibited": True,
        },
        "authorization": {
            "authorized_action": (
                "BOUNDED_ISO_BMFF_PREFLIGHT_FOR_SELECTED_EXACT_URLS_ONLY"
            ),
            "authorized_for_bounded_stream_preflight": [
                item["candidate_id"] for item in selected
            ],
            "authorized_for_full_acquisition": [],
            "authorized_for_processing": [],
            "authorized_for_annotation": [],
            "authorized_for_release": [],
        },
        "page_results": page_results,
        "available_exact_objects": available,
        "objects": selected,
        "limitations": [
            "Page duration is retained only as a prior/hypothesis.",
            "Actual duration and declared audio remain unresolved until bounded ISO-BMFF preflight.",
            "HEAD metadata does not authorize acquisition, processing, annotation, redistribution, or release.",
        ],
    }


def validate_plan(plan: Mapping[str, Any]) -> None:
    objects = plan.get("objects")
    available = plan.get("available_exact_objects")
    if not isinstance(objects, list):
        raise ReconError("PLAN_OBJECTS_NOT_LIST")
    if not isinstance(available, list):
        raise ReconError("PLAN_AVAILABLE_OBJECTS_NOT_LIST")
    status = plan.get("status")
    if status == "READY_FOR_BOUNDED_NOAA_STREAM_PREFLIGHT":
        if not MIN_OBJECTS <= len(objects) <= MAX_OBJECTS:
            raise ReconError("READY_PLAN_OBJECT_COUNT_INVALID")
    elif status == "BLOCKED_INSUFFICIENT_EXACT_NOAA_ROUTES":
        if len(objects) >= MIN_OBJECTS:
            raise ReconError("BLOCKED_PLAN_HAS_SUFFICIENT_OBJECTS")
    else:
        raise ReconError("PLAN_STATUS_INVALID")
    if len({item.get("candidate_id") for item in objects}) != len(objects):
        raise ReconError("DUPLICATE_PLAN_CANDIDATE")
    if len({item.get("url") for item in objects}) != len(objects):
        raise ReconError("DUPLICATE_PLAN_URL")
    source_by_id = {
        item.candidate_id: item for item in load_candidate_pages(SOURCE_CSV_PATH)
    }
    for item in [*available, *objects]:
        candidate_id = item.get("candidate_id")
        source = source_by_id.get(candidate_id)
        if source is None:
            raise ReconError("PLAN_CANDIDATE_OUTSIDE_NOAA_SCOPE")
        if (
            item.get("page_url") != source.page_url
            or item.get("page_title") != source.title
            or item.get("stable_source_id") != source.stable_source_id
        ):
            raise ReconError("PLAN_SOURCE_IDENTITY_MISMATCH")
        prior = item.get("metadata_duration_prior")
        if not isinstance(prior, Mapping) or (
            prior.get("csv_text") != source.metadata_duration_prior_text
            or prior.get("csv_seconds")
            != source.metadata_duration_prior_seconds
            or prior.get("status")
            != "HYPOTHESIS_ONLY_NOT_CONTAINER_DURATION"
        ):
            raise ReconError("PLAN_DURATION_PRIOR_INVALID")
        validate_official_url(
            str(item.get("page_url", "")),
            final_ocean_today_required=True,
        )
        validate_official_url(
            str(item.get("url", "")),
            final_ocean_today_required=False,
            mp4_required=True,
        )
        if not isinstance(item.get("size_bytes"), int) or item["size_bytes"] <= 0:
            raise ReconError("PLAN_SIZE_INVALID")
        for key in ("etag", "last_modified", "content_type", "accept_ranges"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise ReconError(f"PLAN_{key.upper()}_MISSING")
        if item.get("actual_duration_seconds") is not None:
            raise ReconError("PLAN_CONFLATES_PAGE_AND_CONTAINER_DURATION")
        if item.get("declared_audio_track") is not None:
            raise ReconError("PLAN_CONFLATES_PAGE_AND_AUDIO_TRACK")
        if any(
            item.get(key) is not False
            for key in (
                "full_acquisition_authorized",
                "processing_authorized",
                "annotation_authorized",
                "release_authorized",
            )
        ):
            raise ReconError("PLAN_AUTHORITY_TOO_BROAD")
    expected_objects = sorted(
        available, key=lambda item: (item["size_bytes"], item["candidate_id"])
    )[:MAX_OBJECTS]
    if objects != expected_objects:
        raise ReconError("PLAN_SMALL_RENDITION_SELECTION_MISMATCH")
    authorization = plan.get("authorization")
    expected_authorization = {
        "authorized_action": (
            "BOUNDED_ISO_BMFF_PREFLIGHT_FOR_SELECTED_EXACT_URLS_ONLY"
        ),
        "authorized_for_bounded_stream_preflight": [
            item["candidate_id"] for item in objects
        ],
        "authorized_for_full_acquisition": [],
        "authorized_for_processing": [],
        "authorized_for_annotation": [],
        "authorized_for_release": [],
    }
    if authorization != expected_authorization:
        raise ReconError("PLAN_AUTHORIZATION_NOT_EXACT")
    raw = json.dumps(plan)
    if "*" in raw:
        raise ReconError("PLAN_WILDCARD_PROHIBITED")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-csv", type=Path, default=SOURCE_CSV_PATH)
    parser.add_argument("--output", type=Path, default=PLAN_PATH)
    parser.add_argument("--proxy")
    parser.add_argument("--validate-plan", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.validate_plan is not None:
            plan = json.loads(args.validate_plan.read_text(encoding="utf-8"))
            validate_plan(plan)
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "plan_status": plan["status"],
                        "object_count": len(plan["objects"]),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        candidates = load_candidate_pages(args.source_csv)
        with MetadataOnlyNOAAClient(proxy=args.proxy) as client:
            plan = reconcile(candidates, client)
        validate_plan(plan)
        atomic_write_json(args.output, plan)
        print(
            json.dumps(
                {
                    "status": plan["status"],
                    "output": args.output.as_posix(),
                    "selected_object_count": len(plan["objects"]),
                    "request_count": len(client.records),
                    "mp4_body_requests": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if plan["status"].startswith("READY") else 3
    except (
        ReconError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        code = str(exc) if isinstance(exc, ReconError) else type(exc).__name__
        print(f"ERROR: {code}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
