"""Safe, pickleable outcomes shared by browser children and the scheduler."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol


class Reward(StrEnum):
    WHEEL = "wheel"
    GIFT = "gift"


class RewardStatus(StrEnum):
    CLAIMED = "claimed"
    SKIPPED = "skipped"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class RewardResult:
    reward: str
    status: RewardStatus
    reason: str
    observed_at: datetime
    countdown_text: str | None = None
    next_available_at: datetime | None = None


@dataclass(frozen=True)
class RunResult:
    results: tuple[RewardResult, ...]
    auth_status: str
    finished_at: datetime
    error: str | None = None


def utcnow() -> datetime:
    return datetime.now(UTC)


class StopToken(Protocol):
    def is_set(self) -> bool: ...
    def wait(self, timeout: float | None = None) -> bool: ...
