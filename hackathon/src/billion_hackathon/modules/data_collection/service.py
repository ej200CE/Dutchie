"""Register uploads and notes into a CollectedBundle."""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from pathlib import Path

from billion_hackathon.contracts.collected import CollectedBundle, CollectedItem

try:
    from PIL import Image

    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


def _dms_to_decimal(dms, ref: str) -> float:
    def to_float(v):
        if isinstance(v, tuple):
            return v[0] / v[1]
        return float(v)

    d, m, s = dms
    val = to_float(d) + to_float(m) / 60 + to_float(s) / 3600
    if ref in ("S", "W"):
        val = -val
    return round(val, 6)


def _extract_exif(content: bytes) -> dict:
    if not _PIL_AVAILABLE:
        return {}
    try:
        img = Image.open(io.BytesIO(content))
        exif = img.getexif()
        if not exif:
            return {}
        result: dict = {}

        dt_val = exif.get(36867)  # DateTimeOriginal
        if not dt_val:
            dt_val = exif.get(306)  # DateTime fallback
        if dt_val:
            try:
                result["exif_timestamp"] = datetime.strptime(dt_val, "%Y:%m:%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass

        gps_ifd = exif.get_ifd(34853)  # GPSInfo IFD
        if gps_ifd and all(k in gps_ifd for k in (1, 2, 3, 4)):
            try:
                result["gps_lat"] = _dms_to_decimal(gps_ifd[2], gps_ifd[1])
                result["gps_lon"] = _dms_to_decimal(gps_ifd[4], gps_ifd[3])
            except (TypeError, ZeroDivisionError, ValueError):
                pass

        return result
    except Exception:
        return {}


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

        is_image = (mime_type or "").startswith("image/")
        is_audio = (mime_type or "").startswith("audio/")
        exif_meta = _extract_exif(content) if is_image else {}

        item = CollectedItem(
            id=f"file-{uuid.uuid4().hex[:8]}",
            kind="image" if is_image else ("audio" if is_audio else "file"),
            stored_path=str(path),
            mime_type=mime_type,
            original_filename=filename,
            file_size=len(content),
            **exif_meta,
        )
        bundle.items.append(item)
        return item
