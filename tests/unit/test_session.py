import json
import os

import pytest

from monopolygo_rewards.errors import SessionError
from monopolygo_rewards.session import AUTH_COOKIES, import_har, load_cookies, save_cookies
from monopolygo_rewards.storage import account_lock, atomic_write_json


def test_import_without_signing_bundle_and_roundtrip(tmp_path):
    capture = {
        "log": {
            "entries": [
                {
                    "request": {
                        "url": "https://api.prod.monopolygo.com/web-portal/user-profile",
                        "method": "GET",
                        "cookies": [{"name": n, "value": "synthetic"} for n in AUTH_COOKIES],
                    },
                    "response": {"status": 200},
                }
            ]
        }
    }
    har = tmp_path / "test.har"
    har.write_text(json.dumps(capture))
    dest = tmp_path / "cookies"
    import_har(har, dest)
    cookies = load_cookies(dest)
    assert {c["name"] for c in cookies} == AUTH_COOKIES
    assert all(c["httpOnly"] and c["secure"] for c in cookies)
    assert dest.stat().st_mode & 0o777 == 0o600
    cookies[0]["expires"] = 1
    save_cookies(dest, cookies)
    with pytest.raises(SessionError):
        load_cookies(dest)


def test_lock_canonical_path_and_atomic_private_state(tmp_path):
    alias = tmp_path / "alias"
    data = tmp_path / "data"
    data.mkdir()
    alias.symlink_to(data, target_is_directory=True)
    with account_lock(data):
        with pytest.raises(SessionError):
            with account_lock(alias):
                pytest.fail("Second owner was allowed")
    with account_lock(data):
        atomic_write_json(data / "state.json", {"safe": True})
    assert json.loads((data / "state.json").read_text()) == {"safe": True}
    assert os.stat(data / "state.json").st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "capture", [None, {"log": {"entries": [{"request": {"url": 123}}]}}, {"log": {"entries": []}}]
)
def test_malformed_har_has_safe_error(tmp_path, capture):
    source = tmp_path / "bad.har"
    source.write_text(json.dumps(capture))
    with pytest.raises(SessionError):
        import_har(source, tmp_path / "cookies")


def test_ambiguous_har_cookie_does_not_replace_existing_session(tmp_path):
    source = tmp_path / "bad.har"
    request = {
        "url": "https://api.prod.monopolygo.com/web-portal/user-profile",
        "method": "GET",
        "cookies": [{"name": n, "value": "synthetic"} for n in AUTH_COOKIES],
    }
    request["cookies"].append({"name": next(iter(AUTH_COOKIES)), "value": "different"})
    source.write_text(
        json.dumps({"log": {"entries": [{"request": request, "response": {"status": 200}}]}})
    )
    destination = tmp_path / "cookies"
    destination.write_text("original")
    with pytest.raises(SessionError):
        import_har(source, destination)
    assert destination.read_text() == "original"


def test_empty_domain_marker_imports_and_loads_but_empty_token_fails(tmp_path):
    source = tmp_path / "capture.har"
    token = "X-WithBuddies-Cookie-SessionToken"
    marker = token + "-Domain"

    def capture(value):
        return {
            "log": {
                "entries": [
                    {
                        "request": {
                            "url": "https://api.prod.monopolygo.com/web-portal/user-profile",
                            "method": "GET",
                            "cookies": [
                                {"name": token, "value": value},
                                {"name": marker, "value": ""},
                            ],
                        },
                        "response": {"status": 200},
                    }
                ]
            }
        }

    source.write_text(json.dumps(capture("synthetic-token")))
    destination = tmp_path / "cookies"
    import_har(source, destination)
    cookies = load_cookies(destination)
    assert {c["name"]: c["value"] for c in cookies} == {token: "synthetic-token", marker: ""}
    original = destination.read_bytes()
    source.write_text(json.dumps(capture("")))
    with pytest.raises(SessionError):
        import_har(source, destination)
    assert destination.read_bytes() == original


def test_saved_empty_session_token_is_rejected(tmp_path):
    destination = tmp_path / "cookies"
    save_cookies(
        destination,
        [
            {
                "name": n,
                "value": "",
                "domain": "api.prod.monopolygo.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "expires": -1,
                "sameSite": "Lax",
            }
            for n in AUTH_COOKIES
        ],
    )
    with pytest.raises(SessionError):
        load_cookies(destination)
