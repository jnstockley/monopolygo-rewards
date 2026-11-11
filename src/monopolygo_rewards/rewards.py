"""Guarded Playwright workflow for the two daily free rewards."""

import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Locator, Page, Request, Response, expect

from .config import Settings, parse_duration
from .errors import AuthenticationError, WorkflowError
from .models import RewardResult, RewardStatus, RunResult, utcnow
from .session import HOST, PROFILE

WHEEL = "/web-portal/loyalty-program/v3/daily-spin"
GIFT = "/web-portal/loyalty-program/free-gift"
UNLOCK = "/web-portal/loyalty-program/v2/unlock-benefit"


def error_summary(error: BaseException) -> str:
    lines = str(error).strip().splitlines()
    message = lines[0] if lines else type(error).__name__
    message = re.sub(r'https?://[^\s<>"\']+', "[URL redacted]", message)
    message = re.sub(
        r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b", "[token redacted]", message
    )
    return f"{type(error).__name__}: {message}"


def verify_identity(payload: object, expected: str) -> str:
    if not isinstance(payload, dict) or payload.get("IsSuccess") is not True:
        raise AuthenticationError("Profile did not confirm authentication.")
    data = payload.get("Data")
    # The site's fetchSession maps API DisplayName to its visible user name.
    if not isinstance(data, dict) or data.get("DisplayName") != expected:
        raise AuthenticationError("Profile username does not match the expected username.")
    return expected


def free_wheel_key(data: object) -> str | None:
    if not isinstance(data, dict) or type(data.get("FreeSpinAvailable")) is not bool:
        raise WorkflowError("Daily wheel availability is missing or unrecognized.")
    if data["FreeSpinAvailable"] is False:
        return None
    wheels = data.get("Wheels")
    if not isinstance(wheels, list):
        raise WorkflowError("Daily wheel metadata is missing.")
    free = [
        w
        for w in wheels
        if isinstance(w, dict)
        and type(w.get("PointsCost")) is int
        and w["PointsCost"] == 0
        and w.get("Available") is True
        and isinstance(w.get("Key"), str)
        and w["Key"]
    ]
    if len(free) != 1:
        raise WorkflowError("Cannot identify one available zero-cost daily wheel.")
    return free[0]["Key"]


def gift_available(data: object) -> bool:
    if not isinstance(data, dict) or data.get("FreeGiftDefined") is not True:
        raise WorkflowError("Daily shop gift is missing or unrecognized.")
    available = data.get("FreeGiftAvailable")
    if type(available) is not bool:
        raise WorkflowError("Daily shop gift availability is missing.")
    return available


