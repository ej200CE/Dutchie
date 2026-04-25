"""Merge EvidenceBundle → GraphBlueprint.

Two paths:
  rules  (always available) — deterministic; handles well-structured evidence
  llm    (when provider != stub) — cross-correlates ambiguous evidence, resolves
         person identity across images, infers missing payers from context

The LLM path falls back to rules if the model returns invalid JSON or errors.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from billion_hackathon.contracts.evidence import EvidenceBundle, EvidenceItem
from billion_hackathon.contracts.graph_blueprint import GraphBlueprint, GraphOperation
from billion_hackathon.modules.evidence_aggregation.prompts import (
    AGGREGATION_SYSTEM,
    AGGREGATION_USER_TMPL,
)
from billion_hackathon.modules.llm.client import (
    ChatMessage,
    StubLLMClient,
    get_llm_client,
)

log = logging.getLogger("billion.aggregation")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug(s: str) -> str:
    x = re.sub(r"[^\w\-]+", "-", s.strip().lower()).strip("-")
    return x or "item"


def _good_id_for(ev: EvidenceItem) -> str:
    if ev.extra.get("good_id"):
        return str(ev.extra["good_id"])
    return f"good-{_slug(ev.label or 'expense')}"


def _context_key(ev: EvidenceItem) -> tuple | None:
    """Tuple for cross-correlating evidence from the same transaction."""
    ctx = ev.extra.get("context") or {}
    venue = ctx.get("venue")
    total = ctx.get("total_amount_cents")
    dt = ctx.get("datetime_visible")
    if venue and total is not None:
        return (str(venue).lower().strip(), int(total))
    if venue and dt:
        return (str(venue).lower().strip(), str(dt)[:10])
    return None


def _norm_venue_key(ctx: dict) -> str | None:
    v = ctx.get("venue")
    if not v:
        return None
    s = str(v).strip().lower()
    return s or None


def _is_people_centric_for_merge(ev: EvidenceItem) -> bool:
    it = (ev.extra or {}).get("image_type")
    if it == "people_photo":
        return True
    if ev.kind == "presence_hint" and (
        ev.participant_person_ids
        or (ev.extra or {}).get("persons")
    ):
        return True
    return False


def _person_id_list_ordered(ev: EvidenceItem) -> list[str]:
    ppl = (ev.extra or {}).get("persons") or []
    return [str(p["person_id"]) for p in ppl if p.get("person_id")]


def _all_reference_person_ids(bundle: EvidenceBundle) -> set[str]:
    s: set[str] = set()
    for ev in bundle.items:
        for p in (ev.extra or {}).get("persons") or []:
            if p.get("person_id"):
                s.add(str(p["person_id"]))
        s.update(str(x) for x in (ev.participant_person_ids or []))
        if ev.payer_person_id:
            s.add(str(ev.payer_person_id))
    return s


def _find_cross_image_person_pairs(bundle: EvidenceBundle) -> list[tuple[str, str]]:
    """(id_a, id_b) to merge: same N people, same venue label, list-order alignment."""
    by_src: dict[str, EvidenceItem] = {}
    for ev in bundle.items:
        sid = (ev.source_item_ids or [None])[0]
        if not sid or sid in by_src:
            continue
        if not _is_people_centric_for_merge(ev):
            continue
        if len(_person_id_list_ordered(ev)) < 2:
            continue
        by_src[sid] = ev
    if len(by_src) < 2:
        return []
    per_src: dict[str, list[str]] = {s: _person_id_list_ordered(v) for s, v in by_src.items()}
    sids = list(per_src.keys())
    pairs: list[tuple[str, str]] = []
    for i in range(len(sids)):
        for j in range(i + 1, len(sids)):
            a, b = sids[i], sids[j]
            p1, p2 = per_src[a], per_src[b]
            if len(p1) != len(p2) or not p1 or not p2:
                continue
            if set(p1) & set(p2):
                continue
            ev1, ev2 = by_src[a], by_src[b]
            c1, c2 = (ev1.extra or {}).get("context") or {}, (ev2.extra or {}).get("context") or {}
            v1, v2 = _norm_venue_key(c1), _norm_venue_key(c2)
            if not v1 or v1 != v2:
                continue
            n = len(p1)
            if n < 2 or n > 10:
                continue
            for u, w in zip(p1, p2):
                if u != w:
                    pairs.append((u, w))
    return pairs


def _person_id_merge_map(bundle: EvidenceBundle) -> dict[str, str]:
    pairs = _find_cross_image_person_pairs(bundle)
    pairs.extend(_alias_person_pairs(bundle))
    ref = _all_reference_person_ids(bundle)
    if not pairs:
        return {x: x for x in ref}
    universe = set(ref) | {x for t in pairs for x in t}
    return _uf_project_to_canonical(universe, pairs)


def _alias_person_pairs(bundle: EvidenceBundle) -> list[tuple[str, str]]:
    """Conservatively merge ids that share explicit aliases from ingestion metadata."""
    by_alias: dict[str, set[str]] = {}
    for ev in bundle.items:
        aliases = (ev.extra or {}).get("person_aliases") or {}
        if not isinstance(aliases, dict):
            continue
        for pid, vals in aliases.items():
            if not pid or not isinstance(vals, list):
                continue
            for v in vals:
                key = _slug(str(v or ""))
                if not key:
                    continue
                by_alias.setdefault(key, set()).add(str(pid))
    pairs: list[tuple[str, str]] = []
    for ids in by_alias.values():
        if len(ids) < 2:
            continue
        ordered = sorted(ids)
        a = ordered[0]
        for b in ordered[1:]:
            if a != b:
                pairs.append((a, b))
    return pairs


def _remap_evidence_person_ids(
    bundle: EvidenceBundle, merge_map: dict[str, str]
) -> EvidenceBundle:
    if not any(merge_map.get(p, p) != p for p in merge_map):
        return bundle

    def m(x: str | None) -> str | None:
        if x is None:
            return None
        return merge_map.get(x, x)

    new_items: list[EvidenceItem] = []
    for ev in bundle.items:
        ex = {**(ev.extra or {})}
        ppl2: list[dict] = []
        for p in ex.get("persons") or []:
            row = {**p}
            if row.get("person_id"):
                row["person_id"] = m(str(row["person_id"]))
            ppl2.append(row)
        ex["persons"] = ppl2
        new_items.append(
            ev.model_copy(
                update={
                    "payer_person_id": m(ev.payer_person_id),
                    "participant_person_ids": [m(x) for x in (ev.participant_person_ids or [])],
                    "extra": ex,
                },
            )
        )
    return bundle.model_copy(update={"items": new_items})


def _uf_project_to_canonical(ids: set[str], pairs: list[tuple[str, str]]) -> dict[str, str]:
    """For each id in the universe, return representative (min in UF component)."""
    parent: dict[str, str] = {x: x for x in ids}
    for a, b in pairs:
        parent.setdefault(a, a)
        parent.setdefault(b, b)

    def p(x: str) -> str:
        if parent.get(x, x) != x:
            parent[x] = p(parent[x])
        return parent.get(x, x)

    def u(a: str, b: str) -> None:
        ra, rb = p(a), p(b)
        if ra == rb:
            return
        if ra < rb:
            parent[rb] = ra
        else:
            parent[ra] = rb

    for a, b in pairs:
        u(a, b)
    for x in set(ids):
        parent.setdefault(x, x)
    return {x: p(x) for x in set(ids) | set(parent)}


def _merge_cross_file_same_headcount_people(
    persons: dict[str, str],
    cash_flows: list[dict[str, Any]],
    contributions: dict[tuple[str, str], float],
    context_payers: dict[tuple, tuple[str, int]],
    context_presence: dict[tuple, set[str]],
    bundle: EvidenceBundle,
) -> None:
    """Merge the same people described twice (different photos) into one id each.

    Ingestion runs one image at a time, so unnamed groups often get unique appearance
    slugs. When two files list the same N people for the same venue, pair them
    in list order (left-to-right) and map to a single representative id.
    """
    pairs = _find_cross_image_person_pairs(bundle)
    if not pairs:
        return

    universe: set[str] = set(persons) | {x for t in pairs for x in t}
    canon: dict[str, str] = _uf_project_to_canonical(universe, pairs)

    def ren(pid: str) -> str:
        return canon.get(pid, pid)

    new_persons: dict[str, str] = {}
    for old, disp in persons.items():
        np = ren(str(old))
        if np not in new_persons or len(disp) > len(new_persons.get(np, "")):
            new_persons[np] = disp
    persons.clear()
    persons.update(new_persons)

    new_c: dict[tuple[str, str], float] = {}
    for (pi, g), v in list(contributions.items()):
        npi = ren(str(pi))
        new_c[(npi, g)] = v
    contributions.clear()
    contributions.update(new_c)

    for cf in cash_flows:
        if "from_id" in cf and cf.get("from_id") is not None:
            cf["from_id"] = ren(str(cf["from_id"]))
        t = cf.get("to_id")
        if t is not None and cf.get("target") == "person":
            cf["to_id"] = ren(str(t))
        to_g = cf.get("to_id")
        fr = cf.get("from_id")
        if cf.get("target") == "good" and fr is not None and to_g is not None:
            cf["edge_id"] = f"cf-{to_g}-{fr}"
    for ck in list(context_payers):
        p0, a = context_payers[ck]
        context_payers[ck] = (ren(str(p0)), a)
    for _ck, s in list(context_presence.items()):
        old = set(s)
        s.clear()
        s.update(ren(str(pid)) for pid in old)

    log.info(
        "person merge: %d pair edges, %d people after",
        len(pairs),
        len(persons),
    )



def _collect_persons(ev: EvidenceItem, persons: dict[str, str]) -> None:
    """Add all persons from this item into the ordered persons dict."""
    # Rich descriptors from LLM ingestor take priority for display_name
    for p in ev.extra.get("persons") or []:
        pid = p.get("person_id")
        if pid and pid not in persons:
            persons[pid] = p.get("display_name") or pid
    # Direct participant / payer references
    all_pids = list(dict.fromkeys(
        [*(ev.participant_person_ids or []), *([ev.payer_person_id] if ev.payer_person_id else [])]
    ))
    for pid in all_pids:
        if pid and pid not in persons:
            persons[pid] = pid


def _participants_for(ev: EvidenceItem) -> list[str]:
    return list(dict.fromkeys(
        [*(ev.participant_person_ids or []), *([ev.payer_person_id] if ev.payer_person_id else [])]
    ))


_MIN_CONF_BY_KIND: dict[str, float] = {
    "spend_hint": 0.35,
    "receipt_line": 0.3,
    "p2p_hint": 0.45,
    "presence_hint": 0.4,
    "free_text": 0.95,  # effectively ignored for graph construction
}


def _should_use_item(ev: EvidenceItem) -> bool:
    if (ev.extra or {}).get("needs_review") is True:
        return False
    min_conf = _MIN_CONF_BY_KIND.get(ev.kind, 0.4)
    return float(ev.confidence or 0.0) >= min_conf


# ---------------------------------------------------------------------------
# Rule-based aggregation
# ---------------------------------------------------------------------------


def _aggregate_rules(bundle: EvidenceBundle) -> GraphBlueprint:
    persons: dict[str, str] = {}            # pid → display_name (insertion-ordered)
    goods: dict[str, dict[str, Any]] = {}   # gid → attrs
    cash_flows: list[dict[str, Any]] = []
    contributions: dict[tuple[str, str], float] = {}  # (pid, gid) → value

    # spend_hint context key → (payer_id, amount) for receipt_line cross-correlation
    context_payers: dict[tuple, tuple[str, int]] = {}
    # presence context key → set of pids (for contribution fallback)
    context_presence: dict[tuple, set[str]] = {}

    # Pass 1: collect persons / goods declared in extra arrays (LLM ingestor output)
    for ev in bundle.items:
        for p in ev.extra.get("persons") or []:
            pid = p.get("person_id")
            if pid and pid not in persons:
                persons[pid] = p.get("display_name") or pid
        for g in ev.extra.get("goods") or []:
            gid = g.get("good_id")
            if gid and gid not in goods:
                goods[gid] = {
                    "display_name": g.get("label") or gid,
                    "amount_cents": g.get("total_cents"),
                    "currency": "EUR",
                }

    # Pass 2: process each evidence item
    for ev in bundle.items:
        if not _should_use_item(ev):
            continue
        _collect_persons(ev, persons)

        if ev.kind == "spend_hint" and ev.payer_person_id and ev.amount_cents is not None:
            good_id = _good_id_for(ev)
            goods.setdefault(good_id, {
                "display_name": ev.label or good_id,
                "amount_cents": ev.amount_cents,
                "currency": ev.currency or "EUR",
            })
            cash_flows.append({
                "kind": "cash_flow",
                "edge_id": f"cf-{good_id}-{ev.payer_person_id}",
                "from_id": ev.payer_person_id,
                "target": "good",
                "to_id": good_id,
                "amount_cents": ev.amount_cents,
            })
            for pid in _participants_for(ev):
                if (pid, good_id) not in contributions:
                    contributions[(pid, good_id)] = 1.0
            ck = _context_key(ev)
            if ck:
                context_payers[ck] = (ev.payer_person_id, ev.amount_cents)

        elif ev.kind == "receipt_line":
            good_id = _good_id_for(ev)
            if ev.amount_cents is not None:
                goods.setdefault(good_id, {
                    "display_name": ev.label or good_id,
                    "amount_cents": ev.amount_cents,
                    "currency": ev.currency or "EUR",
                })
            for pid in _participants_for(ev):
                if (pid, good_id) not in contributions:
                    contributions[(pid, good_id)] = 1.0
            if ev.payer_person_id and ev.amount_cents is not None:
                cash_flows.append({
                    "kind": "cash_flow",
                    "edge_id": f"cf-{good_id}-{ev.payer_person_id}",
                    "from_id": ev.payer_person_id,
                    "target": "good",
                    "to_id": good_id,
                    "amount_cents": ev.amount_cents,
                })

        elif ev.kind == "p2p_hint" and ev.payer_person_id:
            for to_pid in [p for p in (ev.participant_person_ids or []) if p != ev.payer_person_id]:
                cash_flows.append({
                    "kind": "cash_flow",
                    "edge_id": f"cf-p2p-{ev.payer_person_id}-{to_pid}",
                    "from_id": ev.payer_person_id,
                    "target": "person",
                    "to_id": to_pid,
                    "amount_cents": ev.amount_cents,
                })

        elif ev.kind == "presence_hint":
            ck = _context_key(ev)
            if ck:
                grp = context_presence.setdefault(ck, set())
                for pid in ev.participant_person_ids or []:
                    grp.add(pid)

    # Pass 3: cross-correlate receipt_lines (no payer) with matching spend_hints
    for ev in bundle.items:
        if not _should_use_item(ev):
            continue
        if ev.kind != "receipt_line" or ev.payer_person_id:
            continue
        ck = _context_key(ev)
        if not ck or ck not in context_payers:
            continue
        payer, _ = context_payers[ck]
        good_id = _good_id_for(ev)
        eid = f"cf-{good_id}-{payer}"
        if good_id in goods and ev.amount_cents is not None:
            if not any(cf["edge_id"] == eid for cf in cash_flows):
                cash_flows.append({
                    "kind": "cash_flow",
                    "edge_id": eid,
                    "from_id": payer,
                    "target": "good",
                    "to_id": good_id,
                    "amount_cents": ev.amount_cents,
                })

    # Pass 4: presence-based contribution fallback (goods with no contributors)
    for ck, present_pids in context_presence.items():
        for ev in bundle.items:
            if _context_key(ev) != ck or ev.kind not in ("spend_hint", "receipt_line"):
                continue
            good_id = _good_id_for(ev)
            if good_id not in goods:
                continue
            if not any(gid == good_id for (_, gid) in contributions):
                for pid in present_pids:
                    if (pid, good_id) not in contributions:
                        contributions[(pid, good_id)] = 1.0

    _merge_cross_file_same_headcount_people(
        persons, cash_flows, contributions, context_payers, context_presence, bundle
    )

    # Build operations: persons → goods → cash_flows → contributions
    ops: list[GraphOperation] = []
    seen_persons: set[str] = set()
    for pid, display in persons.items():
        if pid not in seen_persons:
            seen_persons.add(pid)
            ops.append(GraphOperation(
                op="add_node",
                node={"id": pid, "kind": "person", "display_name": display},
            ))

    for gid, ginfo in goods.items():
        node: dict[str, Any] = {"id": gid, "kind": "good", "display_name": ginfo["display_name"]}
        if ginfo.get("amount_cents") is not None:
            node["stated_total_cents"] = ginfo["amount_cents"]
        ops.append(GraphOperation(op="add_node", node=node))

    seen_cf: set[str] = set()
    for cf in cash_flows:
        eid = cf.get("edge_id", "")
        if eid in seen_cf:
            continue
        seen_cf.add(eid)
        ops.append(GraphOperation(op="add_edge", edge={k: v for k, v in cf.items() if v is not None}))

    for (pid, gid), val in contributions.items():
        ops.append(GraphOperation(
            op="add_edge",
            edge={
                "kind": "contribution",
                "edge_id": f"ct-{gid}-{pid}",
                "person_id": pid,
                "good_id": gid,
                "value": val,
            },
        ))

    log.info("rules: %d persons, %d goods, %d cash_flows, %d contributions",
             len(persons), len(goods), len(seen_cf), len(contributions))
    return GraphBlueprint(event_id=bundle.event_id, operations=ops)


# ---------------------------------------------------------------------------
# LLM-assisted aggregation
# ---------------------------------------------------------------------------


def _aggregate_with_llm(bundle: EvidenceBundle, client: Any) -> GraphBlueprint:
    evidence_json = json.dumps(
        [ev.model_dump(mode="json") for ev in bundle.items],
        indent=2,
        ensure_ascii=False,
    )
    messages = [
        ChatMessage(role="system", content=AGGREGATION_SYSTEM),
        ChatMessage(
            role="user",
            content=AGGREGATION_USER_TMPL.format(
                event_id=bundle.event_id,
                evidence_json=evidence_json,
            ),
        ),
    ]
    log.info("LLM aggregation: %d evidence items → calling model", len(bundle.items))
    response = client.complete(messages, max_tokens=8192)
    return _parse_llm_blueprint(bundle.event_id, response.text)


def _parse_llm_blueprint(event_id: str, text: str) -> GraphBlueprint:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise ValueError(f"LLM returned no JSON: {text[:200]}")
        data = json.loads(m.group())

    ops: list[GraphOperation] = []

    for p in data.get("persons") or []:
        ops.append(GraphOperation(
            op="add_node",
            node={"id": p["id"], "kind": "person", "display_name": p.get("display_name") or p["id"]},
        ))

    for g in data.get("goods") or []:
        node: dict[str, Any] = {
            "id": g["id"],
            "kind": "good",
            "display_name": g.get("display_name") or g["id"],
        }
        if g.get("amount_cents") is not None:
            node["stated_total_cents"] = g["amount_cents"]
        ops.append(GraphOperation(op="add_node", node=node))

    for cf in data.get("cash_flows") or []:
        edge: dict[str, Any] = {
            "kind": "cash_flow",
            "edge_id": cf.get("edge_id") or f"cf-{cf.get('to_id')}-{cf.get('from_id')}",
            "from_id": cf["from_id"],
            "target": cf.get("target", "good"),
            "to_id": cf["to_id"],
        }
        if cf.get("amount_cents") is not None:
            edge["amount_cents"] = cf["amount_cents"]
        ops.append(GraphOperation(op="add_edge", edge=edge))

    for ct in data.get("contributions") or []:
        ops.append(GraphOperation(
            op="add_edge",
            edge={
                "kind": "contribution",
                "edge_id": ct.get("edge_id") or f"ct-{ct.get('good_id')}-{ct.get('person_id')}",
                "person_id": ct["person_id"],
                "good_id": ct["good_id"],
                "value": float(ct.get("value", 1.0)),
            },
        ))

    log.info("LLM blueprint: %d persons, %d goods, %d cash_flows, %d contributions",
             len(data.get("persons") or []), len(data.get("goods") or []),
             len(data.get("cash_flows") or []), len(data.get("contributions") or []))
    return GraphBlueprint(event_id=event_id, operations=ops)


# ---------------------------------------------------------------------------
# Service entry point
# ---------------------------------------------------------------------------


class EvidenceAggregationService:
    def __init__(self) -> None:
        import os
        self._client = get_llm_client(
            model_override=os.environ.get("BILLION_AGGREGATION_LLM_MODEL") or None
        )

    def aggregate(self, bundle: EvidenceBundle) -> GraphBlueprint:
        mmap = _person_id_merge_map(bundle)
        if any(mmap.get(p, p) != p for p in mmap):
            log.info("cross-image person remapping before aggregate: %d ids in map", len(mmap))
            bundle = _remap_evidence_person_ids(bundle, mmap)
        if not isinstance(self._client, StubLLMClient):
            try:
                return _aggregate_with_llm(bundle, self._client)
            except Exception as exc:
                log.warning("LLM aggregation failed (%s) — falling back to rules", exc)
        return _aggregate_rules(bundle)
