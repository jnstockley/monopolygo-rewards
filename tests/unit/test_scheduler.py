from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from monopolygo_rewards.config import Settings
from monopolygo_rewards.models import RewardResult, RewardStatus, RunResult
from monopolygo_rewards.scheduler import initial_deadline, plan_next_run
from monopolygo_rewards.state import load_state, save_state

T = datetime(2026, 11, 9, tzinfo=UTC)
S = Settings(expected_username="test")


def result(name, minutes=None, status=RewardStatus.SKIPPED):
    return RewardResult(
        name,
        status,
        "test",
        T,
        (f"Resets in {minutes}m" if name == "wheel" else f"Available in {minutes}m")
        if minutes is not None
        else None,
        T + timedelta(minutes=minutes) if minutes is not None else None,
    )


def test_auto_earliest_and_unknown_fallback():
    state = plan_next_run(
        S, None, RunResult((result("wheel", 670), result("gift", 671)), "verified", T)
    )
    assert state.next_check_at == T + timedelta(hours=11, minutes=11, seconds=30)
    state = plan_next_run(
        S, state, RunResult((result("wheel", 670), result("gift")), "verified", T)
    )
    assert state.next_check_at == T + timedelta(minutes=15)


def test_backoff_partial_and_recovery():
    run = RunResult((result("wheel", status=RewardStatus.UNCERTAIN),), "verified", T, "uncertain")
    state = None
    for minutes in [5, 10, 20, 40, 60, 60]:
        state = plan_next_run(S, state, run)
        assert state.next_check_at == T + timedelta(minutes=minutes)
    state = plan_next_run(
        S, state, RunResult((result("wheel", 10), result("gift", 20)), "verified", T)
    )
    assert state.failures == {"wheel": 0, "gift": 0}


def test_fixed_auth_and_minimum_wait():
    s = replace(S, check_interval=timedelta(hours=1))
    assert plan_next_run(
        s, None, RunResult((result("wheel", 0), result("gift", 0)), "verified", T)
    ).next_check_at == T + timedelta(hours=1)
    assert plan_next_run(S, None, RunResult((), "blocked", T)).next_check_at == T + timedelta(
        hours=1
    )
    s = replace(S, gift_enabled=False, reset_buffer=timedelta(0))
    assert plan_next_run(
        s, None, RunResult((result("wheel", 0),), "verified", T)
    ).next_check_at == T + timedelta(seconds=1)


def test_restart_and_corrupt_deadline(tmp_path):
    p = tmp_path / "state.json"
    state = plan_next_run(
        S,
        None,
        RunResult((result("wheel", 3 * 24 * 60), result("gift", 3 * 24 * 60)), "verified", T),
    )
    save_state(p, state)
    restored = load_state(p, S, T)
    assert restored == state
    assert initial_deadline(S, restored, T) == T + timedelta(days=3, seconds=90)
    assert load_state(p, replace(S, expected_username="other"), T) is None
    import json

    data = json.loads(p.read_text())
    data["next_check_at"] = "2099-01-01T00:00:00+00:00"
    p.write_text(json.dumps(data))
    assert load_state(p, S, T) is None
    p.write_text("{bad")
    assert load_state(p, S, T) is None


@pytest.mark.parametrize("shape", [["wheel"], None, "wheel", 1])
def test_malformed_failures_shape_rebuilds(tmp_path, shape):
    import json

    s = replace(S, gift_enabled=False)
    p = tmp_path / "state.json"
    save_state(p, plan_next_run(s, None, RunResult((result("wheel", 60),), "verified", T)))
    raw = json.loads(p.read_text())
    raw["failures"] = shape
    p.write_text(json.dumps(raw))
    assert load_state(p, s, T) is None


def test_long_countdown_requires_consistent_provenance(tmp_path):
    s = replace(S, gift_enabled=False)
    p = tmp_path / "state.json"
    r = RewardResult(
        "wheel", RewardStatus.SKIPPED, "timer", T, "Resets in 1h", T + timedelta(days=365)
    )
    save_state(p, plan_next_run(s, None, RunResult((r,), "verified", T)))
    assert load_state(p, s, T) is None
