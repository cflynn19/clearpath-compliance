from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..review import store as review_store
from ..review.api import ACTOR
from . import registry
from .models import Channel, FlagType, Product

router = APIRouter(prefix="/api/rules")


class RuleStats(BaseModel):
    flagged: int = 0
    dismissed: int = 0
    reasons: dict[str, int] = {}


class RuleOut(BaseModel):
    id: str
    name: str
    type: FlagType
    citation: str
    description: str
    products: list[Product]
    channels: list[Channel]
    enabled: bool
    source: Literal["builtin", "custom"]
    stats: RuleStats


class NewRule(BaseModel):
    name: str = Field(max_length=registry.MAX_NAME)
    kind: Literal["phrases", "instruction"]
    phrases: list[str] = Field(default=[], max_length=registry.MAX_PHRASES)
    instruction: str | None = Field(default=None, max_length=registry.MAX_INSTRUCTION)
    products: list[Product] = []
    channels: list[Channel] = []


class Toggle(BaseModel):
    enabled: bool
    note: str | None = Field(default=None, max_length=500)


class RuleEvent(BaseModel):
    id: int
    rule_id: str
    rule_name: str
    actor: str
    action: Literal["switched_on", "switched_off", "created", "deleted"]
    note: str | None
    created_at: datetime


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except registry.RuleError as e:
        raise HTTPException(e.status, e.message) from e


@router.get("")
def list_rules() -> list[RuleOut]:
    stats = review_store.rule_stats()
    code, judgment = registry.load()
    return [
        RuleOut(
            id=r.id,
            name=r.name,
            type=r.type,
            citation=r.citation,
            description=getattr(r, "description", None) or getattr(r, "instruction", ""),
            products=sorted(r.products),
            channels=sorted(r.channels),
            enabled=r.enabled,
            source=r.source,
            stats=RuleStats(**stats.get(r.id, {})),
        )
        for r in [*code, *judgment]
    ]


@router.post("")
def create_rule(new: NewRule) -> list[RuleOut]:
    _guard(
        registry.create_custom,
        name=new.name,
        kind=new.kind,
        phrases=new.phrases,
        instruction=new.instruction,
        products=new.products,
        channels=new.channels,
        actor=ACTOR,
    )
    return list_rules()


@router.get("/history")
def rule_history() -> list[RuleEvent]:
    return [RuleEvent.model_validate(e) for e in registry.history()]


@router.patch("/{rule_id}")
def toggle_rule(rule_id: str, body: Toggle) -> list[RuleOut]:
    _guard(registry.set_enabled, rule_id, body.enabled, ACTOR, body.note)
    return list_rules()


@router.delete("/{rule_id}")
def delete_rule(rule_id: str) -> list[RuleOut]:
    _guard(registry.delete_custom, rule_id, ACTOR)
    return list_rules()
