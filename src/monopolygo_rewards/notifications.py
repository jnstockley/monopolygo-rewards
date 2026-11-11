"""Optional, bounded Apprise delivery; notification failures never retry rewards."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from multiprocessing import get_context
from multiprocessing.connection import Connection

from .config import Settings
from .diagnostics import display_time
from .models import RewardStatus, RunResult, StopToken


@dataclass(frozen=True)
class Notification:
    title: str
    body: str
    failed: bool


@dataclass
class DeliveryState:
    """Parent-owned attempt state shared by worker and fatal-error reporting."""

    attempted: bool = False


def build_notification(
    settings: Settings,
    result: RunResult,
    next_check: datetime | None = None,
    *,
    login_only: bool = False,
) -> Notification | None:
    if not settings.apprise_url:
        return None
    successful = {
        r.reward for r in result.results if r.status in {RewardStatus.CLAIMED, RewardStatus.SKIPPED}
    }
    failed = (
        bool(result.error)
        or result.auth_status != "verified"
        or (not login_only and successful != set(settings.enabled_rewards))
    )
    if not failed and settings.apprise_notify_on == "error":
        return None
    lines = [
        f"Account: {settings.expected_username}",
        f"Completed: {display_time(result.finished_at, settings.tz)}",
    ]
    lines.extend(f"{r.reward}: {r.status} — {r.reason}" for r in result.results)
    if result.error:
        lines.append(f"Error: {result.error}")
    elif failed:
        lines.append("The check did not complete successfully for every enabled reward.")
    if next_check is not None:
        lines.append(f"Next check: {display_time(next_check, settings.tz)}")
    return Notification(
        "MONOPOLY GO: check failed" if failed else "MONOPOLY GO: check succeeded",
        "\n".join(lines),
        failed,
    )


def _deliver(url: str, message: Notification, pipe: Connection) -> None:
    # Plugin errors/debug logs can contain service URLs and tokens. Never forward them.
    logging.disable(logging.CRITICAL)
    try:
        import apprise

        client = apprise.Apprise()
        added = client.add(url)
        ok = added and client.notify(
            title=message.title,
            body=message.body,
            notify_type=apprise.NotifyType.FAILURE
            if message.failed
            else apprise.NotifyType.SUCCESS,
        )
        pipe.send(bool(ok))
    except BaseException:
        pipe.send(False)
    finally:
        pipe.close()


def notify_startup(
    settings: Settings,
    next_check: datetime,
    *,
    stop_event: StopToken,
    heartbeat: Callable[[], None],
) -> None:
    """Report scheduled-worker readiness separately from reward check outcomes."""
    if not settings.apprise_url or not settings.apprise_notify_startup or stop_event.is_set():
        return
    message = Notification(
        "MONOPOLY GO: worker started",
        f"Account: {settings.expected_username}\n"
        f"Worker started; identity will be checked before reward actions.\n"
        f"Next check: {display_time(next_check, settings.tz)}",
        False,
    )
    try:
        send_bounded(settings, message, stop_event=stop_event, heartbeat=heartbeat)
    except Exception:
        logging.warning("Apprise startup notification failed; worker continues")


def send_bounded(
    settings: Settings,
    message: Notification,
    *,
    stop_event: StopToken | None = None,
    heartbeat: Callable[[], None] = lambda: None,
    target: Callable = _deliver,
) -> bool:
    ctx = get_context("spawn")
    read, write = ctx.Pipe(duplex=False)
    child = ctx.Process(target=target, args=(settings.apprise_url, message, write), daemon=True)
    delivered = False
    started = False
    try:
        child.start()
        started = True
        write.close()
        deadline = time.monotonic() + settings.apprise_timeout.total_seconds()
        while time.monotonic() < deadline and not (stop_event and stop_event.is_set()):
            heartbeat()
            if read.poll(min(0.1, max(0, deadline - time.monotonic()))):
                delivered = read.recv() is True
                break
            if not child.is_alive():
                break
    except Exception:
        delivered = False
    finally:
        if started:
            if child.is_alive():
                child.terminate()
            child.join(timeout=0.2)
            if child.is_alive():
                child.kill()
                child.join(timeout=0.2)
            child.close()
        read.close()
        write.close()
    if not delivered and not (stop_event and stop_event.is_set()):
        logging.warning(
            "Apprise notification delivery failed or timed out; reward outcome unchanged"
        )
    return delivered


def notify_run(
    settings: Settings,
    result: RunResult,
    next_check: datetime | None = None,
    *,
    login_only: bool = False,
    stop_event: StopToken | None = None,
    heartbeat: Callable[[], None] = lambda: None,
    delivery_state: DeliveryState | None = None,
) -> None:
    if (stop_event and stop_event.is_set()) or (
        delivery_state is not None and delivery_state.attempted
    ):
        return
    try:
        message = build_notification(settings, result, next_check, login_only=login_only)
        if message is not None:
            if delivery_state is not None:
                delivery_state.attempted = True
            send_bounded(settings, message, stop_event=stop_event, heartbeat=heartbeat)
    except Exception:
        logging.warning("Apprise notification failed; reward outcome unchanged")
