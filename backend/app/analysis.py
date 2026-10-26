"""Analyse one asset: code checks always, LLM checks when allowed (D11)."""

import os
from typing import Literal

from pydantic import BaseModel

from .llm import checker, store
from .rules.engine import run_code_checks
from .rules.models import Asset, Flag


class AIStatus(BaseModel):
    status: Literal["ran", "cached", "limited", "unavailable", "disabled"]
    message: str
    remaining_this_hour: int
    limit_per_hour: int = store.PER_VISITOR_PER_HOUR
    dropped: int = 0  # model findings discarded because their quotes weren't in the asset


class AnalyzeResult(BaseModel):
    flags: list[Flag]
    ai: AIStatus


def analyze(asset: Asset, visitor: str, enforce_limits: bool = True) -> AnalyzeResult:
    """enforce_limits=False is for server-side work only (seeding the demo queue)."""
    code_flags = run_code_checks(asset)
    ai_flags, ai = _ai_checks(asset, visitor, enforce_limits)
    flags = sorted(code_flags + ai_flags, key=lambda f: f.spans[0].start if f.spans else -1)
    return AnalyzeResult(flags=flags, ai=ai)


def _ai_checks(asset: Asset, visitor: str, enforce_limits: bool) -> tuple[list[Flag], AIStatus]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return [], AIStatus(
            status="disabled",
            message="AI checks are off (no API key configured). Code checks still ran.",
            remaining_this_hour=0,
        )

    rules = checker.applicable_rules(asset)
    key = checker.cache_key(asset, rules)

    # Unchanged text: reuse the stored answer. Free, and it doesn't use up the limit.
    stored = store.get_result(key)
    if stored is not None:
        flags, dropped = stored
        return flags, AIStatus(
            status="cached",
            message="AI results reused: this exact text was already checked.",
            remaining_this_hour=store.remaining(visitor),
            dropped=dropped,
        )

    allowed, limit, left = store.reserve_call(visitor) if enforce_limits else (True, None, store.remaining(visitor))
    if not allowed:
        message = (
            "AI checks are paused for today (daily limit reached). Code checks still ran."
            if limit == "daily"
            else f"AI checks paused: {store.PER_VISITOR_PER_HOUR} per hour per visitor. "
            "Code checks still ran."
        )
        return [], AIStatus(status="limited", message=message, remaining_this_hour=0)

    try:
        output = checker.call_model(checker.build_prompt(asset, rules))
    except checker.LLMUnavailable:
        return [], AIStatus(
            status="unavailable",
            message="AI checks are unavailable right now. Code checks still ran.",
            remaining_this_hour=left,
        )

    flags, dropped = checker.to_flags(output, asset, rules)
    store.save_result(key, checker.MODEL, flags, dropped)
    return flags, AIStatus(status="ran", message="AI checks ran.", remaining_this_hour=left, dropped=dropped)
