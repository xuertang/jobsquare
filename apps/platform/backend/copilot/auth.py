"""Login for a deployment that is reachable from a network.

On localhost the app runs without a login, as the design doc intends. On a
server it must not: set COPILOT_REQUIRE_AUTH=1 and every /api route needs
either a session cookie (the dashboard, after the password) or a bearer token
(the apply worker). Nothing is open except the health check and the login
endpoints themselves, and with no password configured everything is refused.

The password is never stored: only a scrypt hash, which you generate with
`python -m copilot.auth hash` and put in COPILOT_PASSWORD_HASH."""
from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import os
import secrets
import sys
import time
from dataclasses import dataclass, field

COOKIE = "copilot_session"
SESSION_DAYS = 30
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    """scrypt:n:r:p:salt:hash. Colon separated and base64url, so it survives
    a Compose .env file, where a dollar sign would be read as a variable."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                            p=SCRYPT_P, maxmem=128 * 1024 * 1024, dklen=32)
    return f"scrypt:{SCRYPT_N}:{SCRYPT_R}:{SCRYPT_P}:{_b64(salt)}:{_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split(":")
        if scheme != "scrypt":
            return False
        expected = _unb64(digest)
        got = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r),
                             p=int(p), maxmem=128 * 1024 * 1024, dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, expected)


def make_session(secret: str, ttl_seconds: int = SESSION_DAYS * 86400,
                 now: float | None = None) -> str:
    """A signed expiry time. Stateless: rotating the secret signs everyone out."""
    expires = str(int((now or time.time()) + ttl_seconds))
    sig = hmac.new(secret.encode(), expires.encode(), hashlib.sha256).digest()
    return f"{expires}.{_b64(sig)}"


def check_session(secret: str, token: str, now: float | None = None) -> bool:
    try:
        expires, sig = token.split(".", 1)
        expected = hmac.new(secret.encode(), expires.encode(), hashlib.sha256).digest()
        return (hmac.compare_digest(_unb64(sig), expected)
                and int(expires) > (now or time.time()))
    except (ValueError, TypeError):
        return False


@dataclass
class Throttle:
    """Slow down password guessing: after `limit` failures from one address,
    refuse that address for `lock` seconds. In memory, which is enough for a
    single process and a single user."""
    limit: int = 5
    window: int = 600
    lock: int = 600
    failures: dict[str, list[float]] = field(default_factory=dict)

    def retry_after(self, key: str, now: float | None = None) -> int:
        now = now or time.time()
        recent = [t for t in self.failures.get(key, []) if now - t < self.window]
        self.failures[key] = recent
        if len(recent) >= self.limit:
            return max(1, int(self.lock - (now - recent[-1])))
        return 0

    def fail(self, key: str, now: float | None = None) -> None:
        self.failures.setdefault(key, []).append(now or time.time())

    def clear(self, key: str) -> None:
        self.failures.pop(key, None)


@dataclass
class AuthConfig:
    required: bool = False
    password_hash: str = ""
    session_secret: str = ""
    worker_token: str = ""
    secure_cookie: bool = False
    throttle: Throttle = field(default_factory=Throttle)

    @classmethod
    def from_env(cls) -> "AuthConfig":
        password_hash = os.getenv("COPILOT_PASSWORD_HASH", "").strip()
        secret = os.getenv("COPILOT_SESSION_SECRET", "").strip()
        if password_hash and not secret:
            secret = secrets.token_hex(32)      # sessions end when the process does
        return cls(
            required=os.getenv("COPILOT_REQUIRE_AUTH", "0").lower() in ("1", "true", "yes"),
            password_hash=password_hash,
            session_secret=secret,
            worker_token=os.getenv("COPILOT_WORKER_TOKEN", "").strip(),
            secure_cookie=os.getenv("COPILOT_DASHBOARD_URL", "").startswith("https://"))

    @property
    def enabled(self) -> bool:
        """A password hash turns the login on; REQUIRE_AUTH makes it mandatory
        even when nobody has set one yet (then everything is refused)."""
        return self.required or bool(self.password_hash)

    @property
    def configured(self) -> bool:
        return bool(self.password_hash and self.session_secret)

    def session_ok(self, cookie: str | None) -> bool:
        return bool(cookie) and self.configured and check_session(self.session_secret, cookie)

    def worker_ok(self, authorization: str | None) -> bool:
        if not self.worker_token or not authorization:
            return False
        scheme, _, token = authorization.partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(
            token.strip().encode(), self.worker_token.encode())


OPEN_PATHS = ("/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/logout")


def decide(auth: AuthConfig, method: str, path: str, cookie: str | None,
           authorization: str | None) -> tuple[int, str]:
    """(status, message) for a request: 200 lets it through."""
    if not auth.enabled or method == "OPTIONS" or not path.startswith("/api/"):
        return 200, ""
    if path in OPEN_PATHS:
        return 200, ""
    if path.startswith("/api/worker/"):
        if not auth.worker_token:
            return 503, "No worker token is configured on the server."
        return (200, "") if auth.worker_ok(authorization) else (401, "Worker token rejected.")
    if not auth.configured:
        return 503, "No password is set on the server yet."
    return (200, "") if auth.session_ok(cookie) else (401, "Sign in to continue.")


def main(argv: list[str]) -> int:
    if argv[1:] != ["hash"]:
        print("usage: python -m copilot.auth hash", file=sys.stderr)
        return 2
    first = getpass.getpass("New dashboard password: ")
    if len(first) < 10:
        print("Use at least 10 characters.", file=sys.stderr)
        return 1
    if first != getpass.getpass("Again: "):
        print("The two entries differ.", file=sys.stderr)
        return 1
    print(hash_password(first))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
