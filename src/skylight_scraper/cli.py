import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from .auth import CredentialError, load_authorization, load_login_credentials
from .client import SkylightClient, SkylightError, build_login_session
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
        "--email-file",
        type=Path,
        help="private file containing the Skylight login email",
    )
    parser.add_argument(
        "--password-file",
        type=Path,
        help="private file containing the Skylight login password",
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
        use_bearer = args.auth_file is not None or bool(
            environ.get("SKYLIGHT_AUTHORIZATION")
        )
        use_login_files = args.email_file is not None or args.password_file is not None
        if use_bearer and use_login_files:
            raise CredentialError(
                "Bearer authorization and login credentials are mutually exclusive"
            )
        if use_bearer:
            authorization = load_authorization(args.auth_file, environ)
            client = SkylightClient(args.frame, authorization)
        else:
            credentials = load_login_credentials(
                args.email_file,
                args.password_file,
                environ,
            )
            session = build_login_session(credentials.email, credentials.password)
            client = SkylightClient(args.frame, session=session)
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
