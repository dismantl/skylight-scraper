import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from uuid import NAMESPACE_URL, uuid5

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_ROOT = "https://app.ourskylight.com/api"
WEB_ROOT = "https://app.ourskylight.com"
DEFAULT_TIMEOUT = (5, 60)
OAUTH_CLIENT_ID = "skylight-mobile"
OAUTH_REDIRECT_URI = "https://ourskylight.com/welcome"
OAUTH_SCOPE = "everything"


class SkylightError(RuntimeError):
    """Base error for Skylight API and download failures."""


class AuthenticationError(SkylightError):
    """Raised when Skylight rejects the configured authorization."""


class ProtocolError(SkylightError):
    """Raised when Skylight returns an unexpected response shape."""


@dataclass(frozen=True)
class Asset:
    asset_key: str
    asset_type: str
    asset_url: str
    created_at: str
    from_email: str


def build_session(authorization: str) -> requests.Session:
    session = _retrying_session()
    session.headers.update({"Authorization": authorization})
    return session


def build_login_session(
    email: str,
    password: str,
    *,
    session: requests.Session | None = None,
    web_root: str = WEB_ROOT,
    timeout: tuple[int, int] = DEFAULT_TIMEOUT,
) -> requests.Session:
    session = session or _retrying_session()
    web_root = web_root.rstrip("/")
    login_url = f"{web_root}/auth/session"
    try:
        form = session.get(f"{login_url}/new", timeout=timeout)
        form.raise_for_status()
        parser = _AuthenticityTokenParser()
        parser.feed(form.text)
        if parser.token is None:
            raise ProtocolError("Skylight login form is missing its security token")
        response = session.post(
            login_url,
            data={
                "authenticity_token": parser.token,
                "email": email,
                "password": password,
            },
            headers={
                "Origin": web_root,
                "Referer": f"{login_url}/new",
            },
            allow_redirects=False,
            timeout=timeout,
        )
        login_target = urlparse(
            urljoin(response.url, response.headers.get("Location", ""))
        )
        if not 300 <= response.status_code < 400 or (
            login_target.path != "/auth/session/success"
        ):
            raise AuthenticationError("Skylight login was rejected")

        authorization_code = _request_authorization_code(
            session,
            web_root,
            timeout,
        )
        token_response = session.post(
            f"{web_root}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": OAUTH_CLIENT_ID,
                "scope": OAUTH_SCOPE,
                "redirect_uri": OAUTH_REDIRECT_URI,
                "code": authorization_code,
                "skylight_api_client_device_fingerprint": str(
                    uuid5(NAMESPACE_URL, f"skylight-scraper:{email.casefold()}")
                ),
                "skylight_api_client_device_platform": "web",
                "skylight_api_client_device_name": "skylight-scraper",
                "skylight_api_client_device_os_version": "unknown",
                "skylight_api_client_device_app_version": "unknown",
                "skylight_api_client_device_hardware": "unknown",
                "source": "js-mobile",
            },
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
        if token_response.status_code in {400, 401, 403, 422}:
            raise AuthenticationError("Skylight token exchange was rejected")
        token_response.raise_for_status()
        token_body = token_response.json()
        if not isinstance(token_body, dict):
            raise ProtocolError("Skylight token response is not an object")
        access_token = token_body.get("access_token")
        token_type = token_body.get("token_type")
        if not isinstance(access_token, str) or not access_token:
            raise ProtocolError("Skylight token response is missing an access token")
        if not isinstance(token_type, str) or token_type.casefold() != "bearer":
            raise ProtocolError("Skylight token response has an invalid token type")
        session.headers.update({"Authorization": f"Bearer {access_token}"})
    except (AuthenticationError, ProtocolError):
        raise
    except (requests.RequestException, ValueError) as exc:
        raise SkylightError("failed to authenticate with Skylight") from exc
    return session


