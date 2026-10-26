from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from tools import noaa_webinar_route_recon as recon


PAGE = "https://oceantoday.noaa.gov/deeperdive/webinars/example.html"
SMALL = "https://oceantoday.noaa.gov/deeperdive/webinars/example-sm.mp4"
LARGE = "https://oceantoday.noaa.gov/deeperdive/webinars/example-lg.mp4"
CDN_SMALL = (
    "https://cdn.oceanservice.noaa.gov/oceantodayprod/media/"
    "deeperdive/webinars/example-sm.mp4"
)


def html_page(*, include_youtube: bool = True) -> bytes:
    youtube = (
        '<iframe src="https://www.youtube.com/embed/not-an-object"></iframe>'
        if include_youtube
        else ""
    )
    return f"""
    <html><head><title> NOAA Test Webinar </title></head>
    <body>
      <video>
        <source src="example-lg.mp4" type="video/mp4"
                data-res="720p" label="720P">
        <source src="example-sm.mp4#t=12,99" type="video/mp4"
                data-res="360p" label="360P">
      </video>
      <a href="/deeperdive/webinars/example-lg.mp4">1280 x 720</a>
      <a href="/deeperdive/webinars/example-sm.mp4">640 x 360</a>
      <h2>Length: 50 minutes</h2>
      {youtube}
    </body></html>
    """.encode()


def page(candidate_id: str = "cand-048") -> recon.CandidatePage:
    return recon.CandidatePage(
        candidate_id=candidate_id,
        title="NOAA Test Webinar",
        page_url=PAGE,
        stable_source_id="NOAA-test",
        metadata_duration_prior_text="00:50:00",
        metadata_duration_prior_seconds=3000,
    )


def mock_client(handler) -> recon.MetadataOnlyNOAAClient:
    raw = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    return recon.MetadataOnlyNOAAClient(client=raw)


def head(
    url: str, size: int, *, label: str = ""
) -> recon.RouteHead:
    return recon.RouteHead(
        requested_url=url,
        effective_url=url,
        content_length=size,
        etag=f'"etag-{size}"',
        last_modified="Wed, 09 Sep 2026 00:00:00 GMT",
        content_type="video/mp4",
        accept_ranges="bytes",
        redirect_chain=(),
    )


def test_official_host_and_redirect_allowlists() -> None:
    assert recon.ocean_today_host_allowed("oceantoday.noaa.gov")
    assert not recon.ocean_today_host_allowed("www.noaa.gov")
    assert recon.direct_mp4_host_allowed("oceantoday.noaa.gov")
    assert recon.direct_mp4_host_allowed("cdn.oceanservice.noaa.gov")
    for host in (
        "media.noaa.gov",
        "cdn.noaa.gov",
        "oceanservice.noaa.gov",
        "cdn.oceanservice.noaa.gov.evil.example",
        "cdn-oceanservice.noaa.gov",
        "youtube.com",
    ):
        assert not recon.direct_mp4_host_allowed(host)
        assert not recon.noaa_redirect_host_allowed(host)


def test_page_route_extraction_strips_fragment_and_ignores_youtube() -> None:
    title, duration, routes = recon.extract_page_routes(PAGE, html_page())
    assert title == "NOAA Test Webinar"
    assert duration == "50 minutes"
    assert [item.url for item in routes] == [SMALL, LARGE]
    assert routes[0].small_hint == 0
    assert all("youtube" not in item.url for item in routes)


def test_page_route_extraction_accepts_exact_cdn_mp4_only() -> None:
    body = f"""
    <html><body>
      <video><source src="{CDN_SMALL}?download=1#clip"></video>
      <a href="https://media.noaa.gov/arbitrary.mp4">reject arbitrary NOAA</a>
      <a href="https://cdn.oceanservice.noaa.gov.evil.example/look.mp4">
        reject lookalike
      </a>
    </body></html>
    """.encode()
    _, _, routes = recon.extract_page_routes(PAGE, body)
    assert [item.url for item in routes] == [CDN_SMALL]


def test_prefer_exact_smallest_validated_rendition() -> None:
    class Stub:
        records: list[dict] = []

        def get_page(self, url: str):
            assert url == PAGE
            return url, html_page()

        def head_mp4(self, url: str):
            return head(url, 200 if url == SMALL else 900)

    plan = recon.reconcile([page()], Stub())  # type: ignore[arg-type]
    assert plan["available_exact_objects"][0]["url"] == SMALL
    assert plan["available_exact_objects"][0]["size_bytes"] == 200
    assert plan["objects"][0]["route_evidence"]["small_rendition_hint"] is True


def test_head_only_for_mp4_and_exact_headers_are_frozen() -> None:
    methods: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(
            (request.method, str(request.url), request.headers.get("range"))
        )
        if request.url.path.endswith(".html"):
            body = html_page()
            return httpx.Response(
                200,
                headers={
                    "content-length": str(len(body)),
                    "content-type": "text/html; charset=utf-8",
                },
                content=body,
            )
        size = 200 if request.url.path.endswith("-sm.mp4") else 900
        return httpx.Response(
            200,
            headers={
                "content-length": str(size),
                "content-type": "video/mp4",
                "etag": f'"etag-{size}"',
                "last-modified": "Wed, 09 Sep 2026 00:00:00 GMT",
                "accept-ranges": "bytes",
            },
        )

    client = mock_client(handler)
    plan = recon.reconcile([page()], client)
    selected = plan["objects"][0]
    assert selected["url"] == SMALL
    assert selected["size_bytes"] == 200
    assert selected["etag"] == '"etag-200"'
    assert selected["last_modified"] == "Wed, 09 Sep 2026 00:00:00 GMT"
    assert all(
        method == "HEAD"
        for method, url, _ in methods
        if url.endswith(".mp4")
    )
    assert all(range_header is None for _, _, range_header in methods)
    assert sum(record["body_bytes"] for record in client.records[1:]) == 0


