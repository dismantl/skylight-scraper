import os
import stat
from collections.abc import Mapping
from pathlib import Path


class CredentialError(ValueError):
    """Raised when Skylight authorization cannot be loaded safely."""


def load_authorization(auth_file: Path | None, environ: Mapping[str, str]) -> str:
    if auth_file is not None:
        if os.name == "posix" and stat.S_IMODE(auth_file.stat().st_mode) & 0o077:
            raise CredentialError(
                f"authorization file permissions are too broad: {auth_file}"
            )
        value = auth_file.read_text(encoding="ascii")
    else:
        value = environ.get("SKYLIGHT_AUTHORIZATION", "")

    value = value.rstrip("\r\n")
    if "\r" in value or "\n" in value:
        raise CredentialError("authorization must be a single line")
    if value.lower().startswith("authorization:"):
        value = value.split(":", 1)[1].strip()

    parts = value.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise CredentialError("authorization must use the Bearer scheme")
    return f"Bearer {parts[1]}"
