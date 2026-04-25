"""Ingest image CollectedItems → EvidenceItems.

Sends the image to the LLM via the vision API and maps the JSON response to
EvidenceItems.  When the LLM client is the stub (no API key), falls back to
EXIF-based placeholder evidence so the pipeline keeps running.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("billion.ingest")

from billion_hackathon.contracts.collected import CollectedItem
from billion_hackathon.contracts.evidence import EvidenceItem
from billion_hackathon.modules.data_ingestion.image_ocr import (
    classify_image_hint,
    extract_ocr_text,
)
from billion_hackathon.modules.data_ingestion.image_preprocess import preprocess_image_bytes
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

    def ingest(
        self, item: CollectedItem, *, event_context: dict[str, Any] | None = None
    ) -> list[EvidenceItem]:
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
        if len(raw) > _MAX_IMAGE_BYTES * 2:
            return [_fallback(item, f"image too large ({len(raw)} bytes, max {_MAX_IMAGE_BYTES * 2})")]

        context = _exif_context(item)
        t0 = time.perf_counter()
        processed, processed_mime, preprocess_diag = preprocess_image_bytes(
            raw, mime_type=mime, original_filename=item.original_filename
        )
        t_pre = int((time.perf_counter() - t0) * 1000)
        if len(processed) > _MAX_IMAGE_BYTES:
            return [_fallback(item, f"processed image too large ({len(processed)} bytes, max {_MAX_IMAGE_BYTES})")]
        t1 = time.perf_counter()
        ocr_text, ocr_meta = extract_ocr_text(processed)
        t_ocr = int((time.perf_counter() - t1) * 1000)
        image_hint = classify_image_hint(item.original_filename, ocr_text)
        preprocess_summary = _preprocess_summary(preprocess_diag, ocr_meta, image_hint)
        b64 = base64.standard_b64encode(processed).decode()
        event_summary = _event_context_text(event_context)
        log.info(
            "preprocess %s: pre=%dms ocr=%dms hint=%s ocr_engine=%s chars=%s",
            item.original_filename or item.id,
            t_pre,
            t_ocr,
            image_hint or "n/a",
            (ocr_meta or {}).get("engine", "none"),
            (ocr_meta or {}).get("chars", 0),
        )

        log.info("image  %s  (%d B)  exif_ts=%s  gps=%s",
                 item.original_filename or item.id,
                 len(raw),
                 item.exif_timestamp.isoformat() if item.exif_timestamp else "—",
                 f"{item.gps_lat:.4f},{item.gps_lon:.4f}" if item.gps_lat is not None else "—")

        messages = [
            ChatMessage(role="system", content=IMAGE_SYSTEM),
            ChatMessage(
                role="user",
                content=[
                    TextPart(
                        text=IMAGE_USER_TMPL.format(
                            context=context,
                            event_context=event_summary,
                            ocr_text=(ocr_text[:1800] if ocr_text else "<none>"),
                            preprocess_summary=preprocess_summary,
                        )
                    ),
                    ImagePart(data=b64, media_type=processed_mime),
                ],
            ),
        ]

        response = self._client.complete(messages, max_tokens=4096)

        if response.model == "stub":
            log.info("   → stub (no LLM key)")
            return [_stub_from_exif(item)]

        items = _parse(
            item,
            response.text,
            preprocess_diag=preprocess_diag,
            ocr_text=ocr_text,
            ocr_meta=ocr_meta,
            image_class_hint=image_hint,
        )
        log.info("   → %d evidence item(s) from LLM", len(items))
        return items


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


def _event_context_text(event_context: dict[str, Any] | None) -> str:
    if not event_context:
        return "Known event context: none."
    return (
        "Known event context from other files:\n"
        f"- candidate_payers: {event_context.get('candidate_payers') or []}\n"
        f"- candidate_venue: {event_context.get('candidate_venue')}\n"
        f"- candidate_datetime: {event_context.get('candidate_datetime')}\n"
        f"- candidate_total_cents: {event_context.get('candidate_total_cents')}\n"
        f"- expected_group_size: {event_context.get('expected_group_size')}\n"
    )


def _preprocess_summary(
    preprocess_diag: dict[str, Any], ocr_meta: dict[str, Any], image_hint: str | None
) -> str:
    src_q = (preprocess_diag or {}).get("source_quality") or {}
    return (
        f"applied={((preprocess_diag or {}).get('applied') or [])}; "
        f"segmentation={((preprocess_diag or {}).get('segmentation') or {})}; "
        f"quality={src_q}; "
        f"ocr_meta={ocr_meta or {}}; "
        f"image_type_hint_local={image_hint or 'n/a'}"
    )


def _parse(
    item: CollectedItem,
    text: str,
    *,
    preprocess_diag: dict[str, Any] | None = None,
    ocr_text: str = "",
    ocr_meta: dict[str, Any] | None = None,
    image_class_hint: str | None = None,
) -> list[EvidenceItem]:
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
    person_ids = {str(p.get("person_id")) for p in persons if p.get("person_id")}
    good_ids = {str(g.get("good_id")) for g in goods if g.get("good_id")}

    # Shared extra attached to every item so aggregator has full picture per item
    shared_extra = {
        "image_type": image_type,
        "image_type_hint_local": image_class_hint,
        "context": context,
        "persons": persons,
        "goods": goods,
        "preprocess": preprocess_diag or {},
        "ocr_text": ocr_text[:2000] if ocr_text else "",
        "ocr_meta": ocr_meta or {},
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
        participants = [str(p) for p in participants if str(p) in person_ids]
        payer = li.get("payer_person_id")
        payer = str(payer) if payer and str(payer) in person_ids else None
        good_id = li.get("good_id")
        good_id = str(good_id) if good_id and str(good_id) in good_ids else None
        conf = float(li.get("confidence", overall_conf))
        needs_review = conf < 0.45

        result.append(
            EvidenceItem(
                id=f"ev-{item.id}-{i}",
                source_item_ids=[item.id],
                kind=kind,
                amount_cents=amount,
                currency=li.get("currency") or "EUR",
                label=li.get("label"),
                payer_person_id=payer,
                participant_person_ids=participants,
                confidence=conf,
                raw_excerpt=raw_desc,
                extra={
                    **shared_extra,
                    "good_id": good_id,
                    "notes": li.get("notes", ""),
                    "extraction_mode": "ocr_assisted" if ocr_text else "raw_vision",
                    "source_quality": (preprocess_diag or {}).get("source_quality", {}),
                    "amount_candidates": _amount_candidates(context, llm_items),
                    "person_aliases": _person_aliases(persons),
                    "needs_review": needs_review,
                },
            )
        )
    return result


def _amount_candidates(context: dict[str, Any], llm_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    t = context.get("total_amount_cents")
    if t is not None:
        out.append({"amount_cents": int(t), "confidence": 0.95, "source": "context_total"})
    for it in llm_items:
        a = it.get("amount_cents")
        if a is None:
            continue
        out.append(
            {
                "amount_cents": int(a),
                "confidence": float(it.get("confidence", 0.5)),
                "source": f"item:{it.get('kind', 'unknown')}",
            }
        )
    # Keep top unique by amount.
    seen: set[int] = set()
    uniq: list[dict[str, Any]] = []
    for row in sorted(out, key=lambda x: x["confidence"], reverse=True):
        cents = int(row["amount_cents"])
        if cents in seen:
            continue
        seen.add(cents)
        uniq.append(row)
        if len(uniq) >= 5:
            break
    return uniq


def _person_aliases(persons: list[dict[str, Any]]) -> dict[str, list[str]]:
    alias_map: dict[str, list[str]] = {}
    for p in persons:
        pid = str(p.get("person_id") or "").strip()
        disp = str(p.get("display_name") or "").strip()
        if not pid or not disp:
            continue
        bits = [disp]
        tokens = [t for t in re.split(r"\s+", disp) if t]
        if len(tokens) >= 2:
            bits.append(tokens[-1])
            bits.append(f"{tokens[0][0]}. {tokens[-1]}")
        alias_map[pid] = list(dict.fromkeys(bits))
    return alias_map


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
