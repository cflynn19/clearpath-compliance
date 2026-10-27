# Decisions

What I built, what I didn't, and why. The assumptions these rest on are in
[ASSUMPTIONS.md](ASSUMPTIONS.md).

## How I used AI

I was the product lead on this, making the important product decisions and assumptions. I took us in the directions I felt like were most important in the time I had for the initial v1. Claude handled most of the code, tests, and doc drafts. I had Claude mark any product decision and come back to me which I answered and those product decisions and discussions are labeled D1, D2, etc... in this file for a deeper dive if curious. I ran through testing myself and gave feedback on the UI/UX throughout ensuring we were emphasizing and showing the right things.

## Throughput

Right now it seems that a lot of time is spent both with the email and Excel system - constantly having to go back and check the status of items. And having to manually send back emails with review notes that the reviewer has most likely sent frequently. On top of that we have the obvious time it takes a reviewer to manually review each item, while reading each line and checking regulation documents constantly. Not to mention a most likely annoying re-review process that feels like a fresh start each time.

So I built this v1 platform with the goal of speeding up those specific bottlenecks within the review process. A shared FIFO queue system with the oldest ads prioritized ensuring ads don't get backlogged and missed, and an easy re-review process where the reviewer only has to look at what changed: earlier resolutions carry over and a summary shows what was fixed, still flagged or new. We have default rules based on federal advertising regulations - Reg Z (Truth in Lending: 12 CFR 1026.24 for loans and mortgages, 1026.16(g) for credit card promotional rates), the CAN-SPAM Act for email, and UDAAP for misleading claims - so users don't have to search around for issues; they are right there for them. The platform identifies using code checks and AI processes the flags that users should look into instead of having to review the entire text word for word. The key assumption we made was the importance of overflagging instead of underflagging as to not miss potential issues. The other assumption being the review is ultimately still in the hands of the reviewer - AI here is a tool, not an auto review process.

Building off of that I added the Insights log to measure throughput for ClearPath with metrics on speed of reviews and frequent dismissals of rules, while each ad keeps an audit trail to appease regulators and provide useful info for reviewers on the history of items. Insights that could prove the impact of the systems for ClearPath (adoption motivation) and also give them data to improve the speed and quality of their reviews given the insight onto the dismissal rates of rules.

What I can't prove is any tangible improvement yet without real reviewers. Without information on how fast their email/Excel processes take and how fast actual users use the current platform this is still just hypothetical improvements. An easy way would be to at least get insight to how many approvals they go through in a day, week, month etc... and could determine a time per ad would help. That is something that I am sure I could get immediately from their Excel workflows.

## The problem

ClearPath's compliance team reviews marketing before it goes live. Today that runs on
Excel and email, and it can't keep up with how much marketing (especially affiliate
marketing) the company wants to run.

**Goal:** more ads reviewed per reviewer per day, *without* lowering review quality.

**Approach:** every ad arrives already checked. Code finds definite violations, an LLM
finds possible issues, and the reviewer makes every call. Status, decisions and history
live in one place instead of in inboxes.

## Decisions

### D1. AI assists, the human decides
The tool flags. It never approves or rejects. Reviewers answer to regulators, so a human
signs off on every ad.

