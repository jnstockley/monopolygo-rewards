import subprocess
import sys

from monopolygo_rewards.cli import main


def test_help_does_not_require_credentials(monkeypatch):
    monkeypatch.delenv("EXPECTED_USERNAME", raising=False)
    result = subprocess.run(
        [sys.executable, "-m", "monopolygo_rewards", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "--once" in result.stdout


def test_missing_session_and_invalid_inspection_exit_before_browser(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXPECTED_USERNAME", "test")
    assert main(["--once"]) == 2
    assert main(["--keep-open"]) == 2
    monkeypatch.setenv("WHEEL_ENABLED", "false")
    monkeypatch.setenv("GIFT_ENABLED", "false")
    assert main(["--once"]) == 2


def test_import_command_needs_no_username_and_never_networks(tmp_path, monkeypatch):
    import json

    from monopolygo_rewards.session import AUTH_COOKIES

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EXPECTED_USERNAME", raising=False)
    path = tmp_path / "synthetic.har"
    path.write_text(
        json.dumps(
            {
                "log": {
                    "entries": [
                        {
                            "request": {
                                "url": "https://api.prod.monopolygo.com/web-portal/user-profile",
                                "method": "GET",
                                "cookies": [
                                    {"name": n, "value": "synthetic"} for n in AUTH_COOKIES
                                ],
                            },
                            "response": {"status": 200},
                        }
                    ]
                }
            }
        )
    )
    assert main(["import-session", "--har", str(path)]) == 0
    assert (tmp_path / "data/session.cookies").exists()
