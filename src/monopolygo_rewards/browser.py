"""One browser run; never leave a browser alive during scheduled sleep."""

from collections.abc import Callable
from multiprocessing.synchronize import Event
from typing import cast

from playwright._impl._api_structures import SetCookieParam
from playwright.sync_api import sync_playwright

from .config import Settings
from .diagnostics import configure_logging, safe_error
from .errors import AuthenticationError, SessionError
from .models import RewardResult, RewardStatus, RunResult, utcnow
from .rewards import DailyRewards
from .session import load_cookies, save_cookies


def run_browser(
    settings: Settings, stop_event: Event, emit: Callable, *, login_only: bool = False
) -> RunResult:
    configure_logging(settings)
    outcomes: list[RewardResult] = []
    auth = "unknown"
    error = None
    workflow = None
    browser = None

    def record(result: RewardResult) -> None:
        outcomes.append(result)
        emit(("result", result))

    try:
        cookies = load_cookies(settings.session_file)
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=settings.headless)
                context = browser.new_context()
                context.add_cookies(cast(list[SetCookieParam], cookies))
                page = context.new_page()
                page.set_default_timeout(settings.action_timeout.total_seconds() * 1000)
                workflow = DailyRewards(
                    page,
                    settings.expected_username,
                    settings=settings,
                    stop_requested=stop_event.is_set,
                    emit=record,
                )

                def progress(stage, reward, mutation):
                    emit(("progress", (stage, reward, mutation)))
                    if workflow.authenticated:
                        emit(("auth", "verified"))

                workflow.progress = progress
                page.on("response", workflow.observe)
                workflow.install_popup_handlers()
                workflow.step("loading website")
                page.goto(
                    "https://www.monopolygo.com/news",
                    wait_until="domcontentloaded",
                    timeout=settings.navigation_timeout.total_seconds() * 1000,
                )
                if login_only:
                    workflow.verify_login()
                else:
                    workflow.run()
                auth = "verified"
            except Exception as exc:
                auth = (
                    "blocked"
                    if isinstance(exc, (AuthenticationError, SessionError))
                    else ("verified" if workflow and workflow.authenticated else "unknown")
                )
                error = safe_error(exc)
                if (
                    workflow
                    and workflow.active_reward
                    and not any(r.reward == workflow.active_reward for r in outcomes)
                ):
                    record(
                        RewardResult(
                            workflow.active_reward,
                            RewardStatus.UNCERTAIN
                            if workflow.mutation_started
                            else RewardStatus.FAILED,
                            error,
                            utcnow(),
                        )
                    )
                if workflow and settings.artifacts_enabled:
                    try:
                        workflow.screenshot(settings.artifact_dir)
                    except Exception:
                        pass
            finally:
                if workflow and workflow.authenticated:
                    try:
                        save_cookies(settings.session_file, context.cookies())
                    except Exception as exc:
                        error = error or safe_error(exc)
                if settings.keep_open and browser and not stop_event.is_set():
                    emit(("inspection_ready", None))
                    while not stop_event.is_set():
                        stop_event.wait(0.1)
                if browser:
                    try:
                        browser.close()
                    except Exception as exc:
                        error = error or safe_error(exc)
    except Exception as exc:
        error = error or safe_error(exc)
        if isinstance(exc, SessionError):
            auth = "blocked"
    return RunResult(tuple(outcomes), auth, utcnow(), error)
