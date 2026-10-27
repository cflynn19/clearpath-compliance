"""Queue items, their flags, reviewer actions and the audit trail (D5, D6, D7, D9)."""

from datetime import datetime, timezone
from statistics import median

from sqlalchemy import (
    JSON,
    Boolean,
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
    # in_review | needs_changes (sent back to the submitter) | approved | rejected
    Column("status", String(16), nullable=False, server_default="in_review"),
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
    # True when a reviewer's resolution was carried over from the previous version.
    Column("carried_over", Boolean, nullable=False, server_default="false"),
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

def ensure_schema() -> None:
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE flags ADD COLUMN IF NOT EXISTS carried_over BOOLEAN NOT NULL DEFAULT false"))


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


def _flag_rows(version_id: int, found: list[Flag]) -> list[dict]:
    return [
        {
            "version_id": version_id,
            "rule_id": f.rule_id,
            "rule_name": f.rule_name,
            "type": f.type.value,
            "citation": f.citation,
            "why": f.why,
            "spans": [sp.model_dump(mode="json") for sp in f.spans],
        }
        for f in found
    ]


def _latest_version(conn, asset_id: int):
    return conn.execute(
        select(versions).where(versions.c.asset_id == asset_id).order_by(versions.c.number.desc()).limit(1)
    ).first()


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
            conn.execute(flags.insert(), _flag_rows(version_id, found))
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
            func.array_remove(func.array_agg(func.distinct(flags.c.rule_id)), None).label("rule_ids"),
        )
        .select_from(latest.outerjoin(flags, flags.c.version_id == latest.c.version_id))
        .group_by(latest.c.asset_id)
        .subquery()
    )


