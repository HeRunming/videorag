#!/usr/bin/env python3
"""Run bounded ISO-BMFF preflight for the exact 20-object VES wave-2 plan.

This module is only a plan/allowlist adapter. HTTP requests, redirects, range
validation, response budgets, in-memory sparse reads, ISO-BMFF parsing,
duration/track extraction, timeline checks, and decisions are all delegated to
``hf_audio_stream_preflight``.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from tools import ves_long_candidate_recon as recon
    from tools import ves_discovery_stream_preflight as wave1_runner
    from tools import ves_wave2_plan as wave2_plan
except ModuleNotFoundError:  # Support direct ``python tools/...py`` execution.
    import ves_long_candidate_recon as recon  # type: ignore[no-redef]
    import ves_discovery_stream_preflight as wave1_runner  # type: ignore[no-redef]
    import ves_wave2_plan as wave2_plan  # type: ignore[no-redef]

core = wave1_runner.core

SCHEMA_VERSION = "1.0.0"
PLAN_PATH = wave2_plan.PLAN_REL
RESULT_PATH = Path(
    "data/acquisition_preflight/ves_wave2_stream_preflight_result.json"
)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CANDIDATE_BYTES = 12 * 1024 * 1024
MAX_AGGREGATE_BYTES = 256 * 1024 * 1024
OBJECT_COUNT = 20

# A modified JSON plan cannot broaden access. These exact identities are
# intentionally repeated in executable code and must match in this order.
EXACT_VES_OBJECTS: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "ves-wave2-01",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/DVwtoliP7t0.mp4",
        "size_bytes": 228_924_265,
        "hash_algorithm": "sha256",
        "hash": "b7f715c66c95531fd18ac8ae0c443e1cd26494b1a7137b1ce763d7bc33fcba32",
        "blob_id": "915585a40bf0d8098360b67924fdb730201126a2",
    },
    {
        "candidate_id": "ves-wave2-02",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/F7ddEfRBx4k.mp4",
        "size_bytes": 222_035_960,
        "hash_algorithm": "sha256",
        "hash": "9611920413c092aed73118e8d45ef55fdcf812d3e5a7b2c273d8ece6e4a47f34",
        "blob_id": "6968e0b53a8a30fb7e90dccba8952f77181c2def",
    },
    {
        "candidate_id": "ves-wave2-03",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/2c5d38ed-012f-4732-9eb8-89beddb07641.mp4",
        "size_bytes": 193_732_158,
        "hash_algorithm": "sha256",
        "hash": "57bbb527f8268c8e7761880b10782b5452d8dc61cf7dd0193c7132ae20d3f609",
        "blob_id": "fea3afb44a5db122161ef2df93d05bc74dc3034b",
    },
    {
        "candidate_id": "ves-wave2-04",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/c66RN87YjNE.mp4",
        "size_bytes": 179_789_327,
        "hash_algorithm": "sha256",
        "hash": "c4d7b90fff6051373d1617a7eec077bcfc5370cebf3c532ad7a5439ac71da578",
        "blob_id": "730117b8f8cf1b4d7401a37a1803a201c2693838",
    },
    {
        "candidate_id": "ves-wave2-05",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/30b70283-b0ce-4c24-a01d-896af252d70a.mp4",
        "size_bytes": 178_736_166,
        "hash_algorithm": "sha256",
        "hash": "78e02a060772798e0f7c01e2942f173152838a24b5deab940e439f97985670a7",
        "blob_id": "9ca68d2355a1ec5dc77c298e58d821f7eae37242",
    },
    {
        "candidate_id": "ves-wave2-06",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/1U65VOEwz4I.mp4",
        "size_bytes": 177_036_854,
        "hash_algorithm": "sha256",
        "hash": "5ce7481b5f1c23c0eaca6c2726ff51ea0619552c8e10523aa42964b6677bb1a3",
        "blob_id": "a560227bed5df976807e16c4f81169c73652f718",
    },
    {
        "candidate_id": "ves-wave2-07",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/0Y9-MQ44MdU.mp4",
        "size_bytes": 174_498_357,
        "hash_algorithm": "sha256",
        "hash": "5321291aae116fe639585e167835d05b6fc9ffcf935f4fd744b9a62b41d7584c",
        "blob_id": "242d6ea12275e0b1faeef49323801ee29af132e1",
    },
    {
        "candidate_id": "ves-wave2-08",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/_dncs2stX-w.mp4",
        "size_bytes": 170_316_616,
        "hash_algorithm": "sha256",
        "hash": "07edeaf1e15568ace9540df601d2a125f9c328e44f35ca5b7dda819175a2e284",
        "blob_id": "dfb1c93e035193bf3f2da2d0cdb78eb016275a5a",
    },
    {
        "candidate_id": "ves-wave2-09",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/kGR4r4Av1ig.mp4",
        "size_bytes": 163_519_821,
        "hash_algorithm": "sha256",
        "hash": "636d9da605e191b511847d1bb90341c40b8d5c65ace84b8f1c62c6b604e06854",
        "blob_id": "3cc70cbf519c25de45b6d8cbbbcb06ace9b63645",
    },
    {
        "candidate_id": "ves-wave2-10",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/erjwCQ-UZyw.mp4",
        "size_bytes": 154_178_387,
        "hash_algorithm": "sha256",
        "hash": "ab2b2f1dbb47eccc1e588c1fc52d19a07e1b554029b0d4b0be74e2251f021cb4",
        "blob_id": "2f43a0512827c7ca222d8b8d28956f2fa6e0c905",
    },
    {
        "candidate_id": "ves-wave2-11",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/WOGaS19VZ8Q.mp4",
        "size_bytes": 146_379_989,
        "hash_algorithm": "sha256",
        "hash": "b9e502a99eda172d19e46c7f209ea9ec2eb0dab718ad8114f34fd15ac8cfc1de",
        "blob_id": "1634a2535cc6e63c24178007b8eacf263e706e24",
    },
    {
        "candidate_id": "ves-wave2-12",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/PAI-gQ19pbs.mp4",
        "size_bytes": 145_251_474,
        "hash_algorithm": "sha256",
        "hash": "1a18bbdc4f23743b5d6549fa796cdad72e1a7ce70fea2bc8b6c781efede2ae04",
        "blob_id": "7c09b861df119714ba4883671fea9ba6bb122314",
    },
    {
        "candidate_id": "ves-wave2-13",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/EavQ0LtEICY.mp4",
        "size_bytes": 143_020_711,
        "hash_algorithm": "sha256",
        "hash": "67b3cca119bd4f2e540f289b318c29563a07c291ea9aa1767d7dd38b5e63ca23",
        "blob_id": "59f9f9ba932b0fb1dae28b307945cde91d5f4782",
    },
    {
        "candidate_id": "ves-wave2-14",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/us78iBEMihk.mp4",
        "size_bytes": 136_611_334,
        "hash_algorithm": "sha256",
        "hash": "e9e0d82346bda075bff638ad9384ff1e78620d334b2679493e8e8ab1ec9b933e",
        "blob_id": "e3570bc614d271370161d3250ae78020343a4f19",
    },
    {
        "candidate_id": "ves-wave2-15",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/3m29MQ-qPfg.mp4",
        "size_bytes": 136_544_107,
        "hash_algorithm": "sha256",
        "hash": "fd97b5f8d459a177d30cd7638e34cd917a89dcc0cf0e283357166685851513da",
        "blob_id": "170fe368a6fe7ef87a78ecf052fe73b070b4b7fb",
    },
    {
        "candidate_id": "ves-wave2-16",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/ooqdg9Wr-mo.mp4",
        "size_bytes": 135_229_759,
        "hash_algorithm": "sha256",
        "hash": "11e81585265a69c244339f0b7279a0ea205d85c4e4bddf1e8f75094cef828472",
        "blob_id": "f91179cad8fb0ffd197911314606868db49c0f05",
    },
    {
        "candidate_id": "ves-wave2-17",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/tCRpDpDgBcE.mp4",
        "size_bytes": 128_780_596,
        "hash_algorithm": "sha256",
        "hash": "1b847499aaebb9ff476600b36858cace00663f74ecf136670a2a4127b9e9cf0b",
        "blob_id": "b94af41e81b8eca3150ccb9cb6b5cb0e1d6e7710",
    },
    {
        "candidate_id": "ves-wave2-18",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/NrtwBO_nyFA.mp4",
        "size_bytes": 115_946_975,
        "hash_algorithm": "sha256",
        "hash": "884520aa0df909891d5fa3bec13552f76ca57a2b8010915a233ddf1bca5b0995",
        "blob_id": "7e33ee948f5669dc388610dc82fa185b5cef4c8f",
    },
    {
        "candidate_id": "ves-wave2-19",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/0wM4B7DONu0.mp4",
        "size_bytes": 114_485_081,
        "hash_algorithm": "sha256",
        "hash": "7a6cafe7d33357cb39bb00df4b8cffa54c0615c52b21d9400d63f9a34f4020bc",
        "blob_id": "58f97e1284dcc48e53425b1433aa05167945d09b",
    },
    {
        "candidate_id": "ves-wave2-20",
        "repo_id": "buaaplay/VES-Bench",
        "revision": "b1cdbb370ad866090e6fec82ccb9e699b10edbc7",
        "path": "videos/ZQIZx5Oqw88.mp4",
        "size_bytes": 114_100_763,
        "hash_algorithm": "sha256",
        "hash": "1808f07aace3ea7a4d1981ea63297aec0ec756d8307e7afec15d21486bd39e3d",
        "blob_id": "483d0efb929b89691e770e3d2c4f35a19fae74d9",
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
    "ranking_heuristic",
    "evidence_extent_is_duration",
    "size_ratio_is_duration",
    "qualification_status",
    "requested_action",
    "rights_status",
    "full_acquisition_authorized",
    "processing_authorized",
    "annotation_authorized",
    "release_authorized",
)


def _candidate_mapping(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": item["wave2_id"],
        "repo_id": item["repo_id"],
        "revision": item["revision"],
        "path": item["path"],
        "size_bytes": item["size_bytes"],
        "hash_algorithm": item["hash_algorithm"],
        "hash": item["sha256"],
        "blob_id": item["blob_id"],
    }


def _validate_wave2_plan(plan: Mapping[str, Any]) -> None:
    try:
        wave2_plan.validate_plan(plan)
    except recon.ReconError as exc:
        raise core.ConfigurationError(f"VES_WAVE2_PLAN_INVALID_{exc.code}") from None
    authorization = plan.get("authorization")
    expected_authorization = {
        "authorized_actions": [wave2_plan.AUTHORIZED_ACTION],
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
        raise core.ConfigurationError("VES_WAVE2_AUTHORIZATION_NOT_EXACT")
    scope = plan.get("wave2_scope")
    if (
        not isinstance(scope, Mapping)
        or scope.get("selected_object_count") != OBJECT_COUNT
        or scope.get("selected_objects_are_duration_qualified") is not False
        or scope.get("evidence_extent_is_duration") is not False
    ):
        raise core.ConfigurationError("VES_WAVE2_SCOPE_INVALID")


def load_plan(
    path: Path = PLAN_PATH,
) -> tuple[dict[str, Any], list[core.Candidate], list[dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        plan = json.load(handle)
    if not isinstance(plan, dict):
        raise core.ConfigurationError("VES_WAVE2_PLAN_NOT_OBJECT")
    _validate_wave2_plan(plan)
    raw_objects = plan.get("wave2_objects")
    if not isinstance(raw_objects, list) or not all(
        isinstance(item, Mapping) for item in raw_objects
    ):
        raise core.ConfigurationError("VES_WAVE2_OBJECTS_INVALID")
    try:
        candidates = [
            core.Candidate.from_mapping(_candidate_mapping(item))
            for item in raw_objects
        ]
    except (KeyError, TypeError, ValueError):
        raise core.ConfigurationError("VES_WAVE2_IDENTITY_INVALID") from None
    expected = [core.Candidate.from_mapping(item) for item in EXACT_VES_OBJECTS]
    if candidates != expected:
        raise core.ConfigurationError("VES_WAVE2_PLAN_NOT_EXACT_ALLOWLIST")

    provenance: list[dict[str, Any]] = []
    for item in raw_objects:
        if any(
            key in item
            for key in (
                "duration_seconds",
                "duration_s",
                "metadata_duration",
                "inferred_duration",
                "estimated_duration",
            )
        ):
            raise core.ConfigurationError("VES_WAVE2_UNTESTED_DURATION_PRESENT")
        if any(
            key.endswith("_authorized") and item[key] is not False
            for key in item
        ):
            raise core.ConfigurationError("VES_WAVE2_OBJECT_AUTHORITY_TOO_BROAD")
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
        raise core.ConfigurationError("VES_WAVE2_RUNTIME_COUNT_INVALID")
    generic = core.run_preflight(
        candidates, client, window_bytes=window_bytes
    )
    generic_results = generic.pop("candidates")
    objects = []
    for candidate, source, result in zip(
        candidates, provenance, generic_results, strict=True
    ):
        if result["candidate_id"] != candidate.candidate_id:
            raise core.ConfigurationError("VES_WAVE2_RESULT_MAPPING_MISMATCH")
        result["wave2_id"] = candidate.candidate_id
        result["metadata_provenance"] = copy.deepcopy(dict(source))
        objects.append(result)
    generic.update(
        {
            "schema_version": SCHEMA_VERSION,
            "plan_schema_version": plan.get("schema_version"),
            "mode": "live_bounded_ves_wave2_stream_container_preflight",
            "wave2_object_count": len(objects),
            "wave2_objects": objects,
            "plan_provenance": {
                "as_of_date": plan.get("as_of_date"),
                "repository": copy.deepcopy(plan.get("repository")),
                "metadata_snapshots": copy.deepcopy(
                    plan.get("metadata_snapshots")
                ),
                "wave1_calibration": copy.deepcopy(
                    plan.get("wave1_calibration")
                ),
                "wave2_scope": copy.deepcopy(plan.get("wave2_scope")),
            },
        }
    )
    generic["global_limitations"].extend(
        [
            "Wave-1 size/duration ratios affected ranking only; no untested duration was inferred.",
            "Metadata topic and modality labels remain unverified hypotheses.",
            "This run does not authorize full acquisition, processing, annotation, or release.",
        ]
    )
    return generic


def validate_plan_only(path: Path = PLAN_PATH) -> dict[str, Any]:
    plan, candidates, _ = load_plan(path)
    return {
        "status": "PASS",
        "schema_version": plan.get("schema_version"),
        "wave2_object_count": len(candidates),
        "wave2_ids": [item.candidate_id for item in candidates],
        "exact_allowlist_match": True,
        "duration_qualified_object_count": 0,
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
                    "wave2_object_count": len(candidates),
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
