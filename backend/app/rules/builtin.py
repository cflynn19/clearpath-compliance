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
CARD = frozenset({Product.CREDIT_CARD})
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


# --- Reg Z 1026.16(g): promotional rates on credit cards -------------------------------

# A rate that comes after "then" / "after ..." or before "variable APR" is the rate that
# applies once the promotion ends ("0% intro APR for 15 months, then 19.24% variable APR").
AFTER_PROMO_BEFORE = re.compile(r"\b(?:then|thereafter|afterwards?|after\b[^.\n]{0,30})[^.\n]{0,15}$", re.I)
AFTER_PROMO_FOLLOWING = re.compile(r"^[^.\n]{0,25}\b(?:variable|standard|regular|ongoing|go-to)\s?APR", re.I)
PROMO_DURATION = re.compile(
    r"\bfor\s(?:the\s)?(?:first\s)?\d{1,2}\s(?:months|billing\scycles)\b"
    r"|\buntil\s(?:\w+\s){0,3}\d{4}\b"
    r"|\bthrough\s\w+\s\d{1,2},?\s\d{4}\b",
    re.I,
)
PROMO_WORDS = re.compile(r"\b(?:intro|introductory|promotional|promo|limited[- ]time|special)\b", re.I)
INTRO = re.compile(r"\bintro(?:ductory)?\b", re.I)


def _is_after_promo(text: str, m: re.Match) -> bool:
    return bool(AFTER_PROMO_BEFORE.search(text[max(0, m.start() - 45) : m.start()])) or bool(
        AFTER_PROMO_FOLLOWING.match(text[m.end() : m.end() + 40])
    )


def promotional_rate(asset: Asset) -> list[Finding]:
    """(g)(3): "intro" next to each introductory rate. (g)(4): when it ends and the APR
    after it, close to the first listing.

    A rate counts as promotional if it's 0%, or a promotion or a time limit is mentioned
    in the same sentence, and it isn't the rate that applies afterwards.
    """
    text = asset.body
    rates = [m for m in PERCENT.finditer(text) if not NOT_A_RATE.match(text, m.end())]
    after = [m for m in rates if _is_after_promo(text, m)]
    promos = [
        m
        for m in rates
        if m not in after
        and (
            re.fullmatch(r"0(?:\.0+)?\s?%", m.group())
            or PROMO_DURATION.search(_sentence_around(text, m.start(), m.end(), 60))
            or PROMO_WORDS.search(_sentence_around(text, m.start(), m.end(), 60))
        )
    ]
    if not promos:
        return []

    # DECISION(Q18): card acquisition ads, so every promotional rate is treated as an
    # "introductory" rate (offered when the account opens) and needs the word "intro".
    # "Immediate proximity" = within 25 characters, same sentence; "closely proximate" to
    # the first listing = within 200 characters after it.
    first = promos[0]
    near_first = text[max(0, first.start() - 100) : first.end() + 200]
    missing = []
    if any(not INTRO.search(_sentence_around(text, m.start(), m.end(), 25)) for m in promos):
        missing.append('"intro" or "introductory" right next to the rate')
    if not PROMO_DURATION.search(near_first):
        missing.append("when the promotional rate ends")
    if not any(first.start() < m.start() <= first.end() + 200 for m in after):
        missing.append("the APR that applies after the promotion")
    if not missing:
        return []

    spans = _spans(promos)
    return [
        Finding(
            why=f"Advertises a promotional rate ({_quoted(spans)}) without {_join(missing)}.",
            spans=spans,
        )
    ]


# --- Security: text aimed at automated review (prompt injection, D12) -----------------

