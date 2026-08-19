from collections import deque

import pytest
import requests

from skylight_scraper.client import (
    Asset,
    AuthenticationError,
    ProtocolError,
    SkylightClient,
    SkylightError,
    build_login_session,
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
    def __init__(self, status_code, body, *, text="", headers=None, url=""):
        self.status_code = status_code
        self._body = body
        self.text = text
        self.headers = headers or {}
        self.url = url

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
        self.requests.append(("GET", url, kwargs))
        response = self.responses.popleft()
        response.url = response.url or url
        return response

    def post(self, url, **kwargs):
        self.requests.append(("POST", url, kwargs))
        response = self.responses.popleft()
        response.url = response.url or url
        return response


def test_build_login_session_posts_csrf_protected_credentials():
    login_form = """
    <form action="/auth/session" method="post">
      <input type="hidden" name="authenticity_token" value="csrf-token">
    </form>
    """
    session = StubSession(
        [
            StubResponse(200, None, text=login_form),
            StubResponse(
                302,
                None,
                headers={"Location": "/auth/session/success"},
            ),
            StubResponse(
                302,
                None,
                headers={
                    "Location": "https://ourskylight.com/welcome?code=example-code"
                },
            ),
            StubResponse(
                200,
                {
                    "access_token": "example-access-token",
                    "token_type": "Bearer",
                    "expires_in": 86400,
                    "refresh_token": "unused-refresh-token",
                },
            ),
        ]
    )

    result = build_login_session(
        "person@example.com",
        "example-password",
        session=session,
    )

    assert result is session
    assert session.headers["Authorization"] == "Bearer example-access-token"
    assert [request[:2] for request in session.requests] == [
        ("GET", "https://app.ourskylight.com/auth/session/new"),
        ("POST", "https://app.ourskylight.com/auth/session"),
        (
            "GET",
            (
                "https://app.ourskylight.com/oauth/authorize"
                "?client_id=skylight-mobile&response_type=code&scope=everything&"
                "redirect_uri=https%3A%2F%2Fourskylight.com%2Fwelcome"
            ),
        ),
        ("POST", "https://app.ourskylight.com/oauth/token"),
    ]
    login_request = session.requests[1][2]
    assert login_request["data"] == {
        "authenticity_token": "csrf-token",
        "email": "person@example.com",
        "password": "example-password",
    }
    assert login_request["headers"] == {
        "Origin": "https://app.ourskylight.com",
        "Referer": "https://app.ourskylight.com/auth/session/new",
    }
    assert login_request["allow_redirects"] is False
    token_request = session.requests[3][2]
    assert token_request["data"]["grant_type"] == "authorization_code"
    assert token_request["data"]["client_id"] == "skylight-mobile"
    assert token_request["data"]["code"] == "example-code"
    assert token_request["data"]["skylight_api_client_device_name"] == (
        "skylight-scraper"
    )


def test_build_login_session_rejects_invalid_credentials_without_response_body():
    session = StubSession(
        [
            StubResponse(
                200,
                None,
                text='<input name="authenticity_token" value="csrf-token">',
            ),
            StubResponse(422, {"password": "private detail"}),
        ]
    )

    with pytest.raises(AuthenticationError, match="login was rejected") as exc:
        build_login_session(
            "person@example.com",
            "wrong-password",
            session=session,
        )

    assert "private detail" not in str(exc.value)


def test_build_login_session_rejects_missing_authorization_code():
    session = StubSession(
        [
            StubResponse(
                200,
                None,
                text='<input name="authenticity_token" value="csrf-token">',
            ),
            StubResponse(
                302,
                None,
                headers={"Location": "/auth/session/success"},
            ),
            StubResponse(200, None),
        ]
    )

    with pytest.raises(ProtocolError, match="did not redirect"):
        build_login_session(
            "person@example.com",
            "example-password",
            session=session,
        )


def test_build_login_session_rejects_token_response_without_access_token():
    session = StubSession(
        [
            StubResponse(
                200,
                None,
                text='<input name="authenticity_token" value="csrf-token">',
            ),
            StubResponse(
                302,
                None,
                headers={"Location": "/auth/session/success"},
            ),
            StubResponse(
                302,
                None,
                headers={
                    "Location": "https://ourskylight.com/welcome?code=example-code"
                },
            ),
            StubResponse(200, {"token_type": "Bearer"}),
        ]
    )

    with pytest.raises(ProtocolError, match="missing an access token"):
        build_login_session(
            "person@example.com",
            "example-password",
            session=session,
        )


def test_build_login_session_requires_csrf_token():
    session = StubSession([StubResponse(200, None, text="<form></form>")])

    with pytest.raises(ProtocolError, match="security token"):
        build_login_session(
            "person@example.com",
            "example-password",
            session=session,
        )


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
    assert [request[2]["params"] for request in session.requests] == [
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
    assert media_session.requests[0][2]["stream"] is True
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
