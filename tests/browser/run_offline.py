"""Exercise the real CLI/worker/supervisor against synthetic intercepted pages."""

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from test_rewards_browser import HTML

from monopolygo_rewards import browser, cli, supervisor, worker
from monopolygo_rewards.rewards import GIFT, UNLOCK, WHEEL
from monopolygo_rewards.session import AUTH_COOKIES, HOST, PROFILE, save_cookies


def fixture_browser(settings, stop, emit, *, login_only=False):
    original = browser.sync_playwright
    claimed = set()
    available = os.environ.get("OFFLINE_AVAILABLE") == "1"

    @contextmanager
    def playwright():
        with original() as p:
            launch = p.chromium.launch

            def launch_fixture(**kwargs):
                b = launch(**kwargs)
                new_context = b.new_context

                def context_fixture(**options):
                    c = new_context(**options)

                    def route(r):
                        parsed = urlsplit(r.request.url)
                        if parsed.hostname == "www.monopolygo.com":
                            r.fulfill(content_type="text/html", body=HTML)
                            return
                        if parsed.hostname != HOST:
                            r.abort()
                            return
                        path = parsed.path
                        if r.request.method == "POST":
                            if path not in {GIFT, UNLOCK} or path in claimed:
                                raise AssertionError("Unexpected or duplicate claim")
                            claimed.add(path)
                            data = (
                                {"UnlockedBenefit": {"PointsCost": 0}}
                                if path == UNLOCK
                                else {"NextFreeGift": "2026-11-10T13:00:00Z"}
                            )
                        elif path == PROFILE:
                            data = {"DisplayName": "WonderfulFinch83"}
                        elif path == WHEEL:
                            ready = available and UNLOCK not in claimed
                            data = {
                                "FreeSpinAvailable": ready,
                                "Wheels": [{"Key": "free", "PointsCost": 0, "Available": ready}],
                            }
                        elif path == GIFT:
                            data = {
                                "FreeGiftDefined": True,
                                "FreeGiftAvailable": available and GIFT not in claimed,
                            }
                        else:
                            r.abort()
                            return
                        r.fulfill(
                            content_type="application/json",
                            headers={
                                "Access-Control-Allow-Origin": "*",
                                "Access-Control-Allow-Headers": "*",
                            },
                            body=json.dumps({"IsSuccess": True, "Data": data}),
                        )

                    c.route("**/*", route)
                    return c

                b.new_context = context_fixture
                return b

            p.chromium.launch = launch_fixture
            yield p

    with patch.object(browser, "sync_playwright", playwright):
        return browser.run_browser(settings, stop, emit, login_only=login_only)


def main():
    with tempfile.TemporaryDirectory() as directory:
        os.environ.update(
            DATA_DIR=directory,
            EXPECTED_USERNAME="WonderfulFinch83",
            HEADLESS="true",
            ARTIFACTS_ENABLED="false",
            APPRISE_URL="",
        )
        save_cookies(
            Path(directory) / "session.cookies",
            [
                {
                    "name": n,
                    "value": "synthetic-only",
                    "domain": HOST,
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                    "expires": -1,
                }
                for n in AUTH_COOKIES
            ],
        )
        worker.supervise = partial(supervisor.supervise, target=fixture_browser)
        return cli.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
