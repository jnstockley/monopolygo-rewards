import os

from monopolygo_rewards.diagnostics import prune_artifacts, safe_error


def test_raw_exception_details_never_reach_safe_error():
    secret = "cookie=synthetic-secret https://example.test/token"
    assert secret not in safe_error(RuntimeError(secret))
    assert "synthetic-secret" not in safe_error(RuntimeError(secret))


def test_retention_only_removes_app_regular_files(tmp_path):
    old = tmp_path / "daily-rewards-20000101T000000000000Z.png"
    other = tmp_path / "important.png"
    old.write_text("synthetic")
    other.write_text("keep")
    link = tmp_path / "daily-rewards-20000102T000000000000Z.png"
    link.symlink_to(other)
    for p in (old, other):
        os.utime(p, (0, 0))
    prune_artifacts(tmp_path, 7)
    assert not old.exists()
    assert other.exists() and link.is_symlink()


def test_logs_and_next_check_use_timezone_with_daylight_saving():
    import logging
    from datetime import datetime

    from monopolygo_rewards.diagnostics import ZoneFormatter, display_time

    formatter = ZoneFormatter("America/Chicago")
    for utc, expected in [
        ("2026-11-10T13:01:32+00:00", "2026-11-10T07:01:32-06:00"),
        ("2026-07-10T13:01:32+00:00", "2026-07-10T08:01:32-05:00"),
    ]:
        instant = datetime.fromisoformat(utc)
        assert display_time(instant, "America/Chicago") == expected
        record = logging.LogRecord(
            "test",
            logging.INFO,
            "",
            0,
            "Next check: %s",
            (display_time(instant, "America/Chicago"),),
            None,
        )
        record.created = instant.timestamp()
        assert formatter.format(record) == f"{expected} INFO Next check: {expected}"
        assert instant.utcoffset().total_seconds() == 0
