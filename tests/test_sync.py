import pytest

from skylight_scraper.client import Asset, SkylightError
from skylight_scraper.sync import sync_frame


class StubClient:
    def __init__(self, assets):
        self.assets = assets
        self.downloads = []

    def iter_assets(self):
        yield from self.assets

    def download_asset(self, asset, destination):
        self.downloads.append((asset, destination))
        destination.write_bytes(asset.asset_type.encode())


def make_asset(key, asset_type="photo", sender="sender@example.invalid"):
    return Asset(
        asset_key=key,
        asset_type=asset_type,
        asset_url=f"https://assets.example.invalid/{key}",
        created_at="2026-01-02T03:04:05.000Z",
        from_email=sender,
    )


def test_syncs_photos_and_videos_with_legacy_filenames(tmp_path):
    client = StubClient([make_asset("photo.jpg"), make_asset("video.mp4", "video")])

    result = sync_frame(client, tmp_path)

    expected_names = {
        "2026-01-02T03:04:05.000Z_sender@example.invalid_photo.jpg",
        "2026-01-02T03:04:05.000Z_sender@example.invalid_video.mp4",
    }
    assert {path.name for path in tmp_path.iterdir()} == expected_names
    assert result.found == 2
    assert result.downloaded == 2
    assert result.skipped == 0
    assert result.filtered == 0


def test_filters_senders_case_insensitively(tmp_path):
    client = StubClient(
        [
            make_asset("keep.jpg", sender="Allowed@Example.invalid"),
            make_asset("skip.jpg", sender="other@example.invalid"),
        ]
    )

    result = sync_frame(client, tmp_path, senders={"allowed@example.invalid"})

    assert [asset.asset_key for asset, _ in client.downloads] == ["keep.jpg"]
    assert result.filtered == 1


def test_skips_an_existing_destination(tmp_path):
    item = make_asset("photo.jpg")
    destination = tmp_path / "2026-01-02T03:04:05.000Z_sender@example.invalid_photo.jpg"
    destination.write_bytes(b"existing")
    client = StubClient([item])

    result = sync_frame(client, tmp_path)

    assert client.downloads == []
    assert destination.read_bytes() == b"existing"
    assert result.skipped == 1


def test_rejects_asset_metadata_that_could_escape_output_directory(tmp_path):
    client = StubClient([make_asset("../outside.jpg")])

    with pytest.raises(SkylightError, match="unsafe filename"):
        sync_frame(client, tmp_path)

    assert not (tmp_path.parent / "outside.jpg").exists()
