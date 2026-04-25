"""Ingest text-file CollectedItems → EvidenceItems.

Reads the file content and sends it to the LLM for structured extraction.
Binary formats (PDF, DOCX, …) are noted as stubs — full extraction requires
a dedicated parser that can be wired in later without changing the interface.

When the LLM client is the stub, falls back to a simple regex pass so the
pipeline keeps running.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("billion.ingest")

from billion_hackathon.contracts.collected import CollectedItem
from billion_hackathon.contracts.evidence import EvidenceItem
from billion_hackathon.modules.data_ingestion.prompts import DOCUMENT_SYSTEM, DOCUMENT_USER_TMPL
from billion_hackathon.modules.llm.client import ChatMessage, LLMClient

_TEXT_MIME_PREFIXES = (
    "text/",
    "application/json",
    "application/xml",
    "application/csv",
    "application/x-ndjson",
)

_MAX_CONTENT_CHARS = 8_000  # truncate before sending to LLM

_VALID_KINDS = frozenset({"spend_hint", "receipt_line", "p2p_hint", "presence_hint", "free_text"})

# Simple expense line pattern — same grammar as note ingestor
_NOTE_EXPENSE = re.compile(
    r"EXPENSE:\s*(?P<cents>\d+)\s*cents\s+for\s+(?P<label>[\w\s-]+?)"
    r"(?:\s+payer=(?P<payer>\w+))?"
    r"(?:\s+participants=(?P<parts>[\w,]+))?(?:\s*$|\n)",
    re.IGNORECASE | re.MULTILINE,
)


class DocumentIngestor:
    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def ingest(
        self, item: CollectedItem, *, event_context: dict[str, Any] | None = None
    ) -> list[EvidenceItem]:
        """Return ≥1 EvidenceItems for one file CollectedItem."""
        if not item.stored_path:
            return [_fallback(item, "no stored_path")]

        path = Path(item.stored_path)
        if not path.exists():
            return [_fallback(item, "file not found on disk")]

        mime = item.mime_type or ""
        if not _is_text(mime):
            # Binary file — no text extraction yet
            return [
                EvidenceItem(
                    id=f"ev-{item.id}",
                    source_item_ids=[item.id],
                    kind="free_text",
                    confidence=0.0,
                    raw_excerpt=f"[doc-ingestor] binary document: {item.original_filename or item.id}",
                    extra={
                        "stub": True,
                        "mime_type": mime,
                        "reason": "binary extraction not yet implemented",
                    },
                )
            ]

        content = _read_text(path)
        if not content:
            return [_fallback(item, "could not read file content")]

        log.info("doc    %s  (%s  %d chars)", item.original_filename or item.id, mime, len(content))

        messages = [
            ChatMessage(role="system", content=DOCUMENT_SYSTEM),
            ChatMessage(
                role="user",
                content=DOCUMENT_USER_TMPL.format(
                    filename=item.original_filename or path.name,
                    event_context=_event_context_text(event_context),
                    content=content[:_MAX_CONTENT_CHARS],
                ),
            ),
        ]

        response = self._client.complete(messages, max_tokens=2048)

        if response.model == "stub":
            log.info("   → stub (no LLM key)")
            return _stub_from_text(item, content)

        items = _parse(item, response.text)
        log.info("   → %d evidence item(s) from LLM", len(items))
        return items
def _event_context_text(event_context: dict[str, Any] | None) -> str:
    if not event_context:
        return "none"
    return (
        f"candidate_payers={event_context.get('candidate_payers') or []}; "
        f"candidate_venue={event_context.get('candidate_venue')}; "
        f"candidate_datetime={event_context.get('candidate_datetime')}; "
        f"candidate_total_cents={event_context.get('candidate_total_cents')}; "
        f"expected_group_size={event_context.get('expected_group_size')}"
    )




# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_text(mime: str) -> bool:
    return any(mime.startswith(p) for p in _TEXT_MIME_PREFIXES)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _stub_from_text(item: CollectedItem, content: str) -> list[EvidenceItem]:
    """Try structured EXPENSE: lines first; fall back to free_text."""
    results: list[EvidenceItem] = []

    for i, m in enumerate(_NOTE_EXPENSE.finditer(content)):
        parts_raw = m.group("parts") or ""
        participants = [p.strip() for p in parts_raw.split(",") if p.strip()]
        payer = m.group("payer")
        if payer and payer not in participants:
            participants.append(payer)
        results.append(
            EvidenceItem(
                id=f"ev-{item.id}-{i}",
                source_item_ids=[item.id],
                kind="spend_hint",
                amount_cents=int(m.group("cents")),
                label=m.group("label").strip(),
                payer_person_id=payer,
                participant_person_ids=participants,
                confidence=0.7,
                raw_excerpt=m.group(0).strip(),
                extra={"stub": True},
            )
        )

    if results:
        return results

    return [
        EvidenceItem(
            id=f"ev-{item.id}",
            source_item_ids=[item.id],
            kind="free_text",
            confidence=0.1,
            raw_excerpt=content[:300],
            extra={"stub": True, "mime_type": item.mime_type},
        )
    ]


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
    doc_type = str(data.get("document_type", "unknown"))
    # Top-level arrays shared across all items from this document
    context: dict = data.get("context") or {}
    persons: list[dict] = data.get("persons") or []
    goods: list[dict] = data.get("goods") or []
    llm_items: list[dict] = data.get("items") or []
    person_ids = {str(p.get("person_id")) for p in persons if p.get("person_id")}
    good_ids = {str(g.get("good_id")) for g in goods if g.get("good_id")}

    shared_extra = {
        "document_type": doc_type,
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
                raw_excerpt=raw_desc or f"document analyzed: {doc_type}",
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
                    "extraction_mode": "raw_text_llm",
                    "source_quality": {},
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
        out.append({"amount_cents": int(t), "confidence": 0.9, "source": "context_total"})
    for it in llm_items:
        if it.get("amount_cents") is None:
            continue
        out.append(
            {
                "amount_cents": int(it["amount_cents"]),
                "confidence": float(it.get("confidence", 0.5)),
                "source": f"item:{it.get('kind', 'unknown')}",
            }
        )
    out.sort(key=lambda x: x["confidence"], reverse=True)
    seen: set[int] = set()
    uniq: list[dict[str, Any]] = []
    for row in out:
        cents = int(row["amount_cents"])
        if cents in seen:
            continue
        seen.add(cents)
        uniq.append(row)
        if len(uniq) >= 5:
            break
    return uniq


def _person_aliases(persons: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for p in persons:
        pid = str(p.get("person_id") or "").strip()
        disp = str(p.get("display_name") or "").strip()
        if not pid or not disp:
            continue
        aliases = [disp]
        tokens = [x for x in re.split(r"\s+", disp) if x]
        if len(tokens) >= 2:
            aliases.append(tokens[-1])
            aliases.append(f"{tokens[0][0]}. {tokens[-1]}")
        out[pid] = list(dict.fromkeys(aliases))
    return out


def _fallback(item: CollectedItem, reason: str) -> EvidenceItem:
    return EvidenceItem(
        id=f"ev-{item.id}",
        source_item_ids=[item.id],
        kind="free_text",
        confidence=0.0,
        raw_excerpt=f"[doc-ingestor] {reason}",
        extra={"stub": True},
    )
