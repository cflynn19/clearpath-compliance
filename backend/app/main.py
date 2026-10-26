import hashlib
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
from .llm.rules import JUDGMENT_RULES  # noqa: E402
from .rules.builtin import BUILTIN_RULES  # noqa: E402
from .rules.models import Asset, Channel, FlagType, Product  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DECISION(Q16): tables are created at startup. Fine while the schema is small;
    # switch to migrations (Alembic) once there's data worth preserving across changes.
    store.metadata.create_all(engine)
    yield


app = FastAPI(title="ClearPath Compliance Review", lifespan=lifespan)


def visitor_id(request: Request) -> str:
    """Who to count usage against: the client's IP address, hashed so it isn't stored raw.

    Behind Render's proxy the client address is the first X-Forwarded-For entry. A client
    can forge that header, but all it gains is more per-visitor quota; the global daily
    cap still bounds the cost (D11).
    """
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")
    return hashlib.sha256(ip.encode()).hexdigest()[:32]


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
    remaining_this_hour: int
    limit_per_hour: int


@app.get("/api/limits")
def limits(request: Request) -> Limits:
    return Limits(
        remaining_this_hour=store.remaining(visitor_id(request)),
        limit_per_hour=store.PER_VISITOR_PER_HOUR,
    )


class RuleOut(BaseModel):
    id: str
    name: str
    type: FlagType
    citation: str
    description: str
    products: list[Product]
    channels: list[Channel]
    enabled: bool
    source: str


@app.get("/api/rules")
def rules() -> list[RuleOut]:
    code = [
        RuleOut(
            id=r.id,
            name=r.name,
            type=r.type,
            citation=r.citation,
            description=r.description,
            products=sorted(r.products),
            channels=sorted(r.channels),
            enabled=r.enabled,
            source=r.source,
        )
        for r in BUILTIN_RULES
    ]
    judgment = [
        RuleOut(
            id=r.id,
            name=r.name,
            type=r.type,
            citation=r.citation,
            description=r.instruction,
            products=sorted(r.products),
            channels=sorted(r.channels),
            enabled=r.enabled,
            source=r.source,
        )
        for r in JUDGMENT_RULES
    ]
    return code + judgment


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
