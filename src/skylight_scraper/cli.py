import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from .auth import CredentialError, load_authorization
from .client import SkylightClient, SkylightError
from .sync import sync_frame


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skylight-scraper",
        description="Sync media from a Skylight Frame to a local directory",
    )
    parser.add_argument(
        "-f",
        "--frame",
        required=True,
        type=int,
        help="numeric ID of the frame to download from",
    )
    parser.add_argument(
        "--auth-file",
        type=Path,
        help=(
            "private file containing the Bearer authorization header; "
            "defaults to SKYLIGHT_AUTHORIZATION"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="directory to download media to",
    )
    parser.add_argument(
        "-s",
        "--senders",
        help="only download media sent by these comma-separated email addresses",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if environ is None:
        environ = os.environ

    senders = None
    if args.senders:
        senders = {
            sender.strip() for sender in args.senders.split(",") if sender.strip()
        }

    try:
        authorization = load_authorization(args.auth_file, environ)
        client = SkylightClient(args.frame, authorization)
        result = sync_frame(client, args.output, senders=senders)
    except (CredentialError, SkylightError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Found {result.found} assets; downloaded {result.downloaded}, "
        f"skipped {result.skipped}, filtered {result.filtered}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
