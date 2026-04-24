"""Structured evidence after ingestion (LLM or rules). Output contract for data_ingestion."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    id: str
    source_item_ids: list[str] = Field(default_factory=list)
    kind: Literal["spend_hint", "receipt_line", "p2p_hint", "presence_hint", "free_text"]
    amount_cents: int | None = None
    currency: str | None = "EUR"
    label: str | None = None
    payer_person_id: str | None = None
    participant_person_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    raw_excerpt: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class EvidenceBundle(BaseModel):
    event_id: str
    items: list[EvidenceItem] = Field(default_factory=list)
