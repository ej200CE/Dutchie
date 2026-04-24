"""Apply GraphBlueprint and surface inconsistencies."""

from __future__ import annotations

from typing import Any

from billion_hackathon.contracts.graph_blueprint import GraphBlueprint
from billion_hackathon.contracts.inconsistency import Inconsistency
from billion_hackathon.modules.graph_builder.inconsistency import find_inconsistencies
from billion_hackathon.modules.graph_builder.state import GraphState


class GraphBuilderService:
    def build(self, blueprint: GraphBlueprint) -> tuple[dict[str, Any], list[Inconsistency]]:
        state = GraphState(blueprint.event_id)
        raw_ops = [op.model_dump(exclude_none=True) for op in blueprint.operations]
        errs = state.apply_blueprint_ops(raw_ops)
        snap = state.to_snapshot()
        issues = find_inconsistencies(snap)
        for msg in errs:
            issues.append(
                Inconsistency(code="BLUEPRINT_ERROR", severity="error", message=msg)
            )
        return snap, issues
