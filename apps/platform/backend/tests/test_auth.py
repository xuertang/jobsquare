"""The login that guards a networked deployment. Local runs have it off."""
import time

import pytest
from fastapi.testclient import TestClient

from copilot import auth as authlib
from copilot.main import create_app
from tests.conftest import add_posting
from copilot import db

PASSWORD = "correct horse battery"          # a test value, used nowhere else


@pytest.fixture(scope="module")
def password_hash():
    return authlib.hash_password(PASSWORD)


def make(db_path, **kw):
    return create_app(db_path, scheduler=False, auth=authlib.AuthConfig(**kw))


@pytest.fixture
def secured(db_path, password_hash):
    cfg = dict(required=True, password_hash=password_hash, session_secret="s" * 32,
               worker_token="w" * 40)
    with TestClient(make(db_path, **cfg)) as c:
        yield c


def test_hash_and_verify():
    stored = authlib.hash_password(PASSWORD)
    assert stored.startswith("scrypt:") and "$" not in stored, "must survive a .env file"
    assert authlib.verify_password(PASSWORD, stored)
    assert not authlib.verify_password(PASSWORD + "x", stored)
    assert not authlib.verify_password(PASSWORD, "garbage")
    assert authlib.hash_password(PASSWORD) != stored, "salted"


def test_session_tokens_expire_and_cannot_be_forged():
    token = authlib.make_session("secret", ttl_seconds=60, now=1000)
    assert authlib.check_session("secret", token, now=1030)
    assert not authlib.check_session("secret", token, now=1061), "expired"
    assert not authlib.check_session("other", token, now=1030), "wrong key"
    later, sig = token.split(".")
    assert not authlib.check_session("secret", f"{int(later) + 9999}.{sig}", now=1030)
    assert not authlib.check_session("secret", "nonsense", now=1030)


def test_local_default_has_no_login(client):
    assert client.get("/api/auth/status").json() == {
        "required": False, "configured": False, "authenticated": True}
    assert client.get("/api/matches").status_code == 200


def test_everything_is_closed_without_a_session(secured):
    assert secured.get("/api/health").json() == {"ok": True}
    assert secured.get("/api/auth/status").json() == {
        "required": True, "configured": True, "authenticated": False}
    for path in ("/api/status", "/api/matches", "/api/settings/profile",
                 "/api/settings/export", "/api/applications/1/screenshot"):
        r = secured.get(path)
        assert r.status_code == 401 and r.json()["detail"] == "Sign in to continue.", path
    assert secured.post("/api/run/daily").status_code == 401
    assert secured.put("/api/settings/profile", json={}).status_code == 401
    # The API schema is not published. (With a built dashboard these paths
    # fall through to the single-page app, so check the routes themselves.)
    assert secured.app.docs_url is None and secured.app.openapi_url is None
    assert "swagger" not in secured.get("/docs").text.lower()