### D2. Two flag types, labelled by the kind of decision they need
- **Check failed:** found by code. A yes/no fact ("5.99% with no APR"). Quick to confirm.
- **Needs judgment:** found by the LLM. An ambiguous call ("'everyone qualifies' may
  imply guaranteed approval"). The reviewer reads and decides.

Types, not tiers: tiers suggest LLM flags matter less, but an LLM flag can be the most
serious issue on the page. No confidence score: an LLM's self-reported confidence is
poorly calibrated, and a precise-looking number would mislead reviewers.

### D3. Overflag on purpose
Missing a real violation is worse than a false flag (A11). The flag types and the
dismissal data (D7) keep it manageable.

### D4. Every flag shows its evidence
Each flag names the rule, says why it fired, and highlights the exact text. The LLM must
quote the text it flags, and code checks the quote is really in the ad. Otherwise the
flag is dropped.

### D5. Resolve before approve
Check-failed flags must be dismissed with a reason; needs-judgment flags must be
acknowledged or dismissed. A hard block would stall real work on false positives; no
block would leave no record of why a flagged ad was approved.

### D6. Dismissal reasons are a pick list, plus a note
False positive / requirement met elsewhere / approved exception / other (note required).
Structured so they can be counted, and quick because every click costs reviewer time.
"Fixed in this revision" isn't needed: a fixed problem simply doesn't fire on the next
version (D19).

### D7. Count dismissals per rule
A rule that's dismissed constantly is a bad rule, and the reason says why: lots of "met
elsewhere" means the check can't see enough of the material; lots of "false positive"
means the rule needs fixing.

### D8. Rules: built-in plus custom
- Built-in rules come from public regulation (A9). The team can **switch any rule off**
  but can't edit a built-in rule's logic, so a regulatory rule can't be quietly edited
  into uselessness.
- The team can **add its own rules**, and the kind decides the flag type: **exact
  phrases** are matched by code (check failed); **plain English** is judged by the LLM
  (needs judgment). Both can be scoped to products and channels.
- **Changes apply to new checks only.** Existing flags keep the rule they were checked
  with, so the audit trail matches what the reviewer saw.
- **A plain-English rule is user text in the model's instructions.** On a real deployment
  writing rules would sit behind a permission; on the public demo, rules are capped at 500
  characters and the usual safeguards hold (flags only, verified quotes, code checks).
- **Every rule change is on the record** (who, when, and why it was switched off).
  Switching a rule off asks for confirmation, more firmly for a regulatory rule.

### D9. Audit trail
Flags, decisions and dismissals are stored against a specific version of the ad, as they
were at review time. The LLM may not give the same answer twice, so we keep what it said
when the decision was made.

### D10. Intake: seeded queue plus a paste box
A pre-loaded queue shows the workflow; "New check" lets anyone paste their own ad.
Submitters stay outside the tool for v1 (A6).

### D11. Running an LLM on a public URL
- The LLM is called only from the backend; the key never reaches the repo or the browser.
- Results are stored by content hash: the same text gets the same flags, free.
- 10 AI checks per visitor per hour, 300 a day, input and output caps, and a spend limit
  at the provider. When a limit is hit or the API is down, code checks still run.
- The endpoint returns only verified, structured flags, so it can't be used as a chatbot.

### D12. Prompt injection
Affiliate content is untrusted text going into an LLM.
- It's fenced in a randomly named tag it can't close, and the model is told to report
  embedded instructions, not follow them.
- **A code backstop** flags injection phrasing aimed at a reviewer, and invisible
  characters (zero-width and Unicode "tag" characters), decoding hidden text so the
  reviewer can read it. A regex can't be talked out of matching. It deliberately ignores AI
  as a product feature ("our AI assistant…"), and tests cover both sides.
- **The model must return a verdict for every rule.** If it skips one, the ad gets an
  "AI review incomplete" flag, so a model told to "report no issues" can't go quietly
  silent.

This lowers the risk; it doesn't eliminate it. A manipulated model could still say "not
violated" for every rule, which is why the AI never approves anything (D1).

### D13. Stack and hosting
React + FastAPI + Postgres as one service (FastAPI serves the built React app): one
thing to deploy. On Render, after Railway's sign-ups turned out to be closed. A paid
instance so a grader opening the link days later doesn't wait through a cold start.

### D14. Demo reset
No login (A17), so anyone can change the demo. Reset restores the sample queue and the
default rules, from stored AI results, at no cost.

### D15. Rule engine
- **One flag per rule per ad, pointing at every occurrence.** Three "counselor"s are one
  issue to fix, with all three highlighted.
- **Every percentage is treated as a rate** unless it's clearly not ("95% of borrowers",
  "10% down").
- **The APR must be readable at a glance with the rate:** within ~40 characters, same
  sentence.
- **Any down payment statement is a trigger term, including "no down payment"**; the
  down payment *disclosure* is required only for mortgages ("as applicable").
- **Physical address = street address or PO Box.**
- **LLM quotes must match the ad's text,** ignoring only case and spacing.

Known limits: "over 20 years of experience" reads as a repayment term; ads offering both
fixed and adjustable mortgages get the "fixed before ARM" flag; the "is this a rate?"
test is a word list; the taxes-and-insurance rule assumes first-lien mortgages (A22).

### D16. LLM checks
- **Claude Opus 5.5, one call per ad** for every judgment rule that applies.
- **The model only reports; code decides what counts.** Findings must name a rule it was
  given and quote real text (D4); the UI says how many were discarded.
- **A UDAAP rule for misleading claims** ("guaranteed approval", false urgency): the most
  common marketing-compliance problem.
- **Limits are visible** ("8 of 10 AI checks left this hour").
- **No re-run on unchanged text:** two answers for one unchanged ad is what the audit
  trail exists to prevent.
- **Visitors are counted by hashed IP.** Forging the header only buys per-visitor quota;
  the daily cap bounds the cost.
- **If the model declines**, the request falls back to Anthropic's recommended model.
- **"Rate shown more prominently than the APR" is off in v1.** It double-flagged what the
  code rule already catches, and prominence is visual, which text can't show (A13).

### D17. Review workflow and Insights
- **Every check creates a queue item**, so nothing is reviewed off the record.
- **Resolutions can be undone** until the ad is decided. **Approve needs every flag
  resolved; reject is always available.** Decided ads are locked.
