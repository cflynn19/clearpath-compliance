# Build plan

**Deliverables:** public deployed URL + public GitHub repo.

## Core loop (v1)

Asset arrives (seeded queue or paste box) -> code checks + LLM checks run -> reviewer
opens it, sees the text with highlights and the two flag types -> resolves flags
(fix / dismiss with reason / acknowledge) -> approves or rejects -> decision and flags
stored against the version.

## Scope

**Must**
- Review screen: asset text with highlights, check-failed and needs-judgment flags
- Code rule engine plus starter rules, with unit tests
- LLM judgment checks: structured output, quote verification, injection handling
- Resolve-before-approve flow, dismiss reasons, audit storage
- Queue view with statuses
- Seeded mock data (LLM results computed at seed time) plus a paste box
- LLM safety: caching, rate limit, daily cap, fallback to code checks only
- Reset demo button
- Deployed, public, works without me

**Should**
- Custom rules (phrase rule = check failed, plain English = needs judgment)
- Dismissal counts per rule
- Evaluation script on labelled data

**Won't (v1):** see DECISIONS.md

## Architecture (sketch, refine as I build)

- `backend/` FastAPI
  - `rules/`: built-in code checks, each one a small testable function
  - `llm/`: judgment checks, prompt, output schema, quote verification
  - `checks.py`: runs both, merges the flags, caches by content hash
  - API: queue, asset detail, analyze (paste), resolve flag, decide, rules, reset
- `frontend/` React (Vite), built and served by FastAPI
- Postgres

**Entities (shape TBD):** Asset, AssetVersion, Rule, Flag, FlagResolution, Decision,
AuditEvent

## Starter rules (verify each one before relying on it)

**Code (check failed)**
- Rate or payment terms mentioned without an APR disclosure (Reg Z / TILA advertising)
- Mortgage content without an NMLS ID
- Email without an unsubscribe mechanism or physical address (CAN-SPAM)
- Banned or high-risk phrases: "guaranteed approval", "risk-free", ...
- Required product disclaimer missing

**LLM (needs judgment)**
- Misleading speed or approval claims ("approved in minutes")
- Implied guarantees ("everyone qualifies")
- Unsupported comparisons ("lowest rates anywhere")
- Urgency or pressure tactics
- Disclosure present but buried, or contradicted by the headline
- Injection-like text in the asset

## Mock data

- ~20-30 text assets across personal loans / credit cards / mortgage prequal, and
  channels: email, social, landing page, affiliate page, search ad
- Rough mix: 1/3 clean, 1/3 subtle issues, 1/3 obvious issues
- At least 2 prompt-injection attempts in affiliate content
- Every asset labelled with its expected flags (for the evaluation)
- I write the tricky ones by hand; AI can generate volume

## Build order

| Phase | Ship | Done when |
|---|---|---|
| 1 | Docs committed first. Scaffold. Deploy hello world. Rule engine + 5-8 code checks + tests. | Live URL; pasting an ad returns check-failed flags |
| 2 | LLM checks with quote verification + injection handling. Review screen with highlights and both flag types. | One ad reviewed end to end |
| 3 | Resolve / dismiss / acknowledge / approve. Audit storage. Queue + statuses. | Full core loop on the live URL |
| 4 | Mock data + seed script + reset. Evaluation script. Custom rules. Dismissal counts. | Demo-ready |
| 5 | README, final DECISIONS, final deploy | Submitted |

Deploy first, so deployment problems show up early rather than at the deadline. Then a
thin slice end to end, then depth, then polish.

**If behind, cut in this order:** custom rules UI -> dismissal counts -> queue polish.
**Never cut:** the review screen with both flag types, the resolve/approve flow, the
deployed URL, DECISIONS.md.
