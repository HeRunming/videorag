from __future__ import annotations

import csv
import json
from pathlib import Path

import httpx
import pytest

from tools import audio_asset_recon as recon


ROOT = Path(__file__).resolve().parents[1]


def test_offline_catalog_is_exact_and_fail_closed() -> None:
    candidates = recon.build_candidates(ROOT)
    assert len(candidates) == 16
    assert len({candidate.candidate_id for candidate in candidates}) == 16
    assert not any(candidate.audio_verified for candidate in candidates)

    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    assert by_id["cand-061"].exact_duration_s == 5375
    assert by_id["cand-023"].exact_duration_s == 2243
    assert by_id["cand-048"].exact_duration_s == 3000
    assert by_id["ccp-005"].object_size_bytes == 59708138
    assert (
        by_id["ccp-005"].object_hash
        == "40737590a6b572791746bea7a87ac80c270cdd0750e9aae65b1eeed08232c7c1"
    )
    assert by_id["omni-video_284"].object_size_bytes == 190135475
    assert by_id["omni-video_284"].duplicate_aliases == []
    assert (
        by_id["lvb-alt-ccp-003"].audio_status
        == "VERIFIED_ABSENT_CURRENT_RENDITION_ALTERNATE_NOT_LOCATED"
    )


def test_allowlist_is_shortlist_not_transfer_authorization() -> None:
    candidates = recon.build_candidates(ROOT)
    result = recon.proposed_allowlist(candidates, "offline")
    recon.validate_outputs(candidates, result)
    assert result["authorized_for_transfer"] == []
    assert result["audio_verified_count"] == 0
    assert [
        item["candidate_id"]
        for item in result["proposed_primary_after_gate_resolution"]
    ] == ["cand-061", "cand-048", "cand-051"]
    assert [
        item["candidate_id"]
        for item in result["proposed_reserves_after_gate_resolution"]
    ] == ["cand-056"]
    assert any(
        item["candidate_id"] == "cand-023"
        and item["reason"] == "STALE_OR_MISMATCHED_ID_HOLD"
        for item in result["rejected_or_deferred"]
    )


def test_duration_gate_is_exact_and_fail_closed() -> None:
    assert recon.duration_gate(1200) == "PASS"
    assert recon.duration_gate(5400) == "PASS"
    assert recon.duration_gate(1199.999) == "FAIL"
    assert recon.duration_gate(5400.001) == "FAIL"
    assert recon.duration_gate(None) == "UNRESOLVED"


def test_metadata_client_rejects_media_response_body() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, headers={"content-type": "video/mp4"}, content=b"not allowed"
        )
    )
    raw_client = httpx.Client(transport=transport, follow_redirects=False)
    client = recon.MetadataClient(client=raw_client)
    with pytest.raises(recon.ReconError, match="MEDIA_RESPONSE_BODY_PROHIBITED"):
        client.get_bytes(
            "https://huggingface.co/api/datasets/example/repo", "unit-test"
        )
    client.close()


def test_metadata_client_head_never_reads_body_and_get_is_bounded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(
                200,
                headers={"content-type": "video/mp4", "content-length": "999999"},
                content=b"ignored-by-head",
            )
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b'{"ok":true}',
        )

    raw_client = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    client = recon.MetadataClient(
        client=raw_client, max_response_bytes=32, max_total_bytes=32
    )
    record = client.head(
        "https://huggingface.co/datasets/example/repo/resolve/rev/file.mp4",
        "head-only",
    )
    assert record["body_bytes"] == 0
    assert client.get_json(
        "https://huggingface.co/api/datasets/example/repo", "metadata"
    ) == {"ok": True}
    assert client.total_bytes == 11
    client.close()


def test_metadata_client_does_not_forward_hf_token_to_redirect_host() -> None:
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.headers.get("authorization")))
        if request.url.host == "huggingface.co":
            return httpx.Response(
                302,
                headers={
                    "location": "https://commons.wikimedia.org/w/api.php",
                    "content-length": "0",
                },
            )
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b"{}",
        )

    client = recon.MetadataClient(
        "secret-token",
        client=httpx.Client(
            transport=httpx.MockTransport(handler), follow_redirects=False
        ),
    )
    assert client.get_json(
        "https://huggingface.co/api/datasets/example/repo", "redirect"
    ) == {}
    assert seen == [
        ("huggingface.co", "Bearer secret-token"),
        ("commons.wikimedia.org", None),
    ]
    client.close()


