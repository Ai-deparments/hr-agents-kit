from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import agents, camera, discipline, docs, engagement, hh, hiring, kpi, materials, miniapp, nudges, org, panel, rauf, vacancies
from .config import settings
from .db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = settings()
    if not s.debug and (s.jwt_secret == "dev-only-change-me" or len(s.jwt_secret) < 32):
        raise RuntimeError("Set a random JWT_SECRET (>= 32 chars) in .env before running in production")
    init_db()
    yield


_dbg = settings().debug
app = FastAPI(title="HR Agents Kit", version="0.2.0", lifespan=lifespan,
              docs_url="/docs" if _dbg else None, redoc_url=None, openapi_url="/openapi.json" if _dbg else None)
app.add_middleware(CORSMiddleware, allow_origins=[settings().webapp_url] + (["http://localhost:5173"] if _dbg else []),
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-Api-Key"])

MAX_BODY = 5 * 1024 * 1024  # uploads (SOP .md, sales CSV) are small; refuse anything bigger


@app.middleware("http")
async def security_headers(request: Request, call_next):
    limit = 50 * 1024 * 1024 if request.url.path == "/api/onboarding/materials" else MAX_BODY  # videos for the bot
    if int(request.headers.get("content-length") or 0) > limit:
        return JSONResponse({"detail": "Request too large"}, status_code=413)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
    # the Mini App is framed by Telegram Web; nobody else may frame us
    resp.headers["Content-Security-Policy"] = ("frame-ancestors 'self' https://web.telegram.org https://*.telegram.org; "
                                               "object-src 'none'; base-uri 'self'")
    if not _dbg:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000"
    return resp
app.include_router(panel.router)
app.include_router(org.router)
app.include_router(kpi.router)
app.include_router(hh.router)
app.include_router(materials.router)
app.include_router(vacancies.router)
app.include_router(hiring.router)
app.include_router(docs.router)
app.include_router(nudges.router)
app.include_router(vacancies.public)
app.include_router(vacancies.facts_router)
app.include_router(miniapp.router)
app.include_router(agents.router)
app.include_router(rauf.router)
app.include_router(rauf.mini)
app.include_router(engagement.router)
app.include_router(engagement.mini)
app.include_router(camera.router)
app.include_router(discipline.router)


@app.get("/api/health")
def health():
    return {"ok": True}


if WEB_DIST.exists():  # production: serve the built React app from the same origin
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    _DIST = WEB_DIST.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        # resolve() + containment check: "%2e%2e/%2e%2e/.env" must never leave web/dist
        f = (_DIST / path).resolve()
        if path and f.is_file() and f.is_relative_to(_DIST):
            return FileResponse(f)
        return FileResponse(_DIST / "index.html")
