"""Small credential-safe diagnostics boundary."""

import logging
import re
from datetime import UTC, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings
from .errors import RewardsError
from .models import utcnow


def safe_error(error: BaseException) -> str:
    # Site selectors/request payloads can appear anywhere in driver exceptions.
    return (
        str(error)
        if isinstance(error, RewardsError)
        else f"{type(error).__name__}: operation failed; inspect the workflow stage"
    )


def display_time(value: datetime, timezone: str) -> str:
    return value.astimezone(ZoneInfo(timezone)).isoformat(timespec="seconds")


class ZoneFormatter(logging.Formatter):
    """Include the configured local offset, including DST, on every log line."""

    def __init__(self, timezone: str) -> None:
        super().__init__("%(asctime)s %(levelname)s %(message)s")
        self.timezone = timezone

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return display_time(datetime.fromtimestamp(record.created, UTC), self.timezone)


def configure_logging(settings: Settings) -> None:
    formatter = ZoneFormatter(settings.tz)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if settings.log_dir:
        settings.log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = settings.log_dir / "rewards.log"
        if not path.exists():
            path.touch(mode=0o600)
        handlers.append(RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=3))
    for handler in handlers:
        handler.setFormatter(formatter)
    logging.basicConfig(level=settings.log_level, handlers=handlers, force=True)


def prune_artifacts(directory: Path, days: int) -> None:
    if not directory.exists():
        return
    cutoff = (utcnow() - timedelta(days=days)).timestamp()
    for path in directory.iterdir():
        if (
            re.fullmatch(r"daily-rewards-\d{8}T\d{12}Z\.png", path.name)
            and not path.is_symlink()
            and path.is_file()
        ):
            if path.stat().st_mtime < cutoff:
                path.unlink()