def test_login_sets_a_session_cookie(secured):
    assert secured.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    r = secured.post("/api/auth/login", json={"password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert secured.get("/api/matches").status_code == 200
    assert secured.get("/api/auth/status").json()["authenticated"] is True
    secured.post("/api/auth/logout")
    assert secured.get("/api/matches").status_code == 401


def test_cookie_is_secure_behind_https(db_path, password_hash):
    app = make(db_path, required=True, password_hash=password_hash, session_secret="s" * 32,
               secure_cookie=True)
    with TestClient(app, base_url="https://copilot.test") as c:
        r = c.post("/api/auth/login", json={"password": PASSWORD})
        assert "secure" in r.headers["set-cookie"].lower()


def test_password_guessing_is_throttled(secured):
    for _ in range(5):
        assert secured.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    locked = secured.post("/api/auth/login", json={"password": PASSWORD})
    assert locked.status_code == 429 and int(locked.headers["retry-after"]) > 0
    # A different address is not locked out by someone else's guesses.
    ok = secured.post("/api/auth/login", json={"password": PASSWORD},
                      headers={"x-forwarded-for": "203.0.113.9"})
    assert ok.status_code == 200


def test_throttle_window():
    t = authlib.Throttle(limit=2, window=60, lock=30)
    t.fail("a", now=100); t.fail("a", now=101)
    assert t.retry_after("a", now=102) == 29
    assert t.retry_after("a", now=200) == 0, "failures age out"
    assert t.retry_after("b", now=102) == 0


def test_worker_needs_its_token_and_a_session_is_not_enough(secured, db_path):
    assert secured.post("/api/worker/claim").status_code == 401
    assert secured.post("/api/worker/claim",
                        headers={"Authorization": "Bearer wrong"}).status_code == 401
    good = {"Authorization": "Bearer " + "w" * 40}
    assert secured.post("/api/worker/claim", headers=good).json() == {"task": None}
    # The dashboard session does not open the worker endpoints, and the
    # worker token does not open the dashboard's.
    secured.post("/api/auth/login", json={"password": PASSWORD})
    assert secured.post("/api/worker/claim").status_code == 401
    secured.post("/api/auth/logout")
    assert secured.get("/api/settings/profile", headers=good).status_code == 401


def test_required_but_unconfigured_refuses_everything(db_path):
    with TestClient(make(db_path, required=True)) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/auth/status").json() == {
            "required": True, "configured": False, "authenticated": False}
        assert c.get("/api/matches").status_code == 503
        assert c.post("/api/worker/claim", headers={"Authorization": "Bearer x"}).status_code == 503
        assert c.post("/api/auth/login", json={"password": "anything"}).status_code == 503


def test_config_from_env(monkeypatch, password_hash):
    monkeypatch.setenv("COPILOT_REQUIRE_AUTH", "1")
    monkeypatch.setenv("COPILOT_PASSWORD_HASH", password_hash)
    monkeypatch.setenv("COPILOT_SESSION_SECRET", "k" * 64)
    monkeypatch.setenv("COPILOT_WORKER_TOKEN", "t" * 64)
    monkeypatch.setenv("COPILOT_DASHBOARD_URL", "https://copilot.example.com")
    cfg = authlib.AuthConfig.from_env()
    assert cfg.required and cfg.configured and cfg.secure_cookie
    assert cfg.worker_ok("Bearer " + "t" * 64) and not cfg.worker_ok("Basic " + "t" * 64)
    monkeypatch.delenv("COPILOT_SESSION_SECRET")
    assert len(authlib.AuthConfig.from_env().session_secret) == 64, "falls back to a random key"


def test_worker_client_sends_its_token(secured, tmp_path, monkeypatch):
    from worker.__main__ import load_worker_env
    from worker.client import Api

    api = Api("https://copilot.example.com/", token="w" * 40)
    assert str(api.http.base_url) == "https://copilot.example.com/api/worker/"
    assert api.http.headers["authorization"] == "Bearer " + "w" * 40
    assert "authorization" not in Api("http://127.0.0.1:8000").http.headers
    # The same header against the real app.
    assert secured.post("/api/worker/claim", headers=dict(api.http.headers)).status_code == 200

    env = tmp_path / ".worker.env"
    env.write_text("# written by deploy.sh\nCOPILOT_API=https://copilot.example.com\n"
                   "COPILOT_WORKER_TOKEN='abc123'\n")
    monkeypatch.delenv("COPILOT_API", raising=False)
    monkeypatch.setenv("COPILOT_WORKER_TOKEN", "from-shell")
    assert load_worker_env(env) is True
    import os
    assert os.environ["COPILOT_API"] == "https://copilot.example.com"
    assert os.environ["COPILOT_WORKER_TOKEN"] == "from-shell", "the shell wins over the file"
    assert load_worker_env(tmp_path / "missing") is False


def test_hash_command_prompts_twice_and_rejects_weak_or_mismatched(monkeypatch, capsys):
    answers = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr(authlib.getpass, "getpass", lambda prompt="": next(answers))
    assert authlib.main(["auth", "hash"]) == 0
    printed = capsys.readouterr().out.strip()
    assert authlib.verify_password(PASSWORD, printed) and PASSWORD not in printed

    answers = iter(["short"])
    assert authlib.main(["auth", "hash"]) == 1
    answers = iter([PASSWORD, PASSWORD + "typo"])
    assert authlib.main(["auth", "hash"]) == 1
    assert authlib.main(["auth"]) == 2
    assert capsys.readouterr().out == "", "nothing is printed on failure"
