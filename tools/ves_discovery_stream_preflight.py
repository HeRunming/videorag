#!/usr/bin/env python3
"""Run bounded ISO-BMFF preflight for the exact ten-object VES plan.

This is intentionally a thin adapter over ``hf_audio_stream_preflight``.  The
shared module remains the only implementation of HTTP, range validation,
in-memory byte handling, ISO-BMFF parsing, and decision classification.
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
    from tools import ves_discovery_preflight_plan as discovery_plan
    from tools import ves_long_candidate_recon as recon
except ModuleNotFoundError:  # Support direct ``python tools/...py`` execution.
    import hf_audio_stream_preflight as core  # type: ignore[no-redef]
    import ves_discovery_preflight_plan as discovery_plan  # type: ignore[no-redef]
    import ves_long_candidate_recon as recon  # type: ignore[no-redef]


SCHEMA_VERSION = "1.0.0"
PLAN_PATH = Path(
    "data/acquisition_preflight/ves_discovery_stream_preflight_plan.json"
)
RESULT_PATH = Path(
    "data/acquisition_preflight/ves_discovery_stream_preflight_result.json"
)

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CANDIDATE_BYTES = 12 * 1024 * 1024
MAX_AGGREGATE_BYTES = 128 * 1024 * 1024
OBJECT_COUNT = 10

# A changed plan cannot broaden network access.  These identities are copied
# from the reviewed Task 71 artifact and must match in this exact order.
EXACT_VES_OBJECTS: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "ves-discovery-01",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/30805f57-8f23-4d41-91a0-19d248a62c1d.mp4",
        "size_bytes": 401_298_734,
        "hash_algorithm": "sha256",
        "hash": "902713fe9963c619c33098a0405a9c7af8d36b3ad6a63002b40f387e545ffa8a",
        "blob_id": "f3b3f19669b566f2f3c6174fde2ecfcd9831d38d",
    },
    {
        "candidate_id": "ves-discovery-02",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/nP5efbYfBPU.mp4",
        "size_bytes": 288_120_363,
        "hash_algorithm": "sha256",
        "hash": "521f7ed5309f8d5059ed1ecaad62bca1ebf5a5869a68e36b5f2792e8d2914048",
        "blob_id": "118835e8a63781b4f9ebbc54a1e8c348973538e0",
    },
    {
        "candidate_id": "ves-discovery-03",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/43f87662-2d38-447b-ba72-0eb7a9daebf1.mp4",
        "size_bytes": 205_762_861,
        "hash_algorithm": "sha256",
        "hash": "42c5d667bcc09df89a7614d7c645ed824bbb8a1be3c178a0c0d43a2f1c82b396",
        "blob_id": "aa9626bfd77ffe16be7a9e5641ddaae732d3aa07",
    },
    {
        "candidate_id": "ves-discovery-04",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/0yKvPsqOtT0.mp4",
        "size_bytes": 176_685_257,
        "hash_algorithm": "sha256",
        "hash": "50ee1b97f7b8878f02732de027cd6e919f6aeb43135a62cf13869bb7f5495992",
        "blob_id": "c22bf64ff2c7de57820ae8477b8b557c3d9e2e69",
    },
    {
        "candidate_id": "ves-discovery-05",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/4b5a1000-66ba-4ebb-8ca0-daf0772c1697.mp4",
        "size_bytes": 181_990_391,
        "hash_algorithm": "sha256",
        "hash": "c70402e52080703fb2656c704fbc6e6b2a7c4a8525c41f0bec22fa55e79a6698",
        "blob_id": "c8d9c1f2678fa0ecc8467d4cfb87ab077b74d0f2",
    },
    {
        "candidate_id": "ves-discovery-06",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/_Pbquj-6MVc.mp4",
        "size_bytes": 90_159_790,
        "hash_algorithm": "sha256",
        "hash": "891d84380924e2112188f945ea30ddc4423e80959afbf6d2219bb3cc81a7dadd",
        "blob_id": "26038b05eb42fcfff309cf766c50d9e444f9c479",
    },
    {
        "candidate_id": "ves-discovery-07",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/Pf1hNFndi60.mp4",
        "size_bytes": 52_192_940,
        "hash_algorithm": "sha256",
        "hash": "5859ae1c04888b8eb9ada32e90ca16684873ec8403ac441ecff3c2c6a8079f75",
        "blob_id": "59ec1e421f3dd7462d5f1bb392dbdc072f0c43a8",
    },
    {
        "candidate_id": "ves-discovery-08",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/awHc8IySU-I.mp4",
        "size_bytes": 91_866_964,
        "hash_algorithm": "sha256",
        "hash": "282eb146deb1012a767b0cdaf1055e17c8045e728a99d8174c5b5f77e1546864",
        "blob_id": "1e53cba65d0676c2c7e94d265443e31478541d3b",
    },
    {
        "candidate_id": "ves-discovery-09",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/x8zGsWuu-e0.mp4",
        "size_bytes": 97_629_553,
        "hash_algorithm": "sha256",
        "hash": "cdd549adf37cdeb71df0318493f915df8924efb868ed3a402a24b9e2c74ffc58",
        "blob_id": "2f4ff00a3539c78ecf9642a1ed9acc35b62c22ff",
    },
    {
        "candidate_id": "ves-discovery-10",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/wUnEDnAYTpE.mp4",
        "size_bytes": 63_902_073,
        "hash_algorithm": "sha256",
        "hash": "65bd1c0107b5ddf400d2378db56998888539b3214133b922a886313dac46737b",
        "blob_id": "83cb73a3d73eb099dcd0b61d3dc11b1b05b78d84",
    },
)

PROVENANCE_KEYS = (
    "rank",
    "dataset",
    "tasks",
    "topic_hypothesis",
    "modality_role_hypothesis",
    "metadata_evidence_rows",
    "evidence_interval_count",
    "max_evidence_endpoint_s",
    "ranking_provenance",
    "evidence_extent_is_duration",
    "duration_qualification_status",
    "requested_action",
    "rights_status",
    "full_acquisition_authorized",
    "processing_authorized",
    "annotation_authorized",
    "release_authorized",
)


def _candidate_mapping(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": item["discovery_id"],
        "repo_id": item["repo_id"],
        "revision": item["revision"],
        "path": item["path"],
        "size_bytes": item["size_bytes"],
        "hash_algorithm": item["hash_algorithm"],
        "hash": item["sha256"],
        "blob_id": item["blob_id"],
    }


def _validate_discovery_plan(plan: Mapping[str, Any]) -> None:
    try:
        discovery_plan.validate_plan(plan)
    except recon.ReconError as exc:
        raise core.ConfigurationError(f"VES_PLAN_INVALID_{exc.code}") from None

    if plan.get("schema_version") != discovery_plan.SCHEMA_VERSION:
        raise core.ConfigurationError("VES_PLAN_SCHEMA_VERSION_MISMATCH")
    if plan.get("status") != "READY_FOR_BOUNDED_DISCOVERY_STREAM_PREFLIGHT":
        raise core.ConfigurationError("VES_PLAN_STATUS_INVALID")
    authorization = plan.get("authorization")
    expected_authorization = {
        "authorized_actions": [
            "BOUNDED_ISO_BMFF_RANGE_PREFLIGHT_FOR_THE_TEN_EXACT_OBJECTS_ONLY"
        ],
        "authorized_for_bounded_stream_container_preflight": [
            item["candidate_id"] for item in EXACT_VES_OBJECTS
        ],
        "authorized_for_full_acquisition": [],
        "authorized_for_full_media_download": [],
        "authorized_for_processing": [],
        "authorized_for_annotation": [],
        "authorized_for_release": [],
    }
    if authorization != expected_authorization:
        raise core.ConfigurationError("VES_AUTHORIZATION_NOT_EXACT")
    scope = plan.get("discovery_scope")
    if not isinstance(scope, Mapping):
        raise core.ConfigurationError("VES_DISCOVERY_SCOPE_ABSENT")
    if (
        scope.get("selected_object_count") != OBJECT_COUNT
        or scope.get("selected_objects_are_duration_qualified_candidates")
        is not False
        or scope.get("evidence_extent_is_duration") is not False
    ):
        raise core.ConfigurationError("VES_DISCOVERY_SCOPE_INVALID")

    constraints = plan.get("constraints")
    if not isinstance(constraints, Mapping) or any(
        constraints.get(key) is not False
        for key in (
            "full_object_response_permitted_in_later_preflight",
            "full_object_range_permitted_in_later_preflight",
            "rights_cleared",
        )
    ):
        raise core.ConfigurationError("VES_PLAN_TRANSFER_SCOPE_TOO_BROAD")
    if (
        constraints.get("closed_exact_object_list") is not True
        or constraints.get("wildcards_allowed") is not False
    ):
        raise core.ConfigurationError("VES_PLAN_NOT_CLOSED")

    task70 = plan.get("task_70_duration_qualified_pool")
    if not isinstance(task70, Mapping) or (
        task70.get("candidate_count") != 0
        or task70.get("status") != "EMPTY_FAIL_CLOSED"
        or task70.get("unchanged_by_this_plan") is not True
    ):
        raise core.ConfigurationError("VES_DURATION_QUALIFICATION_SCOPE_INVALID")


def load_plan(
    path: Path = PLAN_PATH,
) -> tuple[dict[str, Any], list[core.Candidate], list[dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        plan = json.load(handle)
    if not isinstance(plan, dict):
        raise core.ConfigurationError("VES_PLAN_NOT_OBJECT")
    _validate_discovery_plan(plan)
    raw_objects = plan.get("discovery_objects")
    if not isinstance(raw_objects, list):
        raise core.ConfigurationError("VES_DISCOVERY_OBJECTS_NOT_LIST")

    if not all(isinstance(item, Mapping) for item in raw_objects):
        raise core.ConfigurationError("VES_DISCOVERY_OBJECT_NOT_MAPPING")
    try:
        candidates = [
            core.Candidate.from_mapping(_candidate_mapping(item))
            for item in raw_objects
        ]
    except (KeyError, TypeError, ValueError):
        raise core.ConfigurationError("VES_DISCOVERY_IDENTITY_INVALID") from None
    expected = [
        core.Candidate.from_mapping(item) for item in EXACT_VES_OBJECTS
    ]
    if candidates != expected:
        raise core.ConfigurationError("VES_PLAN_DOES_NOT_MATCH_EXACT_ALLOWLIST")

    provenance: list[dict[str, Any]] = []
    for item in raw_objects:
        if any(
            key.endswith("_authorized") and item[key] is not False
            for key in item
        ):
            raise core.ConfigurationError("VES_OBJECT_AUTHORITY_TOO_BROAD")
        if any(
            key in item
            for key in ("duration_seconds", "duration_s", "metadata_duration")
        ):
            raise core.ConfigurationError("VES_EVIDENCE_MUST_NOT_BECOME_DURATION")
        provenance.append(
            {key: copy.deepcopy(item[key]) for key in PROVENANCE_KEYS}
        )
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
    candidates: Sequence[core.Candidate],
    provenance: Sequence[Mapping[str, Any]],
    client: core.SafeHFRangeClient,
    *,
    window_bytes: int = core.DEFAULT_WINDOW_BYTES,
) -> dict[str, Any]:
    if len(candidates) != OBJECT_COUNT or len(provenance) != OBJECT_COUNT:
        raise core.ConfigurationError("VES_RUNTIME_OBJECT_COUNT_INVALID")
    generic = core.run_preflight(
        candidates, client, window_bytes=window_bytes
    )
    generic_results = generic.pop("candidates")
    objects = []
    for candidate, source, result in zip(
        candidates, provenance, generic_results, strict=True
    ):
        if result["candidate_id"] != candidate.candidate_id:
            raise core.ConfigurationError("VES_RESULT_MAPPING_MISMATCH")
        result["discovery_id"] = candidate.candidate_id
        result["metadata_provenance"] = copy.deepcopy(dict(source))
        objects.append(result)

    generic.update(
        {
            "schema_version": SCHEMA_VERSION,
            "plan_schema_version": plan.get("schema_version"),
            "mode": "live_bounded_ves_discovery_stream_container_preflight",
            "discovery_object_count": len(objects),
            "discovery_objects": objects,
            "plan_provenance": {
                "as_of_date": plan.get("as_of_date"),
                "repository": copy.deepcopy(plan.get("repository")),
                "metadata_snapshots": copy.deepcopy(
                    plan.get("metadata_snapshots")
                ),
                "task_70_duration_qualified_pool": copy.deepcopy(
                    plan.get("task_70_duration_qualified_pool")
                ),
            },
        }
    )
    generic["global_limitations"].extend(
        [
            "VES evidence endpoints are ranking provenance only and were not used as duration.",
            "This run does not authorize full acquisition, processing, annotation, or release.",
        ]
    )
    return generic


def validate_plan_only(path: Path = PLAN_PATH) -> dict[str, Any]:
    plan, candidates, _ = load_plan(path)
    return {
        "status": "PASS",
        "schema_version": plan.get("schema_version"),
        "discovery_object_count": len(candidates),
        "discovery_ids": [item.candidate_id for item in candidates],
        "exact_allowlist_match": True,
        "duration_qualified_candidate_count": 0,
        "bounded_preflight_only": True,
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
        token = core.load_hf_token()
        if not token:
            raise core.ConfigurationError("HF_TOKEN_NOT_AVAILABLE")
        budget = core.Budget(
            maximum_response_bytes=args.max_response_bytes,
            maximum_total_bytes=args.max_total_bytes,
        )
        with core.SafeHFRangeClient(
            token,
            proxies=args.proxy,
            budget=budget,
            maximum_candidate_bytes=args.max_candidate_bytes,
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
                    "output": str(args.output),
                    "discovery_object_count": len(candidates),
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
