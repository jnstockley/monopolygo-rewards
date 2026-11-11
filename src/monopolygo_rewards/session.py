"""Offline cookie bootstrap and compatible Mozilla cookie persistence."""

import http.cookiejar
import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Cookie

from .errors import SessionError

HOST = "api.prod.monopolygo.com"
PROFILE = "/web-portal/user-profile"
AUTH_COOKIES = {"X-WithBuddies-Cookie-SessionToken", "X-WithBuddies-Cookie-SessionToken-Domain"}
DOMAINS = {HOST, "prod.monopolygo.com", "monopolygo.com"}


def load_cookies(path: Path) -> list[Cookie]:
    jar = http.cookiejar.MozillaCookieJar()
    try:
        jar.load(str(path), ignore_discard=True)
        cookies: list[Cookie] = []
        identities = set()
        for c in jar:
            if c.name not in AUTH_COOKIES or c.domain.lstrip(".") not in DOMAINS or c.is_expired():
                continue
            identity = (c.domain, c.path, c.name)
            if (
                identity in identities
                or c.value is None
                or not c.secure
                or (c.name == "X-WithBuddies-Cookie-SessionToken" and not c.value)
            ):
                raise ValueError
            identities.add(identity)
            cookies.append(
                {
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain,
                    "path": c.path,
                    "secure": c.secure,
                    "httpOnly": c.has_nonstandard_attr("HttpOnly")
                    or c.has_nonstandard_attr("HTTPOnly"),
                    "sameSite": "Lax",
                    "expires": float(c.expires) if c.expires else -1,
                }
            )
        if {c["name"] for c in cookies} != AUTH_COOKIES:
            raise ValueError
        return cookies
    except OSError, ValueError, http.cookiejar.LoadError:
        raise SessionError(
            "Required unexpired session cookies missing; import a new session"
        ) from None


def save_cookies(path: Path, cookies: Sequence[Cookie]) -> None:
    jar = http.cookiejar.MozillaCookieJar()
    identities = set()
    for c in cookies:
        if c["name"] not in AUTH_COOKIES or c["domain"].lstrip(".") not in DOMAINS:
            continue
        identity = (c["domain"], c["path"], c["name"])
        if identity in identities:
            raise SessionError("Ambiguous duplicate session cookie")
        identities.add(identity)
        expiry = c.get("expires", -1)
        jar.set_cookie(
            http.cookiejar.Cookie(
                version=0,
                name=c["name"],
                value=c["value"],
                port=None,
                port_specified=False,
                domain=c["domain"],
                domain_specified=True,
                domain_initial_dot=c["domain"].startswith("."),
                path=c["path"],
                path_specified=True,
                secure=c.get("secure", True),
                expires=int(expiry) if expiry > 0 else None,
                discard=expiry <= 0,
                comment=None,
                comment_url=None,
                rest={"HTTPOnly": ""} if c.get("httpOnly") else {},
                rfc2109=False,
            )
        )
    if {c.name for c in jar} != AUTH_COOKIES:
        raise SessionError("Cannot save incomplete session cookies")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".rewards-cookies-", dir=path.parent)
    os.close(fd)
    try:
        jar.save(name, ignore_discard=True, ignore_expires=True)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def import_har(source: Path, destination: Path) -> None:
    try:
        entries = json.loads(source.read_text())["log"]["entries"]
        requests = [
            e["request"]
            for e in entries
            if urlsplit(e["request"]["url"]).scheme == "https"
            and urlsplit(e["request"]["url"]).hostname == HOST
            and urlsplit(e["request"]["url"]).path == PROFILE
            and e["request"]["method"] == "GET"
            and e["response"]["status"] == 200
        ]
        values = {
            c["name"]: c["value"] for c in requests[-1]["cookies"] if c["name"] in AUTH_COOKIES
        }
        names = [c["name"] for c in requests[-1]["cookies"] if c["name"] in AUTH_COOKIES]
        if (
            len(names) != len(set(names))
            or set(values) != AUTH_COOKIES
            or not all(isinstance(v, str) for v in values.values())
            or not values.get("X-WithBuddies-Cookie-SessionToken")
        ):
            raise ValueError
        cookies: list[Cookie] = [
            {
                "name": n,
                "value": v,
                "domain": HOST,
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
                "expires": -1,
            }
            for n, v in values.items()
        ]
        save_cookies(destination, cookies)
    except OSError, ValueError, KeyError, IndexError, TypeError, AttributeError:
        raise SessionError(
            "HAR has no successful profile request with complete session cookies"
        ) from None
