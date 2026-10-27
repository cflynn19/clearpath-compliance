from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import analysis
from ..rules.models import Asset, Channel, FlagType, Product, Span
from ..visitors import visitor_id
from . import seeds, store

router = APIRouter(prefix="/api")

# DECISION(Q17): there's no auth in v1 (A17), so every action is recorded as one demo
# reviewer. The audit trail still has the right shape: a real login only changes this name.
ACTOR = "Demo reviewer"


class FlagOut(BaseModel):
    id: int
    rule_id: str
    rule_name: str
    type: FlagType
    citation: str
    why: str
    spans: list[Span]
    status: Literal["open", "dismissed", "acknowledged"]
    reason: str | None
    note: str | None
    resolved_by: str | None
    resolved_at: datetime | None


class EventOut(BaseModel):
    id: int
    actor: str
    action: str
    detail: dict
    created_at: datetime


class VersionOut(BaseModel):
    number: int
    subject: str | None
    body: str
    ai: analysis.AIStatus
    created_at: datetime


class AssetSummary(BaseModel):
    id: int
    title: str
    submitter: str
    product: Product
    channel: Channel
    status: Literal["in_review", "approved", "rejected"]
    created_at: datetime
    decided_at: datetime | None
    open_failed: int
    open_judgment: int
    total: int


class AssetDetail(BaseModel):
    id: int
    title: str
    submitter: str
    product: Product
    channel: Channel
    status: Literal["in_review", "approved", "rejected"]
    created_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    version: VersionOut
    flags: list[FlagOut]
    events: list[EventOut]


class NewAsset(Asset):
    title: str | None = Field(default=None, max_length=120)
    submitter: str | None = Field(default=None, max_length=120)


class Dismissal(BaseModel):
    reason: str
    note: str | None = Field(default=None, max_length=1000)


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=1000)


def _detail(asset_id: int) -> AssetDetail:
    found = store.get_asset(asset_id)
    if found is None:
        raise HTTPException(404, "Ad not found.")
    return AssetDetail.model_validate(found)


def _run(fn, *args) -> AssetDetail:
    try:
        return _detail(fn(*args))
    except store.ReviewError as e:
        raise HTTPException(e.status, e.message) from e


@router.get("/assets")
def list_assets() -> list[AssetSummary]:
    return [AssetSummary.model_validate(a) for a in store.list_assets()]


@router.post("/assets")
def create_asset(new: NewAsset, request: Request) -> AssetDetail:
    asset = Asset(body=new.body, product=new.product, channel=new.channel, subject=new.subject)
    result = analysis.analyze(asset, visitor_id(request))
    title = (new.title or "").strip() or _default_title(new.body)
    submitter = (new.submitter or "").strip() or f"Pasted by {ACTOR.lower()}"
    asset_id = store.create_asset(
        title=title, submitter=submitter, asset=asset, found=result.flags, ai=result.ai, actor=ACTOR
    )
    return _detail(asset_id)


def _default_title(body: str) -> str:
    words = body.split()
    return " ".join(words[:7]) + ("…" if len(words) > 7 else "")


@router.get("/assets/{asset_id}")
def get_asset(asset_id: int) -> AssetDetail:
    return _detail(asset_id)


@router.post("/flags/{flag_id}/dismiss")
def dismiss(flag_id: int, body: Dismissal) -> AssetDetail:
    return _run(store.dismiss_flag, flag_id, body.reason, body.note, ACTOR)


@router.post("/flags/{flag_id}/acknowledge")
def acknowledge(flag_id: int) -> AssetDetail:
    return _run(store.acknowledge_flag, flag_id, ACTOR)


@router.post("/flags/{flag_id}/reopen")
def reopen(flag_id: int) -> AssetDetail:
    return _run(store.reopen_flag, flag_id, ACTOR)


@router.post("/assets/{asset_id}/decision")
def decide(asset_id: int, body: Decision) -> AssetDetail:
    try:
        store.decide(asset_id, body.decision, body.note, ACTOR)
    except store.ReviewError as e:
        raise HTTPException(e.status, e.message) from e
    return _detail(asset_id)


class Metrics(BaseModel):
    in_review: int
    oldest_waiting_minutes: float | None
    approved: int
    rejected: int
    median_decision_minutes: float | None
    flags_per_ad: float | None
    dismiss_rate: float | None


@router.get("/metrics")
def metrics() -> Metrics:
    return Metrics(**store.metrics())


class ReviewConfig(BaseModel):
    actor: str
    dismiss_reasons: dict[str, str]


@router.get("/review-config")
def review_config() -> ReviewConfig:
    return ReviewConfig(actor=ACTOR, dismiss_reasons=store.DISMISS_REASONS)


@router.post("/demo/reset")
def reset_demo() -> dict:
    return {"seeded": seeds.reset()}
