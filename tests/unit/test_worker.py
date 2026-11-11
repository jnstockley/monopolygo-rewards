import time
from datetime import timedelta
from multiprocessing import get_context

from monopolygo_rewards.config import Settings
from monopolygo_rewards.models import RewardResult, RewardStatus, RunResult, utcnow
from monopolygo_rewards.supervisor import supervise
from monopolygo_rewards.worker import health_status, wait_until, write_health


def blocked_child(settings, stop, emit, login_only=False):
    emit(("auth", "verified"))
    emit(("result", RewardResult("wheel", RewardStatus.SKIPPED, "cooldown", utcnow())))
    emit(("progress", ("checking gift", "gift", True)))
    while True:
        time.sleep(1)


def test_blocked_child_is_reaped_and_preserves_partial_results(tmp_path):
    s = Settings(
        "test",
        run_timeout=timedelta(seconds=0.2),
        shutdown_timeout=timedelta(seconds=0.2),
        data_dir=tmp_path,
    )
    event = get_context("spawn").Event()
    started = time.monotonic()
    result = supervise(s, event, target=blocked_child)
    assert time.monotonic() - started < 5
    assert [r.status for r in result.results] == [RewardStatus.SKIPPED, RewardStatus.UNCERTAIN]
    assert result.auth_status == "verified"


def test_sleep_interrupts_without_waiting_for_daily_reset(tmp_path):
    event = get_context("spawn").Event()
    event.set()
    started = time.monotonic()
    wait_until(utcnow() + timedelta(hours=23), event, lambda: None)
    assert time.monotonic() - started < 0.2


def test_health_during_wait_and_auth_block(tmp_path):
    s = Settings("test", data_dir=tmp_path)
    write_health(s, "waiting")
    assert health_status(s, utcnow())
    assert not health_status(s, utcnow() + timedelta(seconds=121))
    write_health(s, "auth_blocked")
    assert not health_status(s, utcnow())


def test_wait_rechecks_clock_after_forward_jump(monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from monopolygo_rewards import worker

    start = datetime(2026, 11, 9, tzinfo=UTC)
    values = iter([start, start, start + timedelta(days=2)])
    monkeypatch.setattr(worker, "utcnow", lambda: next(values))
    waits = []
    event = SimpleNamespace(is_set=lambda: False, wait=lambda seconds: waits.append(seconds))
    worker.wait_until(start + timedelta(hours=23), event, lambda: None)
    assert waits == [30]


def test_auth_recovery_verifies_before_full_run(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from monopolygo_rewards import worker
    from monopolygo_rewards.scheduler import plan_next_run
    from monopolygo_rewards.state import save_state

    t = datetime(2026, 11, 1, tzinfo=UTC)
    s = Settings("test", data_dir=tmp_path)
    save_state(tmp_path / "schedule.json", plan_next_run(s, None, RunResult((), "blocked", t)))
    event = get_context("spawn").Event()
    modes = []

    def run(settings, stop, *, login_only=False, **kwargs):
        modes.append(login_only)
        if not login_only:
            stop.set()
        return RunResult((), "verified", utcnow())

    monkeypatch.setattr(worker, "supervise", run)
    assert worker.run_worker(s, event) == 0
    assert modes == [True, False]


def test_one_shot_does_not_report_partial_success(tmp_path, monkeypatch):
    from monopolygo_rewards import worker

    s = Settings("test", data_dir=tmp_path)
    event = get_context("spawn").Event()
    monkeypatch.setattr(
        worker,
        "supervise",
        lambda *a, **k: RunResult(
            (RewardResult("wheel", RewardStatus.SKIPPED, "timer", utcnow()),), "verified", utcnow()
        ),
    )
    assert worker.run_worker(s, event, once=True) == 1


def test_backward_clock_jump_cannot_extend_elapsed_wait(monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from monopolygo_rewards import worker

    t = datetime(2026, 11, 9, tzinfo=UTC)
    mono = [0.0]
    calls = [0]
    waits = []

    def now():
        calls[0] += 1
        return t if calls[0] == 1 else t - timedelta(days=365)

    def wait(seconds):
        waits.append(seconds)
        mono[0] += seconds

    monkeypatch.setattr(worker, "utcnow", now)
    monkeypatch.setattr(worker.time, "monotonic", lambda: mono[0])
    event = SimpleNamespace(is_set=lambda: mono[0] > 5, wait=wait)
    worker.wait_until(t + timedelta(seconds=1), event, lambda: None)
    assert waits == [1.0]


def inspection_child(settings, stop, emit, login_only=False):
    emit(("inspection_ready", None))
    stop.wait(2)
    return RunResult((), "verified", utcnow())


def test_inspection_input_is_owned_by_parent_across_spawn(tmp_path, monkeypatch):
    prompts = []
    monkeypatch.setattr("builtins.input", lambda text: prompts.append(text) or "")
    s = Settings(
        "test",
        keep_open=True,
        run_timeout=timedelta(seconds=0.3),
        shutdown_timeout=timedelta(seconds=0.3),
        data_dir=tmp_path,
    )
    result = supervise(s, get_context("spawn").Event(), target=inspection_child)
    assert result.auth_status == "verified" and result.error is None
    assert len(prompts) == 1
