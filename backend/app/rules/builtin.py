"""Built-in code rules. Every flag they raise is "check failed": a yes/no fact.

Sources: Reg Z 12 CFR 1026.24 (closed-end credit advertising) and the FTC's CAN-SPAM
compliance guide. Illustrative, not legal advice.

Each check only reads the body. Subject lines go to the LLM checks. A check returns at
most one Finding, pointing at every occurrence of the problem (Q7, Q9).
"""

import re
from collections.abc import Iterable

from .models import Asset, Channel, Finding, FlagType, Product, Rule, Span

CLOSED_END = frozenset({Product.PERSONAL_LOAN, Product.MORTGAGE})
MORTGAGE = frozenset({Product.MORTGAGE})
EMAIL = frozenset({Channel.EMAIL})

APR = re.compile(r"\bAPR\b|(?i:annual percentage rate)")


def _spans(matches: Iterable[re.Match]) -> tuple[Span, ...]:
    return tuple(Span(quote=m.group(), start=m.start(), end=m.end()) for m in matches)


def _quoted(spans: tuple[Span, ...]) -> str:
    return _join([f'"{s.quote}"' for s in spans])


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _sentence_around(text: str, start: int, end: int, reach: int) -> str:
    """Up to `reach` characters either side of text[start:end], cut at sentence ends."""
    before = re.split(r"[.!?](?:\s|$)|\n", text[max(0, start - reach) : start])[-1]
    after = re.split(r"[.!?](?:\s|$)|\n", text[end : end + reach])[0]
    return before + text[start:end] + after


# --- Reg Z 1026.24(c): a stated rate must be stated as an APR -------------------------

PERCENT = re.compile(r"\d{1,2}(?:\.\d{1,3})?\s?%")

# Q2: every percentage is treated as a rate (overflagging, D3) unless one of these
# follows it. "10% down" is a down payment, which the trigger-terms rule handles.
# REVISIT: a smarter test for "is this a rate" (e.g. let the LLM classify edge cases).
NOT_A_RATE = re.compile(r"\s*(?:down\b|cash\s?back|off\b|of\b|more\b|less\b|faster\b)", re.I)

# Q3: the APR has to be readable at a glance with the rate: close by, and never in a
# separate sentence or section. 40 characters sits in the 30-50 range.
APR_REACH = 40


def rate_not_apr(asset: Asset) -> list[Finding]:
    text = asset.body
    bad = [
        m
        for m in PERCENT.finditer(text)
        if not NOT_A_RATE.match(text, m.end())
        and not APR.search(_sentence_around(text, m.start(), m.end(), APR_REACH))
    ]
    if not bad:
        return []
    spans = _spans(bad)
    noun = "a rate" if len(spans) == 1 else f"{len(spans)} rates"
    return [
        Finding(
            why=f"States {noun} ({_quoted(spans)}) without calling it an annual percentage rate (APR).",
            spans=spans,
        )
    ]


# --- Reg Z 1026.24(d): trigger terms require the full set of disclosures --------------

PAYMENT = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d{2})?\s?(?:/\s?|per\s|a\s|each\s)(?:mo\b|month|wk\b|week)", re.I
)
# Q4: number of payments or period of repayment.
# REVISIT: known false positive, "over 20 years of experience" matches the third pattern.
TERM = re.compile(
    r"\b\d{1,3}\s?(?:monthly\s)?payments\b"
    r"|\b\d{1,3}-(?:month|year)\b"
    r"|\b(?:terms?|repay(?:ment)?|over)\b[^.\n]{0,20}?\b\d{1,3}\s?(?:months|years)\b",
    re.I,
)
# Q5: any statement about the down payment is a trigger, including "no down payment".
DOWN = re.compile(
    r"\bno\sdown\s?payment\b"  # before the shorter "no down" so the full phrase is quoted
    r"|(?:\$\s?\d[\d,]*|\d{1,2}(?:\.\d+)?\s?%)\s?down\b"
    r"|\b(?:no|zero|nothing)\s(?:money\s)?down\b",
    re.I,
)
FINANCE_CHARGE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d{2})?\s(?:in\s)?(?:interest|finance charges?)\b", re.I
)
TRIGGERS = [PAYMENT, TERM, DOWN, FINANCE_CHARGE]

