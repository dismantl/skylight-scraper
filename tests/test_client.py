from collections import deque

import pytest
import requests

from skylight_scraper.client import (
    Asset,
    AuthenticationError,
    ProtocolError,
    SkylightClient,
    SkylightError,
    build_media_session,
    build_session,
)


def asset(asset_key, asset_type):
    return {
        "id": f"message-{asset_key}",
        "type": "message",
        "attributes": {
            "asset_bucket": "example-bucket",
            "asset_key": asset_key,
            "asset_type": asset_type,
            "asset_url": f"https://assets.example.invalid/{asset_key}",
            "caption": "",
            "comments_count": 0,
            "created_at": "2026-01-02T03:04:05.000Z",
            "destroyed_at": None,
            "frame_id": 42,
            "frame_name": "Example Frame",
            "frame_owner_id": 7,
            "from_email": "sender@example.invalid",
            "month_in_review_display_date": None,
            "sender_id": 8,
            "thumbnail_key": None,
            "thumbnail_url": f"https://assets.example.invalid/thumb-{asset_key}",
        },
    }


def page(number, total, items):
    return {
        "meta": {
            "current_page": number,
            "frame_owner": True,
            "num_pages": total,
            "trial_days_remaining": None,
        },
        "data": items,
    }


class StubResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class StubSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = deque(responses)
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses.popleft()


def test_iterates_assets_page_by_page():
    session = StubSession(
        [
            StubResponse(200, page(1, 2, [asset("photo.jpg", "photo")])),
            StubResponse(200, page(2, 2, [asset("video.mp4", "video")])),
        ]
    )
    client = SkylightClient(42, "Bearer example-token", session=session)

    assets = list(client.iter_assets())

    assert [item.asset_key for item in assets] == ["photo.jpg", "video.mp4"]
    assert [item.asset_type for item in assets] == ["photo", "video"]
    assert [request[1]["params"] for request in session.requests] == [
        {"page": 1},
        {"page": 2},
    ]
    assert session.headers["Authorization"] == "Bearer example-token"


def test_reports_authentication_failure_without_exposing_response_body():
    session = StubSession([StubResponse(401, {"errors": ["private detail"]})])
    client = SkylightClient(42, "Bearer example-token", session=session)

    with pytest.raises(AuthenticationError, match="authorization was rejected") as exc:
        list(client.iter_assets())

    assert "private detail" not in str(exc.value)


def test_rejects_malformed_page_data():
    session = StubSession([StubResponse(200, {"meta": {"num_pages": 1}})])
    client = SkylightClient(42, "Bearer example-token", session=session)

    with pytest.raises(ProtocolError, match="data"):
        list(client.iter_assets())


def test_default_session_retries_transient_get_failures():
    session = build_session("Bearer example-token")

    retries = session.get_adapter("https://").max_retries
    assert retries.total == 3
    assert retries.allowed_methods == frozenset({"GET"})
    assert {429, 500, 502, 503, 504}.issubset(retries.status_forcelist)


class DownloadResponse(StubResponse):
    def __init__(self, chunks):
        super().__init__(200, None)
        self.chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size):
        assert chunk_size > 0
        yield from self.chunks

    def close(self):
        self.closed = True


def test_downloads_media_atomically_without_account_authorization(tmp_path):
    response = DownloadResponse([b"first", b"second"])
    media_session = StubSession([response])
    client = SkylightClient(
        42,
        "Bearer example-token",
        session=StubSession([]),
        media_session=media_session,
    )
    item = Asset(
        asset_key="photo.jpg",
        asset_type="photo",
        asset_url="https://assets.example.invalid/photo.jpg",
        created_at="2026-01-02T03:04:05.000Z",
        from_email="sender@example.invalid",
    )
    destination = tmp_path / "photo.jpg"

    client.download_asset(item, destination)

    assert destination.read_bytes() == b"firstsecond"
    assert not list(tmp_path.glob("*.part"))
    assert "Authorization" not in media_session.headers
    assert media_session.requests[0][1]["stream"] is True
    assert response.closed is True


def test_removes_partial_download_after_stream_failure(tmp_path):
    def failing_chunks():
        yield b"partial"
        raise requests.ConnectionError("connection reset")

    media_session = StubSession([DownloadResponse(failing_chunks())])
    client = SkylightClient(
        42,
        "Bearer example-token",
        session=StubSession([]),
        media_session=media_session,
    )
    item = Asset(
        asset_key="video.mp4",
        asset_type="video",
        asset_url="https://assets.example.invalid/video.mp4",
        created_at="2026-01-02T03:04:05.000Z",
        from_email="sender@example.invalid",
    )
    destination = tmp_path / "video.mp4"

    with pytest.raises(SkylightError, match="download"):
        client.download_asset(item, destination)

    assert not destination.exists()
    assert not list(tmp_path.iterdir())


def test_media_session_has_retries_but_no_authorization():
    session = build_media_session()

    assert "Authorization" not in session.headers
    assert session.get_adapter("https://").max_retries.total == 3
