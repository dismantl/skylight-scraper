import os

import pytest

from skylight_scraper.auth import CredentialError, load_authorization


def test_loads_full_authorization_header_from_private_file(tmp_path):
    auth_file = tmp_path / "authorization"
    auth_file.write_text("Authorization: Bearer example-token\n")
    auth_file.chmod(0o600)

    assert load_authorization(auth_file, {}) == "Bearer example-token"


def test_rejects_authorization_file_readable_by_other_users(tmp_path):
    auth_file = tmp_path / "authorization"
    auth_file.write_text("Bearer example-token\n")
    auth_file.chmod(0o644)

    with pytest.raises(CredentialError, match="permissions"):
        load_authorization(auth_file, {})


def test_loads_authorization_from_environment():
    environ = {"SKYLIGHT_AUTHORIZATION": "Bearer example-token"}

    assert load_authorization(None, environ) == "Bearer example-token"


def test_rejects_multiline_authorization():
    environ = {"SKYLIGHT_AUTHORIZATION": "Bearer first\nBearer second"}

    with pytest.raises(CredentialError, match="single line"):
        load_authorization(None, environ)


def test_requires_bearer_authorization():
    environ = {"SKYLIGHT_AUTHORIZATION": "Basic example-token"}

    with pytest.raises(CredentialError, match="Bearer"):
        load_authorization(None, environ)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are unavailable")
def test_private_file_permission_check_uses_only_group_and_other_bits(tmp_path):
    auth_file = tmp_path / "authorization"
    auth_file.write_text("Bearer example-token\n")
    auth_file.chmod(0o400)

    assert load_authorization(auth_file, {}) == "Bearer example-token"