# What counts as having disclosed the repayment terms and the down payment.
REPAYMENT_TERMS = re.compile(TERM.pattern + r"|\bfor\s\d{1,3}\s?(?:months|years)\b", re.I)
DOWN_DISCLOSED = re.compile(DOWN.pattern + r"|down\s?payment", re.I)


def trigger_terms(asset: Asset) -> list[Finding]:
    text = asset.body
    triggers = sorted((m for p in TRIGGERS for m in p.finditer(text)), key=lambda m: m.start())
    if not triggers:
        return []

    missing = []
    if not APR.search(text):
        missing.append("the APR")
    if not REPAYMENT_TERMS.search(text):
        missing.append("the repayment terms")
    # Q6: the down payment is required "as applicable". Personal loans have no down
    # payment, so this is required for mortgages only.
    if asset.product is Product.MORTGAGE and not DOWN_DISCLOSED.search(text):
        missing.append("the down payment")
    if not missing:
        return []

    spans = _spans(triggers)
    return [
        Finding(
            why=f"Mentions {_quoted(spans)}, which requires the ad to also state {_join(missing)}.",
            spans=spans,
        )
    ]


# --- Reg Z 1026.24(f)(3)(i)(C): mortgage payments must note taxes and insurance -------

TAXES_INSURANCE = re.compile(r"tax(?:es)?\s(?:and|&)\s(?:homeowners?'?\s)?insurance", re.I)


def mortgage_payment_taxes(asset: Asset) -> list[Finding]:
    # Q8: this applies to first-lien mortgages; every ClearPath mortgage is assumed to
    # be first-lien (A22). REVISIT if ClearPath offers second-lien products.
    text = asset.body
    if TAXES_INSURANCE.search(text):
        return []
    spans = _spans(PAYMENT.finditer(text))
    if not spans:
        return []
    return [
        Finding(
            why=f"States a payment ({_quoted(spans)}) without saying it excludes taxes and "
            "insurance and that the actual payment will be higher.",
            spans=spans,
        )
    ]


# --- Reg Z 1026.24(i): prohibited practices in mortgage ads ---------------------------

COUNSELOR = re.compile(r"\bcounsell?ors?\b", re.I)


def counselor(asset: Asset) -> list[Finding]:
    spans = _spans(COUNSELOR.finditer(asset.body))
    if not spans:
        return []
    return [
        Finding(
            why='Uses "counselor" to describe a for-profit mortgage lender or its staff.',
            spans=spans,
        )
    ]


GOVERNMENT = re.compile(
    r"government[- ](?:loan program|backed|sponsored|supported|insured|endorsed|approved)"
    r"|federally[- ](?:backed|insured|sponsored)"
    r"|backed by the (?:federal )?government",
    re.I,
)


def government_endorsement(asset: Asset) -> list[Finding]:
    spans = _spans(GOVERNMENT.finditer(asset.body))
    if not spans:
        return []
    return [
        Finding(
            why=f"Implies government endorsement ({_quoted(spans)}); ClearPath offers no "
            "government loan programs (A19).",
            spans=spans,
        )
    ]


FIXED = re.compile(r"\bfixed\b", re.I)
ARM_TERMS = re.compile(r"\bARM\b|(?i:adjustable[- ]rate|variable[- ]rate)")


def fixed_before_arm(asset: Asset) -> list[Finding]:
    # Q10: an ad offering both fixed and adjustable products falls under (i)(1)(iii),
    # where order doesn't matter. Code can't tell the two cases apart, so this flags
    # both and the reviewer dismisses the mixed-product case.
    # REVISIT: hand the mixed case to the LLM instead.
    text = asset.body
    fixed, arm = FIXED.search(text), ARM_TERMS.search(text)
    if not (fixed and arm) or arm.start() < fixed.start():
        return []
    return [
        Finding(
            why=f'Uses "fixed" before identifying the loan as adjustable-rate ("{arm.group()}" comes later).',
            spans=_spans([fixed]),
        )
    ]


# --- CAN-SPAM: physical address and opt-out ------------------------------------------

