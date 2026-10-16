from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import agents, miniapp, panel
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


app = FastAPI(title="HR Agents Kit", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings().webapp_url, "http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(panel.router)
app.include_router(miniapp.router)
app.include_router(agents.router)


@app.get("/api/health")
def health():
    return {"ok": True}


if WEB_DIST.exists():  # production: serve the built React app from the same origin
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = WEB_DIST / path
        return FileResponse(f if path and f.is_file() else WEB_DIST / "index.html")
