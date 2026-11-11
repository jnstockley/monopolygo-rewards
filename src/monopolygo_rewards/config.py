"""Typed settings; process environment overrides literal dotenv values."""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import dotenv_values

from .errors import ConfigurationError


def parse_duration(value: str, *, allow_zero: bool = False) -> timedelta:
    text = value.strip().lower()
    parts = re.findall(r"(\d+)\s*([dhms])", text)
    if not parts or re.sub(r"\d+\s*[dhms]", "", text).strip():
        raise ValueError("Invalid duration")
    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    if len({unit for _, unit in parts}) != len(parts):
        raise ValueError("Duplicate duration unit")
    seconds = sum(int(number) * units[unit] for number, unit in parts)
    if seconds == 0 and not allow_zero:
        raise ValueError("Duration must be positive")
    return timedelta(seconds=seconds)


@dataclass(frozen=True)
class Settings:
    expected_username: str
    check_interval: timedelta | None = None
    fallback_interval: timedelta = timedelta(minutes=15)
    reset_buffer: timedelta = timedelta(seconds=90)
    error_retry_interval: timedelta = timedelta(minutes=5)
    error_retry_max_interval: timedelta = timedelta(hours=1)
    auth_retry_interval: timedelta = timedelta(hours=1)
    wheel_enabled: bool = True
    gift_enabled: bool = True
    headless: bool = True
    action_timeout: timedelta = timedelta(seconds=15)
    navigation_timeout: timedelta = timedelta(seconds=45)
    readiness_timeout: timedelta = timedelta(seconds=45)
    run_timeout: timedelta = timedelta(minutes=5)
    shutdown_timeout: timedelta = timedelta(seconds=20)
    data_dir: Path = Path("data")
    session_file: Path = Path("data/session.cookies")
    artifact_dir: Path = Path("artifacts")
    artifacts_enabled: bool = True
    artifact_retention_days: int = 7
    log_level: str = "INFO"
    log_dir: Path | None = None
    keep_open: bool = False
    tz: str = "UTC"
    apprise_url: str = field(default="", repr=False)
    apprise_notify_on: str = "error"
    apprise_notify_startup: bool = True
    apprise_timeout: timedelta = timedelta(seconds=10)

    @property
    def enabled_rewards(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, enabled in [("wheel", self.wheel_enabled), ("gift", self.gift_enabled)]
            if enabled
        )


def load_settings(
    env_file: Path | None = None,
    overrides: Mapping[str, str] | None = None,
    *,
    require_username: bool = True,
) -> Settings:
    values = {
        **dotenv_values(env_file or Path.cwd() / ".env", interpolate=False),
        **os.environ,
        **(overrides or {}),
    }

    def value(key: str, default: str) -> str:
        return values.get(key) or ("" if key in values else default)

    def boolean(key: str, default: str = "true") -> bool:
        text = value(key, default).lower()
        if text not in {"true", "false", "1", "0", "yes", "no"}:
            raise ConfigurationError(f"Invalid {key}")
        return text in {"true", "1", "yes"}

    def duration(key: str, default: str, zero: bool = False) -> timedelta:
        try:
            return parse_duration(value(key, default), allow_zero=zero)
        except ValueError, OverflowError:
            raise ConfigurationError(f"Invalid {key}") from None

    def path(key: str, default: str) -> Path:
        return Path(value(key, default)).expanduser().resolve()

    username = value("EXPECTED_USERNAME", "").strip()
    if not username and require_username:
        raise ConfigurationError("EXPECTED_USERNAME is required")
    interval = (
        None
        if value("CHECK_INTERVAL", "auto").lower() == "auto"
        else duration("CHECK_INTERVAL", "auto")
    )
    data = path("DATA_DIR", "./data")
    session = Path(value("SESSION_FILE", "session.cookies")).expanduser()
    try:
        retention = int(value("ARTIFACT_RETENTION_DAYS", "7"))
        if retention < 1:
            raise ValueError
    except ValueError:
        raise ConfigurationError("Invalid ARTIFACT_RETENTION_DAYS") from None
    level = value("LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigurationError("Invalid LOG_LEVEL")
    timezone = value("TZ", "UTC")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError, ValueError:
        raise ConfigurationError(
            "Invalid TZ; use an IANA timezone such as America/Chicago"
        ) from None
    notify_on = value("APPRISE_NOTIFY_ON", "error").strip().lower()
    if notify_on not in {"error", "all"}:
        raise ConfigurationError("Invalid APPRISE_NOTIFY_ON; use error or all")
    settings = Settings(
        apprise_url=value("APPRISE_URL", "").strip(),
        apprise_notify_on=notify_on,
        apprise_notify_startup=boolean("APPRISE_NOTIFY_STARTUP"),
        apprise_timeout=duration("APPRISE_TIMEOUT", "10s"),
        tz=timezone,
        expected_username=username,
        check_interval=interval,
        fallback_interval=duration("FALLBACK_INTERVAL", "15m"),
        reset_buffer=duration("RESET_BUFFER", "90s", True),
        error_retry_interval=duration("ERROR_RETRY_INTERVAL", "5m"),
        error_retry_max_interval=duration("ERROR_RETRY_MAX_INTERVAL", "1h"),
        auth_retry_interval=duration("AUTH_RETRY_INTERVAL", "1h"),
        wheel_enabled=boolean("WHEEL_ENABLED"),
        gift_enabled=boolean("GIFT_ENABLED"),
        headless=boolean("HEADLESS"),
        action_timeout=duration("ACTION_TIMEOUT", "15s"),
        navigation_timeout=duration("NAVIGATION_TIMEOUT", "45s"),
        readiness_timeout=duration("READINESS_TIMEOUT", "45s"),
        run_timeout=duration("RUN_TIMEOUT", "5m"),
        shutdown_timeout=duration("SHUTDOWN_TIMEOUT", "20s"),
        data_dir=data,
        session_file=(data / session).resolve(),
        artifact_dir=path("ARTIFACT_DIR", "./artifacts"),
        artifacts_enabled=boolean("ARTIFACTS_ENABLED"),
        artifact_retention_days=retention,
        log_level=level,
        log_dir=path("LOG_DIR", "") if value("LOG_DIR", "") else None,
    )
    if settings.error_retry_max_interval < settings.error_retry_interval:
        raise ConfigurationError("ERROR_RETRY_MAX_INTERVAL must be >= ERROR_RETRY_INTERVAL")
    return settings
