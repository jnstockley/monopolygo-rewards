from types import SimpleNamespace

from monopolygo_rewards import browser
from monopolygo_rewards.config import Settings
from monopolygo_rewards.errors import AuthenticationError, WorkflowError
from monopolygo_rewards.session import AUTH_COOKIES, HOST, load_cookies, save_cookies


def test_primary_failure_survives_cleanup_and_verified_cookie_updates(tmp_path, monkeypatch):
    s = Settings("test", session_file=tmp_path / "cookies", artifacts_enabled=False)
    cookies = [
        {
            "name": n,
            "value": "before",
            "domain": HOST,
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "expires": -1,
            "sameSite": "Lax",
        }
        for n in AUTH_COOKIES
    ]
    save_cookies(s.session_file, cookies)
    closed = []

    class Driver:
        def __enter__(self):
            return SimpleNamespace(chromium=self)

        def __exit__(self, *args):
            pass

        def launch(self, **kwargs):
            return self

        def new_context(self):
            return self

        def add_cookies(self, values):
            pass

        def new_page(self):
            return SimpleNamespace(
                set_default_timeout=lambda *_: None, on=lambda *_: None, goto=lambda *a, **k: None
            )

        def cookies(self):
            return [{**c, "value": "after"} for c in cookies]

        def close(self):
            closed.append(True)
            raise RuntimeError("cleanup-private-detail")

    class Workflow:
        active_reward = None
        authenticated = True

        def __init__(self, *a, **k):
            pass

        def observe(self, *a):
            pass

        def install_popup_handlers(self):
            pass

        def step(self, *a):
            pass

        def run(self):
            raise WorkflowError("Original failure")

    monkeypatch.setattr(browser, "sync_playwright", Driver)
    monkeypatch.setattr(browser, "DailyRewards", Workflow)
    event = SimpleNamespace(is_set=lambda: False)
    result = browser.run_browser(s, event, lambda _: None)
    assert result.error == "Original failure"
    assert closed == [True]
    assert all(c["value"] == "after" for c in load_cookies(s.session_file))
    Workflow.authenticated = False
    Workflow.run = lambda self: (_ for _ in ()).throw(AuthenticationError("Wrong account"))
    save_cookies(s.session_file, cookies)
    result = browser.run_browser(s, event, lambda _: None)
    assert result.auth_status == "blocked"
    assert all(c["value"] == "before" for c in load_cookies(s.session_file))
