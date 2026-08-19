import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class CredentialError(ValueError):
    """Raised when Skylight authorization cannot be loaded safely."""


@dataclass(frozen=True)
class LoginCredentials:
    email: str
    password: str


def load_login_credentials(
    email_file: Path | None,
    password_file: Path | None,
    environ: Mapping[str, str],
) -> LoginCredentials:
    email = _load_secret(email_file, environ, "SKYLIGHT_EMAIL", "email")
    password = _load_secret(
        password_file,
        environ,
        "SKYLIGHT_PASSWORD",
        "password",
    )
    if email != email.strip() or "@" not in email:
        raise CredentialError("Skylight email is invalid")
    return LoginCredentials(email=email, password=password)


def load_authorization(auth_file: Path | None, environ: Mapping[str, str]) -> str:
    value = _load_secret(
        auth_file,
        environ,
        "SKYLIGHT_AUTHORIZATION",
        "authorization",
        encoding="ascii",
    )
    if value.lower().startswith("authorization:"):
        value = value.split(":", 1)[1].strip()

    parts = value.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise CredentialError("authorization must use the Bearer scheme")
    return f"Bearer {parts[1]}"


def _load_secret(
    path: Path | None,
    environ: Mapping[str, str],
    environment_key: str,
    label: str,
    *,
    encoding: str = "utf-8",
) -> str:
    if path is not None:
        if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise CredentialError(f"{label} file permissions are too broad: {path}")
        value = path.read_text(encoding=encoding)
    else:
        value = environ.get(environment_key, "")

    value = value.rstrip("\r\n")
    if "\r" in value or "\n" in value:
        raise CredentialError(f"{label} must be a single line")
    if not value:
        raise CredentialError(f"{label} is required")
    return value