def test_301_to_exact_ocean_service_cdn_is_accepted_and_frozen() -> None:
    requests: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (
                request.method,
                request.url.host,
                request.headers.get("authorization"),
            )
        )
        if request.url.host == recon.PAGE_HOST:
            return httpx.Response(
                301,
                headers={
                    "content-length": "0",
                    "location": f"{CDN_SMALL}?download=1#media-fragment",
                },
            )
        assert request.url.host == recon.OCEAN_SERVICE_CDN_HOST
        return httpx.Response(
            200,
            headers={
                "content-length": "321",
                "content-type": "video/mp4",
                "etag": '"cdn-etag"',
                "last-modified": "Wed, 09 Sep 2026 00:00:00 GMT",
                "accept-ranges": "bytes",
            },
            content=b"this HEAD body must never be consumed",
        )

    client = mock_client(handler)
    result = client.head_mp4(SMALL)
    assert result.effective_url == CDN_SMALL
    assert "?" not in result.effective_url
    assert "#" not in result.effective_url
    assert result.redirect_chain == (
        {
            "status_code": 301,
            "from_host": recon.PAGE_HOST,
            "to_host": recon.OCEAN_SERVICE_CDN_HOST,
            "location": CDN_SMALL,
        },
    )
    assert requests == [
        ("HEAD", recon.PAGE_HOST, None),
        ("HEAD", recon.OCEAN_SERVICE_CDN_HOST, None),
    ]
    assert client.records[-1]["body_bytes"] == 0


@pytest.mark.parametrize(
    "host",
    [
        "media.noaa.gov",
        "cdn.noaa.gov",
        "cdn.oceanservice.noaa.gov.evil.example",
    ],
)
def test_mp4_redirect_rejects_arbitrary_and_lookalike_hosts(host: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            301,
            headers={
                "content-length": "0",
                "location": f"https://{host}/object.mp4",
            },
        )

    with pytest.raises(recon.ReconError, match="NON_OFFICIAL_NOAA_HOST"):
        mock_client(handler).head_mp4(SMALL)


def test_page_body_limit_is_enforced_while_streaming() -> None:
    body = b"x" * (recon.MAX_PAGE_BYTES + 1)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=body,
        )

    with pytest.raises(
        recon.ReconError,
        match="PAGE_(?:CONTENT_LENGTH_EXCEEDS_LIMIT|BODY_LIMIT_EXCEEDED)",
    ):
        mock_client(handler).get_page(PAGE)


def test_redirect_outside_noaa_is_rejected() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={
                "content-length": "0",
                "location": "https://youtube.com/not-allowed",
            },
        )

    with pytest.raises(recon.ReconError, match="NON_OFFICIAL_NOAA_HOST"):
        mock_client(handler).get_page(PAGE)


def test_landing_page_redirect_to_cdn_is_rejected() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            301,
            headers={
                "content-length": "0",
                "location": (
                    "https://cdn.oceanservice.noaa.gov/"
                    "oceantodayprod/media/page.html"
                ),
            },
        )

    with pytest.raises(recon.ReconError, match="NON_OFFICIAL_NOAA_HOST"):
        mock_client(handler).get_page(PAGE)


def test_plan_keeps_page_duration_as_prior_only() -> None:
    class Stub:
        records: list[dict] = []

        def get_page(self, url: str):
            return url, html_page()

        def head_mp4(self, url: str):
            return head(url, 200 if url == SMALL else 900)

    plan = recon.reconcile([page()], Stub())  # type: ignore[arg-type]
    item = plan["objects"][0]
    assert item["metadata_duration_prior"]["csv_seconds"] == 3000
    assert item["actual_duration_seconds"] is None
    assert item["declared_audio_track"] is None
    assert item["stream_facts_status"].startswith("UNRESOLVED")


def test_checked_in_plan_is_valid_and_contains_no_wildcard() -> None:
    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root / recon.PLAN_PATH).read_text(encoding="utf-8"))
    recon.validate_plan(plan)
    assert plan["status"] in {
        "BLOCKED_INSUFFICIENT_EXACT_NOAA_ROUTES",
        "READY_FOR_BOUNDED_NOAA_STREAM_PREFLIGHT",
    }
    if plan["status"].startswith("READY"):
        assert recon.MIN_OBJECTS <= len(plan["objects"]) <= recon.MAX_OBJECTS
        assert all(
            recon.direct_mp4_host_allowed(
                httpx.URL(item["url"]).host or ""
            )
            for item in plan["objects"]
        )
    else:
        assert len(plan["objects"]) < recon.MIN_OBJECTS
    assert "*" not in json.dumps(plan)
