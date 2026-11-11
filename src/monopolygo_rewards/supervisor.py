"""Bound browser/driver lifetime with a spawned, separately grouped child."""

import os
import signal
import threading
import time
from collections.abc import Callable
from multiprocessing import get_context
from multiprocessing.connection import Connection
from multiprocessing.synchronize import Event

from .browser import run_browser
from .config import Settings
from .diagnostics import safe_error
from .models import RewardResult, RewardStatus, RunResult, StopToken, utcnow


def _child(
    settings: Settings, event: Event, pipe: Connection, target: Callable, login_only: bool
) -> None:
    os.setsid()
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    pipe.send(("group_ready", os.getpid()))
    try:
        result = target(settings, event, pipe.send, login_only=login_only)
        pipe.send(("done", result))
    except BaseException as exc:
        pipe.send(("error", safe_error(exc)))
    finally:
        pipe.close()


def supervise(
    settings: Settings,
    stop_event: StopToken,
    *,
    target: Callable = run_browser,
    login_only: bool = False,
    heartbeat: Callable[[], None] = lambda: None,
) -> RunResult:
    ctx = get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    child_stop = ctx.Event()
    process = ctx.Process(target=_child, args=(settings, child_stop, child, target, login_only))
    partial: dict[str, RewardResult] = {}
    auth = "unknown"
    active = None
    mutation = False
    grouped = False
    done = None
    error = None
    started = time.monotonic()
    stop_deadline = None
    inspection_closed = threading.Event()
    inspection_prompted = False

    def inspect_input() -> None:
        try:
            input("Press Enter to close the browser...")
        except EOFError, KeyboardInterrupt:
            pass
        finally:
            inspection_closed.set()

    process.start()
    child.close()
    try:
        while True:
            heartbeat()
            if parent.poll(0.1):
                try:
                    kind, data = parent.recv()
                except EOFError:
                    break
                if kind == "group_ready":
                    grouped = True
                elif kind == "result":
                    partial[data.reward] = data
                    active, mutation = None, False
                elif kind == "auth":
                    auth = data
                elif kind == "progress":
                    stage, active, mutation = data
                elif kind == "inspection_ready" and not inspection_prompted:
                    inspection_prompted = True
                    threading.Thread(target=inspect_input, daemon=True).start()
                elif kind == "done":
                    done = data
                    break
                elif kind == "error":
                    error = data
            if not process.is_alive() and not parent.poll():
                break
            if inspection_closed.is_set():
                child_stop.set()
            now = time.monotonic()
            if stop_deadline is None and (
                stop_event.is_set() or now - started >= settings.run_timeout.total_seconds()
            ):
                child_stop.set()
                stop_deadline = now + settings.shutdown_timeout.total_seconds()
                error = (
                    "Shutdown requested"
                    if stop_event.is_set()
                    else "Browser run exceeded RUN_TIMEOUT"
                )
            if stop_deadline is not None and now >= stop_deadline:
                break
    finally:
        # Reap the whole isolated group, including a wedged driver/Chromium.
        if grouped and process.pid is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.is_alive():
            process.kill()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join()
        parent.close()
        process.close()
    if done is not None:
        return done
    if active and active not in partial:
        partial[active] = RewardResult(
            active,
            RewardStatus.UNCERTAIN if mutation else RewardStatus.FAILED,
            error or "Browser child stopped",
            utcnow(),
        )
    return RunResult(
        tuple(partial.values()), auth, utcnow(), error or "Browser child stopped unexpectedly"
    )


supervised_run = supervise