def test_metadata_client_reports_sanitized_endpoint_and_transport_error() -> None:
    secret = "do-not-print-this-token"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "proxy failed for "
            "https://huggingface.co/api/datasets/example/repo"
            f"?token={secret}&X-Amz-Signature={secret}",
            request=request,
        )

    client = recon.MetadataClient(
        secret,
        client=httpx.Client(
            transport=httpx.MockTransport(handler), follow_redirects=False
        ),
    )
    with pytest.raises(recon.ReconError) as caught:
        client.get_json(
            "https://huggingface.co/api/datasets/example/repo?revision=main",
            "repository-metadata",
        )
    diagnostic = caught.value.diagnostic()
    serialized = json.dumps(diagnostic)
    assert diagnostic == {
        "error": "LIVE_METADATA_REQUEST_FAILED",
        "purpose": "repository-metadata",
        "method": "GET",
        "endpoint": "https://huggingface.co/api/datasets/example/repo",
        "exception_class": "httpx.ConnectError",
        "exception_message": (
            "proxy failed for "
            "https://huggingface.co/api/datasets/example/repo"
        ),
        "proxy_attempts": ["injected-client"],
    }
    assert secret not in serialized
    assert "X-Amz-Signature" not in serialized
    assert client.records[-1]["body_bytes"] == 0
    client.close()


def test_explicit_proxy_configuration_is_used_without_env_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)

        def close(self) -> None:
            pass

    monkeypatch.setattr(recon.httpx, "Client", FakeClient)
    monkeypatch.setenv("HTTPS_PROXY", "http://ignored.example:9999")
    client = recon.MetadataClient(
        proxies=[
            "https://proxy.example.invalid:3128",
            "https://proxy.example.invalid:3128",
        ]
    )
    assert [item["proxy"] for item in created] == [
        "https://proxy.example.invalid:3128",
        "https://proxy.example.invalid:3128",
    ]
    assert all(item["trust_env"] is False for item in created)
    assert client.proxy_routes == [
        "https://proxy.example.invalid:3128",
        "https://proxy.example.invalid:3128",
    ]
    assert "password" not in json.dumps(client.proxy_routes)
    client.close()


def test_load_hf_token_falls_back_to_authenticated_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr("huggingface_hub.get_token", lambda: "cached-secret")
    assert recon.load_hf_token() == "cached-secret"


