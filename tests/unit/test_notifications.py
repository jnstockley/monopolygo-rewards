import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from multiprocessing import get_context

import pytest

from monopolygo_rewards.config import Settings, load_settings
from monopolygo_rewards.models import RewardResult, RewardStatus, RunResult
from monopolygo_rewards.notifications import build_notification, send_bounded

T = datetime(2026, 11, 10, 3, tzinfo=UTC)
S = Settings("WonderfulFinch83")


def outcome(status=RewardStatus.SKIPPED):
    return RunResult(
        tuple(RewardResult(name, status, "cooldown", T) for name in ["wheel", "gift"]),
        "verified",
        T,
    )


def test_no_url_disables_and_url_is_not_in_settings_repr():
    assert build_notification(S, outcome()) is None
    s = replace(S, apprise_url="json://synthetic.invalid/secret-token", apprise_notify_on="all")
    assert "secret-token" not in repr(s)
    assert build_notification(s, outcome()) is not None


def test_error_only_default_and_success_mode_includes_skips():
    s = replace(S, apprise_url="json://synthetic.invalid/secret-token")
    assert build_notification(s, outcome()) is None
    assert build_notification(s, outcome(RewardStatus.CLAIMED)) is None
    for result in [
        RunResult((), "blocked", T, "Session rejected"),
        outcome(RewardStatus.UNCERTAIN),
        RunResult(outcome().results[:1], "verified", T),
    ]:
        message = build_notification(s, result)
        assert message is not None and message.failed
        assert "secret-token" not in message.body
    s = replace(s, apprise_notify_on="all", tz="America/Chicago")
    message = build_notification(s, outcome(), T + timedelta(hours=10))
    assert not message.failed
    assert "skipped" in message.body and "2026-11-10T07:00:00-06:00" in message.body
    assert build_notification(s, RunResult((), "verified", T), login_only=True).failed is False


def test_notification_settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXPECTED_USERNAME", "test")
    s = load_settings(overrides={"APPRISE_URL": "   ", "APPRISE_NOTIFY_ON": "all"})
    assert s.apprise_url == ""
    from monopolygo_rewards.errors import ConfigurationError

    with pytest.raises(ConfigurationError, match="APPRISE_NOTIFY_ON"):
        load_settings(overrides={"APPRISE_NOTIFY_ON": "unexpected"})


def stuck_delivery(url, message, pipe):
    while True:
        time.sleep(1)


def test_delivery_timeout_is_bounded_and_hides_url(caplog):
    s = replace(
        S,
        apprise_url="json://synthetic.invalid/secret-token",
        apprise_timeout=timedelta(seconds=0.2),
        apprise_notify_on="all",
    )
    started = time.monotonic()
    assert send_bounded(s, build_notification(s, outcome()), target=stuck_delivery) is False
    assert time.monotonic() - started < 3
    assert "secret-token" not in caplog.text


def test_worker_notifies_once_without_changing_exit_when_delivery_fails(tmp_path, monkeypatch):
    from monopolygo_rewards import notifications, worker

    sent = []

    def deliver(settings, message, **kwargs):
        sent.append(message)
        return False

    monkeypatch.setattr(notifications, "send_bounded", deliver)
    monkeypatch.setattr(worker, "supervise", lambda *a, **k: outcome())
    s = replace(
        S,
        data_dir=tmp_path,
        apprise_url="json://synthetic.invalid/secret-token",
        apprise_notify_on="all",
    )
    assert worker.run_worker(s, get_context("spawn").Event(), once=True) == 0
    assert len(sent) == 1 and not sent[0].failed
    monkeypatch.setattr(
        worker, "supervise", lambda *a, **k: RunResult((), "blocked", T, "Rejected session")
    )
    s = replace(s, apprise_notify_on="error")
    assert worker.run_worker(s, get_context("spawn").Event(), once=True) == 2
    assert len(sent) == 2 and sent[-1].failed


def test_missing_session_notifies_but_healthcheck_does_not(tmp_path, monkeypatch):
    from monopolygo_rewards import notifications
    from monopolygo_rewards.cli import main

    sent = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXPECTED_USERNAME", "test")
    monkeypatch.setenv("APPRISE_URL", "json://synthetic.invalid/secret-token")
    monkeypatch.setattr(notifications, "send_bounded", lambda s, m, **k: sent.append(m) or True)
    assert main(["--once"]) == 2
    assert len(sent) == 1 and sent[0].failed
    assert main(["healthcheck"]) == 1
    assert len(sent) == 1


