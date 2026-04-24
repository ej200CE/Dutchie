"""Register uploads and notes into a CollectedBundle."""

from __future__ import annotations

import uuid
from pathlib import Path

from billion_hackathon.contracts.collected import CollectedBundle, CollectedItem


class DataCollectionService:
    def __init__(self, upload_dir: Path) -> None:
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def add_note(self, bundle: CollectedBundle, text: str) -> CollectedItem:
        item = CollectedItem(id=f"note-{uuid.uuid4().hex[:8]}", kind="note", text=text)
        bundle.items.append(item)
        return item

    def add_upload(
        self,
        bundle: CollectedBundle,
        filename: str,
        content: bytes,
        mime_type: str | None,
    ) -> CollectedItem:
        safe = filename.replace("..", "_").replace("/", "_")
        path = self.upload_dir / f"{uuid.uuid4().hex}_{safe}"
        path.write_bytes(content)
        item = CollectedItem(
            id=f"file-{uuid.uuid4().hex[:8]}",
            kind="image" if (mime_type or "").startswith("image/") else "file",
            stored_path=str(path),
            mime_type=mime_type,
        )
        bundle.items.append(item)
        return item
