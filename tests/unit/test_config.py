from datetime import timedelta

import pytest

from monopolygo_rewards.config import load_settings, parse_duration
from monopolygo_rewards.errors import ConfigurationError


@pytest.mark.parametrize(("text", "seconds"), [("1h 30m", 5400), ("90s", 90), ("1d2h3m4s", 93784)])
def test_duration(text, seconds):
    assert parse_duration(text) == timedelta(seconds=seconds)


@pytest.mark.parametrize("text", ["0s", "-1m", "1m1m", "1x", "nan", "1.5h"])
def test_invalid_duration(text):
    with pytest.raises(ValueError):
        parse_duration(text)


def test_settings_precedence_and_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("EXPECTED_USERNAME=dotenv\nCHECK_INTERVAL=2h\n")
    monkeypatch.setenv("EXPECTED_USERNAME", "environment")
    s = load_settings(overrides={"CHECK_INTERVAL": "1h"})
    assert s.expected_username == "environment"
    assert s.check_interval == timedelta(hours=1)
    assert s.session_file == tmp_path / "data/session.cookies"
    assert parse_duration("0s", allow_zero=True) == timedelta(0)


@pytest.mark.parametrize(
    "extra",
    [{"HEADLESS": "secret-invalid"}, {"ERROR_RETRY_MAX_INTERVAL": "1s"}, {"EXPECTED_USERNAME": ""}],
)
def test_invalid_settings_do_not_expose_values(tmp_path, monkeypatch, extra):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXPECTED_USERNAME", "test")
    with pytest.raises(ConfigurationError) as error:
        load_settings(overrides=extra)
    assert "secret-invalid" not in str(error.value)


def test_dotenv_does_not_expand_variables(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("EXPECTED_USERNAME=${SECRET}\n")
    monkeypatch.delenv("EXPECTED_USERNAME", raising=False)
    assert load_settings().expected_username == "${SECRET}"


def test_timezone_validated_and_environment_beats_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("EXPECTED_USERNAME=test\nTZ=UTC\n")
    monkeypatch.setenv("TZ", "America/Chicago")
    assert load_settings().tz == "America/Chicago"
    with pytest.raises(ConfigurationError, match="TZ"):
        load_settings(overrides={"TZ": "Invalid/Timezone"})