def api_payload_data(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("IsSuccess") is not True:
        raise WorkflowError("API response did not confirm success.")
    data = payload.get("Data")
    if not isinstance(data, dict):
        raise WorkflowError("API response data is missing or unrecognized.")
    return data


def verify_claim(payload: object, reward: str) -> None:
    data = api_payload_data(payload)
    if reward == "wheel":
        benefit = data.get("UnlockedBenefit")
        if (
            not isinstance(benefit, dict)
            or type(benefit.get("PointsCost")) is not int
            or benefit["PointsCost"] != 0
        ):
            raise WorkflowError("Wheel response did not confirm a zero-cost reward.")
    elif reward == "gift":
        # The site's reducer uses NextFreeGift to start the cooldown; the POST
        # response need not include the availability flag from the GET.
        next_gift = data.get("NextFreeGift")
        if (
            data.get("FreeGiftAvailable", False) is not False
            or not isinstance(next_gift, str)
            or not next_gift.strip()
        ):
            fields = ", ".join(sorted(data))
            raise WorkflowError(
                f"Gift response did not confirm the daily cooldown (fields: {fields})."
            )
    else:
        raise WorkflowError("Unknown reward type.")


class DailyRewards:
    def __init__(
        self,
        page: Page,
        expected: str,
        diagnostics: bool = False,
        *,
        settings: Settings | None = None,
        stop_requested: Callable[[], bool] | None = None,
        emit: Callable[[RewardResult], None] | None = None,
    ) -> None:
        self.page = page
        self.expected = expected
        self.responses: dict[tuple[str, str], tuple[int, Any]] = {}
        self.results: list[RewardResult] = []
        self.settings = settings or Settings(expected_username=expected)
        self.stop_requested = stop_requested or (lambda: False)
        self.emit = emit or (lambda result: None)
        self.authenticated = False
        self.active_reward: str | None = None
        self.mutation_started = False
        self.progress: Callable[[str, str | None, bool], None] = lambda stage, reward, mutation: (
            None
        )
        self.stage = "initializing"
        self._dismissing_popups = False
        self.diagnostics = diagnostics

    def step(self, stage: str) -> None:
        if self.stop_requested():
            raise WorkflowError("Shutdown requested")
        self.stage = stage
        self.progress(stage, self.active_reward, self.mutation_started)
        logging.getLogger(__name__).info("Step: %s", stage)

    def stop_diagnostics(self) -> None:
        pass

    def install_popup_handlers(self) -> None:
        # A modal can arrive after a manual check but before a click/assertion.
        self.page.add_locator_handler(
            self.page.locator('[data-testid="modal-backdrop"]:visible').last,
            lambda _: self.dismiss_popups(),
            # Manual dismissal also clicks a control inside the overlay. Its
            # nested handler must not wait for the overlay before that click.
            no_wait_after=True,
        )

    def observe(self, response: Response) -> None:
        parsed = urlsplit(response.url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != HOST
            or parsed.path not in {PROFILE, WHEEL, GIFT, UNLOCK}
        ):
            return
        try:
            payload = response.json()
        except Exception:
            payload = None
        self.responses[(response.request.method, parsed.path)] = (response.status, payload)

    def wait_for(
        self, predicate: Callable[[], bool], description: str, timeout: float = 45000
    ) -> None:
        timeout = min(timeout, self.settings.readiness_timeout.total_seconds() * 1000)
        deadline = time.monotonic() + timeout / 1000
        while not predicate():
            if self.stop_requested() and not self.mutation_started:
                raise WorkflowError("Shutdown requested")
            if time.monotonic() >= deadline:
                raise WorkflowError(
                    f"Timed out waiting for {description}. No claim will be retried."
                )
            # Pump Playwright events while waiting for the observed API state.
            self.page.wait_for_timeout(100)

    def api_data(self, path: str, method: str = "GET") -> dict[str, Any]:
        self.wait_for(lambda: (method, path) in self.responses, "API response")
        status, payload = self.responses[(method, path)]
        if path == PROFILE and status in {401, 403}:
            raise AuthenticationError("Profile rejected the session")
        if path == PROFILE and 200 <= status < 300:
            verify_identity(payload, self.expected)
        if not 200 <= status < 300:
            raise WorkflowError(f"API request failed (HTTP {status}).")
        return api_payload_data(payload)

    def wait_for_ready(self, locator: Locator, description: str, timeout: float = 45000) -> None:
        def ready() -> bool:
            # Closing the modal may be necessary before the target even mounts;
            # action-time handlers alone cannot reliably resolve that ordering.
            self.dismiss_popups()
            count = locator.count()
            if count > 1:
                raise WorkflowError(f"Multiple controls found for {description}; stopping.")
            return count == 1 and locator.is_visible()

        self.wait_for(ready, description, timeout=timeout)

    def scroll_to(self, locator: Locator, description: str) -> None:
        self.step(f"closing pop-ups before scrolling to {description}")
        self.dismiss_popups()
        self.step(f"scrolling to {description}")
        # Only move the viewport. Avoid stability/actionability checks on the
        # animated wheel, which may also invoke a modal handler mid-scroll.
        locator.evaluate(
            "element => element.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'})",
            timeout=10000,
        )
        self.step(f"closing pop-ups after scrolling to {description}")
        self.dismiss_popups()

    def verify_login(self) -> None:
        self.step("verifying account")
        self.api_data(PROFILE)
        verify_identity(self.responses[("GET", PROFILE)][1], self.expected)
        names = self.page.locator('[data-testid="user-name"]:visible')
        expect(names).to_have_count(1)
        expect(names).to_have_text(self.expected)
        self.authenticated = True
        logging.getLogger(__name__).info("Authenticated username verified: %s", self.expected)

    def dismiss_popups(self) -> None:
        if self._dismissing_popups:
            return
        self._dismissing_popups = True
        try:
            self._close_popups()
        finally:
            self._dismissing_popups = False

    @staticmethod
    def _dismiss_control(control: Locator) -> None:
        # Called only with the site's explicit modal/banner close selectors.
        # An arriving overlay can cover another close button between the count
        # check and click; DOM activation avoids waiting on pointer interception
        # or recursively entering the action-time overlay handler.
        control.evaluate(
            """element => {
                if (element.tagName !== 'BUTTON' || element.disabled)
                    throw new Error('Expected an enabled dismissal button');
                element.click();
            }""",
            timeout=10000,
        )

    def _close_popups(self) -> None:
        # Only explicit dismissal controls; never choose arbitrary CTA buttons.
        for _ in range(10):
            backdrops = self.page.locator('[data-testid="modal-backdrop"]:visible')
            count = backdrops.count()
            if count:
                top = backdrops.last
                close = top.locator('[data-testid="close-btn"]:visible')
                if close.count() != 1:
                    raise WorkflowError("A blocking modal has no recognized close control.")
                logging.getLogger(__name__).info("Closing page pop-up.")
                self._dismiss_control(close)
                expect(backdrops).to_have_count(count - 1, timeout=10000)
                continue
            banner_close = self.page.locator(
                '[data-testid="communications-banner"] [data-testid="close-icon"]:visible'
            )
            if banner_close.count() == 1:
                logging.getLogger(__name__).info("Closing communications banner.")
                self._dismiss_control(banner_close)
                # Closing is animated. Do not repeatedly activate the same
                # control while its component is still visible.
                expect(banner_close).to_have_count(0, timeout=10000)
                continue
            if self.page.locator(
                '[role="dialog"]:visible:not([data-testid="modal-backdrop"] *), [data-testid="shop-tutorial-backdrop"]:visible'
            ).count():
                raise WorkflowError("An unrecognized blocking pop-up needs inspection.")
            return
        raise WorkflowError("Too many pop-ups; stopping for inspection.")

    def navigate(self, path: str) -> None:
        self.step(f"opening {path.lstrip('/')}")
        self.step(f"closing pop-ups before {path.lstrip('/')} navigation")
        self.dismiss_popups()
        link = self.page.locator(
            f'[data-testid="nav"] a[href="{path}"]:visible, '
            f'[data-testid="nav"] a[href="https://www.monopolygo.com{path}"]:visible'
        )
        self.step(f"waiting for {path.lstrip('/')} menu link")
        self.wait_for_ready(
            link,
            f"{path} navigation link",
            timeout=self.settings.action_timeout.total_seconds() * 1000,
        )
        self.step(f"clicking {path.lstrip('/')} menu link")
        link.click()
        self.step(f"waiting for {path.lstrip('/')} page")
        self.page.wait_for_url(
            f"https://www.monopolygo.com{path}",
            timeout=self.settings.navigation_timeout.total_seconds() * 1000,
        )
        self.step(f"closing pop-ups after {path.lstrip('/')} navigation")
        self.dismiss_popups()

    @staticmethod
    def cooldown(locator: Locator, label: str) -> str | None:
        text = " ".join(locator.inner_text().split())
        match = re.search(label + r"\s*(?:\d+\s*[dhms]\s*)+", text, re.I)
        return match.group(0).strip() if match else None

    def record(self, reward: str, status: str, reason: str) -> None:
        observed = utcnow()
        label = r"Resets\s+in" if reward == "wheel" else r"Available\s+in"
        text = reason if status == "skipped" else getattr(self, "_last_countdown", None)
        duration = parse_countdown(text or "", label)
        result = RewardResult(
            reward,
            RewardStatus(status),
            reason,
            observed,
            text if duration is not None else None,
            observed + duration if duration is not None else None,
        )
        self.results.append(result)
        self.emit(result)
        self.mutation_started = False
        logging.getLogger(__name__).info("%s: %s — %s", reward, status, reason)

    def wait_for_cooldown(
        self, locator: Locator, label: str, description: str, timeout: float = 60000
    ) -> None:
        def settled() -> bool:
            # The site defers displayed wheel updates while its result modal is open.
            self.dismiss_popups()
            self._last_countdown = self.cooldown(locator, label)
            return bool(self._last_countdown)

        self.wait_for(settled, description, timeout=timeout)

    def claim(self, button: Locator, path: str, reward: str) -> None:
        if self.stop_requested():
            raise WorkflowError("Shutdown requested")
        self.dismiss_popups()
        expect(button).to_have_count(1)
        expect(button).to_be_visible()
        expect(button).to_be_enabled()
        self.responses.pop(("POST", path), None)
        # Exclude responses for requests already in flight before this click.
        if self.stop_requested():
            raise WorkflowError("Shutdown requested")
        initiated: list[Request] = []

        def capture(request: Request) -> None:
            parsed = urlsplit(request.url)
            if (
                request.method == "POST"
                and parsed.scheme == "https"
                and parsed.hostname == HOST
                and parsed.path == path
            ):
                initiated.append(request)

        self.page.on("request", capture)
        try:
            with self.page.expect_response(
                lambda response: bool(initiated) and response.request == initiated[0],
                timeout=self.settings.readiness_timeout.total_seconds() * 1000,
            ) as result:
                if self.stop_requested():
                    raise WorkflowError("Shutdown requested")
                self.mutation_started = True
                self.progress(self.stage, self.active_reward, True)
                button.click(
                    timeout=min(10000, self.settings.action_timeout.total_seconds() * 1000)
                )
        finally:
            self.page.remove_listener("request", capture)
        response = result.value
        if not 200 <= response.status < 300:
            raise WorkflowError(f"{reward} claim failed (HTTP {response.status}); not retrying.")
        try:
            payload = response.json()
        except Exception:
            raise WorkflowError(f"{reward} claim response was unreadable; not retrying.") from None
        verify_claim(payload, reward)

    def wheel(self) -> None:
        self.active_reward = "wheel"
        self._last_countdown = None
        self.navigate("/benefits")
        self.step("waiting for daily wheel to load")
        wheel = self.page.locator(
            '[data-testid="benefits-page"] [data-testid="spinner-container"]:visible'
        )
        self.wait_for_ready(wheel.get_by_test_id("spin-button"), "daily wheel control")
        expect(wheel).to_have_count(1)
        self.step("checking daily wheel")
        self.scroll_to(wheel, "daily wheel")
        self.step("reading daily wheel availability")
        cooldown = self.cooldown(wheel, r"Resets\s+in")
        if cooldown:
            self.record("wheel", "skipped", cooldown)
            return
        key = free_wheel_key(self.api_data(WHEEL))
        if key is None:
            self.record("wheel", "skipped", "API reports no free spin available")
            return
        if (
            wheel.get_attribute("data-wheel-points-cost") != "0"
            or wheel.get_attribute("data-wheel-key") != key
        ):
            raise WorkflowError("Displayed wheel does not match the available zero-cost wheel.")
        # A rerender to the paid wheel must make the click fail closed.
        free_control = self.page.locator(
            '[data-testid="benefits-page"] [data-testid="spinner-container"]'
            '[data-wheel-points-cost="0"]:visible [data-testid="spin-button"]'
        )
        self.claim(free_control, UNLOCK, "wheel")
        self.wait_for_cooldown(wheel, r"Resets\s+in", "wheel cooldown after the spin")
        self.dismiss_popups()
        self.record(
            "wheel", "claimed", "Successful zero-cost response and reset countdown confirmed"
        )

    def gift(self) -> None:
        self.active_reward = "gift"
        self._last_countdown = None
        self.navigate("/shop")
        self.step("checking daily shop gift")
        card = self.page.locator('[data-testid="store-banners-free-gift-card"]:visible')
        self.wait_for_ready(card, "daily shop gift card", timeout=30000)
        # Navigate the carousel containing this specific card, never live offers.
        carousel = card.locator(
            'xpath=ancestor::*[contains(concat(" ", normalize-space(@class), " "), " swiper ")][1]'
        )
        if carousel.count() == 1:
            pages = carousel.get_by_role("button", name=re.compile(r"^Go to slide \d+$"))
            if pages.count():
                pages.last.click()
        self.scroll_to(card, "daily shop gift")
        self.step("reading daily shop gift availability")
        cooldown = self.cooldown(card, r"Available\s+in")
        if cooldown:
            self.record("gift", "skipped", cooldown)
            return
        if not gift_available(self.api_data(GIFT)):
            self.record("gift", "skipped", "API reports daily gift unavailable")
            return
        self.claim(card.get_by_test_id("free-gift-button"), GIFT, "gift")
        self.wait_for_cooldown(card, r"Available\s+in", "daily gift cooldown", timeout=30000)
        self.dismiss_popups()
        self.record("gift", "claimed", "Successful daily gift response and cooldown confirmed")

    def run(self) -> RunResult:
        self.verify_login()
        if self.settings.wheel_enabled:
            self.wheel()
        if self.settings.gift_enabled:
            self.gift()
        return RunResult(tuple(self.results), "verified", utcnow())

    def screenshot(self, directory: Path = Path("artifacts")) -> Path:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        filename = directory / (
            "daily-rewards-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".png"
        )
        # Reserve the file privately before writing any account information.
        with filename.open("xb"):
            filename.chmod(0o600)
        self.page.screenshot(path=str(filename), full_page=True, timeout=10000)
        return filename


def parse_countdown(text: str, label: str) -> timedelta | None:
    matches = list(re.finditer(label + r"\s*([0-9dhms\s]+)(?=$)", " ".join(text.split()), re.I))
    if len(matches) != 1:
        return None
    try:
        return parse_duration(matches[0].group(1), allow_zero=True)
    except ValueError, OverflowError:
        return None
