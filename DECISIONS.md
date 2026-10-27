# Decisions

What I built, what I didn't, and why. The assumptions these rest on are in
[ASSUMPTIONS.md](ASSUMPTIONS.md).

## The problem as I understand it

ClearPath's compliance team reviews marketing before it goes live. Today that runs on
Excel and email, and it can't keep up with how much marketing (especially affiliate
marketing) the company wants to run.

**Goal:** more assets reviewed per reviewer per day, *without* lowering review quality.

**Approach:** a reviewer workspace where every asset arrives already checked. Definite
rule violations are found by code, possible issues are found by an LLM, and the reviewer
makes every final call. Status, decisions and history live in one place instead of in
inboxes.

## Core decisions

### D1. AI assists, the human decides
The tool flags. It never approves or rejects. Reviewers answer to regulators, so a human
signs off on every asset.

### D2. Two flag types, labelled by what kind of decision they need
- **Check failed:** found by code. A yes/no fact ("mentions 5.99%, no APR disclosure found").
  Quick to confirm.
- **Needs judgment:** found by the LLM. An ambiguous call ("'everyone qualifies' may imply
  guaranteed approval"). The reviewer has to read and decide.

Why types and not tiers: tiers suggest the LLM flags matter less, so people skim them. But
an LLM flag can be the most serious issue on the page. The type tells the reviewer how to
treat a flag, not how important it is.

Why no confidence score: an LLM's self-reported confidence is poorly calibrated. A
precise-looking number with nothing behind it would mislead reviewers. The type already
says how much to trust a flag.

### D3. Overflag on purpose
Missing a real violation is worse than a false flag (A11). The flag types are what keep
overflagging manageable.

### D4. Every flag shows its evidence
Each flag shows the rule, why it fired, and highlights the exact text. The LLM has to
return the exact quote it is flagging, and code checks that the quote really appears in
the asset. A flag whose quote can't be found is dropped. No invented evidence.

### D5. Resolve before approve
- Check-failed flags must be fixed or dismissed (with a reason) before approval.
- Needs-judgment flags must be acknowledged.

Considered: a hard block (false positives stall real work, and people learn to click
through), and no block (no record of why a flagged asset was approved). This middle path
keeps the human in charge and leaves a record of every override.

### D6. Dismissal reasons are a pick list, plus a note
Reasons: false positive / requirement met elsewhere / approved exception / fixed in this
revision / other (note required). Structured, so they can be counted. Quick, because
every required click costs reviewer time, which is the thing we're trying to save.

### D7. Count dismissals per rule
A rule that is dismissed constantly is a bad rule. The reason tells you why: lots of
"met elsewhere" means the check needs to see more of the material; lots of "false
positive" means the rule itself needs fixing.

### D8. Rules: built-in set plus custom
- Built-in rules from public regulation (A9). The team can **switch any rule off**, but
  can't edit a built-in rule's logic, so a regulatory rule can't be quietly edited into
  uselessness.
- The team can **add its own rules**, in two kinds, and the kind decides the flag type:
  - **Exact phrases** -> matched by code -> **check failed** (e.g. "no credit check")
  - **Plain English** -> judged by the LLM -> **needs judgment** (e.g. "implies the loan
    will improve the reader's lifestyle")
  Both can be limited to certain products and channels.
- **Changes apply to new checks only.** Flags already raised keep the rule they were
  checked with, so the audit trail always matches what the reviewer saw (D9).
- **A plain-English rule is user-written text that goes into the model's instructions.**
  On the real product that's the trusted compliance team; on this public demo, it's
  anyone. Rules are capped at 500 characters, and the usual safeguards still hold (the
  model can only return flags, quotes are verified, code checks run regardless). On a real
  deployment, writing rules would sit behind a permission.
- **Reset demo restores the default rules,** so one visitor can't switch everything off
  for the next.

### D9. Audit trail
Flags, decisions and dismissals are stored against a specific version of the asset,
exactly as they were at review time. The LLM may not give the same answer twice, so we
keep what it actually said when the decision was made.

### D10. Intake: seeded queue plus a paste box
A pre-loaded queue shows the reviewer workflow. A paste box lets anyone try their own
copy. Submitters stay outside the tool for v1 (A6).

### D11. Running an LLM on a public URL
- The LLM is called only from the backend. The key lives in host environment variables
  and never in the repo or the frontend.
- The seeded queue is analysed once, when the data is loaded. Browsing costs nothing.
- Results are cached by content hash: the same text gives the same flags at no cost.
- Per-visitor rate limit, a global daily cap, a maximum input length, a maximum output
  length, and a spend limit at the provider.
- If a cap is hit or the API is down, the code checks still run and the UI says AI
  checks are paused.
- The endpoint returns only structured flags with verified quotes, so it can't be used
  as a general-purpose chatbot.

### D12. Prompt injection
Affiliate content is untrusted text going into an LLM. To limit the risk:
- The asset is clearly marked as untrusted data in the prompt.
- Only structured output is accepted, with quote verification.
- Injection-like text in an asset is itself flagged for judgment.

Quote verification stops invented flags but **not** suppressed ones. Two things cover
that:
- **The model must return a verdict for every rule** (violated or not, with a reason).
  If it skips any rule, the ad gets an **"AI review incomplete"** flag naming them, so a
  model that's been told to "report no issues" and goes quiet is visible to the reviewer
  instead of looking like a clean result.
- **The code checks can't be affected by injection**, including the backstop for injection
  phrasing and hidden characters.

This lowers the risk; it doesn't eliminate it. A manipulated model could still answer
every rule and say "not violated". That's why the AI never approves anything (D1).

### D13. Stack
React + FastAPI + Postgres, deployed as one service (FastAPI serves the built React app)
with a managed Postgres. One thing to deploy means fewer ways for the deploy to fail.

Hosted on Render. First choice was Railway (builds from the Dockerfile, doesn't sleep
idle apps), but its sign-ups were disabled. Render builds the same Dockerfile, and the
database is reachable only over Render's private network. The free instance sleeps when
idle, so it moves to a paid Starter instance before submission: a grader opening the link
days later shouldn't wait through a cold start.

### D14. Demo reset
No auth (A17), so anyone can change the seeded data. A reset button re-seeds it, so one
grader's clicks don't break the demo for the next.

### D15. Rule engine
- **One flag per rule per asset, pointing at every occurrence.** Three "counselor"s are
  one issue to fix, not three flags to resolve, but the reviewer sees all three
  highlighted.
- **Every percentage is treated as a rate** unless it's clearly something else ("95% of
  borrowers", "10% down"). Overflagging, per D3.
- **The APR has to be readable at a glance with the rate:** within ~40 characters and in
  the same sentence. An APR in a footnote or another section doesn't count.
- **Any down payment statement is a trigger term, including "no down payment"** (Reg Z
  1026.24(d)(1)(i)). The down payment *disclosure* is only required for mortgages: Reg Z
  says "as applicable", and personal loans have no down payment.
- **Physical address = a street address or PO Box.** City, state and ZIP alone don't
  count.
- **LLM quotes must match the asset's text,** ignoring only case and spacing. Rewording
  fails. The stored quote is the asset's own text, never the model's copy of it.

**Known limits, to revisit:**
- "over 20 years of experience" reads as a repayment term (a known false positive,
  documented in the tests).
- Ads offering both fixed and adjustable mortgages get the "fixed before ARM" flag even
  though order doesn't matter for them (1026.24(i)(1)(iii)). The reviewer dismisses
  these; the LLM could separate the two cases.
- The "is this percentage a rate?" test is a word list, and could be smarter.
- The taxes-and-insurance rule assumes every mortgage is first-lien (A22).

### D16. LLM checks
- **Claude Opus 5.5, one call per asset** covering every judgment rule that applies.
  Cheaper and faster than one call per rule, and the model sees the whole ad at once.
- **The model only reports; code decides what counts.** Findings must name a rule the
  model was given and quote text that exists in the asset (D4). Everything else is
  dropped, and the UI says how many were dropped.
- **Untrusted content is fenced** inside a randomly named tag it can't close, and the
  prompt tells the model to report embedded instructions, not follow them. A code rule
  catches the obvious injection phrases too, because text that hijacks the model could
  also suppress the model's own injection flag (D12). It also catches invisible
  characters (zero-width, Unicode "tag" characters), which can hide instructions from a
  human reader but not from a model. The code patterns only target text aimed at a
  reviewer, never AI as a product feature ("our AI assistant compares offers"), so it
  doesn't flood reviewers; the LLM rule covers subtler attempts. Tests guard both sides:
  attacks it must catch and normal copy it must not flag.
- **A UDAAP rule for misleading claims** ("guaranteed approval", "everyone qualifies",
  false urgency) joins the judgment rules. It wasn't in the first rule table, but it's the
  most common marketing-compliance problem.
- **Limits are visible:** "8 of 10 AI checks left this hour". When they run out, the
  code checks still run and the UI says so.
- **No "re-run" on unchanged text.** The same text returns the stored result, free and
  without using the limit. The model can answer differently on a second run, and two
  answers for one unchanged ad is exactly what the audit trail (D9) exists to prevent.
  New text means a new check.
- **Visitors are counted by IP address, stored hashed.** The forwarded-for header can be
  forged, but that only buys more per-visitor quota; the global daily cap is what bounds
  the cost.
- **If the model declines** (a safety classifier), the request falls back to Anthropic's
  recommended fallback model instead of failing.

**Follow-up:** code and LLM checks can flag the same problem twice. In testing, an ad
with "5.99%" and no APR got both the code flag (rate not stated as APR) and the LLM flag
(rate shown more prominently than the APR). Narrowing the LLM rule's wording didn't hold
(see D18), so that rule is now off. The general fix is to merge a code flag and an LLM
flag that point at the same text into one.

### D17. Review workflow
- **Every check creates a queue item.** Pasting an ad in "New check" stores it like any
  other submission, so nothing is reviewed off the record.
- **Check-failed flags are dismissed with a reason; judgment flags can also be
  acknowledged.** A definite violation can't just be noted: it gets a reason on record,
  or the ad is rejected.
- **Resolutions can be undone** until the ad is decided. Undo is logged too.
- **Approve is blocked until every flag is resolved; reject is always available** (D5).
  Once decided, the ad and its flags are locked.
- **"Fixed in this revision" isn't a dismissal reason in v1,** because there's no
  revision loop yet. It comes back with re-review.
- **Every action lands in an append-only audit trail:** who, what, when, and the reason
  and note. With no login (A17), actions are recorded as "Demo reviewer"; a real login
  only changes that name.
- **The demo queue seeds itself** on first start (8 sample ads, AI-checked once, in the
  background so the app serves immediately). Reset re-seeds from the stored AI results,
  so it costs nothing.
- **The queue shows throughput numbers** from the audit trail: ads waiting (and the oldest),
  median time from submission to decision, approved/rejected, flags per ad, and the share
  of resolved flags that were dismissed (the cost of overflagging, D3).
- **The Rules page shows how often each rule fires and how often it's dismissed** (D7),
  so a rule reviewers keep overriding is easy to spot.

### D18. Evaluation
`backend/eval/` scores the checks against 15 hand-labelled ads: the 8 demo-queue ads,
traps that look risky but are fine, problems phrased to slip past obvious patterns, and a
known false positive. Each rule is labelled expected, acceptable either way, or wrong to
fire. Results are in `backend/eval/RESULTS.md`.

What the first run showed:
- **Code checks:** caught every expected flag, with one false flag (the known "over 20
  years" one, kept in the set so it stays visible). Caveat: the code rules and these labels
  were written together, so a clean score is expected, not independent proof.
- **AI checks:** caught every expected flag, with 4 false flags. Two came from one rule,
  "rate shown more prominently than the APR". Prominence is visual and can't be judged from
  text (A13), the same reason Reg Z's "clear and conspicuous" rules are out of scope, so
  that rule is **off in v1**.
- **The AI is not consistent from run to run.** It caught the injection hidden in invisible
  characters in the evaluation, but missed the same ad on the live site. The code backstop
  caught it both times. This is the case for keeping a deterministic layer and for storing
  the result a reviewer acted on (D9).
- **One label changed, with a reason:** "95% of borrowers recommend us" was labelled clean,
  but the AI flagged it as a claim needing substantiation. That's a fair point, so it's now
  "acceptable either way". Labels only change for a reason like this, never to raise the
  score.

## Not in v1, and why

| Cut | Why |
|---|---|
| Submitter portal (marketing / affiliates submit directly) | Content arrives as it does today; the bottleneck being solved is review |
| Request changes / revision loop | v1 covers one review pass end to end; doing that well matters more than a shallow full loop |
| Re-review: diffs between versions, carrying over dismissals | Depends on the revision loop. Probably the biggest throughput win after v1. |
| Auth and roles | Not the interesting part of this problem; the reset button covers the demo |
| Excel import of the existing tracker | Matters for adoption, not for the throughput of the review itself |
| Images and video | Text carries most of the rule triggers |
| Per-reviewer dismissal stats | Can feel like surveillance to the team you need to win over |
| Editable dismissal reasons, per-type reason lists | A fixed list is enough to learn from |
| Per-visitor sandbox | The reset button is enough for a demo |
| Database migrations (Alembic) | Tables are created at startup; fine while the schema is small and demo data is re-seeded |
| Running the AI twice and combining results, or a separate injection classifier | Doubles the cost per check; per-rule verdicts plus the code backstop cover v1 |
| Merging a code flag and an LLM flag that point at the same text | The overlapping rule is off for now; the general fix needs flag-matching logic |
| Editing a custom rule, re-scoping built-in rules, and a history of rule changes | Delete and re-add covers v1; rule-change history belongs in the audit trail once there are real users |

## Tradeoffs

- Code checks vs. LLM: code is free, instant, explainable, testable and consistent, but
  it misses new phrasings and fires on silly matches. The LLM handles meaning but costs
  money, can vary between runs, and is open to injection. Using both, with clear labels,
  gets the strengths of each.
- Overflagging vs. reviewer fatigue: handled through the flag types and the dismissal
  data, not by suppressing flags.

## TBD before submission

- [ ] **Throughput claim:** what I claim and how I support it
- [ ] Evaluation results on the labelled mock data (first run in D18; re-run after turning off the prominence rule)
- [x] Which LLM model, and why (D16: Claude Opus 5.5)
- [ ] Upgrade Render to Starter (no idle sleep); confirm the free database outlasts the review window

## How I used AI

_TODO: write this myself, honestly, before submission._
