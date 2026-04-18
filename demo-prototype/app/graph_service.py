"""In-memory graph + GraphPatch application (demo subset)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class GraphState:
    def __init__(self, event_id: str) -> None:
        self.event_id = event_id
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "event_id": self.event_id,
            "nodes": list(self.nodes.values()),
            "edges": deepcopy(self.edges),
        }

    def load_snapshot(self, data: dict[str, Any]) -> None:
        self.event_id = data.get("event_id", self.event_id)
        self.nodes.clear()
        self.edges.clear()
        for n in data.get("nodes", []):
            self.nodes[n["id"]] = deepcopy(n)
        self.edges = deepcopy(data.get("edges", []))

    def apply_patch(self, patch: dict[str, Any]) -> list[str]:
        """Apply operations in order. Returns error strings (empty if ok)."""
        errors: list[str] = []
        if patch.get("event_id") != self.event_id:
            self.event_id = patch.get("event_id", self.event_id)

        for i, op in enumerate(patch.get("operations", [])):
            kind = op.get("op")
            if kind == "add_node":
                n = op["node"]
                self.nodes[n["id"]] = deepcopy(n)
            elif kind == "add_edge":
                self.edges.append(deepcopy(op["edge"]))
            elif kind == "upsert_contribution":
                e = deepcopy(op["edge"])
                pid, gid = e["person_id"], e["good_id"]
                self.edges = [
                    x
                    for x in self.edges
                    if not (
                        x.get("kind") == "contribution"
                        and x.get("person_id") == pid
                        and x.get("good_id") == gid
                    )
                ]
                self.edges.append(e)
            elif kind == "remove_node":
                nid = op["node_id"]
                if nid in self.nodes:
                    del self.nodes[nid]
                self.edges = [
                    e
                    for e in self.edges
                    if not _edge_touches(e, nid)
                ]
            elif kind == "remove_edge":
                eid = op["edge_id"]
                self.edges = [e for e in self.edges if e.get("edge_id") != eid]
            else:
                errors.append(f"op[{i}]: unknown op {kind!r}")
        return errors


def _edge_touches(e: dict[str, Any], node_id: str) -> bool:
    if e.get("kind") == "cash_flow":
        return e.get("from_id") == node_id or e.get("to_id") == node_id
    if e.get("kind") == "contribution":
        return e.get("person_id") == node_id or e.get("good_id") == node_id
    return False