def list_assets() -> list[dict]:
    counts = _open_counts()
    query = (
        select(assets, counts.c.open_failed, counts.c.open_judgment, counts.c.total, counts.c.rule_ids)
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
        version = _latest_version(conn, asset_id)
        flag_rows = conn.execute(select(flags).where(flags.c.version_id == version.id).order_by(flags.c.id)).all()
        event_rows = conn.execute(
            select(events).where(events.c.asset_id == asset_id).order_by(events.c.created_at.desc(), events.c.id.desc())
        ).all()
    comparison = next(
        (e.detail for e in event_rows if e.action == "revised" and e.detail.get("version") == version.number), None
    )
    return {
        **dict(row._mapping),
        "version": dict(version._mapping),
        "flags": [dict(f._mapping) for f in flag_rows],
        "events": [dict(e._mapping) for e in event_rows],
        "comparison": comparison,
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
    if decision not in ("approve", "reject", "request_changes"):
        raise ReviewError(422, "Decision must be approve, reject or request_changes.")
    note = (note or "").strip() or None
    with engine.begin() as conn:
        row = conn.execute(select(assets).where(assets.c.id == asset_id).with_for_update()).first()
        if row is None:
            raise ReviewError(404, "Ad not found.")
        # Rejecting is allowed while waiting on the submitter; everything else needs the ad in review.
        allowed = ("in_review", "needs_changes") if decision == "reject" else ("in_review",)
        if row.status not in allowed:
            raise ReviewError(409, "This ad isn't in review.")
        # Only the current version counts: earlier versions' flags are history.
        version = _latest_version(conn, asset_id)
        open_flags = conn.scalar(
            select(func.count()).select_from(flags).where(flags.c.version_id == version.id, flags.c.status == "open")
        )
        if decision == "approve" and open_flags:
            raise ReviewError(409, f"Resolve the {open_flags} open flag(s) before approving.")

        if decision == "request_changes":
            # Not a final decision: the ad goes back to the submitter, and the open flags are
            # the list of what to fix.
            conn.execute(assets.update().where(assets.c.id == asset_id).values(status="needs_changes"))
            _event(conn, asset_id, actor, "changes_requested", {"note": note, "open_flags": open_flags})
            return
        status = "approved" if decision == "approve" else "rejected"
        conn.execute(
            assets.update()
            .where(assets.c.id == asset_id)
            .values(status=status, decided_by=actor, decided_at=_now(), decision_note=note)
        )
        _event(conn, asset_id, actor, status, {"note": note})


def _quotes(spans: list) -> tuple:
    return tuple(sorted(" ".join(sp["quote"].split()).lower() for sp in spans))


def revise(asset_id: int, asset: Asset, found: list[Flag], ai: AIStatus, actor: str) -> int:
    """Store a revised version sent back by the submitter, and compare it with the last one.

    The re-review time saver: if the reviewer dismissed or acknowledged a flag and the same
    rule fires on the same text again, that resolution carries over, so nobody resolves the
    same false positive twice. If the text changed, the flag reopens.
    """
    with engine.begin() as conn:
        row = conn.execute(select(assets).where(assets.c.id == asset_id).with_for_update()).first()
        if row is None:
            raise ReviewError(404, "Ad not found.")
        if row.status != "needs_changes":
            raise ReviewError(409, "Revisions can only be submitted after changes are requested.")
        previous = _latest_version(conn, asset_id)
        prev_flags = conn.execute(select(flags).where(flags.c.version_id == previous.id)).all()
        number = previous.number + 1
        version_id = conn.execute(
            versions.insert()
            .values(asset_id=asset_id, number=number, subject=asset.subject, body=asset.body, ai=ai.model_dump(mode="json"))
            .returning(versions.c.id)
        ).scalar_one()

        resolved_before = {(f.rule_id, _quotes(f.spans)): f for f in prev_flags if f.status != "open"}
        rows = _flag_rows(version_id, found)
        carried = 0
        for r in rows:
            match = resolved_before.get((r["rule_id"], _quotes(r["spans"])))
            if match:
                carried += 1
                r.update(
                    status=match.status,
                    reason=match.reason,
                    note=match.note,
                    resolved_by=match.resolved_by,
                    resolved_at=match.resolved_at,
                    carried_over=True,
                )
        if rows:
            conn.execute(flags.insert(), rows)

        before = {f.rule_id: f.rule_name for f in prev_flags}
        after = {f.rule_id: f.rule_name for f in found}
        carried_ids = {r["rule_id"] for r in rows if r.get("carried_over")}
        comparison = {
            "version": number,
            "fixed": sorted(before[r] for r in before.keys() - after.keys()),
            "still_flagged": sorted(after[r] for r in (after.keys() & before.keys()) - carried_ids),
            "new": sorted(after[r] for r in after.keys() - before.keys()),
            "carried_over": carried,
        }
        conn.execute(assets.update().where(assets.c.id == asset_id).values(status="in_review"))
        _event(conn, asset_id, actor, "revised", comparison)
    return asset_id


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


# Below this many flags, a dismissal rate is noise, not a signal about the rule.
MIN_SAMPLE = 3


def metrics(since: datetime | None = None) -> dict:
    """Throughput numbers, straight from the queue and its audit trail.

    The same timestamps a regulator would ask about are what measure the team's speed:
    the audit trail doubles as the measurement. `since` limits everything except the
    current backlog to ads submitted (or decided) after that time.
    """
    now = _now()
    with engine.connect() as conn:
        rows = conn.execute(select(assets.c.status, assets.c.created_at, assets.c.decided_at)).all()
        flag_rows = conn.execute(
            select(
                flags.c.rule_id, flags.c.rule_name, flags.c.type, flags.c.status, flags.c.reason, assets.c.created_at
            ).select_from(
                flags.join(versions).join(assets)
            )
        ).all()

    waiting = [r for r in rows if r.status == "in_review"]
    submitted = [r for r in rows if since is None or r.created_at >= since]
    decided = [r for r in rows if r.decided_at and (since is None or r.decided_at >= since)]
    minutes = [(r.decided_at - r.created_at).total_seconds() / 60 for r in decided]
    in_range = [f for f in flag_rows if since is None or f.created_at >= since]
    resolved = [f for f in in_range if f.status != "open"]

    by_rule: dict[str, dict] = {}
    for f in in_range:
        r = by_rule.setdefault(
            f.rule_id,
            {"rule_id": f.rule_id, "rule_name": f.rule_name, "type": f.type, "flagged": 0, "dismissed": 0, "reasons": {}},
        )
        r["flagged"] += 1
        if f.status == "dismissed":
            r["dismissed"] += 1
            r["reasons"][f.reason] = r["reasons"].get(f.reason, 0) + 1
    for r in by_rule.values():
        # The most common reason says what to do about the rule (DECISIONS D17).
        r["top_reason"] = max(r.pop("reasons").items(), key=lambda kv: kv[1])[0] if r["dismissed"] else None
    # Every rule that fired. Default order: rules with enough flags to judge first, then the
    # ones reviewers dismiss most, so the top of the list is "most overridden".
    health = sorted(
        by_rule.values(),
        key=lambda r: (r["flagged"] >= MIN_SAMPLE, r["dismissed"] / r["flagged"], r["dismissed"], r["flagged"]),
        reverse=True,
    )

    return {
        "in_review": len(waiting),
        "oldest_waiting_minutes": max(((now - r.created_at).total_seconds() / 60 for r in waiting), default=None),
        "submitted": len(submitted),
        "approved": sum(r.status == "approved" for r in decided),
        "rejected": sum(r.status == "rejected" for r in decided),
        "median_decision_minutes": median(minutes) if minutes else None,
        "flags_per_ad": len(in_range) / len(submitted) if submitted else None,
        # Of the flags reviewers have resolved, how many they threw out: the cost of
        # overflagging (D3), and the number to watch when tuning rules.
        "dismiss_rate": sum(f.status == "dismissed" for f in resolved) / len(resolved) if resolved else None,
        "rule_health": health,
    }
