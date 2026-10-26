# ClearPath Compliance Review

A review workspace for ClearPath Financial's marketing compliance team (a fictional
consumer lender). Every marketing asset arrives already checked: definite rule
violations found by code, possible issues found by an LLM. The reviewer makes every
final call, and the decision is recorded with its evidence.

**Live:** https://clearpath-web-j7th.onrender.com

## Key assumptions

- The bottleneck is the review work itself (finding issues, chasing status), not just the
  spreadsheet
- The primary user is the compliance reviewer; submitters stay outside the tool for v1
- Missing a real violation is worse than a false flag, so the tool overflags, with two
  clearly different flag types
- AI assists, the human decides: nothing is approved without a reviewer
- Text-only assets for v1, US market

Full list with reasoning: [ASSUMPTIONS.md](ASSUMPTIONS.md) ·
Decisions and tradeoffs: [DECISIONS.md](DECISIONS.md) ·
Build plan: [PLAN.md](PLAN.md)

## Running locally

Needs Python 3.12, Node 22+, and a local Postgres.

```bash
createdb clearpath
cp .env.example .env

# API on :8000
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload

# UI on :5173 (forwards /api to :8000), in a second terminal
cd frontend
npm install
npm run dev
```

Production runs as a single container (see `Dockerfile`): FastAPI serves both the API
and the built React app.