# Q11: a street address or a PO Box. A city, state and ZIP alone isn't enough.
STREET = re.compile(
    r"\b\d{1,6}\s+(?:[A-Za-z0-9][\w.'-]*\s+){1,5}"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct"
    r"|Place|Pl|Parkway|Pkwy|Suite|Ste)\b",
    re.I,
)
PO_BOX = re.compile(r"\bP\.?\s?O\.?\s?Box\s+\d+", re.I)


def physical_address(asset: Asset) -> list[Finding]:
    if STREET.search(asset.body) or PO_BOX.search(asset.body):
        return []
    return [Finding(why="No valid physical postal address (street address or PO Box).")]


# Presence only. Whether the opt-out is clear, or asks for too much, is an LLM rule.
OPT_OUT = re.compile(
    r"unsubscribe|opt[- ]?out|manage (?:your )?(?:email )?preferences|email preferences", re.I
)


def opt_out(asset: Asset) -> list[Finding]:
    if OPT_OUT.search(asset.body):
        return []
    return [Finding(why="No way to opt out of future marketing email (e.g. an unsubscribe link).")]


BUILTIN_RULES: list[Rule] = [
    Rule(
        id="regz-24c-rate-as-apr",
        name="Rate not stated as APR",
        type=FlagType.CHECK_FAILED,
        citation="Reg Z 12 CFR 1026.24(c)",
        description="A stated rate must be stated as an \"annual percentage rate\", using that term.",
        check=rate_not_apr,
        products=CLOSED_END,
    ),
    Rule(
        id="regz-24d-trigger-terms",
        name="Trigger term without full disclosure",
        type=FlagType.CHECK_FAILED,
        citation="Reg Z 12 CFR 1026.24(d)",
        description="Stating a payment, term, down payment or finance charge requires the APR, "
        "repayment terms and (as applicable) down payment.",
        check=trigger_terms,
        products=CLOSED_END,
    ),
    Rule(
        id="regz-24f3-taxes-insurance",
        name="Mortgage payment without taxes-and-insurance note",
        type=FlagType.CHECK_FAILED,
        citation="Reg Z 12 CFR 1026.24(f)(3)(i)(C)",
        description="A stated mortgage payment must note that it excludes taxes and insurance "
        "and that the actual payment will be greater.",
        check=mortgage_payment_taxes,
        products=MORTGAGE,
    ),
    Rule(
        id="regz-24i6-counselor",
        name="\"Counselor\" in a mortgage ad",
        type=FlagType.CHECK_FAILED,
        citation="Reg Z 12 CFR 1026.24(i)(6)",
        description="For-profit mortgage lenders and their staff may not be called \"counselors\".",
        check=counselor,
        products=MORTGAGE,
    ),
    Rule(
        id="regz-24i3-government",
        name="Implied government endorsement",
        type=FlagType.CHECK_FAILED,
        citation="Reg Z 12 CFR 1026.24(i)(3)",
        description="A mortgage ad may not imply government endorsement unless it is for a "
        "government program.",
        check=government_endorsement,
        products=MORTGAGE,
    ),
    Rule(
        id="regz-24i1-fixed-before-arm",
        name="\"Fixed\" before \"ARM\"",
        type=FlagType.CHECK_FAILED,
        citation="Reg Z 12 CFR 1026.24(i)(1)",
        description="In an ad for adjustable-rate loans, \"ARM\" must appear before the first "
        "use of \"fixed\".",
        check=fixed_before_arm,
        products=MORTGAGE,
    ),
    Rule(
        id="canspam-address",
        name="No physical address",
        type=FlagType.CHECK_FAILED,
        citation="CAN-SPAM Act (FTC compliance guide)",
        description="Marketing email must include a valid physical postal address.",
        check=physical_address,
        channels=EMAIL,
    ),
    Rule(
        id="canspam-opt-out",
        name="No opt-out",
        type=FlagType.CHECK_FAILED,
        citation="CAN-SPAM Act (FTC compliance guide)",
        description="Marketing email must explain how to opt out of future marketing email.",
        check=opt_out,
        channels=EMAIL,
    ),
]
