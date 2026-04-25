"""Deterministic balances + pairwise transfers (same semantics as demo-prototype)."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


def compute(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    persons = [n for n in nodes.values() if n.get("kind") == "person"]
    goods = [n for n in nodes.values() if n.get("kind") == "good"]

    errors: list[dict[str, str]] = []
    fair_share: dict[str, int] = defaultdict(int)

    for g in goods:
        gid = g["id"]
        inflow = sum(
            e["amount_cents"]
            for e in edges
            if e.get("kind") == "cash_flow"
            and e.get("target") == "good"
            and e.get("to_id") == gid
        )
        stated = g.get("stated_total_cents")
        if stated is not None and stated != inflow:
            errors.append(
                {
                    "code": "PRICE_MISMATCH",
                    "message": f"Good {gid}: stated_total_cents={stated} but cash_flow sum={inflow}",
                }
            )

        contribs: dict[str, float] = {}
        for e in edges:
            if e.get("kind") == "contribution" and e.get("good_id") == gid:
                contribs[e["person_id"]] = float(e["value"])

        s = sum(contribs.values())
        if inflow > 0 and s <= 0:
            errors.append(
                {
                    "code": "NO_CONTRIBUTION_UNITS",
                    "message": f"Good {gid}: positive spend but sum(contributions)={s}",
                }
            )
            continue
        if inflow == 0:
            continue
        if s <= 0:
            continue

        for pid, c in contribs.items():
            raw = inflow * c / s
            alloc = int(math.ceil(raw - 1e-9))
            fair_share[pid] += alloc

    if errors:
        return {
            "success": False,
            "errors": errors,
            "per_person": [],
            "suggested_transfers": [],
            "diagnostics": [],
        }

    paid_out: dict[str, int] = defaultdict(int)
    for e in edges:
        if e.get("kind") != "cash_flow":
            continue
        amt = int(e["amount_cents"])
        paid_out[e["from_id"]] += amt
        # Person-to-person cash flow means receiver already got reimbursed.
        if e.get("target") == "person":
            paid_out[e["to_id"]] -= amt

    per_person: list[dict[str, Any]] = []
    nets: dict[str, int] = {}
    for p in persons:
        pid = p["id"]
        po = paid_out.get(pid, 0)
        fs = fair_share.get(pid, 0)
        net = po - fs
        nets[pid] = net
        per_person.append(
            {
                "person_id": pid,
                "display_name": p.get("display_name", pid),
                "paid_out_cents": po,
                "fair_share_owed_cents": fs,
                "net_cents": net,
            }
        )

    transfers = _pairwise(nets)
    return {
        "success": True,
        "errors": [],
        "per_person": per_person,
        "suggested_transfers": transfers,
        "diagnostics": [],
    }


def _pairwise(nets: dict[str, int]) -> list[dict[str, Any]]:
    debtors = sorted([(pid, -n) for pid, n in nets.items() if n < 0], key=lambda x: x[1], reverse=True)
    creditors = sorted([(pid, n) for pid, n in nets.items() if n > 0], key=lambda x: x[1], reverse=True)
    out: list[dict[str, Any]] = []
    di, ci = 0, 0
    while di < len(debtors) and ci < len(creditors):
        d_id, d_amt = debtors[di]
        c_id, c_amt = creditors[ci]
        if d_amt <= 0:
            di += 1
            continue
        if c_amt <= 0:
            ci += 1
            continue
        x = min(d_amt, c_amt)
        out.append(
            {
                "from_person_id": d_id,
                "to_person_id": c_id,
                "amount_cents": x,
            }
        )
        debtors[di] = (d_id, d_amt - x)
        creditors[ci] = (c_id, c_amt - x)
        if debtors[di][1] <= 0:
            di += 1
        if creditors[ci][1] <= 0:
            ci += 1
    return out
