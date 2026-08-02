from skylight_scraper import cli
from skylight_scraper.client import AuthenticationError
from skylight_scraper.sync import SyncResult


def test_main_syncs_with_authorization_file_and_sender_filter(
    tmp_path, monkeypatch, capsys
):
    auth_file = tmp_path / "authorization"
    auth_file.write_text("Bearer example-token\n")
    auth_file.chmod(0o600)
    output = tmp_path / "output"
    observed = {}

    class StubClient:
        def __init__(self, frame_id, authorization):
            observed["frame_id"] = frame_id
            observed["authorization"] = authorization

    def stub_sync(client, destination, *, senders):
        observed["client"] = client
        observed["destination"] = destination
        observed["senders"] = senders
        return SyncResult(found=3, downloaded=1, skipped=1, filtered=1)

    monkeypatch.setattr(cli, "SkylightClient", StubClient)
    monkeypatch.setattr(cli, "sync_frame", stub_sync)

    result = cli.main(
        [
            "--frame",
            "42",
            "--auth-file",
            str(auth_file),
            "--output",
            str(output),
            "--senders",
            " First@Example.invalid, second@example.invalid ",
        ],
        environ={},
    )

    assert result == 0
    assert observed["frame_id"] == 42
    assert observed["authorization"] == "Bearer example-token"
    assert observed["destination"] == output
    assert observed["senders"] == {
        "First@Example.invalid",
        "second@example.invalid",
    }
    assert (
        "Found 3 assets; downloaded 1, skipped 1, filtered 1."
        in capsys.readouterr().out
    )


def test_main_uses_authorization_environment_variable(tmp_path, monkeypatch):
    observed = {}

    class StubClient:
        def __init__(self, frame_id, authorization):
            observed["authorization"] = authorization

    monkeypatch.setattr(cli, "SkylightClient", StubClient)
    monkeypatch.setattr(
        cli,
        "sync_frame",
        lambda client, output, *, senders: SyncResult(0, 0, 0, 0),
    )

    result = cli.main(
        ["--frame", "42", "--output", str(tmp_path)],
        environ={"SKYLIGHT_AUTHORIZATION": "Bearer environment-token"},
    )

    assert result == 0
    assert observed["authorization"] == "Bearer environment-token"


def test_main_reports_api_errors_without_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "SkylightClient", lambda frame_id, authorization: object())

    def fail_sync(client, output, *, senders):
        raise AuthenticationError("Skylight authorization was rejected")

    monkeypatch.setattr(cli, "sync_frame", fail_sync)

    result = cli.main(
        ["--frame", "42", "--output", str(tmp_path)],
        environ={"SKYLIGHT_AUTHORIZATION": "Bearer example-token"},
    )

    stderr = capsys.readouterr().err
    assert result == 1
    assert "Skylight authorization was rejected" in stderr
    assert "Traceback" not in stderr


def test_help_exposes_safe_authorization_inputs(capsys):
    parser = cli.build_parser()

    parser.print_help()

    help_text = capsys.readouterr().out
    assert "--auth-file" in help_text
    assert "SKYLIGHT_AUTHORIZATION" in help_text
    assert "-a AUTH" not in help_text
