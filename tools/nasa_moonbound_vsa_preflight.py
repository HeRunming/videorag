#!/usr/bin/env python3
"""Bounded metadata, rights, and exact-asset preflight for NASA+ Moonbound.

The default plan-only mode reads the frozen route and previously captured
first-party evidence already present in this repository.  Live mode refreshes
only small HTML/JSON/HLS metadata objects and performs HEAD plus bounded Range
probes against three exact MPEG-TS segments.  Media response bodies are parsed
in memory and are never persisted.

This tool does not make semantic, modality-necessity, or human-review claims.
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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "av-trace.nasa-moonbound-vsa-preflight/1.0"
ROUTE_ID = "ARVSA-R01-NASA-MOONBOUND"
SOURCE_GROUP_ID = "EC-NASA-MOONBOUND"
POST_ID = 6979
CONTENT_ID = "15230"
ASSET_ID = "17905"
TITLE = "Moonbound | For All Humanity"

ITEM_URL = "https://plus.nasa.gov/video/moonbound-for-all-humanity/"
API_URL = "https://plus.nasa.gov/wp-json/wp/v2/video/6979"
MASTER_URL = "https://nasaplus.akamaized.net/output/17905.m3u8"
POLICY_URL = "https://www.nasa.gov/nasa-brand-center/images-and-media/"
SELECTED_VARIANT_URI = "17905-2.m3u8"

ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = (
    ROOT / "data/rehearsal_plan/audio_rich_vsa_acquisition_routes_v1.json"
)
SNAPSHOT_ROOT = (
    ROOT
    / "data/source_recon/event_centric_live_preflight_v1/"
    "EC-NASA-MOONBOUND"
)
POLICY_SNAPSHOT = (
    ROOT
    / "data/source_recon/event_centric_live_preflight_v1/"
    "policies/nasa_images_media.body"
)
DEFAULT_OUTPUT = (
    ROOT / "data/rehearsal_plan/nasa_moonbound_vsa_preflight_v1.json"
)

DEFAULT_PROXIES = (
    "https://proxy.example.invalid:3128",
    "https://proxy.example.invalid:3128",
)
ALLOWED_HOSTS = {
    "plus.nasa.gov",
    "www.nasa.gov",
    "nasa.gov",
    "nasaplus.akamaized.net",
}
MAX_METADATA_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_MEDIA_RANGE_BYTES = 64 * 1024
MAX_MEDIA_PROBES = 3
MAX_TOTAL_RESPONSE_BYTES = 7 * 1024 * 1024

READY = "NASA_MOONBOUND_VSA_PREFLIGHT_READY"
REPAIR = "NASA_MOONBOUND_VSA_PREFLIGHT_REPAIR"
NO_GO = "NASA_MOONBOUND_VSA_PREFLIGHT_NO_GO"


class PreflightError(RuntimeError):
    """Stable, credential-free preflight failure."""


@dataclass(frozen=True)
class Snapshot:
    name: str
    path: Path
    content_type: str

    def read(self) -> bytes:
        data = self.path.read_bytes()
        if len(data) > MAX_METADATA_RESPONSE_BYTES:
            raise PreflightError(f"LOCAL_SNAPSHOT_TOO_LARGE:{self.name}")
        return data

    def record(self, data: bytes) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path.relative_to(ROOT)),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "content_type": self.content_type,
        }


SNAPSHOTS = (
    Snapshot("item", SNAPSHOT_ROOT / "item.body", "text/html; charset=UTF-8"),
    Snapshot(
        "api",
        SNAPSHOT_ROOT / "api.body",
        "application/json; charset=UTF-8",
    ),
    Snapshot(
        "master",
        SNAPSHOT_ROOT / "master.body",
        "application/x-mpegURL",
    ),
    Snapshot(
        "variant",
        SNAPSHOT_ROOT / "variant_2.body",
        "application/x-mpegURL",
    ),
    Snapshot(
        "rights_policy",
        POLICY_SNAPSHOT,
        "text/html; charset=UTF-8",
    ),
)


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PreflightError(f"JSON_NOT_OBJECT:{path.relative_to(ROOT)}")
    return value


def find_route(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        if value.get("route_id") == ROUTE_ID:
            return value
        for child in value.values():
            try:
                return find_route(child)
            except PreflightError:
                pass
    elif isinstance(value, list):
        for child in value:
            try:
                return find_route(child)
            except PreflightError:
                pass
    raise PreflightError("FROZEN_ROUTE_NOT_FOUND")


def parse_api(data: bytes) -> dict[str, Any]:
    value = json.loads(data)
    if not isinstance(value, dict):
        raise PreflightError("API_NOT_OBJECT")
    meta = value.get("meta")
    if not isinstance(meta, Mapping):
        raise PreflightError("API_META_MISSING")
    expected = {
        "id": POST_ID,
        "slug": "moonbound-for-all-humanity",
        "status": "publish",
        "type": "video",
        "link": ITEM_URL,
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            raise PreflightError(f"API_IDENTITY_MISMATCH:{key}")
    if value.get("title", {}).get("rendered") != TITLE:
        raise PreflightError("API_TITLE_MISMATCH")
    if meta.get("content-id") != CONTENT_ID:
        raise PreflightError("API_CONTENT_ID_MISMATCH")
    if meta.get("video-url") != MASTER_URL:
        raise PreflightError("API_MASTER_URL_MISMATCH")
    if not str(meta.get("runtime", "")).isdigit():
        raise PreflightError("API_RUNTIME_INVALID")
    return value


def parse_master(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    variants: list[dict[str, Any]] = []
    captions: list[dict[str, str]] = []
    for index, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF:"):
            if index + 1 >= len(lines) or lines[index + 1].startswith("#"):
                raise PreflightError("MASTER_VARIANT_URI_MISSING")
            attrs = line.split(":", 1)[1]
            variants.append(
                {
                    "uri": lines[index + 1],
                    "resolution": _attribute(attrs, "RESOLUTION"),
                    "codecs": _attribute(attrs, "CODECS"),
                    "bandwidth": _integer_attribute(attrs, "BANDWIDTH"),
                    "average_bandwidth": _integer_attribute(
                        attrs, "AVERAGE-BANDWIDTH"
                    ),
                    "audio_only": _attribute(attrs, "RESOLUTION") is None,
                }
            )
        elif line.startswith("#EXT-X-MEDIA:TYPE=CLOSED-CAPTIONS"):
            attrs = line.split(":", 1)[1]
            captions.append(
                {
                    "language": _attribute(attrs, "LANGUAGE") or "",
                    "name": _attribute(attrs, "NAME") or "",
                    "instream_id": _attribute(attrs, "INSTREAM-ID") or "",
                }
            )
    if not variants:
        raise PreflightError("MASTER_HAS_NO_VARIANTS")
    if not any(item["uri"] == SELECTED_VARIANT_URI for item in variants):
        raise PreflightError("SELECTED_VARIANT_MISSING")
    return {"variants": variants, "closed_captions": captions}


def _attribute(text: str, name: str) -> str | None:
    match = re.search(
        rf"(?:^|,){re.escape(name)}=(?:\"([^\"]*)\"|([^,]*))", text
    )
    if match is None:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def _integer_attribute(text: str, name: str) -> int | None:
    value = _attribute(text, name)
    return int(value) if value and value.isdigit() else None


def parse_media_playlist(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    durations: list[float] = []
    segments: list[str] = []
    pending_duration = False
    for line in lines:
        if line.startswith("#EXTINF:"):
            durations.append(float(line.split(":", 1)[1].rstrip(",")))
            pending_duration = True
        elif pending_duration and not line.startswith("#"):
            segments.append(line)
            pending_duration = False
    if not durations or len(durations) != len(segments):
        raise PreflightError("MEDIA_PLAYLIST_INVALID")
    return {
        "duration_seconds": sum(durations),
        "segment_count": len(segments),
        "segments": segments,
        "vod": "#EXT-X-PLAYLIST-TYPE:VOD" in lines,
        "endlist": "#EXT-X-ENDLIST" in lines,
    }


def html_text(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))


def validate_policy(data: bytes) -> dict[str, Any]:
    text = html_text(data)
    required = (
        "generally are not subject to copyright in the United States",
        "educational or informational purposes",
        "NASA occasionally uses copyright-protected material of third parties",
        "use does not convey any rights to others",
        "Artificial Intelligence (AI) Applications",
        "No Permission Implied",
    )
    missing = [phrase for phrase in required if phrase not in text]
    if missing:
        raise PreflightError("RIGHTS_POLICY_TEXT_MISSING")
    return {
        "policy_url": POLICY_URL,
        "general_nasa_content_authority": (
            "Educational or informational use is generally allowed, subject "
            "to the NASA media guidelines, attribution/source controls, "
            "no-endorsement restrictions, identifiers, and identifiable-"
            "person constraints."
        ),
        "ai_application_notice": (
            "The saved policy addresses AI applications but expressly says "
            "source disclosure implies no NASA permission for a specific use."
        ),
        "third_party_boundary": (
            "NASA says that its use of third-party copyrighted material does "
            "not convey downstream rights; exact component ownership must be "
            "resolved separately."
        ),
        "exact_item_component_ledger": "NOT_PRESENT",
    }


def validate_item(data: bytes) -> dict[str, Any]:
    text = data.decode("utf-8", errors="replace")
    required = (
        f"<title>{TITLE} | NASA+</title>",
        f'data-video-url="{MASTER_URL}"',
        f'href="{MASTER_URL}"',
        'title="Download"',
    )
    if any(value not in text for value in required):
        raise PreflightError("ITEM_IDENTITY_OR_DOWNLOAD_ROUTE_MISMATCH")
    return {
        "official_download_control": True,
        "download_target": MASTER_URL,
        "download_authority_interpretation": (
            "The first-party item exposes the exact HLS master through a "
            "Download control. This establishes an official transfer route, "
            "not a component-level copyright or downstream-use clearance."
        ),
    }


def validate_local_inputs() -> dict[str, Any]:
    route = find_route(load_json(ROUTE_PATH))
    exact = route.get("exact_ids_or_pool")
    if not isinstance(exact, Mapping):
        raise PreflightError("ROUTE_EXACT_IDS_MISSING")
    if exact.get("source_group_id") != SOURCE_GROUP_ID:
        raise PreflightError("ROUTE_SOURCE_GROUP_MISMATCH")
    if exact.get("stable_item_id") != (
        "NASA+ post 6979 / content-id 15230 / HLS asset 17905"
    ):
        raise PreflightError("ROUTE_STABLE_ID_MISMATCH")
    if route.get("current_disposition") != "REPAIR":
        raise PreflightError("ROUTE_DISPOSITION_MISMATCH")

    bodies = {snapshot.name: snapshot.read() for snapshot in SNAPSHOTS}
    api = parse_api(bodies["api"])
    master = parse_master(bodies["master"].decode())
    playlist = parse_media_playlist(bodies["variant"].decode())
    item = validate_item(bodies["item"])
    rights = validate_policy(bodies["rights_policy"])
    records = [
        snapshot.record(bodies[snapshot.name]) for snapshot in SNAPSHOTS
    ]
    return {
        "route": route,
        "bodies": bodies,
        "api": api,
        "master": master,
        "playlist": playlist,
        "item": item,
        "rights": rights,
        "snapshot_records": records,
    }


def candidate_segments(segments: Sequence[str]) -> list[dict[str, Any]]:
    if not segments:
        return []
    indices = sorted({0, len(segments) // 2, len(segments) - 1})
    labels = {0: "opening", len(segments) // 2: "middle", len(segments) - 1: "ending"}
    base = urllib.parse.urljoin(MASTER_URL, SELECTED_VARIANT_URI)
    return [
        {
            "position": labels[index],
            "segment_index": index,
            "segment_uri": segments[index],
            "exact_url": urllib.parse.urljoin(base, segments[index]),
        }
        for index in indices
    ]


class BoundedClient:
    """Small allowlisted HTTP client with proxy failover and byte accounting."""

    def __init__(self, proxies: Sequence[str]) -> None:
        self.proxies = tuple(proxies) or DEFAULT_PROXIES
        self.total_bytes = 0
        self.requests: list[dict[str, Any]] = []

    def request(
        self,
        url: str,
        *,
        method: str = "GET",
        range_bytes: int | None = None,
        maximum_bytes: int = MAX_METADATA_RESPONSE_BYTES,
    ) -> tuple[bytes, dict[str, Any]]:
        host = urllib.parse.urlsplit(url).hostname
        if host not in ALLOWED_HOSTS:
            raise PreflightError("REQUEST_HOST_NOT_ALLOWED")
        if method not in {"GET", "HEAD"}:
            raise PreflightError("REQUEST_METHOD_NOT_ALLOWED")
        headers = {"User-Agent": "AV-TRACE-NASA-Moonbound-Preflight/1.0"}
        if range_bytes is not None:
            if not 1 <= range_bytes <= MAX_MEDIA_RANGE_BYTES:
                raise PreflightError("RANGE_LIMIT_INVALID")
            headers["Range"] = f"bytes=0-{range_bytes - 1}"
            maximum_bytes = range_bytes
        attempts: list[dict[str, Any]] = []
        for proxy in self.proxies:
            proxy_host = urllib.parse.urlsplit(proxy).hostname or "unknown"
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler(
                    {"http": proxy, "https": proxy}
                )
            )
            request = urllib.request.Request(
                url, headers=headers, method=method
            )
            try:
                with opener.open(request, timeout=45) as response:
                    effective = response.geturl()
                    effective_host = urllib.parse.urlsplit(effective).hostname
                    if effective_host not in ALLOWED_HOSTS:
                        raise PreflightError("REDIRECT_HOST_NOT_ALLOWED")
                    body = (
                        b""
                        if method == "HEAD"
                        else response.read(maximum_bytes + 1)
                    )
                    if len(body) > maximum_bytes:
                        raise PreflightError("RESPONSE_BODY_LIMIT_EXCEEDED")
                    self.total_bytes += len(body)
                    if self.total_bytes > MAX_TOTAL_RESPONSE_BYTES:
                        raise PreflightError("AGGREGATE_BODY_LIMIT_EXCEEDED")
                    record = {
                        "url": url,
                        "effective_url": effective,
                        "method": method,
                        "range": headers.get("Range"),
                        "proxy_route": proxy_host,
                        "status": response.status,
                        "content_type": response.headers.get("Content-Type"),
                        "content_length": _header_int(
                            response.headers.get("Content-Length")
                        ),
                        "content_range": response.headers.get(
                            "Content-Range"
                        ),
                        "accept_ranges": response.headers.get(
                            "Accept-Ranges"
                        ),
                        "body_bytes": len(body),
                    }
                    self.requests.append(record)
                    return body, record
            except PreflightError:
                raise
            except (OSError, urllib.error.URLError) as exc:
                attempts.append(
                    {
                        "proxy_route": proxy_host,
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                    }
                )
        self.requests.extend(attempts)
        raise PreflightError("ALL_PROXY_ROUTES_FAILED")


def _header_int(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() else None


def parse_ts_stream_types(data: bytes) -> dict[str, Any]:
    """Return advertised MPEG-TS elementary stream types from PAT/PMT tables."""
    if not data:
        return {
            "packet_alignment": False,
            "stream_types": [],
            "video_stream_advertised": False,
            "audio_stream_advertised": False,
        }
    offset = data.find(b"\x47")
    while offset >= 0 and offset + 376 < len(data):
        if data[offset + 188] == 0x47 and data[offset + 376] == 0x47:
            break
        offset = data.find(b"\x47", offset + 1)
    if offset < 0:
        return {
            "packet_alignment": False,
            "stream_types": [],
            "video_stream_advertised": False,
            "audio_stream_advertised": False,
        }

    pmt_pids: set[int] = set()
    stream_types: set[int] = set()
    for start in range(offset, len(data) - 187, 188):
        packet = data[start : start + 188]
        if packet[0] != 0x47:
            break
        payload_start = bool(packet[1] & 0x40)
        pid = ((packet[1] & 0x1F) << 8) | packet[2]
        adaptation = (packet[3] >> 4) & 0x03
        cursor = 4
        if adaptation in {2, 3}:
            cursor += 1 + packet[4]
        if adaptation not in {1, 3} or cursor >= 188:
            continue
        if payload_start:
            cursor += 1 + packet[cursor]
        if cursor + 3 >= 188:
            continue
        if pid == 0 and packet[cursor] == 0x00:
            section_length = ((packet[cursor + 1] & 0x0F) << 8) | packet[cursor + 2]
            end = min(cursor + 3 + section_length - 4, 188)
            entry = cursor + 8
            while entry + 3 < end:
                program = (packet[entry] << 8) | packet[entry + 1]
                if program:
                    pmt_pids.add(
                        ((packet[entry + 2] & 0x1F) << 8)
                        | packet[entry + 3]
                    )
                entry += 4
        elif pid in pmt_pids and packet[cursor] == 0x02:
            section_length = ((packet[cursor + 1] & 0x0F) << 8) | packet[cursor + 2]
            end = min(cursor + 3 + section_length - 4, 188)
            program_info_length = (
                ((packet[cursor + 10] & 0x0F) << 8) | packet[cursor + 11]
            )
            entry = cursor + 12 + program_info_length
            while entry + 4 < end:
                stream_type = packet[entry]
                stream_types.add(stream_type)
                es_info_length = (
                    ((packet[entry + 3] & 0x0F) << 8)
                    | packet[entry + 4]
                )
                entry += 5 + es_info_length
    video_types = {0x01, 0x02, 0x10, 0x1B, 0x24, 0x42}
    audio_types = {0x03, 0x04, 0x0F, 0x11, 0x81, 0x87}
    return {
        "packet_alignment": True,
        "stream_types": [f"0x{value:02x}" for value in sorted(stream_types)],
        "video_stream_advertised": bool(stream_types & video_types),
        "audio_stream_advertised": bool(stream_types & audio_types),
    }


def run_live(
    local: Mapping[str, Any], proxies: Sequence[str]
) -> dict[str, Any]:
    client = BoundedClient(proxies)
    item_data, item_request = client.request(ITEM_URL)
    api_data, api_request = client.request(API_URL)
    master_data, master_request = client.request(MASTER_URL)
    policy_data, policy_request = client.request(POLICY_URL)

    validate_item(item_data)
    api = parse_api(api_data)
    master = parse_master(master_data.decode())
    validate_policy(policy_data)
    variant_url = urllib.parse.urljoin(MASTER_URL, SELECTED_VARIANT_URI)
    variant_data, variant_request = client.request(variant_url)
    playlist = parse_media_playlist(variant_data.decode())

    probes: list[dict[str, Any]] = []
    for candidate in candidate_segments(playlist["segments"])[
        :MAX_MEDIA_PROBES
    ]:
        _, head = client.request(candidate["exact_url"], method="HEAD")
        body, ranged = client.request(
            candidate["exact_url"],
            range_bytes=MAX_MEDIA_RANGE_BYTES,
            maximum_bytes=MAX_MEDIA_RANGE_BYTES,
        )
        probes.append(
            {
                **candidate,
                "head": head,
                "range": ranged,
                "transport_stream_evidence": parse_ts_stream_types(body),
            }
        )
    return {
        "status": "SUCCEEDED",
        "api": api,
        "master": master,
        "playlist": playlist,
        "metadata_requests": [
            item_request,
            api_request,
            master_request,
            policy_request,
            variant_request,
        ],
        "segment_probes": probes,
        "all_requests": client.requests,
        "response_body_bytes_read": client.total_bytes,
        "media_body_bytes_persisted": 0,
        "local_prior_playlist_duration_seconds": local["playlist"][
            "duration_seconds"
        ],
    }


def classify(
    *,
    component_rights_exact: bool,
    exact_asset_evidenced: bool,
    audio_evidenced: bool,
    duration_resolved: bool,
    terminal_failure: bool = False,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if not component_rights_exact:
        blockers.append(
            "Exact item/component rights for score, archive/partner footage, "
            "marks, and identifiable people are not evidenced."
        )
    if not exact_asset_evidenced:
        blockers.append("No exact first-party media asset is evidenced.")
    if not audio_evidenced:
        blockers.append(
            "Native synchronized audio is advertised but not evidenced by a "
            "bounded media payload or decoded timestamps."
        )
    if not duration_resolved:
        blockers.append(
            "Duration is unresolved: API runtime and HLS media timeline do "
            "not agree."
        )
    if not blockers:
        return READY, []
    if terminal_failure or not exact_asset_evidenced:
        return NO_GO, blockers
    return REPAIR, blockers


def build_report(
    *,
    mode: str,
    local: Mapping[str, Any],
    live: Mapping[str, Any] | None = None,
    live_error: str | None = None,
) -> dict[str, Any]:
    api = live["api"] if live else local["api"]
    master = live["master"] if live else local["master"]
    playlist = live["playlist"] if live else local["playlist"]
    api_duration = float(api["meta"]["runtime"])
    playlist_duration = float(playlist["duration_seconds"])
    duration_delta = api_duration - playlist_duration
    duration_resolved = abs(duration_delta) <= 2.0

    segment_probes = list(live.get("segment_probes", [])) if live else []
    audio_evidenced = bool(segment_probes) and all(
        item["transport_stream_evidence"]["audio_stream_advertised"]
        and item["transport_stream_evidence"]["video_stream_advertised"]
        for item in segment_probes
    )
    component_rights_exact = False
    exact_asset_evidenced = True
    marker, blockers = classify(
        component_rights_exact=component_rights_exact,
        exact_asset_evidenced=exact_asset_evidenced,
        audio_evidenced=audio_evidenced,
        duration_resolved=duration_resolved,
    )
    if live_error:
        blockers.append(
            "Live refresh did not complete; the report retains saved "
            f"first-party evidence only ({live_error})."
        )

    variants = master["variants"]
    resolutions = sorted(
        {
            item["resolution"]
            for item in variants
            if item["resolution"] is not None
        }
    )
    codecs = sorted(
        {item["codecs"] for item in variants if item["codecs"] is not None}
    )
    related = api.get("related_videos") or []
    related_record = next(
        (
            item
            for item in related
            if item.get("ID") == 6925
            and item.get("post_name") == "moonbound-charting-the-course"
        ),
        None,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "audit_date": "2026-10-12",
        "mode": mode,
        "route_id": ROUTE_ID,
        "source_group_id": SOURCE_GROUP_ID,
        "final_marker": marker,
        "decision": marker.removeprefix("NASA_MOONBOUND_VSA_PREFLIGHT_"),
        "decision_rule": (
            "READY requires exact component rights, exact asset identity, "
            "native synchronized audio evidence, and resolved duration. No "
            "semantic or modality-necessity gate is evaluated here."
        ),
        "blockers": blockers,
        "scope": {
            "metadata_rights_exact_asset_preflight_only": True,
            "full_media_downloads": 0,
            "maximum_media_range_bytes_per_request": MAX_MEDIA_RANGE_BYTES,
            "maximum_media_probe_count": MAX_MEDIA_PROBES,
            "media_bytes_persisted": (
                live.get("media_body_bytes_persisted", 0) if live else 0
            ),
            "human_review_performed": False,
            "semantic_claims_made": False,
            "v_plus_s_plus_a_necessity_claimed": False,
        },
        "authoritative_identity": {
            "title": TITLE,
            "publisher": "NASA+ / National Aeronautics and Space Administration",
            "item_url": ITEM_URL,
            "api_url": API_URL,
            "post_id": POST_ID,
            "content_id": CONTENT_ID,
            "hls_asset_id": ASSET_ID,
            "hls_master_url": MASTER_URL,
            "api_status": api.get("status"),
            "api_type": api.get("type"),
            "api_modified_gmt": api.get("modified_gmt"),
            "episode_number": api["meta"].get("episode-num"),
            "language": api["meta"].get("language"),
            "identity_status": "ESTABLISHED_FIRST_PARTY",
        },
        "rights_and_download_authority": {
            **local["rights"],
            **local["item"],
            "operative_exact_item_license": "NOT_STATED",
            "component_level_download_authority": "UNRESOLVED",
            "acquisition": "HOLD",
            "internal_processing": "HOLD",
            "restricted_annotation": "HOLD",
            "raw_or_derived_media_release": "NOT_AUTHORIZED",
            "reason": (
                "The official download route and general NASA policy do not "
                "identify or clear every documentary component."
            ),
        },
        "exact_media": {
            "master": {
                "url": MASTER_URL,
                "asset_id": ASSET_ID,
                "variant_count": len(variants),
                "resolutions": resolutions,
                "codecs": codecs,
                "audio_only_variant_advertised": any(
                    item["audio_only"] for item in variants
                ),
            },
            "selected_media_playlist": {
                "url": urllib.parse.urljoin(
                    MASTER_URL, SELECTED_VARIANT_URI
                ),
                "uri": SELECTED_VARIANT_URI,
                "segment_count": playlist["segment_count"],
                "vod": playlist["vod"],
                "endlist": playlist["endlist"],
                "candidate_segment_probes": candidate_segments(
                    playlist["segments"]
                ),
            },
            "head_and_range": {
                "status": (
                    "BOUNDED_PROBES_COMPLETED"
                    if segment_probes
                    else "NOT_EVIDENCED_IN_SAVED_RUN"
                ),
                "probes": segment_probes,
            },
        },
        "duration_and_resolution": {
            "api_runtime_seconds": api_duration,
            "selected_playlist_duration_seconds": playlist_duration,
            "difference_seconds": duration_delta,
            "relation": (
                "RESOLVED"
                if duration_resolved
                else "MISMATCH_REPAIR_REQUIRED"
            ),
            "advertised_resolutions": resolutions,
            "maximum_advertised_resolution": (
                "1920x1080" if "1920x1080" in resolutions else None
            ),
        },
        "native_audio": {
            "master_muxed_audio_video_codecs_advertised": any(
                item["resolution"] is not None
                and item["codecs"]
                and "mp4a" in item["codecs"]
                for item in variants
            ),
            "audio_only_variant_advertised": any(
                item["audio_only"] for item in variants
            ),
            "bounded_media_payload_evidence": audio_evidenced,
            "synchronization_status": (
                "MPEG_TS_VIDEO_AND_AUDIO_STREAM_TYPES_ADVERTISED_IN_ALL_PROBES"
                if audio_evidenced
                else "PLAUSIBLE_FROM_MASTER_ONLY_NOT_PROVEN"
            ),
            "decoded_timestamps_or_samples": False,
        },
        "captions_and_transcript": {
            "in_stream_closed_captions_advertised": bool(
                master["closed_captions"]
            ),
            "closed_caption_services": master["closed_captions"],
            "standalone_caption_asset_url": None,
            "transcript_url": None,
            "availability_status": (
                "IN_STREAM_SERVICES_ADVERTISED; PAYLOAD AND TRANSCRIPT "
                "NOT_VERIFIED"
            ),
        },
        "production_lineage": {
            "primary_lineage": (
                "NASA+ Moonbound series, episode 2, published by NASA+ "
                "Streaming Service"
            ),
            "lineage_block": (
                "The episode, all HLS renditions, captions, clips, archive or "
                "partner inserts, score, and derivatives remain one source "
                "group."
            ),
            "credits_or_component_ledger_present": False,
            "unresolved_components": [
                "music or score",
                "archive footage",
                "partner or contractor footage",
                "NASA identifiers and other marks",
                "identifiable people and voices",
            ],
        },
        "routing_only_plausibility": {
            "speech": (
                "HIGH_METADATA_PLAUSIBILITY: a documentary following four "
                "astronauts and teamwork is likely to contain speech; not "
                "verified from media."
            ),
            "source_world_ambient": (
                "MEDIUM_METADATA_PLAUSIBILITY: physical training and testing "
                "new systems may contain equipment, facility, or training "
                "sounds; not verified from media."
            ),
            "semantic_credit": False,
            "candidate_event_rich_leads": [
                {
                    "lead_id": "moonbound-training-challenges",
                    "asset_id": ASSET_ID,
                    "basis": (
                        "The official item description names physical and "
                        "mental challenges while preparing for crewed flight."
                    ),
                    "temporal_region": "UNLOCALIZED_NO_TIMESTAMP_METADATA",
                    "status": "ROUTING_LEAD_ONLY",
                },
                {
                    "lead_id": "moonbound-system-tests-teamwork",
                    "asset_id": ASSET_ID,
                    "basis": (
                        "The official item description names teamwork and "
                        "testing new systems at the edge of exploration."
                    ),
                    "temporal_region": "UNLOCALIZED_NO_TIMESTAMP_METADATA",
                    "status": "ROUTING_LEAD_ONLY",
                },
            ],
            "related_asset_candidate": (
                {
                    "title": related_record.get("post_title"),
                    "post_id": related_record.get("ID"),
                    "content_id": related_record.get("meta", {}).get(
                        "content-id"
                    ),
                    "hls_url": related_record.get("meta", {}).get(
                        "video-url"
                    ),
                    "runtime_seconds": float(
                        related_record.get("meta", {}).get("runtime")
                    ),
                    "role": (
                        "SECOND_SAME_SERIES_ROUTING_ASSET; NOT A SUBSTITUTE "
                        "FOR THE FROZEN ROUTE"
                    ),
                }
                if related_record
                else None
            ),
        },
        "saved_evidence": local["snapshot_records"],
        "live_run": (
            live
            if live
            else {
                "status": "NOT_RUN",
                "reason": live_error or "PLAN_ONLY",
                "network_requests": 0,
                "response_body_bytes_read": 0,
                "media_body_bytes_persisted": 0,
            }
        ),
        "next_repairs": [
            (
                "Obtain an item/component ledger or rightsholder confirmation "
                "covering score, archive/partner footage, marks, and people."
            ),
            (
                "Identify the rendition corresponding to the 2,202-second "
                "official runtime, or correct the authoritative runtime."
            ),
            (
                "Run this tool in live mode to record HEAD and bounded Range "
                "behavior and MPEG-TS audio/video stream-type evidence."
            ),
            (
                "Locate a first-party standalone caption/transcript asset if "
                "one exists; do not infer it from the master advertisement."
            ),
        ],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--plan-only",
        action="store_true",
        help="Validate frozen local route and saved first-party evidence.",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Refresh metadata and perform bounded segment HEAD/Range probes.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--proxy",
        action="append",
        default=[],
        help="Ordered proxy route; repeat for failover.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        local = validate_local_inputs()
        if args.live:
            try:
                live = run_live(local, args.proxy or DEFAULT_PROXIES)
                report = build_report(mode="live", local=local, live=live)
            except PreflightError as exc:
                report = build_report(
                    mode="live",
                    local=local,
                    live_error=str(exc),
                )
        else:
            report = build_report(mode="plan-only", local=local)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError, PreflightError) as exc:
        print(f"NASA_MOONBOUND_VSA_PREFLIGHT_ERROR:{exc}", file=sys.stderr)
        return 2
    print(report["final_marker"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
