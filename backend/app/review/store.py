"""Queue items, their flags, reviewer actions and the audit trail (D5, D6, D7, D9)."""

from datetime import datetime, timezone
from statistics import median

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
    select,
    text,
)

from ..analysis import AIStatus
from ..db import engine
from ..rules.models import Asset, Flag

metadata = MetaData()

assets = Table(
    "assets",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("title", Text, nullable=False),
    Column("submitter", Text, nullable=False),
    Column("product", String(32), nullable=False),
    Column("channel", String(32), nullable=False),
    Column("status", String(16), nullable=False, server_default="in_review"),  # in_review | approved | rejected
    Column("decided_by", Text),
    Column("decided_at", DateTime(timezone=True)),
    Column("decision_note", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# Versions exist from day one so flags and decisions always point at the exact text that
# was reviewed (D9), even though v1 has no revision loop yet.
versions = Table(
    "asset_versions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("asset_id", Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("number", Integer, nullable=False),
    Column("subject", Text),
    Column("body", Text, nullable=False),
    Column("ai", JSON, nullable=False),  # the AI status when this version was checked
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

flags = Table(
    "flags",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("version_id", Integer, ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("rule_id", String(64), nullable=False, index=True),
    Column("rule_name", Text, nullable=False),
    Column("type", String(16), nullable=False),
    Column("citation", Text, nullable=False),
    Column("why", Text, nullable=False),
    Column("spans", JSON, nullable=False),
    Column("status", String(16), nullable=False, server_default="open"),  # open | dismissed | acknowledged
    Column("reason", String(32)),
    Column("note", Text),
    Column("resolved_by", Text),
    Column("resolved_at", DateTime(timezone=True)),
)

# Append-only: every action, by whom, when.
events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("asset_id", Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("flag_id", Integer),
    Column("actor", Text, nullable=False),
    Column("action", String(32), nullable=False),
    Column("detail", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# D6. "Fixed in this revision" waits for the revision loop, which isn't in v1.
DISMISS_REASONS = {
    "false_positive": "False positive: the rule doesn't apply here",
    "met_elsewhere": "Requirement met elsewhere (landing page, footer, linked terms)",
    "approved_exception": "Approved exception (legal signed off)",
    "other": "Other",
}


class ReviewError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event(conn, asset_id: int, actor: str, action: str, detail: dict, flag_id: int | None = None, at=None):
    conn.execute(
        events.insert().values(
            asset_id=asset_id, flag_id=flag_id, actor=actor, action=action, detail=detail, created_at=at or _now()
        )
    )


def create_asset(
    *,
    title: str,
    submitter: str,
    asset: Asset,
    found: list[Flag],
    ai: AIStatus,
    actor: str,
    created_at: datetime | None = None,
) -> int:
    at = created_at or _now()
    with engine.begin() as conn:
        asset_id = conn.execute(
            assets.insert()
            .values(
                title=title,
                submitter=submitter,
                product=asset.product.value,
                channel=asset.channel.value,
                created_at=at,
            )
            .returning(assets.c.id)
        ).scalar_one()
        version_id = conn.execute(
            versions.insert()
            .values(
                asset_id=asset_id,
                number=1,
                subject=asset.subject,
                body=asset.body,
                ai=ai.model_dump(mode="json"),
                created_at=at,
            )
            .returning(versions.c.id)
        ).scalar_one()
        if found:
            conn.execute(
                flags.insert(),
                [
                    {
                        "version_id": version_id,
                        "rule_id": f.rule_id,
                        "rule_name": f.rule_name,
                        "type": f.type.value,
                        "citation": f.citation,
                        "why": f.why,
                        "spans": [s.model_dump(mode="json") for s in f.spans],
                    }
                    for f in found
                ],
            )
        _event(conn, asset_id, submitter, "submitted", {"version": 1}, at=at)
        _event(
            conn,
            asset_id,
            "System",
            "checked",
            {
                "check_failed": sum(f.type.value == "check_failed" for f in found),
                "needs_judgment": sum(f.type.value == "needs_judgment" for f in found),
                "ai": ai.status,
            },
            at=at,
        )
    return asset_id


def _open_counts():
    """Open flags per asset (latest version), by type."""
    latest = (
        select(versions.c.asset_id, func.max(versions.c.id).label("version_id"))
        .group_by(versions.c.asset_id)
        .subquery()
    )
    return (
        select(
            latest.c.asset_id,
            func.count(flags.c.id).filter(flags.c.type == "check_failed", flags.c.status == "open").label("open_failed"),
            func.count(flags.c.id).filter(flags.c.type == "needs_judgment", flags.c.status == "open").label("open_judgment"),
            func.count(flags.c.id).label("total"),
        )
        .select_from(latest.outerjoin(flags, flags.c.version_id == latest.c.version_id))
        .group_by(latest.c.asset_id)
        .subquery()
    )


def list_assets() -> list[dict]:
    counts = _open_counts()
    query = (
        select(assets, counts.c.open_failed, counts.c.open_judgment, counts.c.total)
        .select_from(assets.join(counts, counts.c.asset_id == assets.c.id))
        .order_by((assets.c.status == "in_review").desc(), assets.c.created_at.desc())
    )
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(query)]


def get_asset(asset_id: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(select(assets).where(assets.c.id == asset_id)).first()
        if row is None:
            return None
        version = conn.execute(
            select(versions).where(versions.c.asset_id == asset_id).order_by(versions.c.number.desc()).limit(1)
        ).first()
        flag_rows = conn.execute(select(flags).where(flags.c.version_id == version.id).order_by(flags.c.id)).all()
        event_rows = conn.execute(
            select(events).where(events.c.asset_id == asset_id).order_by(events.c.created_at.desc(), events.c.id.desc())
        ).all()
    return {
        **dict(row._mapping),
        "version": dict(version._mapping),
        "flags": [dict(f._mapping) for f in flag_rows],
        "events": [dict(e._mapping) for e in event_rows],
    }


def _lock_flag(conn, flag_id: int):
    """The flag and its asset, locked, after checking the asset is still in review."""
    row = conn.execute(
        select(flags, versions.c.asset_id, assets.c.status.label("asset_status"))
        .select_from(flags.join(versions).join(assets))
        .where(flags.c.id == flag_id)
        .with_for_update(of=assets)
    ).first()
    if row is None:
        raise ReviewError(404, "Flag not found.")
    if row.asset_status != "in_review":
        raise ReviewError(409, "This ad has already been decided; its flags can't change.")
    return row


def dismiss_flag(flag_id: int, reason: str, note: str | None, actor: str) -> int:
    if reason not in DISMISS_REASONS:
        raise ReviewError(422, "Pick a dismissal reason.")
    note = (note or "").strip() or None
    if reason == "other" and not note:
        raise ReviewError(422, 'Add a note when the reason is "Other".')
    with engine.begin() as conn:
        row = _lock_flag(conn, flag_id)
        conn.execute(
            flags.update()
            .where(flags.c.id == flag_id)
            .values(status="dismissed", reason=reason, note=note, resolved_by=actor, resolved_at=_now())
        )
        _event(conn, row.asset_id, actor, "flag_dismissed", {"rule": row.rule_name, "reason": reason, "note": note}, flag_id)
    return row.asset_id


def acknowledge_flag(flag_id: int, actor: str) -> int:
    with engine.begin() as conn:
        row = _lock_flag(conn, flag_id)
        if row.type != "needs_judgment":
            # A definite violation can't just be noted: fix it (reject and resubmit) or dismiss it with a reason.
            raise ReviewError(422, "Check-failed flags can't be acknowledged; dismiss them with a reason instead.")
        conn.execute(
            flags.update()
            .where(flags.c.id == flag_id)
            .values(status="acknowledged", reason=None, note=None, resolved_by=actor, resolved_at=_now())
        )
        _event(conn, row.asset_id, actor, "flag_acknowledged", {"rule": row.rule_name}, flag_id)
    return row.asset_id


def reopen_flag(flag_id: int, actor: str) -> int:
    with engine.begin() as conn:
        row = _lock_flag(conn, flag_id)
        conn.execute(
            flags.update()
            .where(flags.c.id == flag_id)
            .values(status="open", reason=None, note=None, resolved_by=None, resolved_at=None)
        )
        _event(conn, row.asset_id, actor, "flag_reopened", {"rule": row.rule_name, "was": row.status}, flag_id)
    return row.asset_id


def decide(asset_id: int, decision: str, note: str | None, actor: str) -> None:
    if decision not in ("approve", "reject"):
        raise ReviewError(422, "Decision must be approve or reject.")
    note = (note or "").strip() or None
    with engine.begin() as conn:
        row = conn.execute(select(assets).where(assets.c.id == asset_id).with_for_update()).first()
        if row is None:
            raise ReviewError(404, "Ad not found.")
        if row.status != "in_review":
            raise ReviewError(409, "This ad has already been decided.")
        if decision == "approve":
            open_flags = conn.scalar(
                select(func.count())
                .select_from(flags.join(versions))
                .where(versions.c.asset_id == asset_id, flags.c.status == "open")
            )
            if open_flags:
                raise ReviewError(409, f"Resolve the {open_flags} open flag(s) before approving.")
        status = "approved" if decision == "approve" else "rejected"
        conn.execute(
            assets.update()
            .where(assets.c.id == asset_id)
            .values(status=status, decided_by=actor, decided_at=_now(), decision_note=note)
        )
        _event(conn, asset_id, actor, status, {"note": note})


def rule_stats() -> dict[str, dict]:
    """How often each rule fires and gets dismissed, and why (D7)."""
    query = select(flags.c.rule_id, flags.c.status, flags.c.reason, func.count().label("n")).group_by(
        flags.c.rule_id, flags.c.status, flags.c.reason
    )
    stats: dict[str, dict] = {}
    with engine.connect() as conn:
        for r in conn.execute(query):
            s = stats.setdefault(r.rule_id, {"flagged": 0, "dismissed": 0, "reasons": {}})
            s["flagged"] += r.n
            if r.status == "dismissed":
                s["dismissed"] += r.n
                s["reasons"][r.reason] = s["reasons"].get(r.reason, 0) + r.n
    return stats


def count_assets() -> int:
    with engine.connect() as conn:
        return conn.scalar(select(func.count()).select_from(assets))


def clear() -> None:
    """Delete every queue item and its history. Stored LLM results are kept, so re-seeding is free."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE events, flags, asset_versions, assets RESTART IDENTITY"))


def metrics() -> dict:
    """Throughput numbers, straight from the queue and its audit trail.

    The same timestamps a regulator would ask about are what measure the team's speed:
    the audit trail doubles as the measurement.
    """
    now = _now()
    with engine.connect() as conn:
        rows = conn.execute(select(assets.c.status, assets.c.created_at, assets.c.decided_at)).all()
        flag_rows = conn.execute(select(flags.c.status)).all()
    waiting = [r for r in rows if r.status == "in_review"]
    decided = [r for r in rows if r.status != "in_review" and r.decided_at]
    minutes = [(r.decided_at - r.created_at).total_seconds() / 60 for r in decided]
    resolved = [f for f in flag_rows if f.status != "open"]
    return {
        "in_review": len(waiting),
        "oldest_waiting_minutes": max(((now - r.created_at).total_seconds() / 60 for r in waiting), default=None),
        "approved": sum(r.status == "approved" for r in decided),
        "rejected": sum(r.status == "rejected" for r in decided),
        "median_decision_minutes": median(minutes) if minutes else None,
        "flags_per_ad": len(flag_rows) / len(rows) if rows else None,
        # Of the flags reviewers have resolved, how many they threw out: the cost of
        # overflagging (D3), and the number to watch when tuning rules.
        "dismiss_rate": sum(f.status == "dismissed" for f in resolved) / len(resolved) if resolved else None,
    }
