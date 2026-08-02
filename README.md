# Skylight Scraper

Skylight Scraper synchronizes photos and videos from a Skylight digital picture
frame to a local directory. The output can be backed up or mirrored to another
photo service.

Skylight does not publish the API used by this project. The scraper can stop
working when Skylight changes its web application or private API.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- A Skylight account with access to the frame

## Setup

```console
git clone https://github.com/dismantl/skylight-scraper.git
cd skylight-scraper
uv sync
```

## Authentication

The scraper uses the Bearer authorization value from a logged-in Skylight
Desktop App session. It does not accept the authorization value as a command-line
argument because command-line secrets can be exposed through shell history and
process listings.

1. Log in at <https://ourskylight.com/>.
2. Open the browser developer tools and select the **Network** panel.
3. Select the frame and find a request whose path contains
   `/api/frames/<FRAME_ID>/messages`.
4. Copy the complete `Authorization` request-header value. It starts with
   `Bearer`.
5. Save that value in a file readable only by your user:

   ```console
   chmod 600 /path/to/skylight-authorization
   ```

The numeric frame ID is also present in that request path. Treat the
authorization value like a password and remove or replace the file if it is no
longer needed.

The `SKYLIGHT_AUTHORIZATION` environment variable can be used instead of an
authorization file. Avoid placing its value directly in shell history.

## Usage

```console
uv run skylight-scraper \
  --frame 1234567 \
  --auth-file /path/to/skylight-authorization \
  --output /path/to/media
```

To download media only from specific senders, provide a comma-separated list:

```console
uv run skylight-scraper \
  --frame 1234567 \
  --auth-file /path/to/skylight-authorization \
  --output /path/to/media \
  --senders first@example.com,second@example.com
```

Existing destination files are skipped. New files retain the original naming
scheme:

```text
<CREATED_AT>_<SENDER>_<ASSET_KEY>
```

Downloads are streamed to temporary files in the output directory and renamed
atomically after completion. Incomplete temporary files are removed after a
failed download.

## Development

Run the tests:

```console
uv run pytest
```

Build the package:

```console
uv build
```
