"""Single-account worker loop, restart scheduling, and local health checks."""

import json
import logging
import os
import time
from collections.abc import Callable
from datetime import datetime

from .config import Settings
from .diagnostics import display_time, prune_artifacts
from .models import RewardStatus, RunResult, StopToken, utcnow
from .notifications import DeliveryState, notify_run, notify_startup
from .scheduler import initial_deadline, plan_next_run
from .state import load_state, save_state, timestamp
from .storage import account_lock, atomic_write_json
from .supervisor import supervise


def write_health(settings: Settings, status: str) -> None:
    atomic_write_json(
        settings.data_dir / "health.json",
        {"pid": os.getpid(), "status": status, "heartbeat_at": utcnow().isoformat()},
    )


def health_status(settings: Settings, now: datetime) -> bool:
    try:
        data = json.loads((settings.data_dir / "health.json").read_text())
        age = (now - timestamp(data["heartbeat_at"])).total_seconds()
        if (
            data["status"] not in {"running", "waiting"}
            or not 0 <= age <= 120
            or type(data["pid"]) is not int
            or data["pid"] <= 0
        ):
            return False
        os.kill(data["pid"], 0)
        return True
    except OSError, ValueError, KeyError, TypeError:
        return False


def wait_until(deadline: datetime, event: StopToken, heartbeat: Callable[[], None]) -> None:
    # A backward wall-clock correction must not lengthen the original wait.
    monotonic_deadline = time.monotonic() + max(0, (deadline - utcnow()).total_seconds())
    while not event.is_set():
        heartbeat()
        remaining = min(
            (deadline - utcnow()).total_seconds(), monotonic_deadline - time.monotonic()
        )
        if remaining <= 0:
            return
        event.wait(min(30, remaining))


def run_worker(
    settings: Settings,
    stop_event: StopToken,
    *,
    once: bool = False,
    login_only: bool = False,
    delivery_state: DeliveryState | None = None,
) -> int:
    if delivery_state is None:
        delivery_state = DeliveryState()
    with account_lock(settings.data_dir):
        state_path = settings.data_dir / "schedule.json"
        state = load_state(state_path, settings, utcnow())
        deadline = utcnow() if once or login_only else initial_deadline(settings, state, utcnow())
        last_heartbeat = 0.0
        health = "waiting"
        final_result: RunResult | None = None
        final_next_check: datetime | None = None

        def heartbeat(force=False):
            nonlocal last_heartbeat
            if force or time.monotonic() - last_heartbeat >= 30:
                write_health(settings, health)
                last_heartbeat = time.monotonic()

        try:
            heartbeat(True)
            if not once and not login_only:
                notify_startup(settings, deadline, stop_event=stop_event, heartbeat=heartbeat)
            while not stop_event.is_set():
                delivery_state.attempted = False
                health = (
                    "auth_blocked"
                    if state and state.last_run.auth_status == "blocked"
                    else "waiting"
                )
                heartbeat(True)
                logging.info("Next check: %s", display_time(deadline, settings.tz))
                wait_until(deadline, stop_event, heartbeat)
                if stop_event.is_set():
                    break
                health = "running"
                heartbeat(True)
                auth_only = bool(
                    state
                    and state.last_run.auth_status == "blocked"
                    and not once
                    and not login_only
                )
                result = supervise(
                    settings, stop_event, login_only=login_only or auth_only, heartbeat=heartbeat
                )
                for r in result.results:
                    logging.info("%s: %s — %s", r.reward, r.status, r.reason)
                if result.error:
                    logging.error("Workflow stopped: %s", result.error)
                if login_only:
                    final_result = result
                    return (
                        0
                        if result.auth_status == "verified" and not result.error
                        else 2
                        if result.auth_status == "blocked"
                        else 1
                    )
                if auth_only and result.auth_status == "verified" and not stop_event.is_set():
                    # Identity recovery succeeded; fresh browser verifies again before any actions.
                    result = supervise(settings, stop_event, heartbeat=heartbeat)
                state = plan_next_run(settings, state, result)
                save_state(state_path, state)
                prune_artifacts(settings.artifact_dir, settings.artifact_retention_days)
                if once:
                    final_result = result
                    final_next_check = state.next_check_at
                    if result.auth_status == "blocked":
                        return 2
                    completed = {
                        r.reward
                        for r in result.results
                        if r.status in {RewardStatus.CLAIMED, RewardStatus.SKIPPED}
                    }
                    return (
                        0
                        if result.auth_status == "verified"
                        and not result.error
                        and completed == set(settings.enabled_rewards)
                        else 1
                    )
                notify_run(
                    settings,
                    result,
                    state.next_check_at,
                    stop_event=stop_event,
                    heartbeat=heartbeat,
                    delivery_state=delivery_state,
                )
                deadline = state.next_check_at
            return 0
        finally:
            write_health(settings, "stopped")
            if final_result is not None:
                notify_run(
                    settings,
                    final_result,
                    final_next_check,
                    login_only=login_only,
                    stop_event=stop_event,
                    delivery_state=delivery_state,
                )
