"""Who may use the studio.

The API listens on 127.0.0.1 only. The web app (Vite) proxies /api and /files to it and, in LAN mode, also serves phones
on the Wi-Fi; it adds X-Forwarded-For / X-Forwarded-Host (`xfwd` in vite.config.ts). So:

- this computer (loopback) is trusted;
- anyone else (a phone) needs the key cookie, set once by opening the phone link /api/unlock?k=<key> (the QR code);
  "Make a new link" (POST /api/lan/reset) changes the key and locks out every phone until it scans again;
- the Host must be this API (a DNS-rebinding page can't talk to it), and a browser write (POST/PUT/PATCH/DELETE) must
  come from the studio's own page (Origin = the address the browser used), so other websites can't queue GPU jobs.
"""

import hmac
import ipaddress
import os
import secrets
from urllib.parse import urlsplit

from .. import paths

COOKIE = "rw_key"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
OPEN = {"/api/unlock"}


def reset_key() -> str:
    k = secrets.token_urlsafe(24)
    paths.LAN_KEY.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(paths.LAN_KEY, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(k + "\n")
    return k


def key() -> str:
    try:
        k = paths.LAN_KEY.read_text().strip()
    except FileNotFoundError:
        k = ""
    return k if len(k) >= 20 else reset_key()


def _loopback(host: str) -> bool:
    host = host.strip("[]")
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def client_host(request) -> str:
    """The real client: the last X-Forwarded-For hop (added by the Vite proxy), else the socket peer."""
    if xff := request.headers.get("x-forwarded-for"):
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else ""


def is_local(request) -> bool:
    return _loopback(client_host(request))


def problem(request) -> tuple[int, str] | None:
    """(status, message) when the request must be refused, else None."""
    host = urlsplit("//" + request.headers.get("host", "")).hostname or ""
    if not _loopback(host):
        return 403, "unknown host"
    if request.method in UNSAFE and (origin := request.headers.get("origin")):
        seen = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        if urlsplit(origin).netloc != seen:
            return 403, "requests from other websites are not allowed"
    if not is_local(request) and request.url.path not in OPEN:
        if not hmac.compare_digest(request.cookies.get(COOKIE, "").encode(), key().encode()):
            return 401, "This phone isn't linked yet: on your Mac, open “Open on your phone” and scan the code again."
    return None


def unlocks(k: str) -> bool:
    return bool(k) and hmac.compare_digest(k.encode(), key().encode())
