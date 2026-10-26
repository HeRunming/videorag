from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tools import ves_long_candidate_recon as recon


ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / recon.PARQUET_REL
API = ROOT / recon.API_REL


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_snapshots_have_exact_identity_and_parse() -> None:
    assert PARQUET.stat().st_size == recon.EXPECTED_PARQUET_SIZE == 422415
    assert digest(PARQUET) == recon.EXPECTED_PARQUET_SHA256
    assert API.stat().st_size == recon.EXPECTED_API_SIZE == 79549
    assert digest(API) == recon.EXPECTED_API_SHA256

    schema, rows = recon.read_parquet(PARQUET)
    assert schema.names == [
        "id",
        "task",
        "dataset",
        "video_id",
        "video_path",
        "question",
        "options",
        "answer",
        "evidence",
        "source_question_id",
    ]
    assert len(rows) == 600
    assert len({row["video_id"] for row in rows}) == 348


def test_real_metadata_joins_every_exact_mp4_but_has_no_duration() -> None:
    schema, rows = recon.read_parquet(PARQUET)
    api = recon.load_api_snapshot(API)
    objects = recon.build_object_index(api)
    joined, duration_column = recon.join_rows(
        schema, rows, objects, require_duration=False
    )
    assert len(objects) == len(joined) == 348
    assert duration_column is None
    assert sum(item.evidence_interval_count for item in joined) == 2025
    assert max(item.max_evidence_end_s for item in joined) == 1080.0
    parquet_identity = recon.validate_parquet_sibling(
        api,
        recon.SnapshotIdentity(
            recon.PARQUET_REL.as_posix(),
            recon.EXPECTED_PARQUET_SIZE,
            recon.EXPECTED_PARQUET_SHA256,
        ),
    )
    assert parquet_identity.repo_path == "VES-Bench.parquet"
    assert parquet_identity.blob_id == "74c9e646c04f2a9923d3de0ffe017d9f62a1fbe2"
    with pytest.raises(recon.ReconError, match="MISSING_ITEM_DURATION_COLUMN"):
        recon.join_rows(schema, rows, objects, require_duration=True)


def test_real_run_is_fail_closed_and_writes_no_fake_candidates(
    tmp_path: Path,
) -> None:
    pool = tmp_path / "pool.csv"
    plan_path = tmp_path / "plan.json"
    result = recon.run(ROOT, pool_path=pool, plan_path=plan_path)
    assert result["status"] == "BLOCKED"
    assert result["candidate_count"] == 0
    assert result["preflight_object_count"] == 0

    with pool.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == []
    assert pool.read_text(encoding="utf-8").splitlines()[0].split(",") == (
        recon.CSV_FIELDS
    )

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["blocker"]["code"] == "MISSING_ITEM_DURATION_COLUMN"
    assert plan["ranked_objects"] == []
    assert plan["authorization"]["authorized_for_full_acquisition"] == []
    assert "*" not in plan_path.read_text(encoding="utf-8")


def make_fixture(
    tmp_path: Path,
    *,
    durations: list[float | None],
    extension: str = ".mp4",
    duplicate_api_path: bool = False,
    conflicting_size: bool = False,
) -> tuple[Path, Path]:
    rows = []
    siblings = []
    for index, duration in enumerate(durations):
        video_id = f"video_{index:02d}"
        path = f"videos/{video_id}{extension}"
        rows.append(
            {
                "id": index + 1,
                "task": (
                    "temporal_ordering" if index % 2 == 0 else "event_counting"
                ),
                "dataset": "ego4d" if index % 4 == 0 else "youtube",
                "video_id": video_id,
                "video_path": path,
                "duration_seconds": duration,
                "question": [
                    "An interview explains a historical map.",
                    "A cook cuts food while a machine runs.",
                    "Athletes race as a crowd watches.",
                    "A driver explores an outdoor mountain road.",
                ][index % 4],
                "evidence": [
                    {
                        "id": 1,
                        "start_sec": 10.0,
                        "end_sec": 20.0 + index,
                        "description": "Exact evidence interval.",
                    }
                ],
                "source_question_id": f"{video_id}_001",
            }
        )
        size = 10_000 + index
        lfs_size = size + 1 if conflicting_size and index == 0 else size
        siblings.append(
            {
                "rfilename": path,
                "blobId": f"{index + 1:040x}",
                "size": size,
                "lfs": {
                    "sha256": f"{index + 1:064x}",
                    "size": lfs_size,
                    "pointerSize": 130,
                },
            }
        )
    if duplicate_api_path:
        siblings.append(dict(siblings[0]))
    api = {
        "id": recon.REPO_ID,
        "sha": recon.REVISION,
        "private": False,
        "gated": False,
        "siblings": siblings,
    }
    parquet_path = tmp_path / "fixture.parquet"
    api_path = tmp_path / "fixture.json"
    pq.write_table(pa.Table.from_pylist(rows), parquet_path)
    api_path.write_text(json.dumps(api), encoding="utf-8")
    return parquet_path, api_path


def load_fixture(parquet_path: Path, api_path: Path):
    schema, rows = recon.read_parquet(parquet_path)
    objects = recon.build_object_index(recon.load_api_snapshot(api_path))
    return schema, rows, objects


