"""Artifacts produced by data collection (uploads + notes)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class CollectedItem(BaseModel):
    """One user-supplied blob (note text or uploaded file reference)."""

    id: str
    kind: Literal["note", "image", "file"]
    text: str | None = None
    stored_path: str | None = Field(
        default=None,
        description="Server-local path or storage key after upload",
    )
    mime_type: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Populated for file uploads
    original_filename: str | None = None
    file_size: int | None = None  # bytes

    # Populated from EXIF for images (when available)
    exif_timestamp: datetime | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None


class CollectedBundle(BaseModel):
    event_id: str
    items: list[CollectedItem] = Field(default_factory=list)
