"""Phone lock (studio/lock.py): this Mac is trusted, phones need the key cookie, other websites and rebinding hosts are refused.
Uses a small app with the same middleware (importing studio.app would open the real job database)."""
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from kidzone import paths
from kidzone.studio import lock

API = {"host": "127.0.0.1:8765"}
PHONE = {**API, "x-forwarded-for": "192.168.1.23", "x-forwarded-host": "192.168.1.5:5173"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LAN_KEY", tmp_path / "lan_key")
    app = FastAPI()

    @app.middleware("http")
    async def _lock(request: Request, call_next):
        if bad := lock.problem(request):
            return JSONResponse({"detail": bad[1], "locked": bad[0] == 401}, status_code=bad[0])
        return await call_next(request)

    @app.get("/api/x")
    def x():
        return {"ok": True}

    @app.post("/api/x")
    def x_post():
        return {"ok": True}

    @app.get("/api/unlock")
    def unlock(k: str = ""):
        return {"ok": lock.unlocks(k)}

    return TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 50000))   # like uvicorn on 127.0.0.1


def test_this_mac_is_trusted(client):
    assert client.get("/api/x", headers=API).status_code == 200
    assert client.post("/api/x", headers={**API, "origin": "http://127.0.0.1:8765"}).status_code == 200
    via_vite = {**API, "x-forwarded-for": "127.0.0.1", "x-forwarded-host": "127.0.0.1:5173", "origin": "http://127.0.0.1:5173"}
    assert client.post("/api/x", headers=via_vite).status_code == 200


def test_phone_needs_the_key(client):
    r = client.get("/api/x", headers=PHONE)
    assert r.status_code == 401 and r.json()["locked"]
    spoof = {**PHONE, "x-forwarded-for": "127.0.0.1, 192.168.1.23"}   # a phone can't claim to be the Mac
    assert client.get("/api/x", headers=spoof).status_code == 401
    assert client.get("/api/unlock", params={"k": "nope"}, headers=PHONE).json() == {"ok": False}
    k = lock.key()
    client.cookies.set(lock.COOKIE, k)
    assert client.get("/api/x", headers=PHONE).status_code == 200
    lock.reset_key()                                                  # "Make a new link" unlinks it
    assert client.get("/api/x", headers=PHONE).status_code == 401


def test_other_websites_and_rebinding_refused(client):
    evil = {**API, "x-forwarded-for": "127.0.0.1", "x-forwarded-host": "127.0.0.1:5173", "origin": "https://evil.example"}
    assert client.post("/api/x", headers=evil).status_code == 403
    assert client.get("/api/x", headers={"host": "rebind.evil.example:8765"}).status_code == 403


def test_key_file_is_private(client):
    lock.key()
    assert (paths.LAN_KEY.stat().st_mode & 0o777) == 0o600
