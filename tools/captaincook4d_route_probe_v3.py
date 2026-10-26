#!/usr/bin/env python3
"""Bounded Task180 probes for the frozen CaptainCook4D 8+2 media routes.

The route-resolution request intentionally mirrors the official downloader:

    requests.get(url, stream=True)

Requests therefore supplies its default headers, follows redirects, and
maintains redirect cookies inside that one call.  This probe adds only a
connect/read timeout so the audit is bounded, and closes the final response
without consuming its media body.

A second GET starts from the same official Box shared link with Range
``bytes=0-0``.  It is not part of the official downloader; it is a bounded
capability check required by Task180.  At most one response-body byte is read
and retained per selected route.

Ephemeral BoxCloud paths and cookie values are never written.  Their SHA-256
identities, path templates, cookie names, and non-secret response metadata are
retained instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
import urllib3


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = (
    ROOT
    / "data/source_recon/captaincook4d_access_v2/derived"
    / "selected_media_route_inventory_v2.json"
)
DEFAULT_OUTPUT = ROOT / "data/source_recon/captaincook4d_access_v3/probes"
DEFAULT_PROXY = "https://proxy.example.invalid:3128"
SENSITIVE_QUERY_MARKERS = (
    "auth",
    "credential",
    "key",
    "policy",
    "secret",
    "sig",
    "token",
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sanitize_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url)
    path = parsed.path
    if parsed.hostname and parsed.hostname.endswith("boxcloud.com"):
        parts = path.split("/")
        if len(parts) >= 5 and parts[1:3] == ["d", "1"]:
            path = "/d/1/[REDACTED_EPHEMERAL_OBJECT_CAPABILITY]/" + parts[-1]
        else:
            path = "/[REDACTED_EPHEMERAL_OBJECT_CAPABILITY]"
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if any(marker in key.lower() for marker in SENSITIVE_QUERY_MARKERS):
            query.append((key, "[REDACTED]"))
        else:
            query.append((key, value))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, path, urlencode(query, doseq=True), "")
    )


def url_identity(url: str) -> dict[str, Any]:
    parsed = urlsplit(url)
    return {
        "scheme": parsed.scheme,
        "host": parsed.netloc,
        "redacted_url": sanitize_url(url),
        "url_sha256": sha256_text(url),
        "path_sha256": sha256_text(parsed.path),
        "path_bytes": len(parsed.path.encode("utf-8")),
        "query_keys": sorted(key for key, _ in parse_qsl(parsed.query)),
        "fragment_present": bool(parsed.fragment),
    }


def sanitize_headers(headers: requests.structures.CaseInsensitiveDict) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in {"set-cookie", "cookie", "authorization", "proxy-authorization"}:
            result[key] = "[REDACTED]"
        elif lower == "location":
            result[key] = sanitize_url(value) or ""
        else:
            result[key] = value
    return result


def response_record(response: requests.Response) -> dict[str, Any]:
    return {
        "status_code": response.status_code,
        "reason": response.reason,
        "url": sanitize_url(response.url),
        "url_identity": url_identity(response.url),
        "request_headers": sanitize_headers(response.request.headers),
        "response_headers": sanitize_headers(response.headers),
        "response_cookie_names": sorted(response.cookies.keys()),
    }


def exchange_record(response: requests.Response) -> dict[str, Any]:
    return {
        "redirect_count": len(response.history),
        "history": [response_record(item) for item in response.history],
        "final": response_record(response),
    }


def official_style_get(
    url: str,
    proxy: str,
    max_retries: int = 5,
    retry_delay_seconds: int = 5,
) -> tuple[requests.Response | None, list[dict[str, Any]]]:
    """Use the official request shape, with only an audit timeout added."""

    attempts: list[dict[str, Any]] = []
    proxies = {"http": proxy, "https": proxy}
    for attempt in range(1, max_retries + 1):
        started = time.time()
        try:
            # This is the official downloader call shape.  timeout is the only
            # audit-only addition and does not alter HTTP headers or redirects.
            response = requests.get(
                url,
                stream=True,
                proxies=proxies,
                timeout=(20, 45),
            )
            response.raise_for_status()
            attempts.append(
                {
                    "attempt": attempt,
                    "elapsed_seconds": round(time.time() - started, 6),
                    "outcome": "SUCCESS",
                    "status_code": response.status_code,
                }
            )
            return response, attempts
        except requests.exceptions.RequestException as exc:
            attempts.append(
                {
                    "attempt": attempt,
                    "elapsed_seconds": round(time.time() - started, 6),
                    "outcome": "REQUEST_ERROR",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "status_code": (
                        exc.response.status_code if exc.response is not None else None
                    ),
                }
            )
            if exc.response is not None:
                exc.response.close()
            if attempt < max_retries:
                time.sleep(retry_delay_seconds)
    return None, attempts


def range_get(url: str, proxy: str) -> tuple[requests.Response, bytes, float]:
    started = time.time()
    response = requests.get(
        url,
        headers={"Range": "bytes=0-0"},
        stream=True,
        proxies={"http": proxy, "https": proxy},
        timeout=(20, 45),
    )
    elapsed = time.time() - started
    body = b""
    for chunk in response.iter_content(chunk_size=1):
        if chunk:
            body = chunk[:1]
            break
    return response, body, elapsed


def probe_asset(asset: dict[str, Any], output_root: Path, proxy: str) -> dict[str, Any]:
    asset_id = asset["asset_id"]
    url = asset["official_shared_link"]
    asset_dir = output_root / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "schema_version": "av-trace.captaincook4d-route-probe/3.0",
        "task_id": 180,
        "created_at": "2026-10-08",
        "asset_id": asset_id,
        "role": asset["role"],
        "rank": asset["rank"],
        "source_group_id": asset["source_group_id"],
        "recording_id": asset["recording_id"],
        "stream": asset["stream"],
        "official_shared_link": url,
        "proxy": proxy,
        "official_semantics": {
            "method": "GET",
            "stream": True,
            "allow_redirects": "requests.get default True",
            "headers": "requests defaults only",
            "cookies": (
                "no caller cookies; requests preserves Set-Cookie values inside "
                "the automatic redirect chain"
            ),
            "query_added": False,
            "body_bytes_consumed": 0,
            "audit_only_difference": "connect/read timeout=(20,45)",
        },
    }

    response, attempts = official_style_get(url, proxy)
    result["official_resolution_attempts"] = attempts
    if response is None:
        result["official_resolution"] = None
        result["range_probe"] = None
        result["probe_status"] = "OFFICIAL_STYLE_GET_FAILED"
        (asset_dir / "probe.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return result

    result["official_resolution"] = exchange_record(response)
    response.close()

    try:
        range_response, body, range_elapsed = range_get(url, proxy)
        result["range_probe"] = {
            "request": {
                "method": "GET",
                "range": "bytes=0-0",
                "starts_at_official_shared_link": True,
                "redirect_handling": "requests automatic redirects",
            },
            "elapsed_seconds": round(range_elapsed, 6),
            "exchange": exchange_record(range_response),
            "body_bytes_read_and_retained": len(body),
            "body_sha256": hashlib.sha256(body).hexdigest() if body else None,
        }
        if body:
            (asset_dir / "range_0_0.bin").write_bytes(body)
        range_response.close()
        result["probe_status"] = "COMPLETE"
    except requests.exceptions.RequestException as exc:
        result["range_probe"] = {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "body_bytes_read_and_retained": 0,
        }
        result["probe_status"] = "RANGE_PROBE_FAILED"

    (asset_dir / "probe.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--proxy", default=DEFAULT_PROXY)
    parser.add_argument("--max-workers", type=int, default=3)
    args = parser.parse_args()

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    assets = inventory["media_assets"]
    if len(assets) != 20:
        raise RuntimeError(f"Expected 20 frozen routes, found {len(assets)}")

    args.output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        results = list(
            executor.map(
                lambda asset: probe_asset(asset, args.output, args.proxy),
                assets,
            )
        )

    summary = {
        "schema_version": "av-trace.captaincook4d-route-probe-summary/3.0",
        "task_id": 180,
        "created_at": "2026-10-08",
        "proxy": args.proxy,
        "python_version": platform.python_version(),
        "requests_version": requests.__version__,
        "urllib3_version": urllib3.__version__,
        "default_requests_headers": dict(requests.utils.default_headers()),
        "max_workers": args.max_workers,
        "elapsed_seconds": round(time.time() - started, 6),
        "asset_count": len(results),
        "complete_count": sum(row["probe_status"] == "COMPLETE" for row in results),
        "official_resolution_success_count": sum(
            row.get("official_resolution") is not None for row in results
        ),
        "range_probe_success_count": sum(
            row.get("range_probe", {})
            .get("exchange", {})
            .get("final", {})
            .get("status_code")
            == 206
            for row in results
        ),
        "retained_range_body_bytes": sum(
            (row.get("range_probe") or {}).get("body_bytes_read_and_retained", 0)
            for row in results
        ),
        "results": [
            {
                "asset_id": row["asset_id"],
                "probe_status": row["probe_status"],
                "official_final_status": (
                    (row.get("official_resolution") or {})
                    .get("final", {})
                    .get("status_code")
                ),
                "official_final_host": (
                    (row.get("official_resolution") or {})
                    .get("final", {})
                    .get("url_identity", {})
                    .get("host")
                ),
                "content_length": (
                    (row.get("official_resolution") or {})
                    .get("final", {})
                    .get("response_headers", {})
                    .get("Content-Length")
                ),
                "accept_ranges": (
                    (row.get("official_resolution") or {})
                    .get("final", {})
                    .get("response_headers", {})
                    .get("accept-ranges")
                ),
                "range_status": (
                    (row.get("range_probe") or {})
                    .get("exchange", {})
                    .get("final", {})
                    .get("status_code")
                ),
                "content_range": (
                    (row.get("range_probe") or {})
                    .get("exchange", {})
                    .get("final", {})
                    .get("response_headers", {})
                    .get("content-range")
                ),
            }
            for row in results
        ],
    }
    (args.output / "route_probe_summary_v3.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
