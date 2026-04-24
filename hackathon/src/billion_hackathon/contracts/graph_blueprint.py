"""Instructions to build / extend the transactional graph (output of evidence_aggregation)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GraphOperation(BaseModel):
    op: Literal["add_node", "add_edge"]
    node: dict[str, Any] | None = None
    edge: dict[str, Any] | None = None


class GraphBlueprint(BaseModel):
    event_id: str
    operations: list[GraphOperation] = Field(default_factory=list)
