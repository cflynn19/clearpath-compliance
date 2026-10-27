"""Which rules are active: built-ins the team can switch off, plus their own rules (D8).

Custom rules come in two kinds, and the kind decides the flag type:
- a list of phrases -> matched by code -> "check failed"
- a plain-English rule -> evaluated by the LLM -> "needs judgment"

Changes apply to new checks only. Flags already raised keep the rule as it was, so the
audit trail always reflects what the reviewer saw (D9).
"""

import re
from dataclasses import replace

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, MetaData, String, Table, Text, func, select, text
from sqlalchemy.dialects.postgresql import insert

from ..db import engine
from ..llm.rules import JUDGMENT_RULES
from .builtin import BUILTIN_RULES
from .models import Channel, Finding, FlagType, JudgmentRule, Product, Rule, Span

metadata = MetaData()

# On/off overrides for any rule, built-in or custom.
rule_settings = Table(
    "rule_settings",
    metadata,
    Column("rule_id", String(64), primary_key=True),
    Column("enabled", Boolean, nullable=False),
)

custom_rules = Table(
    "custom_rules",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, nullable=False),
    Column("kind", String(16), nullable=False),  # phrases | instruction
    Column("phrases", JSON, nullable=False),
    Column("instruction", Text),
    Column("products", JSON, nullable=False),
    Column("channels", JSON, nullable=False),
    Column("created_by", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# Append-only history of rule changes. "Who switched off the APR rule, and when" is one
# of the first things an examiner would ask, so it's recorded like any review action (D9).
rule_events = Table(
    "rule_events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("rule_id", String(64), nullable=False, index=True),
    Column("rule_name", Text, nullable=False),
    Column("actor", Text, nullable=False),
    Column("action", String(16), nullable=False),  # switched_on | switched_off | created | deleted
    Column("note", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

CITATION = "ClearPath policy (custom rule)"
MAX_NAME = 80
MAX_PHRASES = 30
MAX_PHRASE = 80
# A plain-English rule is text written by a user that goes into the model's instructions.
# On the real product that's the trusted compliance team; on this public demo it's anyone.
# The cap limits what one rule can carry, and the usual safeguards still apply: the model
# can only return flags, every quote is verified, and code checks run regardless.
MIN_INSTRUCTION, MAX_INSTRUCTION = 10, 500


class RuleError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _custom_id(n: int) -> str:
    return f"custom-{n}"


def _phrase_check(phrases: list[str]):
    # Whole-phrase, case-insensitive. Lookarounds instead of \b so phrases that start or
    # end with a symbol ("$0 down") still match.
    pattern = re.compile(
        "|".join(rf"(?<!\w){re.escape(p)}(?!\w)" for p in sorted(phrases, key=len, reverse=True)), re.I
    )

    def check(asset) -> list[Finding]:
        matches = list(pattern.finditer(asset.body))
        if not matches:
            return []
        found = sorted({m.group().lower() for m in matches})
        return [
            Finding(
                why="Uses wording the compliance team has ruled out: " + ", ".join(f'"{p}"' for p in found) + ".",
                spans=tuple(Span(quote=m.group(), start=m.start(), end=m.end()) for m in matches),
            )
        ]

    return check


def load() -> tuple[list[Rule], list[JudgmentRule]]:
    """Every rule with its current on/off state: (code rules, judgment rules)."""
    with engine.connect() as conn:
        settings = {r.rule_id: r.enabled for r in conn.execute(select(rule_settings))}
        customs = conn.execute(select(custom_rules).order_by(custom_rules.c.id)).all()

    code = [replace(r, enabled=settings.get(r.id, r.enabled)) for r in BUILTIN_RULES]
    judgment = [replace(r, enabled=settings.get(r.id, r.enabled)) for r in JUDGMENT_RULES]
    for c in customs:
        rule_id = _custom_id(c.id)
        scope = {
            "products": frozenset(Product(p) for p in c.products),
            "channels": frozenset(Channel(ch) for ch in c.channels),
            "enabled": settings.get(rule_id, True),
            "source": "custom",
        }
        if c.kind == "phrases":
            code.append(
                Rule(
                    id=rule_id,
                    name=c.name,
                    type=FlagType.CHECK_FAILED,
                    citation=CITATION,
                    description="Flags any of: " + ", ".join(f'"{p}"' for p in c.phrases),
                    check=_phrase_check(c.phrases),
                    **scope,
                )
            )
        else:
            judgment.append(
                JudgmentRule(id=rule_id, name=c.name, citation=CITATION, instruction=c.instruction, **scope)
            )
    return code, judgment


def _log(conn, rule_id: str, rule_name: str, actor: str, action: str, note: str | None = None) -> None:
    conn.execute(rule_events.insert().values(rule_id=rule_id, rule_name=rule_name, actor=actor, action=action, note=note))


def set_enabled(rule_id: str, enabled: bool, actor: str, note: str | None = None) -> None:
    code, judgment = load()
    rule = next((r for r in code + judgment if r.id == rule_id), None)
    if rule is None:
        raise RuleError(404, "Rule not found.")
    if rule.enabled == enabled:
        return
    with engine.begin() as conn:
        conn.execute(
            insert(rule_settings)
            .values(rule_id=rule_id, enabled=enabled)
            .on_conflict_do_update(index_elements=["rule_id"], set_={"enabled": enabled})
        )
        _log(conn, rule_id, rule.name, actor, "switched_on" if enabled else "switched_off", (note or "").strip() or None)


def create_custom(
    *,
    name: str,
    kind: str,
    phrases: list[str],
    instruction: str | None,
    products: list[Product],
    channels: list[Channel],
    actor: str,
) -> str:
    name = name.strip()
    if not 1 <= len(name) <= MAX_NAME:
        raise RuleError(422, f"Give the rule a name (up to {MAX_NAME} characters).")
    if kind == "phrases":
        phrases = list(dict.fromkeys(p.strip() for p in phrases if p.strip()))
        if not phrases:
            raise RuleError(422, "Add at least one phrase.")
        if len(phrases) > MAX_PHRASES or any(len(p) > MAX_PHRASE for p in phrases):
            raise RuleError(422, f"Up to {MAX_PHRASES} phrases of {MAX_PHRASE} characters each.")
        instruction = None
    elif kind == "instruction":
        instruction = (instruction or "").strip()
        if not MIN_INSTRUCTION <= len(instruction) <= MAX_INSTRUCTION:
            raise RuleError(422, f"Describe the rule in {MIN_INSTRUCTION}-{MAX_INSTRUCTION} characters.")
        phrases = []
    else:
        raise RuleError(422, "Rule kind must be phrases or instruction.")

    with engine.begin() as conn:
        new_id = conn.execute(
            custom_rules.insert()
            .values(
                name=name,
                kind=kind,
                phrases=phrases,
                instruction=instruction,
                products=[p.value for p in products],
                channels=[c.value for c in channels],
                created_by=actor,
            )
            .returning(custom_rules.c.id)
        ).scalar_one()
        _log(conn, _custom_id(new_id), name, actor, "created")
    return _custom_id(new_id)


def delete_custom(rule_id: str, actor: str) -> None:
    if not rule_id.startswith("custom-") or not rule_id.removeprefix("custom-").isdigit():
        raise RuleError(422, "Built-in rules can be switched off but not deleted.")
    with engine.begin() as conn:
        deleted = conn.execute(
            custom_rules.delete()
            .where(custom_rules.c.id == int(rule_id.removeprefix("custom-")))
            .returning(custom_rules.c.name)
        ).first()
        if deleted is None:
            raise RuleError(404, "Rule not found.")
        conn.execute(rule_settings.delete().where(rule_settings.c.rule_id == rule_id))
        _log(conn, rule_id, deleted.name, actor, "deleted")


def history(limit: int = 50) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(rule_events).order_by(rule_events.c.created_at.desc(), rule_events.c.id.desc()).limit(limit)
        )
        return [dict(r._mapping) for r in rows]


def clear() -> None:
    """Back to the built-in rules, all at their defaults (used by the demo reset)."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE custom_rules, rule_settings, rule_events RESTART IDENTITY"))
