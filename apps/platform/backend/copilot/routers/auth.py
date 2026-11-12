from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from .. import auth as authlib

router = APIRouter(prefix="/auth", tags=["auth"])


def client_key(request: Request) -> str:
    """The caller's address for throttling. Behind the reverse proxy the first
    X-Forwarded-For entry is the real client: Caddy replaces whatever the
    client sent with the address it saw."""
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "?")


@router.get("/status")
def status(request: Request):
    cfg: authlib.AuthConfig = request.app.state.auth
    return {"required": cfg.enabled, "configured": cfg.configured,
            "authenticated": not cfg.enabled or cfg.session_ok(
                request.cookies.get(authlib.COOKIE))}


class Login(BaseModel):
    password: str


@router.post("/login")
def login(body: Login, request: Request, response: Response):
    cfg: authlib.AuthConfig = request.app.state.auth
    if not cfg.enabled:
        return {"authenticated": True}
    if not cfg.configured:
        raise HTTPException(503, "No password is set on the server yet.")
    key = client_key(request)
    wait = cfg.throttle.retry_after(key)
    if wait:
        raise HTTPException(429, f"Too many attempts. Try again in {wait // 60 + 1} min.",
                            headers={"Retry-After": str(wait)})
    if not authlib.verify_password(body.password, cfg.password_hash):
        cfg.throttle.fail(key)
        raise HTTPException(401, "Wrong password.")
    cfg.throttle.clear(key)
    response.set_cookie(
        authlib.COOKIE, authlib.make_session(cfg.session_secret),
        max_age=authlib.SESSION_DAYS * 86400, httponly=True, secure=cfg.secure_cookie,
        samesite="lax", path="/")
    return {"authenticated": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(authlib.COOKIE, path="/")
    return {"authenticated": False}
