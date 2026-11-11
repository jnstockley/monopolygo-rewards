"""Public commands and process-level configuration."""

import logging
import signal
import time
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from .config import load_settings
from .diagnostics import configure_logging, safe_error
from .errors import ConfigurationError, RewardsError
from .models import RunResult, utcnow
from .notifications import DeliveryState, notify_run
from .session import import_har, load_cookies
from .storage import account_lock
from .worker import health_status, run_worker


class StopRequest:
    """Signal handlers only assign a flag; never acquire an Event lock."""

    def __init__(self) -> None:
        self.requested = False

    def set(self) -> None:
        self.requested = True

    def is_set(self) -> bool:
        return self.requested

    def wait(self, timeout: float | None = None) -> bool:
        deadline = time.monotonic() + timeout if timeout is not None else float("inf")
        while not self.requested and time.monotonic() < deadline:
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        return self.requested


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Check only the free daily MONOPOLY GO rewards for one verified account."
    )
    parser.add_argument(
        "command", nargs="?", choices=["run", "import-session", "healthcheck"], default="run"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Check immediately once and exit")
    mode.add_argument(
        "--login-only", action="store_true", help="Verify identity without claims and exit"
    )
    parser.add_argument(
        "--env-file", type=Path, help="Dotenv file (default: .env in working directory)"
    )
    parser.add_argument("--state", type=Path, help="Session cookie file (relative to DATA_DIR)")
    parser.add_argument("--username", help="Exact expected DisplayName")
    parser.add_argument("--har", type=Path, help="Input capture for import-session only")
    head = parser.add_mutually_exclusive_group()
    head.add_argument("--headed", action="store_true", help="Show Chromium locally")
    head.add_argument("--headless", action="store_true", help="Hide Chromium")
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Interactive inspection; requires --headed and --once or --login-only",
    )
    args = parser.parse_args(argv)
    event = StopRequest()
    old_signals = {}
    settings = None
    delivery_state = DeliveryState()
    try:
        overrides = {}
        for flag, key in [(args.state, "SESSION_FILE"), (args.username, "EXPECTED_USERNAME")]:
            if flag is not None:
                overrides[key] = str(flag)
        if args.headed or args.headless:
            overrides["HEADLESS"] = "false" if args.headed else "true"
        settings = load_settings(args.env_file, overrides, require_username=args.command == "run")
        if args.keep_open and (
            settings.headless or not (args.once or args.login_only) or args.command != "run"
        ):
            raise ConfigurationError("--keep-open requires a headed --once or --login-only run")
        settings = replace(settings, keep_open=args.keep_open)
        configure_logging(settings)
        if args.command == "healthcheck":
            return 0 if health_status(settings, utcnow()) else 1
        if args.command == "import-session":
            if not args.har:
                raise ConfigurationError("import-session requires --har PATH")
            with account_lock(settings.data_dir):
                import_har(args.har, settings.session_file)
            logging.info("Session imported. Run --login-only to verify the account.")
            return 0
        if args.har:
            raise ConfigurationError(
                "Import captures explicitly: monopolygo-rewards import-session --har PATH"
            )
        if not args.login_only and not settings.enabled_rewards:
            raise ConfigurationError("Enable WHEEL_ENABLED or GIFT_ENABLED")
        # Fail before Chromium on an absent/expired session.
        load_cookies(settings.session_file)
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_signals[sig] = signal.signal(sig, lambda *_: event.set())
        return run_worker(
            settings,
            event,
            once=args.once,
            login_only=args.login_only,
            delivery_state=delivery_state,
        )
    except Exception as exc:
        reason = safe_error(exc)
        logging.error("%s", reason)
        if settings is not None and args.command == "run":
            notify_run(
                settings,
                RunResult(
                    (), "blocked" if isinstance(exc, RewardsError) else "unknown", utcnow(), reason
                ),
                login_only=args.login_only,
                stop_event=event,
                delivery_state=delivery_state,
            )
        return 2 if isinstance(exc, (RewardsError, OSError)) else 1
    finally:
        for sig, previous in old_signals.items():
            signal.signal(sig, previous)
