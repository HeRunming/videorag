from __future__ import annotations

import copy
import hashlib
import io
import json
import os
from pathlib import Path

import httpx
import pytest

from tools import noaa_exact_asset_downloader as noaa


REPO_ROOT = Path(__file__).resolve().parents[1]


def ftyp_payload(length: int = 48) -> bytes:
    prefix = (
        (24).to_bytes(4, "big")
        + b"ftyp"
        + b"isom"
        + (0).to_bytes(4, "big")
        + b"isom"
        + b"mp42"
    )
    assert len(prefix) == 24
    return prefix + bytes((index % 251 for index in range(length - 24)))


def fixture_asset(payload: bytes) -> dict:
    asset = copy.deepcopy(noaa.derive_frozen_plan(REPO_ROOT)["assets"][0])
    asset["size_bytes"] = len(payload)
    return asset


def fixture_plan(asset: dict, *, chunk_bytes: int = 16) -> dict:
    return {
        "plan_id": noaa.PLAN_ID,
        "staging_root": noaa.STAGING_REL.as_posix(),
        "transfer_policy": {"chunk_bytes": chunk_bytes},
        "assets": [asset],
    }


def make_staging_tree(root: Path) -> None:
    (root / "data").mkdir(mode=0o755)
    (root / "data/restricted").mkdir(mode=0o755)
    (root / noaa.STAGING_REL).mkdir(mode=0o700)
    (root / noaa.STAGING_REL / "raw").mkdir(mode=0o700)
    (root / noaa.STAGING_REL / "manifests").mkdir(mode=0o700)


class FixtureFetcher:
    def __init__(self, asset: dict, payload: bytes) -> None:
        self.asset = asset
        self.payload = payload
        self.head_calls = 0
        self.ranges: list[tuple[int, int]] = []

    def validate_identity(self, asset: dict) -> noaa.ObservedIdentity:
        assert asset == self.asset
        self.head_calls += 1
        return noaa._expected_identity(asset)

    def fetch_range(
        self, asset: dict, start: int, end: int
    ) -> noaa.RangeResponse:
        assert asset == self.asset
        self.ranges.append((start, end))
        return noaa.RangeResponse(
            body=self.payload[start : end + 1],
            observed_etag=asset["etag"],
            observed_last_modified=asset["last_modified"],
        )


def test_frozen_plan_exact_selection_and_audit_binding() -> None:
    plan, digest = noaa.validate_frozen_plan(REPO_ROOT)
    authorization = noaa.validate_authorization(REPO_ROOT, plan, digest)

    assert digest == "241a476b503a198eafe208485206385f755cd57756f924e769ce8a37d1d1f6fd"
    assert plan["selection"]["candidate_ids"] == [
        "cand-045",
        "cand-047",
        "cand-049",
        "cand-051",
        "cand-052",
    ]
    assert plan["selection"]["excluded_candidate_ids"] == [
        "cand-046",
        "cand-048",
        "cand-054",
    ]
    assert len(plan["assets"]) == 5
    assert sum(item["size_bytes"] for item in plan["assets"]) == 1_955_298_193
    assert [item["basename"] for item in plan["assets"]] == list(
        noaa.ALLOWLIST
    )
    assert all(
        item["technical_audit"]["container_declared_audio_track_count"] == 1
        and item["technical_audit"]["local_audio_decode_checked"] is False
        and item["technical_audit"]["speech_or_ambient_semantics_checked"]
        is False
        for item in plan["assets"]
    )
    assert authorization["authorized_scope"]["plan_sha256"] == digest
    assert authorization["audit_basis"]["rights_and_public_redistribution"] == (
        "HELD_NOT_AUTHORIZED"
    )


def test_dry_run_is_offline_read_only_and_never_reads_hf_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        __import__("sys").modules,
        "huggingface_hub",
        type(
            "Trap",
            (),
            {"get_token": staticmethod(lambda: pytest.fail("HF token read"))},
        ),
    )
    result = noaa.dry_run(REPO_ROOT)
    assert result["status"] == "GO_EXACT_RESTRICTED_DOWNLOAD"
    assert result["asset_count"] == 5
    assert result["network_attempted"] is False
    assert result["credentials_read"] is False
    assert result["outputs_written"] is False


