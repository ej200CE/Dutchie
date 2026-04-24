"""Merge evidence into a GraphBlueprint (stub: rules; later LLM)."""

from __future__ import annotations

import re

from billion_hackathon.contracts.evidence import EvidenceBundle, EvidenceItem
from billion_hackathon.contracts.graph_blueprint import GraphBlueprint, GraphOperation


def _slug(s: str) -> str:
    x = re.sub(r"[^\w\-]+", "-", s.strip().lower()).strip("-")
    return x or "item"


class EvidenceAggregationService:
    def aggregate(self, bundle: EvidenceBundle) -> GraphBlueprint:
        ops: list[GraphOperation] = []
        seen_person: set[str] = set()
        for ev in bundle.items:
            if ev.kind != "spend_hint" or ev.amount_cents is None:
                continue
            if not ev.payer_person_id:
                continue
            label = ev.label or "expense"
            good_id = f"good-{_slug(label)}"
            payer = ev.payer_person_id
            people = list(dict.fromkeys([*ev.participant_person_ids, payer]))
            for pid in people:
                if pid not in seen_person:
                    seen_person.add(pid)
                    ops.append(
                        GraphOperation(
                            op="add_node",
                            node={
                                "id": pid,
                                "kind": "person",
                                "display_name": pid,
                            },
                        )
                    )
            ops.append(
                GraphOperation(
                    op="add_node",
                    node={
                        "id": good_id,
                        "kind": "good",
                        "display_name": label,
                    },
                )
            )
            ops.append(
                GraphOperation(
                    op="add_edge",
                    edge={
                        "kind": "cash_flow",
                        "edge_id": f"cf-{good_id}-{payer}",
                        "from_id": payer,
                        "target": "good",
                        "to_id": good_id,
                        "amount_cents": ev.amount_cents,
                    },
                )
            )
            for pid in people:
                ops.append(
                    GraphOperation(
                        op="add_edge",
                        edge={
                            "kind": "contribution",
                            "edge_id": f"ct-{good_id}-{pid}",
                            "person_id": pid,
                            "good_id": good_id,
                            "value": 1.0,
                        },
                    )
                )
        return GraphBlueprint(event_id=bundle.event_id, operations=ops)
