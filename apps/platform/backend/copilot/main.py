"""FastAPI app. Local only: bind it to 127.0.0.1."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth as authlib
from . import config, db, seed
from .routers import applications, matches, outreach, settings, system, worker
from .routers import auth as auth_router
from .tasks import Scheduler

log = logging.getLogger("copilot")


def create_app(db_path: Path | str | None = None,
               scheduler: bool | None = None,
               auth: authlib.AuthConfig | None = None) -> FastAPI:
    start_scheduler = config.SCHEDULER_ENABLED if scheduler is None else scheduler
    auth = auth or authlib.AuthConfig.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config.ensure_dirs()
        db.init(app.state.db_path)
        with db.session(app.state.db_path) as conn:
            seed.seed_defaults(conn)
        if start_scheduler:
            app.state.scheduler = Scheduler(app.state.db_path)
            app.state.scheduler.start()
        yield
        if app.state.scheduler:
            app.state.scheduler.shutdown()

    # A networked deployment does not publish its API schema.
    docs = {} if not auth.enabled else {"docs_url": None, "redoc_url": None,
                                        "openapi_url": None}
    app = FastAPI(title="Job Search Copilot", version="1.0", lifespan=lifespan, **docs)
    app.state.db_path = Path(db_path) if db_path else config.DB_PATH
    app.state.scheduler = None
    app.state.worker_seen = 0.0
    app.state.auth = auth
    if auth.required and not auth.configured:
        log.warning("COPILOT_REQUIRE_AUTH is on but no password is set: every request "
                    "is refused until COPILOT_PASSWORD_HASH is configured")

    @app.middleware("http")
    async def require_login(request: Request, call_next):
        status, message = authlib.decide(
            auth, request.method, request.url.path,
            request.cookies.get(authlib.COOKIE), request.headers.get("authorization"))
        if status != 200:
            return JSONResponse({"detail": message}, status_code=status)
        return await call_next(request)

    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS,
                       allow_methods=["*"], allow_headers=["*"],
                       allow_credentials=True)
    for router in (auth_router.router, system.router, matches.router, applications.router,
                   outreach.router, settings.router, worker.router):
        app.include_router(router, prefix="/api")

    @app.get("/api/health")
    def health():
        return {"ok": True}

    # Serve the built dashboard when it exists, so one process is enough for
    # a non-Docker run. Unknown paths fall through to the SPA.
    dist = config.PLATFORM_DIR / "frontend" / "dist"
    if (dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "not found")
            target = (dist / path).resolve()
            if path and target.is_file() and dist.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# The runner ticks every few seconds and a fetch makes hundreds of requests;
# neither belongs in the log line by line.
for noisy in ("apscheduler", "httpx", "httpx2", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
app = create_app()
