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
import re

from billion_hackathon.contracts.collected import CollectedBundle, CollectedItem
from billion_hackathon.contracts.evidence import EvidenceBundle, EvidenceItem
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

    def _process_item(self, item: CollectedItem) -> list[EvidenceItem]:
        if item.kind == "note" and item.text:
            return [_ingest_note(item)]
        if item.kind == "image":
            return self._image.ingest(item)
        if item.kind == "file":
            return self._document.ingest(item)
        return []

    async def aingest(self, bundle: CollectedBundle) -> EvidenceBundle:
        """Ingest all items concurrently — each blocking LLM call runs in a thread."""
        stub = scenario_stub_evidence_if_applicable(bundle)
        if stub is not None:
            return _postprocess_evidence(merge_orphan_payer_with_group_slot(stub))
        tasks = [asyncio.to_thread(self._process_item, item) for item in bundle.items]
        results = await asyncio.gather(*tasks)
        out = [ev for items in results for ev in items]
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
        out: list[EvidenceItem] = []
        for item in bundle.items:
            out.extend(self._process_item(item))
        return _postprocess_evidence(
            merge_orphan_payer_with_group_slot(
                EvidenceBundle(event_id=bundle.event_id, items=out)
            )
        )
