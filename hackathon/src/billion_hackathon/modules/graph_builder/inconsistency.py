"""Graph checks for UX highlighting (subset of compute-engine validation)."""

from __future__ import annotations

from typing import Any

from billion_hackathon.contracts.inconsistency import Inconsistency


def find_inconsistencies(graph: dict[str, Any]) -> list[Inconsistency]:
    out: list[Inconsistency] = []
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    goods = [n for n in nodes.values() if n.get("kind") == "good"]

    for g in goods:
        gid = g["id"]
        inflow = sum(
            int(e["amount_cents"])
            for e in edges
            if e.get("kind") == "cash_flow"
            and e.get("target") == "good"
            and e.get("to_id") == gid
        )
        stated = g.get("stated_total_cents")
        if stated is not None and stated != inflow:
            out.append(
                Inconsistency(
                    code="PRICE_MISMATCH",
                    severity="error",
                    message=f"Good {gid}: stated_total_cents={stated} but cash inflow={inflow}",
                    node_ids=[gid],
                )
            )
        contribs = [
            e for e in edges if e.get("kind") == "contribution" and e.get("good_id") == gid
        ]
        s = sum(float(e["value"]) for e in contribs)
        if inflow > 0 and s <= 0:
            out.append(
                Inconsistency(
                    code="NO_CONTRIBUTION_UNITS",
                    severity="error",
                    message=f"Good {gid}: spend {inflow} but no positive contribution units",
                    node_ids=[gid],
                )
            )
        if inflow == 0 and s > 0:
            out.append(
                Inconsistency(
                    code="CONTRIBUTIONS_WITHOUT_SPEND",
                    severity="warning",
                    message=f"Good {gid}: contributions defined but no cash_flow into good",
                    node_ids=[gid],
                )
            )

    person_ids = {n["id"] for n in nodes.values() if n.get("kind") == "person"}
    for e in edges:
        if e.get("kind") != "cash_flow":
            continue
        if e.get("from_id") not in person_ids:
            out.append(
                Inconsistency(
                    code="UNKNOWN_PAYER",
                    severity="error",
                    message=f"cash_flow from unknown person {e.get('from_id')}",
                    edge_ids=[e.get("edge_id") or ""],
                )
            )
        if e.get("target") == "person" and e.get("to_id") not in person_ids:
            out.append(
                Inconsistency(
                    code="UNKNOWN_PAYEE",
                    severity="error",
                    message=f"cash_flow to unknown person {e.get('to_id')}",
                    edge_ids=[e.get("edge_id") or ""],
                )
            )

    return out
