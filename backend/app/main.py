from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy import text  # noqa: E402

from .db import engine  # noqa: E402
from .rules.builtin import BUILTIN_RULES  # noqa: E402
from .rules.engine import run_code_checks  # noqa: E402
from .rules.models import Asset, Channel, Flag, FlagType, Product  # noqa: E402

app = FastAPI(title="ClearPath Compliance Review")


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


class AnalyzeResult(BaseModel):
    flags: list[Flag]


@app.post("/api/analyze")
def analyze(asset: Asset) -> AnalyzeResult:
    return AnalyzeResult(flags=run_code_checks(asset))


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
    return [
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
