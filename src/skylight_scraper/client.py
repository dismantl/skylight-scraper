import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_ROOT = "https://app.ourskylight.com/api"
DEFAULT_TIMEOUT = (5, 60)


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


class SkylightClient:
    def __init__(
        self,
        frame_id: int,
        authorization: str,
        *,
        session: requests.Session | None = None,
        media_session: requests.Session | None = None,
        base_url: str = API_ROOT,
        timeout: tuple[int, int] = DEFAULT_TIMEOUT,
    ):
        self.frame_id = frame_id
        self.session = session or build_session(authorization)
        self.media_session = media_session or build_media_session()
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