def test_run_live_metadata_preserves_partial_fail_closed_evidence() -> None:
    candidates = recon.build_candidates(ROOT)
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    by_id["cand-061"].official_download_route_status = ""

    class PartialClient:
        proxy_routes = ["test-proxy:3128"]
        total_bytes = 31
        records: list[dict[str, object]] = []

        def get_json(self, url: str, purpose: str) -> object:
            if purpose == "cand-061:commons-file-metadata":
                return {
                    "query": {
                        "pages": [
                            {
                                "pageid": 61,
                                "lastrevid": 610,
                                "imageinfo": [
                                    {
                                        "size": 6100,
                                        "sha1": "abc61",
                                        "mime": "video/webm",
                                        "url": (
                                            "https://upload.wikimedia.org/"
                                            "wikipedia/commons/example.webm"
                                        ),
                                        "metadata": [
                                            {"name": "length", "value": 5375},
                                            {"name": "audiocodec", "value": "opus"},
                                            {"name": "audiochannels", "value": 2},
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                }
            raise recon.ReconError(
                "LIVE_METADATA_REQUEST_FAILED",
                purpose=purpose,
                method="GET",
                endpoint=recon.safe_endpoint(url),
                exception_class="httpx.ConnectError",
                exception_message="[Errno -2] Name or service not known",
                proxy_attempts=["test-proxy:3128"],
            )

        def get_bytes(self, url: str, purpose: str) -> bytes:
            raise recon.ReconError(
                "LIVE_METADATA_REQUEST_FAILED",
                purpose=purpose,
                method="GET",
                endpoint=recon.safe_endpoint(url),
                exception_class="httpx.ConnectError",
                exception_message="[Errno -2] Name or service not known",
                proxy_attempts=["test-proxy:3128"],
            )

        def head(self, url: str, purpose: str) -> dict[str, object]:
            self.records.append(
                {
                    "purpose": purpose,
                    "status": "OK",
                    "method": "HEAD",
                    "endpoint": recon.safe_endpoint(url),
                    "body_bytes": 0,
                }
            )
            return self.records[-1]

    client = PartialClient()
    evidence = recon.run_live_metadata(
        candidates, client, hf_token_available=True  # type: ignore[arg-type]
    )
    assert evidence["status"] == "PARTIAL"
    assert evidence["network"]["huggingface_token_available"] is True
    assert evidence["network"]["credentials_persisted"] is False
    assert any(
        item["candidate_id"] == "cand-061"
        and item["object_hash"] == "abc61"
        and item["audio_verified"] is False
        for item in evidence["candidate_evidence_summary"]
    )
    assert by_id["cand-061"].audio_status == (
        "ITEM_METADATA_DECLARES_AUDIO_NOT_INDEPENDENTLY_PROBED"
    )
    assert by_id["cand-061"].audio_verified is False
    allowlist = recon.proposed_allowlist(candidates, "live", evidence)
    recon.validate_outputs(candidates, allowlist)
    assert allowlist["authorized_for_transfer"] == []
    assert allowlist["live_precheck_complete"] is False


def test_hf_live_absent_optional_fields_preserve_pinned_metadata() -> None:
    candidate = recon.Candidate(
        candidate_id="x",
        route_priority=1,
        route_class="test",
        shortlist_tier="test",
        source_family="HF",
        title="Example",
        canonical_item_id="example",
        official_item_url=(
            "https://huggingface.co/datasets/example/repo/blob/pinned/video.mp4"
        ),
        release_id="example/repo",
        release_revision="pinned",
        object_path="video.mp4",
        object_blob_id="pinned-blob",
        object_size_bytes=1234,
        object_hash_algorithm="sha256",
        object_hash="abc",
        official_download_url=(
            "https://huggingface.co/datasets/example/repo/resolve/pinned/video.mp4"
        ),
    )
    recon._apply_hf_object(
        candidate,
        {"siblings": [{"rfilename": "video.mp4"}]},
        "video.mp4",
        evidence_source="live_hf_api:example/repo",
        conflict_is_fatal=True,
    )
    assert candidate.object_blob_id == "pinned-blob"
    assert candidate.object_size_bytes == 1234
    assert candidate.object_hash == "abc"
    assert candidate.release_revision == "pinned"
    assert candidate.official_download_url.endswith("/pinned/video.mp4")
    assert candidate.metadata_conflicts == []


def test_hf_live_conflict_is_recorded_and_pinned_value_is_preserved() -> None:
    candidate = recon.Candidate(
        candidate_id="x",
        route_priority=1,
        route_class="test",
        shortlist_tier="test",
        source_family="HF",
        title="Example",
        canonical_item_id="example",
        official_item_url="https://huggingface.co/datasets/example/repo",
        release_id="example/repo",
        release_revision="pinned",
        object_path="video.mp4",
        object_size_bytes=1234,
    )
    with pytest.raises(recon.ReconError, match="LIVE_METADATA_CONFLICT") as caught:
        recon._apply_hf_object(
            candidate,
            {"siblings": [{"rfilename": "video.mp4", "size": 5678}]},
            "video.mp4",
            evidence_source="live_hf_api:example/repo",
            conflict_is_fatal=True,
        )
    assert candidate.object_size_bytes == 1234
    assert candidate.disposition == "METADATA_CONFLICT_HOLD"
    assert candidate.metadata_conflicts == [
        {
            "field": "object_size_bytes",
            "pinned_value": 1234,
            "live_value": 5678,
            "evidence_source": "live_hf_api:example/repo",
        }
    ]
    assert caught.value.diagnostic()["field"] == "object_size_bytes"


@pytest.mark.parametrize(
    ("field_name", "pinned_value"),
    [
        ("object_size_bytes", 1234),
        ("object_hash", "abc"),
        ("object_blob_id", "blob"),
        ("release_revision", "revision"),
        ("exact_duration_s", 1300.0),
        ("official_download_url", "https://huggingface.co/example"),
    ],
)
def test_absent_live_field_never_erases_stronger_pinned_value(
    field_name: str, pinned_value: object
) -> None:
    candidate = recon.Candidate(
        candidate_id="x",
        route_priority=1,
        route_class="test",
        shortlist_tier="test",
        source_family="test",
        title="Example",
        canonical_item_id="example",
        official_item_url="https://huggingface.co/example",
    )
    setattr(candidate, field_name, pinned_value)
    changed = recon._merge_evidence_field(
        candidate,
        field_name,
        None,
        "live-test",
        conflict_is_fatal=True,
    )
    assert changed is False
    assert getattr(candidate, field_name) == pinned_value
    assert candidate.metadata_conflicts == []


def test_cand_023_title_mismatch_is_an_identity_hold() -> None:
    candidate = {
        item.candidate_id: item for item in recon.build_candidates(ROOT)
    }["cand-023"]
    with pytest.raises(
        recon.ReconError, match="OFFICIAL_PAGE_TITLE_MARKER_NOT_FOUND"
    ):
        recon.apply_official_page_live(
            candidate,
            b"<html><title>Different current SVS record</title></html>",
        )
    assert candidate.shortlist_tier == "HOLD"
    assert candidate.disposition == "STALE_OR_MISMATCHED_ID_HOLD"
    assert candidate.publication_role == "IDENTITY_MAPPING_HOLD_NOT_ACTIVE"
    assert "disputed_identity" in candidate.duration_evidence_class
    assert candidate.official_item_url == "https://svs.gsfc.nasa.gov/11205/"


def test_commons_item_page_fallback_confirms_identity_only() -> None:
    candidate = recon.Candidate(
        candidate_id="x",
        route_priority=1,
        route_class="test",
        shortlist_tier="test",
        source_family="Commons",
        title="Example lecture.webm",
        canonical_item_id="CommonsFile:Example lecture.webm",
        official_item_url=(
            "https://commons.wikimedia.org/wiki/File:Example_lecture.webm"
        ),
        object_path="Example lecture.webm",
        exact_duration_s=1300,
    )
    recon.apply_commons_item_page_live(
        candidate,
        b"<html><title>File:Example lecture.webm - Wikimedia Commons</title></html>",
    )
    assert candidate.exact_duration_s == 1300
    assert candidate.object_size_bytes is None
    assert candidate.object_hash == ""
    assert candidate.official_download_url == ""
    assert "identity only" in candidate.notes


def test_apply_commons_live_records_declaration_without_verifying_audio() -> None:
    candidate = recon.Candidate(
        candidate_id="x",
        route_priority=1,
        route_class="test",
        shortlist_tier="test",
        source_family="Commons",
        title="Example",
        canonical_item_id="old",
        official_item_url="https://commons.wikimedia.org/wiki/File:Example.webm",
    )
    payload = {
        "query": {
            "pages": [
                {
                    "pageid": 42,
                    "lastrevid": 99,
                    "imageinfo": [
                        {
                            "size": 1234,
                            "sha1": "abc",
                            "mime": "video/webm",
                            "metadata": [
                                {"name": "length", "value": 1300},
                                {"name": "audiocodec", "value": "opus"},
                                {"name": "audiochannels", "value": 2},
                            ],
                        }
                    ],
                }
            ]
        }
    }
    recon.apply_commons_live(candidate, payload)
    assert candidate.exact_duration_s == 1300
    assert candidate.audio_status == "ITEM_METADATA_DECLARES_AUDIO_NOT_INDEPENDENTLY_PROBED"
    assert candidate.audio_verified is False
    assert candidate.object_size_bytes == 1234
    assert candidate.release_revision == "99"


def test_cli_writes_expected_outputs(tmp_path: Path) -> None:
    # The tool needs the repository evidence, so write to the real declared
    # paths through its pure writer and verify a temporary serialization too.
    candidates = recon.build_candidates(ROOT)
    allowlist = recon.proposed_allowlist(candidates, "offline")
    csv_path = tmp_path / "candidates.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=recon.CSV_FIELDS)
        writer.writeheader()
        writer.writerows(candidate.as_row() for candidate in candidates)
    json_path = tmp_path / "allowlist.json"
    json_path.write_text(json.dumps(allowlist), encoding="utf-8")
    assert len(list(csv.DictReader(csv_path.open(encoding="utf-8")))) == 16
    assert json.loads(json_path.read_text())["authorized_for_transfer"] == []


def test_stream_preflight_proposal_has_exact_scope_and_no_authority() -> None:
    candidates = recon.build_candidates(ROOT)
    evidence = {
        "status": "FAIL",
    }
    proposal = recon.stream_preflight_proposal(candidates, evidence)
    recon.validate_preflight_proposal(proposal)
    assert proposal["decision"] == "NO_GO_STREAM_PREFLIGHT_OR_ACQUISITION"
    assert proposal["authorized_for_stream_header_preflight"] == []
    assert proposal["authorized_for_full_acquisition"] == []
    assert proposal["authorized_for_transfer"] == []
    assert [
        item["candidate_id"]
        for item in proposal["item_scoped_identity_and_authority_requests"]
    ] == ["cand-061", "cand-056", "cand-048", "cand-051"]
    assert proposal["identity_mapping_holds"][0]["candidate_id"] == "cand-023"
    by_id = {
        item["candidate_id"]: item
        for item in proposal["exact_compatibility_objects_deferred"]
    }
    assert by_id["ccp-005"]["object_size_bytes"] == 59708138
    assert (
        by_id["ccp-005"]["object_hash"]
        == "40737590a6b572791746bea7a87ac80c270cdd0750e9aae65b1eeed08232c7c1"
    )
    assert by_id["omni-video_284"]["duration_gate"] == "UNRESOLVED"
    assert not any(
        item["audio_verified"]
        for item in proposal["exact_compatibility_objects_deferred"]
    )
