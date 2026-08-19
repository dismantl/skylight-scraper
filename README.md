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

For unattended synchronization, store the Skylight account email and password
in separate files readable only by your user:

```console
chmod 600 /path/to/skylight-email /path/to/skylight-password
```

The scraper signs in through Skylight's web login at the start of each run,
completes the authorization-code exchange, and keeps the resulting Bearer token
in memory. The credentials and token are never placed in command-line arguments
or written to disk.

`SKYLIGHT_EMAIL` and `SKYLIGHT_PASSWORD` can be used instead of files. Avoid
placing their values directly in shell history.

The older `--auth-file` and `SKYLIGHT_AUTHORIZATION` inputs remain available for
short-lived interactive use, but Skylight expires those Bearer tokens and they
are not suitable for scheduled jobs.

## Usage

```console
uv run skylight-scraper \
  --frame 1234567 \
  --email-file /path/to/skylight-email \
  --password-file /path/to/skylight-password \
  --output /path/to/media
```

To download media only from specific senders, provide a comma-separated list:

```console
uv run skylight-scraper \
  --frame 1234567 \
  --email-file /path/to/skylight-email \
  --password-file /path/to/skylight-password \
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
