"""Strictly validated, credential-free scheduling state."""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import Settings
from .models import RewardResult, RewardStatus, RunResult
from .rewards import parse_countdown
from .scheduler import ScheduleState, calculate_deadline, fingerprint
from .storage import atomic_write_json


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("Expected UTC timestamp")
    return parsed.astimezone(UTC)


def save_state(path: Path, state: ScheduleState) -> None:
    atomic_write_json(
        path,
        {
            "schema_version": 1,
            "fingerprint": state.fingerprint,
            "failures": state.failures,
            "next_check_at": state.next_check_at.isoformat(),
            "last_run": {
                "auth_status": state.last_run.auth_status,
                "finished_at": state.last_run.finished_at.isoformat(),
                "error": state.last_run.error,
                "results": [
                    {
                        "reward": r.reward,
                        "status": r.status,
                        "reason": r.reason,
                        "observed_at": r.observed_at.isoformat(),
                        "countdown_text": r.countdown_text,
                        "next_available_at": r.next_available_at.isoformat()
                        if r.next_available_at
                        else None,
                    }
                    for r in state.last_run.results
                ],
            },
        },
    )


def load_state(path: Path, settings: Settings, now: datetime) -> ScheduleState | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if data["schema_version"] != 1 or data["fingerprint"] != fingerprint(settings):
            return None
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("failures"), dict)
            or not isinstance(data.get("last_run"), dict)
        ):
            raise ValueError
        failures = data["failures"]
        if set(failures) != set(settings.enabled_rewards) or any(
            type(v) is not int or not 0 <= v <= 32 for v in failures.values()
        ):
            raise ValueError
        raw = data["last_run"]
        if raw["auth_status"] not in {"verified", "blocked", "unknown"}:
            raise ValueError
        results = tuple(
            RewardResult(
                r["reward"],
                RewardStatus(r["status"]),
                r["reason"],
                timestamp(r["observed_at"]),
                r["countdown_text"],
                timestamp(r["next_available_at"]) if r["next_available_at"] else None,
            )
            for r in raw["results"]
        )
        if len({r.reward for r in results}) != len(results) or any(
            r.reward not in settings.enabled_rewards for r in results
        ):
            raise ValueError
        run = RunResult(results, raw["auth_status"], timestamp(raw["finished_at"]), raw["error"])
        if run.finished_at > now + timedelta(minutes=5):
            raise ValueError
        for r in results:
            if r.observed_at > run.finished_at or (
                r.next_available_at
                and not timedelta(0) <= r.next_available_at - r.observed_at <= timedelta(days=366)
            ):
                raise ValueError
        for r in results:
            if r.next_available_at is not None:
                if not isinstance(r.countdown_text, str):
                    raise ValueError
                duration = parse_countdown(
                    r.countdown_text, r"Resets\s+in" if r.reward == "wheel" else r"Available\s+in"
                )
                if duration is None or r.observed_at + duration != r.next_available_at:
                    raise ValueError
        deadline = timestamp(data["next_check_at"])
        if deadline != calculate_deadline(settings, failures, run):
            raise ValueError
        return ScheduleState(data["fingerprint"], failures, run, deadline)
    except OSError, ValueError, KeyError, TypeError, OverflowError:
        logging.getLogger(__name__).warning(
            "Ignoring invalid scheduling state; checking immediately"
        )
        return None
