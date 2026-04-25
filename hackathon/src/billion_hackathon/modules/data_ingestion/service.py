"""Turn CollectedBundle into EvidenceBundle.

Routing:
  note  → rule-based parser (fast, reliable, no LLM needed)
  image → ImageIngestor  (LLM vision or EXIF stub)
  file  → DocumentIngestor (LLM text or regex stub)

The LLM client is created once and shared across ingestors.
`aingest` fires all LLM calls concurrently via asyncio; `ingest` is a
sequential sync wrapper kept for tests and scripts.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from billion_hackathon.contracts.collected import CollectedBundle, CollectedItem
from billion_hackathon.contracts.evidence import EvidenceBundle, EvidenceItem
from billion_hackathon.modules.data_ingestion.audio_ingestor import AudioIngestor
from billion_hackathon.modules.data_ingestion.document_ingestor import DocumentIngestor
from billion_hackathon.modules.data_ingestion.image_ingestor import ImageIngestor
from billion_hackathon.modules.data_ingestion.consolidate_receipt_lines import (
    consolidate_receipt_lines_for_group_bill,
)
from billion_hackathon.modules.data_ingestion.merge_orphan_payer_with_group import (
    drop_inferred_photographer_if_group_full,
    merge_orphan_payer_with_group_slot,
)
from billion_hackathon.modules.data_ingestion.stub_scenario_evidence import (
    scenario_stub_evidence_if_applicable,
)
from billion_hackathon.modules.llm.client import get_llm_client

log = logging.getLogger("billion.ingest")

def _postprocess_evidence(b: EvidenceBundle) -> EvidenceBundle:
    b = drop_inferred_photographer_if_group_full(b)
    return consolidate_receipt_lines_for_group_bill(b)


_NOTE_EXPENSE = re.compile(
    r"^EXPENSE:\s*(?P<cents>\d+)\s*cents\s+for\s+(?P<label>[\w\s-]+?)"
    r"(?:\s+payer=(?P<payer>\w+))?"
    r"(?:\s+participants=(?P<parts>[\w,]+))?\s*$",
    re.IGNORECASE,
)


def _ingest_note(item: CollectedItem) -> EvidenceItem:
    m = _NOTE_EXPENSE.match((item.text or "").strip())
    if m:
        parts_raw = m.group("parts") or ""
        participants = [p.strip() for p in parts_raw.split(",") if p.strip()]
        payer = m.group("payer")
        if payer and payer not in participants:
            participants.append(payer)
        return EvidenceItem(
            id=f"ev-{item.id}",
            source_item_ids=[item.id],
            kind="spend_hint",
            amount_cents=int(m.group("cents")),
            label=m.group("label").strip(),
            payer_person_id=payer,
            participant_person_ids=participants or [],
            confidence=0.85,
            raw_excerpt=item.text[:200],
        )
    return EvidenceItem(
        id=f"ev-{item.id}",
        source_item_ids=[item.id],
        kind="free_text",
        confidence=0.2,
        raw_excerpt=(item.text or "")[:500],
    )


class DataIngestionService:
    """Routes each CollectedItem to the right ingestor."""

    def __init__(self) -> None:
        client = get_llm_client()
        self._image = ImageIngestor(client)
        self._document = DocumentIngestor(client)
        self._audio = AudioIngestor(client)

    def _process_item(
        self, item: CollectedItem, *, event_context: dict[str, Any] | None = None
    ) -> list[EvidenceItem]:
        if item.kind == "note" and item.text:
            return [_ingest_note(item)]
        if item.kind == "image":
            return self._image.ingest(item, event_context=event_context)
        if item.kind == "audio":
            return self._audio.ingest(item, event_context=event_context)
        if item.kind == "file":
            return self._document.ingest(item, event_context=event_context)
        return []

    @staticmethod
    def _bucket(item: CollectedItem) -> str:
        n = (item.original_filename or "").lower()
        if item.kind == "note":
            return "primary"
        if item.kind == "audio":
            return "secondary"
        if item.kind != "image":
            return "secondary"
        if any(k in n for k in ("transaction", "bank", "payment", "tikkie", "bunq", "screenshot")):
            return "primary"
        if any(k in n for k in ("receipt", "bill", "invoice")):
            return "primary"
        return "secondary"

    @staticmethod
    def _build_event_context(items: list[EvidenceItem]) -> dict[str, Any]:
        payers: list[str] = []
        venue = None
        dt = None
        total = None
        group_size = 0
        for ev in items:
            if ev.payer_person_id:
                payers.append(ev.payer_person_id)
            if ev.participant_person_ids:
                group_size = max(group_size, len(set(ev.participant_person_ids)))
            ex = ev.extra or {}
            ctx = ex.get("context") or {}
            if venue is None and ctx.get("venue"):
                venue = ctx.get("venue")
            if dt is None and ctx.get("datetime_visible"):
                dt = ctx.get("datetime_visible")
            if ctx.get("total_amount_cents"):
                c = int(ctx.get("total_amount_cents"))
                total = c if total is None else max(total, c)
            for p in ex.get("persons") or []:
                pid = p.get("person_id")
                if pid:
                    payers.append(str(pid))
        return {
            "candidate_payers": list(dict.fromkeys([p for p in payers if p]))[:6],
            "candidate_venue": venue,
            "candidate_datetime": dt,
            "candidate_total_cents": total,
            "expected_group_size": group_size or None,
        }

    async def _aingest_two_pass(self, bundle: CollectedBundle) -> list[EvidenceItem]:
        primary = [it for it in bundle.items if self._bucket(it) == "primary"]
        secondary = [it for it in bundle.items if self._bucket(it) != "primary"]

        primary_tasks = [asyncio.to_thread(self._process_item, item, event_context=None) for item in primary]
        primary_results = await asyncio.gather(*primary_tasks) if primary_tasks else []
        first_items = [ev for batch in primary_results for ev in batch]
        event_ctx = self._build_event_context(first_items)
        log.info("ingest context summary: %s", event_ctx)

        secondary_tasks = [
            asyncio.to_thread(self._process_item, item, event_context=event_ctx) for item in secondary
        ]
        secondary_results = await asyncio.gather(*secondary_tasks) if secondary_tasks else []
        second_items = [ev for batch in secondary_results for ev in batch]
        return [*first_items, *second_items]

    def _ingest_two_pass(self, bundle: CollectedBundle) -> list[EvidenceItem]:
        primary = [it for it in bundle.items if self._bucket(it) == "primary"]
        secondary = [it for it in bundle.items if self._bucket(it) != "primary"]
        first_items: list[EvidenceItem] = []
        for item in primary:
            first_items.extend(self._process_item(item))
        event_ctx = self._build_event_context(first_items)
        log.info("ingest context summary: %s", event_ctx)
        second_items: list[EvidenceItem] = []
        for item in secondary:
            second_items.extend(self._process_item(item, event_context=event_ctx))
        return [*first_items, *second_items]

    async def aingest(self, bundle: CollectedBundle) -> EvidenceBundle:
        """Ingest all items concurrently — each blocking LLM call runs in a thread."""
        stub = scenario_stub_evidence_if_applicable(bundle)
        if stub is not None:
            return _postprocess_evidence(merge_orphan_payer_with_group_slot(stub))
        out = await self._aingest_two_pass(bundle)
        return _postprocess_evidence(
            merge_orphan_payer_with_group_slot(
                EvidenceBundle(event_id=bundle.event_id, items=out)
            )
        )

    def ingest(self, bundle: CollectedBundle) -> EvidenceBundle:
        """Sequential sync path — used by tests and scripts."""
        stub = scenario_stub_evidence_if_applicable(bundle)
        if stub is not None:
            return _postprocess_evidence(merge_orphan_payer_with_group_slot(stub))
        out = self._ingest_two_pass(bundle)
        return _postprocess_evidence(
            merge_orphan_payer_with_group_slot(
                EvidenceBundle(event_id=bundle.event_id, items=out)
            )
        )
