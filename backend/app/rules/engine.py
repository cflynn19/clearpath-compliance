import re

from .builtin import BUILTIN_RULES
from .models import Asset, Flag, Rule


def run_code_checks(asset: Asset, rules: list[Rule] = BUILTIN_RULES) -> list[Flag]:
    flags = [
        Flag(
            rule_id=rule.id,
            rule_name=rule.name,
            type=rule.type,
            citation=rule.citation,
            why=finding.why,
            spans=list(finding.spans),
        )
        for rule in rules
        if rule.enabled and rule.applies_to(asset)
        for finding in rule.check(asset)
    ]
    # Whole-asset flags (something missing) first, then in reading order.
    flags.sort(key=lambda f: f.spans[0].start if f.spans else -1)
    return flags


def find_quote(text: str, quote: str) -> list[tuple[int, int]]:
    """Every (start, end) where `quote` appears in `text`, ignoring case and whitespace.

    The LLM checks use this to verify evidence: a flag whose quote can't be found in the
    asset is dropped (D4). Matching tolerates case and spacing but not rewording (Q12).
    Callers should store text[start:end] as the quote, so the evidence shown is always
    the asset's own wording rather than the model's copy of it.
    """
    words = quote.split()
    if not words:
        return []
    pattern = re.compile(r"\s+".join(map(re.escape, words)), re.I)
    return [(m.start(), m.end()) for m in pattern.finditer(text)]
