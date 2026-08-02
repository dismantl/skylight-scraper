from dataclasses import dataclass
from pathlib import Path

from .client import SkylightClient, SkylightError


@dataclass(frozen=True)
class SyncResult:
    found: int
    downloaded: int
    skipped: int
    filtered: int


def sync_frame(
    client: SkylightClient,
    output: Path,
    *,
    senders: set[str] | None = None,
) -> SyncResult:
    output.mkdir(parents=True, exist_ok=True)
    allowed_senders = {sender.casefold() for sender in senders} if senders else None
    found = downloaded = skipped = filtered = 0

    for asset in client.iter_assets():
        found += 1
        if (
            allowed_senders is not None
            and asset.from_email.casefold() not in allowed_senders
        ):
            filtered += 1
            continue

        components = (asset.created_at, asset.from_email, asset.asset_key)
        if any(_is_unsafe_filename_component(component) for component in components):
            raise SkylightError("Skylight returned an unsafe filename component")
        filename = "_".join(components)
        destination = output / filename
        if destination.is_file():
            skipped += 1
            continue

        client.download_asset(asset, destination)
        downloaded += 1

    return SyncResult(
        found=found,
        downloaded=downloaded,
        skipped=skipped,
        filtered=filtered,
    )


def _is_unsafe_filename_component(component: str) -> bool:
    return (
        component in {".", ".."}
        or "/" in component
        or "\\" in component
        or "\0" in component
    )
