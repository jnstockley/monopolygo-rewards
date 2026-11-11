from datetime import timedelta

import pytest

from monopolygo_rewards.models import RewardStatus
from monopolygo_rewards.rewards import DailyRewards, parse_countdown


def test_scoped_countdown_parsing_and_observation():
    assert parse_countdown("Resets in 11h 10m", r"Resets\s+in") == timedelta(minutes=670)
    assert parse_countdown("Available in 0m", r"Available\s+in") == timedelta(0)
    for text in [
        "Available in 1m 2m",
        "Available in -5m",
        "Available in 2x",
        "Available in 1m nonsense",
    ]:
        assert parse_countdown(text, r"Available\s+in") is None
    w = DailyRewards(None, "test")
    w.record("wheel", "skipped", "Resets in 11h 10m")
    r = w.results[0]
    assert r.status == RewardStatus.SKIPPED
    assert r.next_available_at - r.observed_at == timedelta(minutes=670)


def test_completed_result_emits_immediately():
    emitted = []
    w = DailyRewards(None, "test", emit=emitted.append)
    w.record("gift", "skipped", "Unavailable")
    assert emitted == w.results


def test_rejected_profile_is_authentication_failure():
    import pytest

    from monopolygo_rewards.errors import AuthenticationError
    from monopolygo_rewards.rewards import PROFILE

    w = DailyRewards(None, "test")
    w.responses[("GET", PROFILE)] = (401, {"IsSuccess": False})
    with pytest.raises(AuthenticationError):
        w.verify_login()


@pytest.mark.parametrize("during", ["popup", "readiness"])
def test_stop_during_claim_preparation_prevents_click(monkeypatch, during):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from monopolygo_rewards import rewards

    stopped = [False]
    clicks = []
    button = SimpleNamespace(click=lambda **kwargs: clicks.append(True))
    response = SimpleNamespace(
        status=200, json=lambda: {"IsSuccess": True, "Data": {"UnlockedBenefit": {"PointsCost": 0}}}
    )
    page = SimpleNamespace(
        expect_response=lambda *a, **k: nullcontext(SimpleNamespace(value=response))
    )
    workflow = DailyRewards(page, "test", stop_requested=lambda: stopped[0])
    workflow.dismiss_popups = lambda: stopped.__setitem__(0, during == "popup")

    def enabled():
        if during == "readiness":
            stopped[0] = True

    monkeypatch.setattr(
        rewards,
        "expect",
        lambda _: SimpleNamespace(
            to_have_count=lambda _: None, to_be_visible=lambda: None, to_be_enabled=enabled
        ),
    )
    with pytest.raises(rewards.WorkflowError):
        workflow.claim(button, rewards.UNLOCK, "wheel")
    assert clicks == []
