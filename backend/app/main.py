import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy import text  # noqa: E402

from . import analysis  # noqa: E402
from .db import engine  # noqa: E402
from .llm import store  # noqa: E402
from .review import api as review_api  # noqa: E402
from .review import seeds  # noqa: E402
from .review import store as review_store  # noqa: E402
from .rules import api as rules_api  # noqa: E402
from .rules import registry  # noqa: E402
from .rules.models import Asset  # noqa: E402
from .visitors import visitor_id  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DECISION(Q16): tables are created at startup. Fine while the schema is small;
    # switch to migrations (Alembic) once there's data worth preserving across changes.
    store.metadata.create_all(engine)
    review_store.ensure_schema()
    registry.metadata.create_all(engine)
    # Seeding runs the AI checks on the demo queue the first time, which takes a minute,
    # so it happens in the background and the app starts serving straight away.
    threading.Thread(target=seeds.seed_if_empty, daemon=True).start()
    yield


app = FastAPI(title="ClearPath Compliance Review", lifespan=lifespan)
app.include_router(review_api.router)
app.include_router(rules_api.router)


@app.get("/api/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db = "ok"
    except Exception as exc:
        # Report rather than crash: this endpoint exists to diagnose deploys.
        db = f"error: {exc.__class__.__name__}"
    return {"api": "ok", "db": db}


@app.post("/api/analyze")
def analyze(asset: Asset, request: Request) -> analysis.AnalyzeResult:
    return analysis.analyze(asset, visitor_id(request))


class Limits(BaseModel):
    ai_enabled: bool
    remaining_this_hour: int
    limit_per_hour: int


@app.get("/api/limits")
def limits(request: Request) -> Limits:
    return Limits(
        ai_enabled=bool(os.environ.get("ANTHROPIC_API_KEY")),
        remaining_this_hour=store.remaining(visitor_id(request)),
        limit_per_hour=store.PER_VISITOR_PER_HOUR,
    )


# In production FastAPI serves the built React app; in dev, Vite serves it instead.
DIST = (Path(__file__).resolve().parents[2] / "frontend" / "dist").resolve()

if DIST.is_dir():

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        file = (DIST / path).resolve()
        if path and file.is_file() and file.is_relative_to(DIST):
            return FileResponse(file)
        # Anything else is a client-side route.
        return FileResponse(DIST / "index.html")