def test_plan_or_audit_drift_fails_closed(tmp_path: Path) -> None:
    for relative in (
        noaa.PREFLIGHT_PLAN_REL,
        noaa.PREFLIGHT_RESULT_REL,
        noaa.PLAN_REL,
        noaa.AUTHORIZATION_REL,
    ):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REPO_ROOT / relative).read_bytes())

    raw_plan = tmp_path / noaa.PLAN_REL
    plan = json.loads(raw_plan.read_text())
    plan["assets"][0]["size_bytes"] += 1
    raw_plan.write_bytes(noaa.canonical_json_bytes(plan))
    with pytest.raises(noaa.ConfigurationError, match="FROZEN_PLAN_DRIFT"):
        noaa.validate_frozen_plan(tmp_path)

    raw_plan.write_bytes((REPO_ROOT / noaa.PLAN_REL).read_bytes())
    result_path = tmp_path / noaa.PREFLIGHT_RESULT_REL
    result_path.write_bytes(result_path.read_bytes() + b" ")
    with pytest.raises(
        noaa.ConfigurationError, match="AUDIT_INPUT_INTEGRITY_MISMATCH"
    ):
        noaa.validate_frozen_plan(tmp_path)


def make_http_client(handler) -> noaa.SafeExactRangeClient:
    raw = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    return noaa.SafeExactRangeClient(
        client=raw,
        budget=noaa.WireBudget(
            maximum_response_bytes=64, maximum_total_bytes=4096
        ),
    )


def test_safe_client_exact_head_range_identity_and_no_credentials() -> None:
    asset = copy.deepcopy(noaa.FROZEN_SELECTION[0])
    asset.update(
        {
            "content_type": "video/mp4",
            "accept_ranges": "bytes",
        }
    )
    seen: list[
        tuple[str, str | None, str | None, str | None, str | None]
    ] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.method,
                request.headers.get("authorization"),
                request.headers.get("cookie"),
                request.headers.get("range"),
                request.headers.get("if-range"),
            )
        )
        common = {
            "etag": asset["etag"],
            "last-modified": asset["last_modified"],
            "content-type": "video/mp4",
            "accept-ranges": "bytes",
        }
        if request.method == "HEAD":
            return httpx.Response(
                200,
                headers={
                    **common,
                    "content-length": str(asset["size_bytes"]),
                },
            )
        start, end = map(
            int, request.headers["range"].removeprefix("bytes=").split("-")
        )
        body = bytes(range(end - start + 1))
        return httpx.Response(
            206,
            headers={
                **common,
                "content-length": str(len(body)),
                "content-range": (
                    f"bytes {start}-{end}/{asset['size_bytes']}"
                ),
                "content-encoding": "identity",
            },
            content=body,
        )

    client = make_http_client(handler)
    assert client.validate_identity(asset) == noaa._expected_identity(asset)
    response = client.fetch_range(asset, 10, 19)
    assert response.body == bytes(range(10))
    assert seen == [
        ("HEAD", None, None, None, None),
        ("GET", None, None, "bytes=10-19", None),
    ]