def test_duration_gate_boundaries_and_deterministic_diverse_ranking(
    tmp_path: Path,
) -> None:
    durations = [
        1199.999,
        1200.0,
        1300.0,
        1400.0,
        1500.0,
        1600.0,
        1700.0,
        1800.0,
        1900.0,
        2000.0,
        2100.0,
        2200.0,
        5400.0,
        5400.001,
    ]
    parquet_path, api_path = make_fixture(tmp_path, durations=durations)
    schema, rows, objects = load_fixture(parquet_path, api_path)
    joined, column = recon.join_rows(
        schema, rows, objects, require_duration=True
    )
    assert column == "duration_seconds"
    first = recon.select_diverse(joined, count=10)
    second = recon.select_diverse(joined, count=10)
    assert [item.video_id for item in first] == [item.video_id for item in second]
    assert all(recon.duration_in_gate(item.duration_s or 0) for item in first)
    assert "video_00" not in {item.video_id for item in first}
    assert "video_13" not in {item.video_id for item in first}
    candidates = recon.candidates_from_joined(first)
    assert len(candidates) == 10
    assert all("UNVERIFIED" in item.modality_role_hypothesis for item in candidates)
    assert all(item.full_acquisition_authorized is False for item in candidates)


def test_absent_item_duration_fails_closed(tmp_path: Path) -> None:
    parquet_path, api_path = make_fixture(tmp_path, durations=[1200.0])
    table = pq.read_table(parquet_path).drop(["duration_seconds"])
    pq.write_table(table, parquet_path)
    schema, rows, objects = load_fixture(parquet_path, api_path)
    with pytest.raises(recon.ReconError, match="MISSING_ITEM_DURATION_COLUMN"):
        recon.join_rows(schema, rows, objects, require_duration=True)


def test_null_duration_fails_closed(tmp_path: Path) -> None:
    parquet_path, api_path = make_fixture(tmp_path, durations=[None])
    schema, rows, objects = load_fixture(parquet_path, api_path)
    with pytest.raises(recon.ReconError, match="ABSENT_DURATION"):
        recon.join_rows(schema, rows, objects, require_duration=True)


def test_duplicate_sibling_path_is_ambiguous(tmp_path: Path) -> None:
    _, api_path = make_fixture(
        tmp_path, durations=[1200.0], duplicate_api_path=True
    )
    with pytest.raises(recon.ReconError, match="DUPLICATE_SIBLING_PATH"):
        recon.build_object_index(recon.load_api_snapshot(api_path))


def test_missing_mp4_join_fails(tmp_path: Path) -> None:
    parquet_path, api_path = make_fixture(tmp_path, durations=[1200.0])
    api = json.loads(api_path.read_text(encoding="utf-8"))
    api["siblings"] = []
    api_path.write_text(json.dumps(api), encoding="utf-8")
    schema, rows, objects = load_fixture(parquet_path, api_path)
    with pytest.raises(
        recon.ReconError, match="MP4_OBJECT_MISSING_FROM_SIBLING_INDEX"
    ):
        recon.join_rows(schema, rows, objects, require_duration=True)


def test_non_mp4_metadata_object_is_rejected(tmp_path: Path) -> None:
    parquet_path, api_path = make_fixture(
        tmp_path, durations=[1200.0], extension=".mkv"
    )
    schema, rows = recon.read_parquet(parquet_path)
    with pytest.raises(recon.ReconError, match="NON_MP4_METADATA_OBJECT"):
        recon.join_rows(schema, rows, {}, require_duration=True)


def test_conflicting_object_identity_is_rejected(tmp_path: Path) -> None:
    _, api_path = make_fixture(
        tmp_path, durations=[1200.0], conflicting_size=True
    )
    with pytest.raises(recon.ReconError, match="CONFLICTING_OBJECT_IDENTITY"):
        recon.build_object_index(recon.load_api_snapshot(api_path))


def test_plan_contains_exact_objects_and_no_authority(tmp_path: Path) -> None:
    parquet_path, api_path = make_fixture(
        tmp_path, durations=[1200.0 + index for index in range(12)]
    )
    schema, rows, objects = load_fixture(parquet_path, api_path)
    joined, duration_column = recon.join_rows(
        schema, rows, objects, require_duration=True
    )
    selected = recon.select_diverse(joined, count=10)
    candidates = recon.candidates_from_joined(selected)
    details = recon.schema_audit(schema, rows)
    details["duration_column"] = duration_column
    details["duration_finding"] = "PRESENT_AND_ITEM_LEVEL"
    plan = recon.build_plan(
        candidates,
        parquet_identity=recon.SnapshotIdentity("fixture.parquet", 1, "a" * 64),
        api_identity=recon.SnapshotIdentity("fixture.json", 1, "b" * 64),
        schema_details=details,
        joined_count=12,
        rows=rows,
        hypotheses=recon.hypothesis_audit(joined),
        preflight_count=6,
    )
    assert len(plan["ranked_objects"]) == 6
    assert all(item["repo_id"] == recon.REPO_ID for item in plan["ranked_objects"])
    assert all(item["revision"] == recon.REVISION for item in plan["ranked_objects"])
    assert all(item["evidence_rows"] for item in plan["ranked_objects"])
    assert plan["authorization"]["authorized_actions"] == []
    assert plan["authorization"]["authorized_for_full_acquisition"] == []
    assert "*" not in json.dumps(plan)


def test_tool_has_no_network_or_media_body_route() -> None:
    source = (ROOT / "tools/ves_long_candidate_recon.py").read_text(
        encoding="utf-8"
    )
    prohibited = [
        "requests.get(",
        "httpx.get(",
        "urlopen(",
        "curl ",
        "wget ",
        "Range:",
        "Authorization:",
        "X-Amz-Signature",
    ]
    assert not any(token in source for token in prohibited)


def test_no_video_payload_exists_beside_metadata_snapshot() -> None:
    snapshot_dir = PARQUET.parent
    media_suffixes = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
    assert not [
        path
        for path in snapshot_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in media_suffixes
    ]