# The LLM has its own injection rule, but text that hijacks the model could also
# suppress that rule. A regex can't be talked out of matching, so this is the backstop.
# Q14: "check failed" like every code rule (the text being there is a fact). The
# patterns only cover text aimed at a reviewer or model, never AI as a product feature
# ("our AI assistant compares offers"), so the backstop doesn't flood reviewers. The
# LLM's injection rule casts the wider net for subtle or indirect attempts.
INJECTION = re.compile(
    r"\b(?:ignore|disregard|forget|override)\s(?:all\s|any\s|the\s|your\s)?"
    r"(?:previous|prior|above|earlier|system|original)\s(?:instructions|rules|prompts?|guidelines)"
    r"|\bnew\s(?:system\s)?instructions\s?:"
    r"|\bsystem\sprompt\b"
    r"|\b(?:mark|classify|report|flag|treat|label)\s(?:this|the)\s"
    r"(?:ad|asset|content|email|page|post|copy|message)\s(?:as\s)?(?:compliant|approved|safe|clean)"
    r"|\b(?:report|return|output|find|flag)\s(?:no|zero)\s(?:compliance\s)?"
    r"(?:issues|violations|flags|findings|problems)"
    r"|\bno\s(?:compliance\s)?(?:issues|violations)\s(?:were\s)?(?:found|here|present)"
    r"|\b(?:do\snot|don't|dont)\s(?:flag|report|review|check)\s(?:this|the|anything)"
    r"|\b(?:as|you\sare|you're)\san?\s(?:AI|LLM|language\smodel|automated\sreviewer)\b(?!-)"
    r"|\b(?:AI|LLM|automated|bot)\s(?:reviewers?|moderators?|checkers?|compliance\s(?:checker|tool|bot))\b"
    r"|\bnote\sto\s(?:the\s|any\s)?(?:AI|LLM|model|bot|reviewer)\b"
    r"|\b(?:dear|hey|attention)\s(?:AI|LLM|model|bot)\b",
    re.I,
)
# Zero-width, bidirectional-override and Unicode "tag" characters: invisible to a human
# reader, but a model still reads them, which makes them a way to hide instructions.
HIDDEN = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]+")


def reveal_hidden(text: str) -> str:
    """Decode Unicode tag characters into the text they spell out.

    Tag characters U+E0020-U+E007E mirror printable ASCII one-to-one, so hidden text
    written with them can be read back exactly. Other invisible characters (zero-width
    spaces and the like) carry no text and are dropped.
    """
    return "".join(chr(ord(c) - 0xE0000) for c in text if 0xE0020 <= ord(c) <= 0xE007E)


def injection(asset: Asset) -> list[Finding]:
    text_spans = _spans(INJECTION.finditer(asset.body))
    hidden_spans = _spans(HIDDEN.finditer(asset.body))
    if not (text_spans or hidden_spans):
        return []
    why = []
    if text_spans:
        why.append(f"Contains text aimed at an automated reviewer ({_quoted(text_spans)}).")
    if hidden_spans:
        why.append(f"Contains invisible characters in {len(hidden_spans)} place(s), which can hide text from a human reader.")
        decoded = " ".join(t for t in (reveal_hidden(s.quote).strip() for s in hidden_spans) if t)
        if decoded:
            why.append(f'The hidden text reads: "{decoded}"')
    why.append("It may be an attempt to manipulate AI review; check this asset by hand.")
    return [
        Finding(
            why=" ".join(why),
            spans=tuple(sorted(text_spans + hidden_spans, key=lambda s: s.start)),
        )
    ]


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
        id="regz-16g-promotional-rate",
        name="Promotional rate without required details",
        type=FlagType.CHECK_FAILED,
        citation="Reg Z 12 CFR 1026.16(g)(3)-(4)",
        description="A promotional card rate needs \"intro\" next to it, plus when it ends and the "
        "APR that applies afterwards, close to the first mention.",
        check=promotional_rate,
        products=CARD,
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
    Rule(
        id="security-injection",
        name="Text aimed at automated review",
        type=FlagType.CHECK_FAILED,
        citation="Security: prompt injection (D12)",
        description="Text that addresses an AI or automated reviewer, or tries to change how "
        "the asset is reviewed.",
        check=injection,
    ),
]