def test_range_only_avoids_if_range_200_incompatibility() -> None:
    asset = copy.deepcopy(noaa.FROZEN_SELECTION[0])
    asset.update({"content_type": "video/mp4", "accept_ranges": "bytes"})
    seen: list[tuple[str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        range_header = request.headers.get("range")
        if_range_header = request.headers.get("if-range")
        seen.append((range_header, if_range_header))
        if if_range_header is not None:
            return httpx.Response(
                200,
                headers={"content-length": "4"},
                content=b"full",
            )
        start, end = map(
            int, range_header.removeprefix("bytes=").split("-")
        )
        body = bytes(range(end - start + 1))
        return httpx.Response(
            206,
            headers={
                "etag": asset["etag"],
                "last-modified": asset["last_modified"],
                "content-type": asset["content_type"],
                "content-length": str(len(body)),
                "content-range": (
                    f"bytes {start}-{end}/{asset['size_bytes']}"
                ),
                "content-encoding": "identity",
            },
            content=body,
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as probe:
        incompatible = probe.get(
            asset["url"],
            headers={
                "Range": "bytes=0-9",
                "If-Range": asset["etag"],
                "Accept-Encoding": "identity",
            },
        )
    assert incompatible.status_code == 200

    raw = httpx.Client(transport=transport, follow_redirects=False)
    response = noaa.SafeExactRangeClient(
        client=raw,
        budget=noaa.WireBudget(
            maximum_response_bytes=64, maximum_total_bytes=4096
        ),
    ).fetch_range(asset, 0, 9)
    assert response.body == bytes(range(10))
    raw.close()
    assert seen == [
        ("bytes=0-9", asset["etag"]),
        ("bytes=0-9", None),
    ]


@pytest.mark.parametrize("changed_header", ["etag", "last-modified"])
def test_safe_client_rejects_changed_range_identity(
    changed_header: str,
) -> None:
    asset = copy.deepcopy(noaa.FROZEN_SELECTION[0])
    asset.update({"content_type": "video/mp4", "accept_ranges": "bytes"})

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("if-range") is None
        headers = {
            "etag": asset["etag"],
            "last-modified": asset["last_modified"],
            "content-type": asset["content_type"],
            "content-length": "10",
            "content-range": f"bytes 0-9/{asset['size_bytes']}",
            "content-encoding": "identity",
        }
        headers[changed_header] = "changed"
        return httpx.Response(206, headers=headers, content=b"x" * 10)

    with pytest.raises(noaa.SafetyError, match="RANGE_IDENTITY_MISMATCH"):
        make_http_client(handler).fetch_range(asset, 0, 9)


def test_safe_client_rejects_unfrozen_url_redirect_full_200_and_bad_range() -> None:
    asset = copy.deepcopy(noaa.FROZEN_SELECTION[0])
    asset.update({"content_type": "video/mp4", "accept_ranges": "bytes"})
    changed = copy.deepcopy(asset)
    changed["url"] = "https://cdn.oceanservice.noaa.gov/other.mp4"
    client = make_http_client(lambda _: pytest.fail("network not allowed"))
    with pytest.raises(noaa.SafetyError, match="REQUEST_ASSET_NOT_FROZEN"):
        client.validate_identity(changed)
    with pytest.raises(noaa.SafetyError, match="RANGE_OUTSIDE"):
        client.fetch_range(asset, -1, 2)

    redirect_client = make_http_client(
        lambda _: httpx.Response(
            302,
            headers={
                "location": asset["url"],
                "content-length": "0",
            },
        )
    )
    with pytest.raises(noaa.SafetyError, match="REDIRECT_PROHIBITED"):
        redirect_client.validate_identity(asset)

    full_client = make_http_client(
        lambda _: httpx.Response(
            200,
            headers={"content-length": "10"},
            content=b"x" * 10,
        )
    )
    with pytest.raises(noaa.SafetyError, match="FULL_OBJECT_200"):
        full_client.fetch_range(asset, 0, 9)


def test_resumable_download_atomic_sidecar_and_optional_sha256(
    tmp_path: Path,
) -> None:
    payload = ftyp_payload(56)
    asset = fixture_asset(payload)
    plan = fixture_plan(asset, chunk_bytes=16)
    make_staging_tree(tmp_path)
    destination = tmp_path / noaa.STAGING_REL / asset["destination"]
    partial = destination.with_name(destination.name + ".partial")
    state_path = destination.with_name(destination.name + ".partial.json")
    partial.write_bytes(payload[:16])
    os.chmod(partial, 0o600)
    state = noaa._asset_binding(asset, "a" * 64, 16)
    state.update(
        {
            "completed_bytes": 16,
            "prefix_sha256": hashlib.sha256(payload[:16]).hexdigest(),
        }
    )
    noaa.atomic_write_json(state_path, state, replace=False)

    fetcher = FixtureFetcher(asset, payload)
    result = noaa.Acquirer(
        tmp_path,
        plan,
        "a" * 64,
        fetcher,
        compute_whole_file_sha256=True,
        chunk_bytes=16,
        progress_stream=io.StringIO(),
    ).acquire_asset(asset, 1, 1)

    assert result["status"] == "downloaded"
    assert destination.read_bytes() == payload
    assert fetcher.head_calls == 1
    assert fetcher.ranges == [(16, 31), (32, 47), (48, 55)]
    assert not partial.exists()
    assert not state_path.exists()
    metadata_path = destination.with_name(
        destination.name + ".metadata.json"
    )
    metadata = json.loads(metadata_path.read_text())
    expected_hash = hashlib.sha256(payload).hexdigest()
    assert metadata["transfer_sha256"] == expected_hash
    assert metadata["whole_file_sha256"] == expected_hash
    assert metadata["expected_identity"]["etag"] == asset["etag"]
    assert metadata["observed_range_identity"] == {
        "etag": asset["etag"],
        "last_modified": asset["last_modified"],
    }
    assert metadata["authorization_boundary"][
        "public_release_or_redistribution_authorized"
    ] is False
    assert destination.stat().st_mode & 0o777 == 0o600
    assert metadata_path.stat().st_mode & 0o777 == 0o600


def test_zero_byte_partial_resumes_only_after_head_validation(
    tmp_path: Path,
) -> None:
    payload = ftyp_payload(48)
    asset = fixture_asset(payload)
    plan = fixture_plan(asset, chunk_bytes=16)
    make_staging_tree(tmp_path)
    destination = tmp_path / noaa.STAGING_REL / asset["destination"]
    partial = destination.with_name(destination.name + ".partial")
    state_path = destination.with_name(destination.name + ".partial.json")
    partial.write_bytes(b"")
    os.chmod(partial, 0o600)
    state = noaa._asset_binding(asset, "f" * 64, 16)
    state.update(
        {
            "completed_bytes": 0,
            "prefix_sha256": hashlib.sha256().hexdigest(),
        }
    )
    noaa.atomic_write_json(state_path, state, replace=False)

    events: list[str] = []

    class OrderedFetcher(FixtureFetcher):
        def validate_identity(
            self, requested_asset: dict
        ) -> noaa.ObservedIdentity:
            events.append("HEAD")
            return super().validate_identity(requested_asset)

        def fetch_range(
            self, requested_asset: dict, start: int, end: int
        ) -> noaa.RangeResponse:
            events.append(f"GET {start}-{end}")
            return super().fetch_range(requested_asset, start, end)

    fetcher = OrderedFetcher(asset, payload)
    result = noaa.Acquirer(
        tmp_path,
        plan,
        "f" * 64,
        fetcher,
        chunk_bytes=16,
        progress_stream=io.StringIO(),
    ).acquire_asset(asset, 1, 1)

    assert result["status"] == "downloaded"
    assert events == ["HEAD", "GET 0-15", "GET 16-31", "GET 32-47"]
    assert destination.read_bytes() == payload
    assert not partial.exists()
    assert not state_path.exists()


def test_completed_file_is_verified_without_network(tmp_path: Path) -> None:
    payload = ftyp_payload(48)
    asset = fixture_asset(payload)
    plan = fixture_plan(asset, chunk_bytes=16)
    make_staging_tree(tmp_path)
    fetcher = FixtureFetcher(asset, payload)
    acquirer = noaa.Acquirer(
        tmp_path,
        plan,
        "b" * 64,
        fetcher,
        chunk_bytes=16,
        progress_stream=io.StringIO(),
    )
    first = acquirer.acquire_asset(asset, 1, 1)
    assert first["status"] == "downloaded"

    second_fetcher = FixtureFetcher(asset, payload)
    second = noaa.Acquirer(
        tmp_path,
        plan,
        "b" * 64,
        second_fetcher,
        chunk_bytes=16,
        progress_stream=io.StringIO(),
    ).acquire_asset(asset, 1, 1)
    assert second["status"] == "skipped_verified"
    assert second_fetcher.head_calls == 0
    assert second_fetcher.ranges == []


def test_complete_partial_still_requires_live_exact_identity(
    tmp_path: Path,
) -> None:
    payload = ftyp_payload(48)
    asset = fixture_asset(payload)
    plan = fixture_plan(asset, chunk_bytes=16)
    make_staging_tree(tmp_path)
    destination = tmp_path / noaa.STAGING_REL / asset["destination"]
    partial = destination.with_name(destination.name + ".partial")
    state_path = destination.with_name(destination.name + ".partial.json")
    partial.write_bytes(payload)
    os.chmod(partial, 0o600)
    state = noaa._asset_binding(asset, "e" * 64, 16)
    state.update(
        {
            "completed_bytes": len(payload),
            "prefix_sha256": hashlib.sha256(payload).hexdigest(),
        }
    )
    noaa.atomic_write_json(state_path, state, replace=False)

    fetcher = FixtureFetcher(asset, payload)
    result = noaa.Acquirer(
        tmp_path,
        plan,
        "e" * 64,
        fetcher,
        chunk_bytes=16,
        progress_stream=io.StringIO(),
    ).acquire_asset(asset, 1, 1)
    assert result["status"] == "downloaded"
    assert fetcher.head_calls == 1
    assert fetcher.ranges == []


def test_path_traversal_symlink_and_permissive_file_are_rejected(
    tmp_path: Path,
) -> None:
    payload = ftyp_payload(48)
    asset = fixture_asset(payload)
    plan = fixture_plan(asset)
    make_staging_tree(tmp_path)
    acquirer = noaa.Acquirer(
        tmp_path,
        plan,
        "c" * 64,
        FixtureFetcher(asset, payload),
        progress_stream=io.StringIO(),
    )

    traversing = copy.deepcopy(asset)
    traversing["destination"] = "raw/../escape.mp4"
    with pytest.raises(noaa.SafetyError, match="DESTINATION_PATH_NOT_EXACT"):
        acquirer.acquire_asset(traversing, 1, 1)

    destination = tmp_path / noaa.STAGING_REL / asset["destination"]
    destination.symlink_to(tmp_path / "outside.mp4")
    with pytest.raises(noaa.SafetyError, match="SYMLINK_FILE_PROHIBITED"):
        acquirer.acquire_asset(asset, 1, 1)
    destination.unlink()

    destination.write_bytes(payload)
    os.chmod(destination, 0o644)
    with pytest.raises(noaa.SafetyError, match="PERMISSIVE_FILE_PROHIBITED"):
        acquirer.acquire_asset(asset, 1, 1)


def test_resume_rejects_nonboundary_or_state_drift(tmp_path: Path) -> None:
    payload = ftyp_payload(48)
    asset = fixture_asset(payload)
    plan = fixture_plan(asset, chunk_bytes=16)
    make_staging_tree(tmp_path)
    destination = tmp_path / noaa.STAGING_REL / asset["destination"]
    partial = destination.with_name(destination.name + ".partial")
    state_path = destination.with_name(destination.name + ".partial.json")
    partial.write_bytes(payload[:15])
    os.chmod(partial, 0o600)
    state = noaa._asset_binding(asset, "d" * 64, 16)
    state.update(
        {
            "completed_bytes": 15,
            "prefix_sha256": hashlib.sha256(payload[:15]).hexdigest(),
        }
    )
    noaa.atomic_write_json(state_path, state, replace=False)

    with pytest.raises(
        noaa.SafetyError, match="PARTIAL_NOT_ON_EXACT_CHUNK_BOUNDARY"
    ):
        noaa.Acquirer(
            tmp_path,
            plan,
            "d" * 64,
            FixtureFetcher(asset, payload),
            chunk_bytes=16,
            progress_stream=io.StringIO(),
        ).acquire_asset(asset, 1, 1)


def test_staging_tree_rejects_permissive_managed_directory(
    tmp_path: Path,
) -> None:
    (tmp_path / "data").mkdir(mode=0o755)
    (tmp_path / "data/restricted").mkdir(mode=0o755)
    staging = tmp_path / noaa.STAGING_REL
    staging.mkdir(mode=0o755)
    with pytest.raises(
        noaa.SafetyError, match="PERMISSIVE_MANAGED_DIRECTORY"
    ):
        noaa.ensure_staging_tree(tmp_path)
