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
- Built-in rules from public regulation (A9).
- The team can add its own. A phrase or pattern rule counts as **check failed**; a
  plain-English rule is evaluated by the LLM and counts as **needs judgment**. The type
  follows from how the rule is checked.

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

Quote verification stops invented flags but **not** suppressed ones. The code checks
can't be affected by injection, which is one more reason to keep both types. This lowers
the risk; it doesn't eliminate it.

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
(rate shown more prominently than the APR). For now the LLM rule's wording is narrowed to
ads that do state an APR. The general fix is to merge a code flag and an LLM flag that
point at the same text into one.

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
- **The Rules page shows how often each rule fires and how often it's dismissed** (D7),
  so a rule reviewers keep overriding is easy to spot.

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

## Tradeoffs

- Code checks vs. LLM: code is free, instant, explainable, testable and consistent, but
  it misses new phrasings and fires on silly matches. The LLM handles meaning but costs
  money, can vary between runs, and is open to injection. Using both, with clear labels,
  gets the strengths of each.
- Overflagging vs. reviewer fatigue: handled through the flag types and the dismissal
  data, not by suppressing flags.

## TBD before submission

- [ ] **Throughput claim:** what I claim and how I support it
- [ ] Evaluation results on the labelled mock data
- [ ] Which LLM model, and why
- [ ] Upgrade Render to Starter (no idle sleep); confirm the free database outlasts the review window

## How I used AI

_TODO: write this myself, honestly, before submission._
