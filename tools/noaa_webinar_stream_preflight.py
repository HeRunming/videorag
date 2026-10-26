#!/usr/bin/env python3
"""Run bounded ISO-BMFF preflight for exact NOAA Ocean Today MP4 URLs.

This adapter reuses the shared parser, sparse range reader, budgets, request
validation, and decision logic from ``hf_audio_stream_preflight``.  NOAA
requests never carry a bearer token, redirects remain restricted to the exact
Ocean Today and Ocean Service CDN hosts, and no response bytes are persisted.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from tools import hf_audio_stream_preflight as core
    from tools import noaa_webinar_route_recon as recon
except ModuleNotFoundError:  # Support direct ``python tools/...py`` execution.
    import hf_audio_stream_preflight as core  # type: ignore[no-redef]
    import noaa_webinar_route_recon as recon  # type: ignore[no-redef]


SCHEMA_VERSION = "1.0.0"
PLAN_PATH = recon.PLAN_PATH
RESULT_PATH = Path(
    "data/acquisition_preflight/noaa_webinar_stream_preflight_result.json"
)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CANDIDATE_BYTES = 12 * 1024 * 1024
MAX_AGGREGATE_BYTES = 96 * 1024 * 1024
MIN_OBJECTS = 5
MAX_OBJECTS = 8

PROVENANCE_KEYS = (
    "stable_source_id",
    "page_url",
    "page_title",
    "observed_html_title",
    "metadata_duration_prior",
    "route_evidence",
    "stream_facts_status",
    "full_acquisition_authorized",
    "processing_authorized",
    "annotation_authorized",
    "release_authorized",
)


def noaa_stream_host_allowed(host: str) -> bool:
    return recon.noaa_redirect_host_allowed(host)


def load_plan(
    path: Path = PLAN_PATH,
) -> tuple[dict[str, Any], list[core.DirectURLCandidate], list[dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        plan = json.load(handle)
    if not isinstance(plan, dict):
        raise core.ConfigurationError("NOAA_PLAN_NOT_OBJECT")
    try:
        recon.validate_plan(plan)
    except recon.ReconError as exc:
        raise core.ConfigurationError(f"NOAA_PLAN_INVALID_{exc}") from None
    if plan.get("schema_version") != recon.SCHEMA_VERSION:
        raise core.ConfigurationError("NOAA_PLAN_SCHEMA_VERSION_MISMATCH")
    if plan.get("status") != "READY_FOR_BOUNDED_NOAA_STREAM_PREFLIGHT":
        raise core.ConfigurationError("NOAA_PLAN_NOT_READY")
    raw_objects = plan.get("objects")
    if not isinstance(raw_objects, list) or not (
        MIN_OBJECTS <= len(raw_objects) <= MAX_OBJECTS
    ):
        raise core.ConfigurationError("NOAA_PLAN_OBJECT_COUNT_INVALID")
    try:
        candidates = [
            core.DirectURLCandidate.from_mapping(item) for item in raw_objects
        ]
    except (KeyError, TypeError, ValueError):
        raise core.ConfigurationError("NOAA_OBJECT_IDENTITY_INVALID") from None
    if len({item.candidate_id for item in candidates}) != len(candidates):
        raise core.ConfigurationError("NOAA_DUPLICATE_CANDIDATE")
    if len({item.url for item in candidates}) != len(candidates):
        raise core.ConfigurationError("NOAA_DUPLICATE_URL")
    for candidate in candidates:
        parsed_host = core.urlsplit(candidate.url).hostname or ""
        if not recon.direct_mp4_host_allowed(parsed_host):
            raise core.ConfigurationError("NOAA_FINAL_MP4_HOST_NOT_ALLOWED")

    authorization = plan.get("authorization")
    expected = {
        "authorized_action": (
            "BOUNDED_ISO_BMFF_PREFLIGHT_FOR_SELECTED_EXACT_URLS_ONLY"
        ),
        "authorized_for_bounded_stream_preflight": [
            item.candidate_id for item in candidates
        ],
        "authorized_for_full_acquisition": [],
        "authorized_for_processing": [],
        "authorized_for_annotation": [],
        "authorized_for_release": [],
    }
    if authorization != expected:
        raise core.ConfigurationError("NOAA_AUTHORIZATION_NOT_EXACT")
    policy = plan.get("transfer_policy")
    if not isinstance(policy, Mapping):
        raise core.ConfigurationError("NOAA_TRANSFER_POLICY_MISSING")
    required_policy = {
        "per_request_body_bytes": MAX_RESPONSE_BYTES,
        "per_candidate_body_bytes": MAX_CANDIDATE_BYTES,
        "aggregate_body_bytes": MAX_AGGREGATE_BYTES,
        "maximum_object_count": MAX_OBJECTS,
        "head_and_bounded_range_get_only": True,
        "complete_object_range_prohibited": True,
        "full_object_get_prohibited": True,
        "media_byte_persistence_prohibited": True,
    }
    if dict(policy) != required_policy:
        raise core.ConfigurationError("NOAA_TRANSFER_POLICY_NOT_EXACT")

    provenance = [
        {key: copy.deepcopy(item[key]) for key in PROVENANCE_KEYS}
        for item in raw_objects
    ]
    return plan, candidates, provenance


def validate_limits(
    *,
    maximum_response_bytes: int,
    maximum_candidate_bytes: int,
    maximum_total_bytes: int,
) -> None:
    if min(
        maximum_response_bytes,
        maximum_candidate_bytes,
        maximum_total_bytes,
    ) <= 0:
        raise core.ConfigurationError("INVALID_TRANSFER_LIMIT")
    if maximum_response_bytes > MAX_RESPONSE_BYTES:
        raise core.ConfigurationError("PER_REQUEST_LIMIT_MAY_NOT_BE_RAISED")
    if maximum_candidate_bytes > MAX_CANDIDATE_BYTES:
        raise core.ConfigurationError("PER_CANDIDATE_LIMIT_MAY_NOT_BE_RAISED")
    if maximum_total_bytes > MAX_AGGREGATE_BYTES:
        raise core.ConfigurationError("AGGREGATE_LIMIT_MAY_NOT_BE_RAISED")


def run_preflight(
    plan: Mapping[str, Any],
    candidates: Sequence[core.DirectURLCandidate],
    provenance: Sequence[Mapping[str, Any]],
    client: core.SafeDirectURLRangeClient,
    *,
    window_bytes: int = core.DEFAULT_WINDOW_BYTES,
) -> dict[str, Any]:
    if not (
        MIN_OBJECTS
        <= len(candidates)
        == len(provenance)
        <= MAX_OBJECTS
    ):
        raise core.ConfigurationError("NOAA_RUNTIME_OBJECT_COUNT_INVALID")
    generic = core.run_preflight(
        candidates, client, window_bytes=window_bytes
    )
    generic_results = generic.pop("candidates")
    objects: list[dict[str, Any]] = []
    for candidate, source, result in zip(
        candidates, provenance, generic_results, strict=True
    ):
        if result["candidate_id"] != candidate.candidate_id:
            raise core.ConfigurationError("NOAA_RESULT_MAPPING_MISMATCH")
        if source["metadata_duration_prior"]["status"] != (
            "HYPOTHESIS_ONLY_NOT_CONTAINER_DURATION"
        ):
            raise core.ConfigurationError("NOAA_DURATION_PRIOR_STATUS_INVALID")
        result["noaa_provenance"] = copy.deepcopy(dict(source))
        objects.append(result)
    generic.update(
        {
            "schema_version": SCHEMA_VERSION,
            "plan_schema_version": plan.get("schema_version"),
            "mode": "live_bounded_noaa_direct_url_stream_preflight",
            "object_count": len(objects),
            "objects": objects,
            "plan_provenance": {
                "generated_at": plan.get("generated_at"),
                "source_identity_file": plan.get("source_identity_file"),
                "scope": copy.deepcopy(plan.get("scope")),
                "route_discovery_policy": copy.deepcopy(
                    plan.get("route_discovery_policy")
                ),
            },
        }
    )
    generic["global_limitations"].extend(
        [
            "NOAA page duration was retained only as a hypothesis and was not used as container duration.",
            "No bearer token was sent to NOAA.",
            "This run does not authorize full acquisition, processing, annotation, redistribution, or release.",
        ]
    )
    return generic


def validate_plan_only(path: Path = PLAN_PATH) -> dict[str, Any]:
    plan, candidates, _ = load_plan(path)
    return {
        "status": "PASS",
        "schema_version": plan.get("schema_version"),
        "object_count": len(candidates),
        "candidate_ids": [item.candidate_id for item in candidates],
        "exact_urls": [item.url for item in candidates],
        "bounded_preflight_only": True,
        "no_bearer_token": True,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=PLAN_PATH)
    parser.add_argument("--output", type=Path, default=RESULT_PATH)
    parser.add_argument(
        "--proxy",
        action="append",
        default=[],
        help="Ordered explicit proxy route; repeat for failover.",
    )
    parser.add_argument(
        "--window-bytes", type=int, default=core.DEFAULT_WINDOW_BYTES
    )
    parser.add_argument(
        "--max-response-bytes", type=int, default=MAX_RESPONSE_BYTES
    )
    parser.add_argument(
        "--max-candidate-bytes", type=int, default=MAX_CANDIDATE_BYTES
    )
    parser.add_argument(
        "--max-total-bytes", type=int, default=MAX_AGGREGATE_BYTES
    )
    parser.add_argument("--validate-plan-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        plan, candidates, provenance = load_plan(args.plan)
        validate_limits(
            maximum_response_bytes=args.max_response_bytes,
            maximum_candidate_bytes=args.max_candidate_bytes,
            maximum_total_bytes=args.max_total_bytes,
        )
        if args.validate_plan_only:
            print(
                json.dumps(
                    validate_plan_only(args.plan), indent=2, sort_keys=True
                )
            )
            return 0
        budget = core.Budget(
            maximum_response_bytes=args.max_response_bytes,
            maximum_total_bytes=args.max_total_bytes,
        )
        with core.SafeDirectURLRangeClient(
            allowed_host=noaa_stream_host_allowed,
            proxies=args.proxy,
            budget=budget,
            maximum_candidate_bytes=args.max_candidate_bytes,
            user_agent="AV-TRACE-noaa-stream-preflight/1.0",
        ) as client:
            result = run_preflight(
                plan,
                candidates,
                provenance,
                client,
                window_bytes=args.window_bytes,
            )
        core.atomic_write_json(args.output, result)
        print(
            json.dumps(
                {
                    "status": "COMPLETE",
                    "output": args.output.as_posix(),
                    "object_count": len(candidates),
                    "response_body_bytes": budget.total_bytes,
                    "decision_counts": result["aggregate"][
                        "decision_counts"
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except core.PreflightError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(
            f"ERROR: INPUT_OR_OUTPUT_{type(exc).__name__.upper()}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
