from dataclasses import dataclass
from enum import Enum
from typing import Callable, Literal

from pydantic import BaseModel, Field


class FlagType(str, Enum):
    CHECK_FAILED = "check_failed"  # found by code: a yes/no fact
    NEEDS_JUDGMENT = "needs_judgment"  # found by the LLM: the reviewer decides


# Products are the three the brief names. Channels are an assumption about ClearPath's
# "typical marketing channels, including affiliate partners" (A23).
class Product(str, Enum):
    PERSONAL_LOAN = "personal_loan"
    CREDIT_CARD = "credit_card"
    MORTGAGE = "mortgage"


class Channel(str, Enum):
    EMAIL = "email"
    SOCIAL = "social"
    LANDING_PAGE = "landing_page"
    AFFILIATE_PAGE = "affiliate_page"
    SEARCH_AD = "search_ad"


class Asset(BaseModel):
    # Q1: plenty for ad copy, emails and landing pages; raise it if real assets run longer.
    body: str = Field(min_length=1, max_length=20_000)
    product: Product
    channel: Channel
    subject: str | None = Field(default=None, max_length=500)  # email only


class Span(BaseModel):
    """One place in the asset a flag points at: the exact text and where it is."""

    quote: str
    field: Literal["body", "subject"] = "body"
    start: int
    end: int


class Flag(BaseModel):
    rule_id: str
    rule_name: str
    type: FlagType
    citation: str
    why: str
    # One flag per rule per asset, pointing at every occurrence, so repeats read as one
    # issue to fix rather than a pile of separate flags (Q7, Q9). Empty for "something
    # is missing" flags, which apply to the whole asset.
    spans: list[Span] = Field(default_factory=list)


@dataclass(frozen=True)
class Finding:
    """What a rule's check returns. The engine adds the rule's metadata to make a Flag."""

    why: str
    spans: tuple[Span, ...] = ()


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    type: FlagType
    citation: str
    description: str
    check: Callable[[Asset], list[Finding]]
    products: frozenset[Product] = frozenset()  # empty = every product
    channels: frozenset[Channel] = frozenset()  # empty = every channel
    enabled: bool = True
    source: Literal["builtin", "custom"] = "builtin"

    def applies_to(self, asset: Asset) -> bool:
        return _in_scope(self.products, self.channels, asset)


@dataclass(frozen=True)
class JudgmentRule:
    """A rule the LLM evaluates. Every flag it raises is "needs judgment"."""

    id: str
    name: str
    citation: str
    instruction: str  # plain English, sent to the model
    products: frozenset[Product] = frozenset()
    channels: frozenset[Channel] = frozenset()
    enabled: bool = True
    source: Literal["builtin", "custom"] = "builtin"
    requires_subject: bool = False  # skip when the asset has no subject line
    type: FlagType = FlagType.NEEDS_JUDGMENT

    def applies_to(self, asset: Asset) -> bool:
        if self.requires_subject and not asset.subject:
            return False
        return _in_scope(self.products, self.channels, asset)


def _in_scope(products: frozenset[Product], channels: frozenset[Channel], asset: Asset) -> bool:
    return (not products or asset.product in products) and (not channels or asset.channel in channels)
