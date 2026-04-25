"""When vision puts the payer (e.g. e_evans) only on receipt/tx and uses group_pos_1..N in
people_photos for the N people, remap the payer to group_pos_1 to avoid an (N+1)th person node.
"""

from __future__ import annotations

import re
import logging
from billion_hackathon.contracts.evidence import EvidenceBundle, EvidenceItem

log = logging.getLogger("billion.ingest")

_GROUP = re.compile(r"^group_pos_(\d+)$")


def _person_ids_in_people_photos(bundle: EvidenceBundle) -> set[str]:
    s: set[str] = set()
    for ev in bundle.items:
        if (ev.extra or {}).get("image_type") != "people_photo":
            continue
        for p in (ev.extra or {}).get("persons") or []:
            if p.get("person_id"):
                s.add(str(p["person_id"]))
    return s


def _group_slots(people: set[str]) -> list[str]:
    slots: list[tuple[int, str]] = []
    for p in people:
        m = _GROUP.match(p)
        if m:
            slots.append((int(m.group(1)), p))
    slots.sort(key=lambda t: t[0])
    return [t[1] for t in slots]


def _payer_ids_on_money_items(bundle: EvidenceBundle) -> set[str]:
    pay: set[str] = set()
    for ev in bundle.items:
        if ev.kind in ("receipt_line", "spend_hint", "p2p_hint") and ev.payer_person_id:
            pay.add(str(ev.payer_person_id))
    return pay


def _payer_display_from_extra(bundle: EvidenceBundle, pid: str) -> str | None:
    for ev in bundle.items:
        for p in (ev.extra or {}).get("persons") or []:
            if p.get("person_id") == pid and p.get("display_name"):
                return str(p["display_name"])
    return None


def merge_orphan_payer_with_group_slot(bundle: EvidenceBundle) -> EvidenceBundle:
    """Map lone payer id → first group_pos_k when that payer never appears in people_photos."""
    in_people = _person_ids_in_people_photos(bundle)
    slots = _group_slots(in_people)
    if not slots or len(slots) < 2:
        return bundle
    pay = _payer_ids_on_money_items(bundle)
    orphans = pay - in_people
    if len(orphans) != 1:
        return bundle
    orphan = next(iter(orphans))
    if _GROUP.match(orphan) or orphan in in_people:
        return bundle
    target = slots[0]
    donor_name = _payer_display_from_extra(bundle, orphan) or _payer_display_from_extra(
        bundle, target
    )

    def m(x: str | None) -> str | None:
        if x is None:
            return None
        return target if str(x) == orphan else str(x)

    new_items: list[EvidenceItem] = []
    for ev in bundle.items:
        ex = {**(ev.extra or {})}
        ppl2: list[dict] = []
        for p in ex.get("persons") or []:
            row = {**p}
            if row.get("person_id"):
                row["person_id"] = m(str(row["person_id"]))
            if (
                row.get("person_id") == target
                and donor_name
                and (not row.get("display_name") or row.get("display_name") == target)
            ):
                row["display_name"] = donor_name
            ppl2.append(row)
        ex["persons"] = ppl2
        pids = [m(x) for x in (ev.participant_person_ids or []) if m(x) is not None]
        pids = list(dict.fromkeys(pids))
        new_items.append(
            ev.model_copy(
                update={
                    "payer_person_id": m(ev.payer_person_id),
                    "participant_person_ids": pids,
                    "extra": ex,
                }
            )
        )
    log.info("merge_orphan_payer: %r -> %r (avoid N+1 for group split)", orphan, target)
    return bundle.model_copy(update={"items": new_items})


def _max_group_pos_in_bundle(bundle: EvidenceBundle) -> int:
    n = 0
    for ev in bundle.items:
        for p in (ev.extra or {}).get("persons") or []:
            pid = p.get("person_id") or ""
            m = _GROUP.match(str(pid))
            if m:
                n = max(n, int(m.group(1)))
    return n


def drop_inferred_photographer_if_group_full(bundle: EvidenceBundle) -> EvidenceBundle:
    """If any people_photo has group_pos_1..N for N>=4, drop inferred_photographer_1 (N friends fit on frame)."""
    if _max_group_pos_in_bundle(bundle) < 4:
        return bundle
    if not any(
        (p.get("person_id") or "") == "inferred_photographer_1"
        for ev in bundle.items
        for p in (ev.extra or {}).get("persons") or []
    ):
        return bundle

    def strip(ev: EvidenceItem) -> EvidenceItem:
        pids = [x for x in (ev.participant_person_ids or []) if x != "inferred_photographer_1"]
        pids = list(dict.fromkeys(pids))
        ex = {**(ev.extra or {})}
        ppl = [p for p in (ex.get("persons") or []) if p.get("person_id") != "inferred_photographer_1"]
        ex["persons"] = ppl
        return ev.model_copy(update={"participant_person_ids": pids, "extra": ex})

    new_items = [strip(ev) for ev in bundle.items]
    log.info("drop_inferred_photographer: N>=4 group_pos visible — removed inferred_photographer_1")
    return bundle.model_copy(update={"items": new_items})
