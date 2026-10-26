from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from sqlalchemy import text  # noqa: E402

from .db import engine  # noqa: E402

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
