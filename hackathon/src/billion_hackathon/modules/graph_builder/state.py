"""Mutable graph used when applying a GraphBlueprint."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class GraphState:
    def __init__(self, event_id: str) -> None:
        self.event_id = event_id
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []

    def to_snapshot(self) -> dict[str, Any]:
        nodes = sorted(self.nodes.values(), key=lambda n: n["id"])
        return {
            "schema_version": 1,
            "event_id": self.event_id,
            "nodes": deepcopy(nodes),
            "edges": deepcopy(self.edges),
        }

    def apply_blueprint_ops(self, operations: list[dict[str, Any]]) -> list[str]:
        errors: list[str] = []
        seen_edge: set[str] = set()
        for i, raw in enumerate(operations):
            op = raw.get("op")
            if op == "add_node":
                n = raw["node"]
                self.nodes[n["id"]] = deepcopy(n)
            elif op == "add_edge":
                e = deepcopy(raw["edge"])
                eid = e.get("edge_id")
                if eid and eid in seen_edge:
                    continue
                if eid:
                    seen_edge.add(eid)
                self.edges.append(e)
            else:
                errors.append(f"op[{i}]: unknown op {op!r}")
        return errors
