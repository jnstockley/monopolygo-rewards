"""Pure countdown scheduling, independent of browser and sleeping."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import Settings
from .models import RewardStatus, RunResult


@dataclass(frozen=True)
class ScheduleState:
    fingerprint: str
    failures: dict[str, int]
    last_run: RunResult
    next_check_at: datetime


def fingerprint(settings: Settings) -> str:
    values = [settings.expected_username, settings.enabled_rewards]
    durations = [
        settings.check_interval,
        settings.fallback_interval,
        settings.reset_buffer,
        settings.error_retry_interval,
        settings.error_retry_max_interval,
        settings.auth_retry_interval,
    ]
    raw = json.dumps([values, [d.total_seconds() if d is not None else None for d in durations]])
    return hashlib.sha256(raw.encode()).hexdigest()


def calculate_deadline(settings: Settings, failures: dict[str, int], result: RunResult) -> datetime:
    finished = result.finished_at
    if result.auth_status == "blocked":
        return finished + settings.auth_retry_interval
    by_reward = {r.reward: r for r in result.results}
    candidates = []
    for reward in settings.enabled_rewards:
        item = by_reward.get(reward)
        failed = item is None or item.status in {RewardStatus.FAILED, RewardStatus.UNCERTAIN}
        if failed:
            count = min(failures.get(reward, 1), 32)
            delay = min(
                settings.error_retry_interval * (2 ** max(0, count - 1)),
                settings.error_retry_max_interval,
            )
            if settings.check_interval is not None:
                delay = min(delay, settings.check_interval)
            candidate = finished + delay
        elif settings.check_interval is not None:
            candidate = finished + settings.check_interval
        elif item is not None and item.next_available_at is not None:
            candidate = item.next_available_at + settings.reset_buffer
        else:
            candidate = finished + settings.fallback_interval
        candidates.append(candidate)
    if not candidates:
        raise ValueError("No rewards enabled")
    return max(finished + timedelta(seconds=1), min(candidates))


def plan_next_run(
    settings: Settings, previous: ScheduleState | None, result: RunResult
) -> ScheduleState:
    by_reward = {r.reward: r for r in result.results}
    failures = {}
    for reward in settings.enabled_rewards:
        item = by_reward.get(reward)
        failed = item is None or item.status in {RewardStatus.FAILED, RewardStatus.UNCERTAIN}
        prior = previous.failures.get(reward, 0) if previous else 0
        failures[reward] = min(prior + 1, 32) if failed else 0
    return ScheduleState(
        fingerprint(settings), failures, result, calculate_deadline(settings, failures, result)
    )


def initial_deadline(settings: Settings, state: ScheduleState | None, now: datetime) -> datetime:
    if state is None or state.fingerprint != fingerprint(settings):
        return now
    return max(now, state.next_check_at)