@pytest.mark.parametrize("cleanup", ["artifacts", "health"])
@pytest.mark.parametrize("mode", ["all", "error"])
def test_cleanup_failure_does_not_send_two_summaries(tmp_path, monkeypatch, cleanup, mode):
    from monopolygo_rewards import cli, notifications, worker

    sent = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXPECTED_USERNAME", "test")
    monkeypatch.setenv("APPRISE_URL", "json://synthetic.invalid/secret-token")
    monkeypatch.setenv("APPRISE_NOTIFY_ON", mode)
    monkeypatch.setattr(cli, "load_cookies", lambda path: [])
    monkeypatch.setattr(worker, "supervise", lambda *a, **k: outcome())
    monkeypatch.setattr(notifications, "send_bounded", lambda s, m, **k: sent.append(m) or True)

    def fail(*args, **kwargs):
        raise PermissionError("Synthetic cleanup failure")

    if cleanup == "artifacts":
        monkeypatch.setattr(worker, "prune_artifacts", fail)
    else:
        write = worker.write_health
        monkeypatch.setattr(
            worker,
            "write_health",
            lambda s, status: fail() if status == "stopped" else write(s, status),
        )
    assert cli.main(["--once"]) == 2
    assert len(sent) == 1
    assert sent[0].failed


def test_startup_setting_defaults_and_validation(tmp_path, monkeypatch):
    from monopolygo_rewards.errors import ConfigurationError

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXPECTED_USERNAME", "test")
    assert load_settings().apprise_notify_startup is True
    assert (
        load_settings(overrides={"APPRISE_NOTIFY_STARTUP": "false"}).apprise_notify_startup is False
    )
    with pytest.raises(ConfigurationError, match="APPRISE_NOTIFY_STARTUP"):
        load_settings(overrides={"APPRISE_NOTIFY_STARTUP": "invalid"})


@pytest.mark.parametrize(
    "url,enabled,expected",
    [("", True, 0), ("json://synthetic.invalid", False, 0), ("json://synthetic.invalid", True, 1)],
)
def test_startup_notice_before_saved_deadline_wait(tmp_path, monkeypatch, url, enabled, expected):
    from monopolygo_rewards import notifications, worker
    from monopolygo_rewards.models import utcnow
    from monopolygo_rewards.scheduler import plan_next_run
    from monopolygo_rewards.state import save_state

    s = replace(
        S,
        data_dir=tmp_path,
        apprise_url=url,
        apprise_notify_startup=enabled,
        tz="America/Chicago",
        check_interval=timedelta(hours=1),
    )
    result = replace(outcome(), finished_at=utcnow())
    state = plan_next_run(s, None, result)
    save_state(tmp_path / "schedule.json", state)
    sent = []
    stop = get_context("spawn").Event()
    monkeypatch.setattr(notifications, "send_bounded", lambda s, m, **k: sent.append(m) or False)

    def wait(deadline, event, heartbeat):
        assert deadline == state.next_check_at
        assert len(sent) == expected
        event.set()

    monkeypatch.setattr(worker, "wait_until", wait)
    assert worker.run_worker(s, stop) == 0
    assert len(sent) == expected
    if expected:
        assert sent[0].title == "MONOPOLY GO: worker started"
        assert "WonderfulFinch83" in sent[0].body
        assert "Next check:" in sent[0].body and "-06:00" in sent[0].body
        assert "verified" not in sent[0].body.lower()


@pytest.mark.parametrize("login_only", [False, True])
def test_one_shot_commands_do_not_send_startup_notice(tmp_path, monkeypatch, login_only):
    from monopolygo_rewards import notifications, worker

    sent = []
    s = replace(S, data_dir=tmp_path, apprise_url="json://synthetic.invalid")
    monkeypatch.setattr(notifications, "send_bounded", lambda s, m, **k: sent.append(m) or True)
    monkeypatch.setattr(worker, "supervise", lambda *a, **k: outcome())
    assert (
        worker.run_worker(
            s, get_context("spawn").Event(), once=not login_only, login_only=login_only
        )
        == 0
    )
    assert sent == []