def _request_authorization_code(
    session: requests.Session,
    web_root: str,
    timeout: tuple[int, int],
) -> str:
    authorize_url = f"{web_root}/oauth/authorize"
    authorize_params = {
        "client_id": OAUTH_CLIENT_ID,
        "response_type": "code",
        "scope": OAUTH_SCOPE,
        "redirect_uri": OAUTH_REDIRECT_URI,
    }
    next_url = f"{authorize_url}?{urlencode(authorize_params)}"
    expected_origin = urlparse(web_root)

    for _ in range(4):
        response = session.get(
            next_url,
            allow_redirects=False,
            timeout=timeout,
        )
        location = response.headers.get("Location")
        if not 300 <= response.status_code < 400 or not location:
            raise ProtocolError("Skylight authorization did not redirect")
        target = urlparse(urljoin(response.url, location))
        code = parse_qs(target.query).get("code", [None])[0]
        if code:
            return code
        if (target.scheme, target.netloc) != (
            expected_origin.scheme,
            expected_origin.netloc,
        ):
            raise ProtocolError("Skylight authorization redirected unexpectedly")
        next_url = target.geturl()

    raise ProtocolError("Skylight authorization code was not returned")


def build_media_session() -> requests.Session:
    return _retrying_session()


def _retrying_session() -> requests.Session:
    retries = Retry(
        total=3,
        allowed_methods=frozenset({"GET"}),
        status_forcelist={429, 500, 502, 503, 504},
        backoff_factor=0.5,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class _AuthenticityTokenParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag != "input":
            return
        attributes = dict(attrs)
        if attributes.get("name") == "authenticity_token":
            self.token = attributes.get("value")


class SkylightClient:
    def __init__(
        self,
        frame_id: int,
        authorization: str | None = None,
        *,
        session: requests.Session | None = None,
        media_session: requests.Session | None = None,
        base_url: str = API_ROOT,
        timeout: tuple[int, int] = DEFAULT_TIMEOUT,
    ):
        self.frame_id = frame_id
        if session is None and authorization is None:
            raise ValueError("authorization or an authenticated session is required")
        self.session = session or build_session(authorization or "")
        self.media_session = media_session or build_media_session()
        if authorization is not None:
            self.session.headers.update({"Authorization": authorization})
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def iter_assets(self) -> Iterator[Asset]:
        page_number = 1
        total_pages = 1
        while page_number <= total_pages:
            body = self._get_page(page_number)
            meta = body.get("meta")
            data = body.get("data")
            if not isinstance(meta, dict):
                raise ProtocolError("Skylight response is missing meta data")
            if not isinstance(data, list):
                raise ProtocolError("Skylight response data is not a list")

            current_page = meta.get("current_page")
            page_count = meta.get("num_pages")
            if current_page != page_number or not isinstance(page_count, int):
                raise ProtocolError("Skylight response has invalid pagination metadata")
            if page_number == 1:
                total_pages = page_count

            for item in data:
                yield self._parse_asset(item)
            page_number += 1

    def download_asset(self, asset: Asset, destination: Path) -> None:
        destination = Path(destination)
        temporary_path: Path | None = None
        response = None
        try:
            response = self.media_session.get(
                asset.asset_url,
                stream=True,
                timeout=self.timeout,
            )
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".part",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        temporary_file.write(chunk)
            os.replace(temporary_path, destination)
            temporary_path = None
        except (OSError, requests.RequestException) as exc:
            raise SkylightError(f"failed to download {asset.asset_key}") from exc
        finally:
            if response is not None:
                response.close()
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _get_page(self, page_number: int) -> dict[str, Any]:
        url = f"{self.base_url}/frames/{self.frame_id}/messages"
        try:
            response = self.session.get(
                url,
                params={"page": page_number},
                timeout=self.timeout,
            )
            if response.status_code in {401, 403}:
                raise AuthenticationError("Skylight authorization was rejected")
            response.raise_for_status()
            body = response.json()
        except AuthenticationError:
            raise
        except (requests.RequestException, ValueError) as exc:
            raise SkylightError(f"failed to fetch Skylight page {page_number}") from exc
        if not isinstance(body, dict):
            raise ProtocolError("Skylight response is not an object")
        return body

    @staticmethod
    def _parse_asset(item: object) -> Asset:
        if not isinstance(item, dict) or not isinstance(item.get("attributes"), dict):
            raise ProtocolError("Skylight asset is missing attributes")
        attributes = item["attributes"]
        required = (
            "asset_key",
            "asset_type",
            "asset_url",
            "created_at",
            "from_email",
        )
        if any(not isinstance(attributes.get(key), str) for key in required):
            raise ProtocolError("Skylight asset has invalid required attributes")
        return Asset(**{key: attributes[key] for key in required})
