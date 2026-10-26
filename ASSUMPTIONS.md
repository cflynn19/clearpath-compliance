# Assumptions

The brief is intentionally open. These are the calls I made to fill the gaps.
Each one has why I believe it and what I'd change if it turns out wrong.

Confidence: H / M / L. Anything marked **(verify)** I still need to check before relying on it.

## The business and the bottleneck

| # | Assumption | Why | Conf | If wrong, I'd... |
|---|---|---|---|---|
| A1 | The bottleneck is the review work itself: finding issues, back-and-forth, tracking status. Not just "Excel is clunky." | Brief says the *review process* bottlenecks growth | | Refocus on intake / routing / sign-off, wherever the time actually goes |
| A2 | A large share of volume comes from affiliates: many partners, many variants, little control over their copy, and ClearPath is still liable for it | Brief calls out affiliates specifically | | Put less weight on high-volume triage |
| A3 | Reviewers read each asset line by line against a checklist that lives in their heads or a spreadsheet | Excel + email process, no tooling mentioned | | Integrate with their existing checklist instead of replacing it |
| A4 | Many checks are repetitive: the same required disclosures, over and over | Consumer finance ads reuse the same products and rate language | | Lean more on the LLM, less on code checks |
| A5 | Status lives in email threads plus a shared tracker. There is no single queue. | Brief: "Excel and email" | | Drop the queue and focus only on the review screen |

## Users

| # | Assumption | Why | Conf | If wrong, I'd... |
|---|---|---|---|---|
| A6 | The primary user is the compliance reviewer. A lead needs queue visibility. Submitters (marketing, affiliates) stay outside the tool for v1. | Throughput of the *compliance* team is the stated goal; review is where it stalls | | Build a submitter portal so issues get caught before review |
| A7 | Reviewers are domain experts, not engineers, and they own the final call | It's a compliance function answering to regulators | | Add more guidance and explanation per flag |
| A8 | When the team writes its own rules, most will be plain English, not patterns or code | Non-technical users | | Invest in a pattern-rule builder |

## Regulatory

| # | Assumption | Why | Conf | If wrong, I'd... |
|---|---|---|---|---|
| A9 | A starter rule set can come from public regulation: Reg Z / TILA advertising triggers, NMLS ID on mortgage ads, CAN-SPAM for email, UDAAP for misleading claims **(verify)** | Public, citable, covers the three products | | Start from ClearPath's internal policy instead |
| A10 | Every company interprets these differently, so the built-in rules are a starting point and the team must be able to add its own | Compliance policy is company-specific | | Ship a fixed rule set |
| A11 | Missing a real violation costs more than a false flag | Regulatory and legal exposure vs. a few seconds of reviewer time | | Tighten the rules and cut the judgment checks back |
| A12 | An audit trail matters: who approved what, which version, and why | Regulatory exams | | Lighter history |

## Content and scope

| # | Assumption | Why | Conf | If wrong, I'd... |
|---|---|---|---|---|
| A13 | Text only: ad copy, emails, landing page text, social posts, affiliate pages. No images or video. | Fits in 24h; most rule triggers are in the text | | Add OCR / image review |
| A14 | US market, English | National US lender | | |
| A18 | Mortgage prequalification ads count as ads for credit secured by a dwelling, so the Reg Z mortgage rules (1026.24(f), (i)) apply to them | They advertise mortgage credit even though prequal comes before the application | | Scope the mortgage-only rules down |
| A19 | ClearPath offers no government-backed loans (FHA, VA) | Not mentioned in the brief | | Allow government-program language for those products |
| A20 | ClearPath doesn't offer loans above the home's value | Not mentioned in the brief | | Add the 1026.24(h) tax-deductibility rule |
| A21 | ClearPath is responsible for what affiliates publish on its behalf | FTC CAN-SPAM guide: "you can't contract away your legal responsibility to comply" | | Less weight on affiliate content |

## The demo itself

| # | Assumption | Why | Conf | If wrong, I'd... |
|---|---|---|---|---|
| A15 | Graders use the deployed site without me, possibly days later | Deliverable is a public URL | | |
| A16 | Graders will try adversarial input (prompt injection) in the paste box | It's a prompt-injection security company | | |
| A17 | No auth is acceptable for v1, so anyone with the link can act on the data | Auth isn't the interesting part of this problem | | Add a simple login and per-user sandboxes |