- **Every action lands in an append-only audit trail** with who, what, when, and why.
  With no login, actions are recorded as "Demo reviewer".
- **The queue is first in, first out:** oldest first, with how long each ad has waited.
  Newest-first would let old ads sink, which is the backlog problem itself.
- **Throughput numbers live on their own Insights page:** a reviewer needs the queue, a
  lead needs "are we keeping up, and are the rules any good". Backlog, median time to
  decision, approved/rejected, flags per ad and dismissal rate, for 24 hours, 7 days or
  all time, all from the audit trail.
- **Rule health is a sortable table** of every rule that fired: flagged, dismissed,
  dismiss rate, top reason, with actions in a ⋯ menu. The top reason says what to do
  ("may be too broad" / "missing context" / "policy question"). Under 3 flags shows "too
  few to tell".
- **Team-wide on purpose.** Per-reviewer speed would push people to rush. With logins,
  Insights would be lead-only.

### D18. Evaluation
`backend/eval/` scores the checks against 15 hand-labelled ads, including traps that look
risky but are fine, problems phrased to slip past patterns, and a known false positive.
Results: `backend/eval/RESULTS.md`.

| Checks | Caught | Missed | False flags |
|---|---|---|---|
| Code | 15 of 15 | 0 | 1 (the known "over 20 years" one) |
| AI | 10 of 11 | 1 | 4 |

- **The AI varies between runs.** An earlier run caught 11 of 11; this one missed "not
  identified as an ad" on one email. It caught the hidden-text injection here but missed it
  once on the live site; the code backstop caught it every time. That's the case for the
  deterministic layer and for "the AI never decides alone".
- **The subject-line rule is the noisiest:** it falsely flagged the same compliant email
  on both runs. Next to tune.
- **The code score isn't independent proof:** the rules and labels were written together.
- **Labels change only for a principled reason**, never to raise the score. One did ("95%
  of borrowers recommend us" needs substantiation, so flagging it is fair).

### D19. Revision loop
The email back-and-forth is probably where the most time goes, so v1 closes the loop:
- **Request changes** sends the ad back to the submitter; **the open flags are the fix
  list** (the note is optional). Its flags lock while it's with the submitter.
- **The revision is checked again as version 2**, so decisions always point at the exact
  text reviewed. With no submitter portal (A6), the demo submits it from the ad's page.
- **Re-review only what changed:** a dismissed or acknowledged flag **carries over** if
  the same rule fires on the same text; if the text changed, it reopens. A summary shows
  fixed / still flagged / new / carried over.
- **Only the current version's flags gate approval.**

## Not in v1, and why

| Cut | Why |
|---|---|
| Excel import of the existing tracker | Two jobs: adoption (nobody re-types hundreds of rows) and proof (its dates are the "before" baseline for Insights). Cut for time: rushed file handling is fragile and bulk AI checks need a cost cap. First thing to build next. |
| Submitter portal, and a word-level diff between versions | The revision loop works without them; a portal is the next step for adoption |
| Per-flag comments and suggested edits | Reviewers deliberately can't edit ad copy (separation of duties: marketing writes, compliance approves). Next: per-flag comments to the submitter, and suggested wording the submitter accepts. |
| Images and video | Images break quote verification. Next: OCR into the same pipeline, a vision model for visual rules (which unlocks the prominence rule and "clear and conspicuous"), and text in images treated as untrusted. |
| Auth and roles | Not the interesting part of this problem; reset covers the demo |
| Merging a code flag and an LLM flag on the same text | The overlapping rule is off for now |
| Running the AI twice, or a separate injection classifier | Doubles cost; per-rule verdicts plus the code backstop cover v1 |
| Editing custom rules, re-scoping built-in rules | Delete and re-add covers v1 |
| Per-reviewer stats | Can feel like surveillance to the team you need to win over |
| Editable dismissal reasons | A fixed list is enough to learn from |
| Database migrations | Tables are created at startup; fine while the schema is small |

## With another week

1. **Excel import:** adoption on day one, and the "before" dates that turn the throughput
   claim into a measurement.
2. **Submitter portal with per-flag comments and suggested edits:** cuts the
   back-and-forth at the source.
3. **Tune the noisiest rules** with the evaluation and dismissal data (the subject-line
   rule first), and add the newer demo ads to the labelled set.
4. **Logins and roles:** real names in the audit trail; Insights and rule changes for
   leads only.
5. **Images:** OCR into the same pipeline, and a vision model for the visual rules.

## Tradeoffs

- **Code vs. LLM:** code is free, instant, testable and consistent, but misses new
  phrasings. The LLM handles meaning but costs money, varies between runs and is open to
  injection. Both, clearly labelled, gets the strengths of each.
- **Overflagging vs. reviewer fatigue:** handled with the flag types and dismissal data,
  not by suppressing flags.
