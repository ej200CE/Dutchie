"""Turn CollectedBundle into EvidenceBundle. Replace stub with LLM client later."""

from __future__ import annotations

import re

from billion_hackathon.contracts.collected import CollectedBundle
from billion_hackathon.contracts.evidence import EvidenceBundle, EvidenceItem


_NOTE_EXPENSE = re.compile(
    r"^EXPENSE:\s*(?P<cents>\d+)\s*cents\s+for\s+(?P<label>[\w\s-]+?)"
    r"(?:\s+payer=(?P<payer>\w+))?"
    r"(?:\s+participants=(?P<parts>[\w,]+))?\s*$",
    re.IGNORECASE,
)


class DataIngestionService:
    """Deterministic stub: parses structured lines from notes; images become low-confidence hints."""

    def ingest(self, bundle: CollectedBundle) -> EvidenceBundle:
        out: list[EvidenceItem] = []
        for item in bundle.items:
            if item.kind == "note" and item.text:
                m = _NOTE_EXPENSE.match(item.text.strip())
                if m:
                    parts_raw = m.group("parts") or ""
                    participants = [p.strip() for p in parts_raw.split(",") if p.strip()]
                    payer = m.group("payer")
                    if payer and payer not in participants:
                        participants.append(payer)
                    out.append(
                        EvidenceItem(
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
                    )
                else:
                    out.append(
                        EvidenceItem(
                            id=f"ev-{item.id}",
                            source_item_ids=[item.id],
                            kind="free_text",
                            confidence=0.2,
                            raw_excerpt=(item.text or "")[:500],
                        )
                    )
            elif item.kind in ("image", "file"):
                out.append(
                    EvidenceItem(
                        id=f"ev-{item.id}",
                        source_item_ids=[item.id],
                        kind="receipt_line",
                        confidence=0.15,
                        raw_excerpt=f"uploaded:{item.stored_path}",
                        extra={"mime_type": item.mime_type},
                    )
                )
        return EvidenceBundle(event_id=bundle.event_id, items=out)
