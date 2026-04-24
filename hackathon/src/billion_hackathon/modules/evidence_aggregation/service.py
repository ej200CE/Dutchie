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
    response = client.complete(messages, max_tokens=4096)
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
        self._client = get_llm_client()

    def aggregate(self, bundle: EvidenceBundle) -> GraphBlueprint:
        if not isinstance(self._client, StubLLMClient):
            try:
                return _aggregate_with_llm(bundle, self._client)
            except Exception as exc:
                log.warning("LLM aggregation failed (%s) — falling back to rules", exc)
        return _aggregate_rules(bundle)
