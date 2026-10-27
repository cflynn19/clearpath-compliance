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

**Status at submission:** all Must and Should items shipped, plus a credit card promo-rate
rule, queue filters, a team Insights page (throughput and rule health), a rule change
history, per-rule AI verdicts, and a revision loop (request changes, re-check, carry over). **Won't (v1):** see DECISIONS.md.

## Architecture (the plan; README has the final layout)

- `backend/` FastAPI
  - `rules/`: built-in code checks, each one a small testable function
  - `llm/`: judgment checks, prompt, output schema, quote verification
  - `checks.py`: runs both, merges the flags, caches by content hash
  - API: queue, asset detail, analyze (paste), resolve flag, decide, rules, reset
- `frontend/` React (Vite), built and served by FastAPI
- Postgres

**Entities (as planned):** Asset, AssetVersion, Rule, Flag, FlagResolution, Decision,
AuditEvent

## v1 rules

Sources: Reg Z §1026.24 (closed-end credit ads) and the FTC's CAN-SPAM compliance guide.
Illustrative, not legal advice.

**Code (check failed)**

| Rule | Cite | Applies to | Fires when |
|---|---|---|---|
| Rate not stated as APR | Reg Z 1026.24(c) | Personal loan, mortgage | A rate appears with no "APR" / "annual percentage rate" next to it |
| Trigger term without full disclosure | Reg Z 1026.24(d) | Personal loan, mortgage | Payment amount, number of payments or term, down payment, or finance charge appears, but the APR or repayment terms are missing |
| Mortgage payment without taxes-and-insurance note | Reg Z 1026.24(f)(3)(i)(C) | Mortgage | A payment amount, with no note that it excludes taxes and insurance |
| "Counselor" | Reg Z 1026.24(i)(6) | Mortgage | The word appears |
| Government endorsement | Reg Z 1026.24(i)(3) | Mortgage | "government loan program", "government-backed", ... |
| "Fixed" before "ARM" | Reg Z 1026.24(i)(1) | Mortgage | "fixed" and ARM / adjustable / variable both appear, and "ARM" doesn't come first |
| No physical address | CAN-SPAM | Email | No street address / PO Box pattern |
| No opt-out | CAN-SPAM | Email | No "unsubscribe" / "opt out" / preferences link |
| Promotional rate without required details | Reg Z 1026.16(g)(3)-(4) | Credit card | A promotional rate (0%, or a promotion or time limit in the same sentence) without "intro" beside it, when it ends, or the APR afterwards |

**LLM (needs judgment)**

| Rule | Cite | Applies to |
|---|---|---|
| Another rate more prominent than the APR; rate may increase but ad doesn't say so | Reg Z 1026.24(c) | Personal loan, mortgage |
| Misleading payment or rate comparisons | Reg Z 1026.24(i)(2) | Mortgage |
| "Eliminate your debt" claims | Reg Z 1026.24(i)(5) | Mortgage |
| Uses the reader's current lender's name | Reg Z 1026.24(i)(4) | Mortgage |
| Deceptive subject line | CAN-SPAM | Email |
| Not identified as an ad | CAN-SPAM | Email |
| Opt-out unclear, or asks for more than an email / one page | CAN-SPAM | Email |
| Injection-like text in the asset | (security) | All |

**Credit cards** fall under Reg Z §1026.16 (open-end credit), not §1026.24. v1 covers
§1026.16(g) promotional rates as a code rule: "intro" next to each introductory rate, plus
when it ends and the APR afterwards near the first mention. The §1026.16(b) trigger terms
(fees and charges) are not covered yet.

**Deliberately out of scope**

| Rule | Why |
|---|---|
| 1026.24(a) Terms actually available | Needs ClearPath's live rate sheet. Next step: compare advertised rates to it. |
| 1026.24(b), (f) "Clear and conspicuous", equal prominence | Visual; text-only (A13) |
| 1026.24(g) TV / radio | No such channels |
| 1026.24(h) Loans above home value | Not a ClearPath product (A20) |
| 1026.24(i)(7) Foreign-language ads | English only (A14) |
| CAN-SPAM header info, honouring opt-outs | Sending infrastructure and processes, not content |

Note: 1026.24(e) allows an online ad to meet the disclosure requirements through a clearly
linked rates table. That is the basis for the "requirement met elsewhere" dismissal
reason (D6).

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
