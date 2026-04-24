"""Ingest image CollectedItems → EvidenceItems.

Sends the image to the LLM via the vision API and maps the JSON response to
EvidenceItems.  When the LLM client is the stub (no API key), falls back to
EXIF-based placeholder evidence so the pipeline keeps running.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from billion_hackathon.contracts.collected import CollectedItem
from billion_hackathon.contracts.evidence import EvidenceItem
from billion_hackathon.modules.data_ingestion.prompts import IMAGE_SYSTEM, IMAGE_USER_TMPL
from billion_hackathon.modules.llm.client import ChatMessage, ImagePart, LLMClient, TextPart

# Models differ on their per-image size limits; 4 MB raw → ~5.3 MB base64 is safe for both
# OpenAI (20 MB limit) and Anthropic (5 MB base64 limit).
_MAX_IMAGE_BYTES = 4 * 1024 * 1024

_SUPPORTED_MIME = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})

_VALID_KINDS = frozenset({"spend_hint", "receipt_line", "p2p_hint", "presence_hint", "free_text"})


class ImageIngestor:
    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def ingest(self, item: CollectedItem) -> list[EvidenceItem]:
        """Return ≥1 EvidenceItems for one image CollectedItem."""
        if not item.stored_path:
            return [_fallback(item, "no stored_path")]

        path = Path(item.stored_path)
        if not path.exists():
            return [_fallback(item, "file not found on disk")]

        mime = item.mime_type or "image/jpeg"
        if mime not in _SUPPORTED_MIME:
            return [_fallback(item, f"unsupported mime type: {mime}")]

        raw = path.read_bytes()
        if len(raw) > _MAX_IMAGE_BYTES:
            return [_fallback(item, f"image too large ({len(raw)} bytes, max {_MAX_IMAGE_BYTES})")]

        context = _exif_context(item)
        b64 = base64.standard_b64encode(raw).decode()

        messages = [
            ChatMessage(role="system", content=IMAGE_SYSTEM),
            ChatMessage(
                role="user",
                content=[
                    TextPart(text=IMAGE_USER_TMPL.format(context=context)),
                    ImagePart(data=b64, media_type=mime),
                ],
            ),
        ]

        response = self._client.complete(messages, max_tokens=2048)

        if response.model == "stub":
            return [_stub_from_exif(item)]

        return _parse(item, response.text)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _exif_context(item: CollectedItem) -> str:
    parts: list[str] = []
    if item.original_filename:
        parts.append(f"filename={item.original_filename}")
    if item.exif_timestamp:
        parts.append(f"taken={item.exif_timestamp.isoformat()}")
    if item.gps_lat is not None and item.gps_lon is not None:
        parts.append(f"gps={item.gps_lat:.6f},{item.gps_lon:.6f}")
    if item.file_size:
        parts.append(f"size={item.file_size}B")
    return "; ".join(parts) if parts else "no metadata available"


def _parse(item: CollectedItem, text: str) -> list[EvidenceItem]:
    """Parse LLM JSON response into EvidenceItems."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return [_fallback(item, f"LLM returned non-JSON: {text[:200]}")]
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return [_fallback(item, f"Could not extract JSON: {text[:200]}")]

    overall_conf = float(data.get("overall_confidence", 0.5))
    raw_desc = str(data.get("raw_description", ""))
    image_type = str(data.get("image_type", "unknown"))
    # Top-level arrays shared across all items from this image
    context: dict = data.get("context") or {}
    persons: list[dict] = data.get("persons") or []
    goods: list[dict] = data.get("goods") or []
    llm_items: list[dict] = data.get("items") or []

    # Shared extra attached to every item so aggregator has full picture per item
    shared_extra = {
        "image_type": image_type,
        "context": context,
        "persons": persons,
        "goods": goods,
    }

    if not llm_items:
        return [
            EvidenceItem(
                id=f"ev-{item.id}",
                source_item_ids=[item.id],
                kind="free_text",
                confidence=overall_conf,
                raw_excerpt=raw_desc or f"image analyzed: {image_type}",
                extra=shared_extra,
            )
        ]

    result: list[EvidenceItem] = []
    for i, li in enumerate(llm_items):
        kind = li.get("kind", "free_text")
        if kind not in _VALID_KINDS:
            kind = "free_text"

        amount_raw = li.get("amount_cents")
        amount = int(amount_raw) if amount_raw is not None else None

        participants = li.get("participant_person_ids") or []
        if not isinstance(participants, list):
            participants = []

        result.append(
            EvidenceItem(
                id=f"ev-{item.id}-{i}",
                source_item_ids=[item.id],
                kind=kind,
                amount_cents=amount,
                currency=li.get("currency") or "EUR",
                label=li.get("label"),
                payer_person_id=li.get("payer_person_id"),
                participant_person_ids=participants,
                confidence=float(li.get("confidence", overall_conf)),
                raw_excerpt=raw_desc,
                extra={
                    **shared_extra,
                    "good_id": li.get("good_id"),
                    "notes": li.get("notes", ""),
                },
            )
        )
    return result


def _stub_from_exif(item: CollectedItem) -> EvidenceItem:
    """Placeholder built from EXIF metadata only — no LLM."""
    parts = [f"image: {item.original_filename or item.id}"]
    if item.exif_timestamp:
        parts.append(f"taken={item.exif_timestamp.date()}")
    if item.gps_lat is not None:
        parts.append(f"gps=({item.gps_lat:.4f},{item.gps_lon:.4f})")

    return EvidenceItem(
        id=f"ev-{item.id}",
        source_item_ids=[item.id],
        kind="presence_hint",
        confidence=0.1,
        raw_excerpt=" · ".join(parts),
        extra={"stub": True, "mime_type": item.mime_type, "file_size": item.file_size},
    )


def _fallback(item: CollectedItem, reason: str) -> EvidenceItem:
    return EvidenceItem(
        id=f"ev-{item.id}",
        source_item_ids=[item.id],
        kind="free_text",
        confidence=0.0,
        raw_excerpt=f"[image-ingestor] {reason}",
        extra={"stub": True},
    )
