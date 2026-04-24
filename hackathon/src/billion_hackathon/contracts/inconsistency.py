"""User-visible graph problems (not necessarily blocking compute)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Inconsistency(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
