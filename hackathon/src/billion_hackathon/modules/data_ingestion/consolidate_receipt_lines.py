"""Collapse many receipt_line items from a single check image into one line for the table total.

When vision emits one `receipt_line` per dish, rules aggregation creates one good per line and the
graph fragments. We keep a single line whose amount is the `spend_hint` total and align `good_id`
with the transaction so one shared expense connects all participants.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from billion_hackathon.contracts.evidence import EvidenceBundle, EvidenceItem

log = logging.getLogger("billion.ingest")

# Collapse when 3+ receipt lines come from the same source image
_MIN_LINE_EXPLOSION = 3


def _dominant_spend(bundle: EvidenceBundle) -> tuple[int | None, EvidenceItem | None, str | None]:
    best_ev: EvidenceItem | None = None
    best_amount = 0
    for ev in bundle.items:
        if ev.kind != "spend_hint" or not ev.amount_cents:
            continue
        cand = ev.amount_cents
        for row in (ev.extra or {}).get("amount_candidates") or []:
            try:
                if float(row.get("confidence", 0.0)) >= 0.8:
                    cand = max(cand, int(row.get("amount_cents") or 0))
            except Exception:
                continue
        if best_ev is None or cand > best_amount:
            best_ev = ev
            best_amount = cand
    if not best_ev:
        return None, None, None
    gid = (best_ev.extra or {}).get("good_id")
    return best_amount, best_ev, str(gid) if gid else None


def _context_total_cents(ctx: dict[str, Any] | None) -> int | None:
    if not ctx:
        return None
    t = ctx.get("total_amount_cents")
    if t is None:
        return None
    return int(t)


def _align_keeper_to_spend(keeper: EvidenceItem, spend: EvidenceItem, good_id: str | None) -> EvidenceItem:
    ex = {**(keeper.extra or {})}
    if good_id:
        ex["good_id"] = good_id
    parts = [x for x in (spend.participant_person_ids or []) if x]
    parts = list(dict.fromkeys(parts))
    return keeper.model_copy(
        update={
            "amount_cents": spend.amount_cents or keeper.amount_cents,
            "payer_person_id": spend.payer_person_id or keeper.payer_person_id,
            "participant_person_ids": parts or keeper.participant_person_ids,
            "label": spend.label or keeper.label,
            "extra": ex,
        }
    )


def consolidate_receipt_lines_for_group_bill(bundle: EvidenceBundle) -> EvidenceBundle:
    T, spend_ev, spend_good = _dominant_spend(bundle)
    if T is None or T < 1 or spend_ev is None:
        return bundle

    by_source: dict[str, list[EvidenceItem]] = {}
    for ev in bundle.items:
        if ev.kind != "receipt_line":
            continue
        sid = (ev.source_item_ids or [None])[0]
        if not sid:
            continue
        by_source.setdefault(sid, []).append(ev)

    remove_ids: set[str] = set()
    new_items: list[EvidenceItem] = []
    replacements: dict[str, EvidenceItem] = {}

    for sid, lines in by_source.items():
        if len(lines) < _MIN_LINE_EXPLOSION:
            continue

        match_t = [e for e in lines if e.amount_cents == T]
        ctx_t = [e for e in lines if _context_total_cents((e.extra or {}).get("context") or {}) == T]

        if match_t:
            keeper = _align_keeper_to_spend(match_t[0], spend_ev, spend_good)
            replacements[keeper.id] = keeper
        elif ctx_t:
            keeper = _align_keeper_to_spend(ctx_t[0], spend_ev, spend_good)
            replacements[keeper.id] = keeper
        else:
            tplt = lines[0]
            ex: dict[str, Any] = {**(tplt.extra or {})}
            ex["good_id"] = spend_good or ex.get("good_id") or "group_dining_total"
            ex["notes"] = (str(ex.get("notes") or "")) + " [consolidated: one total for group split]"

            parts = [x for x in (spend_ev.participant_person_ids or []) if x]
            parts = list(dict.fromkeys(parts))

            keeper = EvidenceItem(
                id=f"ev-consolidated-{uuid.uuid4().hex[:10]}",
                source_item_ids=[sid],
                kind="receipt_line",
                amount_cents=T,
                currency=spend_ev.currency or tplt.currency or "EUR",
                label=spend_ev.label or "Group bill (total)",
                payer_person_id=spend_ev.payer_person_id,
                participant_person_ids=parts,
                confidence=max((e.confidence for e in lines), default=0.75),
                raw_excerpt="One receipt check total (consolidated from per-line model output).",
                extra=ex,
            )
            new_items.append(keeper)
            for e in lines:
                remove_ids.add(e.id)
            log.info(
                "consolidate_receipt: %d line items (source=%s) -> 1 x %d (synthetic)",
                len(lines),
                sid,
                T,
            )
            continue

        for e in lines:
            if e.id != keeper.id:
                remove_ids.add(e.id)
        log.info(
            "consolidate_receipt: %d line items (source=%s) -> 1 (matched total %d)",
            len(lines),
            sid,
            T,
        )

    if not remove_ids and not new_items and not replacements:
        return bundle

    out_items: list[EvidenceItem] = []
    for e in bundle.items:
        if e.id in remove_ids:
            continue
        if e.id in replacements:
            out_items.append(replacements[e.id])
        else:
            out_items.append(e)
    out_items.extend(new_items)
    return bundle.model_copy(update={"items": out_items})
