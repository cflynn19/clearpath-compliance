"""Stored LLM results and usage limits (D11)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, String, Table, func, select, text
from sqlalchemy.dialects.postgresql import insert

from ..db import engine
from ..rules.models import Flag

PER_VISITOR_PER_HOUR = 10
PER_DAY = 300  # across all visitors; resets at midnight UTC

metadata = MetaData()

# Results by content hash: the same asset text gets the same flags, at no cost (D11),
# and re-checking unchanged text never gives a different answer (D9).
llm_results = Table(
    "llm_results",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("model", String(64), nullable=False),
    Column("flags", JSON, nullable=False),
    Column("dropped", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# One row per model call, for the limits. Visitors are stored as a hash, never a raw IP.
llm_calls = Table(
    "llm_calls",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("visitor", String(64), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now(), index=True),
)


def get_result(key: str) -> tuple[list[Flag], int] | None:
    with engine.connect() as conn:
        row = conn.execute(select(llm_results).where(llm_results.c.key == key)).first()
    if row is None:
        return None
    return [Flag.model_validate(f) for f in row.flags], row.dropped


def save_result(key: str, model: str, flags: list[Flag], dropped: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(llm_results)
            .values(key=key, model=model, flags=[f.model_dump(mode="json") for f in flags], dropped=dropped)
            .on_conflict_do_nothing()
        )


def _counts(conn, visitor: str, now: datetime) -> tuple[int, int]:
    hour = conn.scalar(
        select(func.count())
        .select_from(llm_calls)
        .where(llm_calls.c.visitor == visitor, llm_calls.c.created_at > now - timedelta(hours=1))
    )
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day = conn.scalar(select(func.count()).select_from(llm_calls).where(llm_calls.c.created_at >= midnight))
    return hour, day


def remaining(visitor: str) -> int:
    with engine.connect() as conn:
        hour, day = _counts(conn, visitor, datetime.now(timezone.utc))
    return 0 if day >= PER_DAY else max(0, PER_VISITOR_PER_HOUR - hour)


def reserve_call(visitor: str) -> tuple[bool, str | None, int]:
    """Count a model call against the limits before making it.

    Returns (allowed, which limit blocked it, calls left this hour).
    """
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        # Serialise reservations so two simultaneous requests can't both take the last slot.
        conn.execute(text("SELECT pg_advisory_xact_lock(4815162342)"))
        hour, day = _counts(conn, visitor, now)
        if day >= PER_DAY:
            return False, "daily", 0
        if hour >= PER_VISITOR_PER_HOUR:
            return False, "hourly", 0
        conn.execute(llm_calls.insert().values(visitor=visitor, created_at=now))
    return True, None, PER_VISITOR_PER_HOUR - hour - 1
