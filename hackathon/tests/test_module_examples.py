"""Golden tests: each module's examples/ folder defines artifact → expected."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from billion_hackathon.contracts.collected import CollectedBundle
from billion_hackathon.contracts.evidence import EvidenceBundle
from billion_hackathon.contracts.graph_blueprint import GraphBlueprint
from billion_hackathon.modules.computation.engine import compute
from billion_hackathon.modules.data_ingestion.service import DataIngestionService
from billion_hackathon.modules.evidence_aggregation.service import EvidenceAggregationService
from billion_hackathon.modules.graph_builder.inconsistency import find_inconsistencies
from billion_hackathon.modules.graph_builder.service import GraphBuilderService
from billion_hackathon.modules.llm.client import ChatMessage, StubLLMClient

PKG = Path(__file__).resolve().parent.parent / "src" / "billion_hackathon"


def _read_llm(name: str) -> dict:
    p = PKG / "modules" / "llm" / "examples" / name
    return json.loads(p.read_text())


def _read(module: str, name: str) -> dict:
    p = PKG / "modules" / module / "examples" / name
    return json.loads(p.read_text())


class ModuleExampleTests(unittest.TestCase):
    def test_data_ingestion_stub_matches_expected(self):
        raw = _read("data_ingestion", "artifact_bundle.json")
        bundle = CollectedBundle.model_validate(raw)
        got = DataIngestionService().ingest(bundle)
        expected = EvidenceBundle.model_validate(_read("data_ingestion", "expected_evidence.json"))
        self.assertEqual(got.model_dump(), expected.model_dump())

    def test_evidence_aggregation_matches_expected(self):
        ev = EvidenceBundle.model_validate(_read("evidence_aggregation", "artifact_evidence.json"))
        got = EvidenceAggregationService().aggregate(ev)
        expected = GraphBlueprint.model_validate(
            _read("evidence_aggregation", "expected_blueprint.json")
        )
        self.assertEqual(got.model_dump(), expected.model_dump())

    def test_graph_builder_snapshot(self):
        bp = GraphBlueprint.model_validate(_read("graph_builder", "artifact_blueprint.json"))
        snap, issues = GraphBuilderService().build(bp)
        expected = _read("graph_builder", "expected_graph.json")
        self.assertEqual(snap["event_id"], expected["event_id"])
        self.assertEqual(snap["nodes"], expected["nodes"])
        self.assertEqual(snap["edges"], expected["edges"])
        self.assertEqual(issues, [])

    def test_computation_golden(self):
        g = _read("computation", "artifact_graph.json")
        got = compute(g)
        expected = _read("computation", "expected_compute.json")
        self.assertEqual(got, expected)

    def test_price_mismatch_inconsistency(self):
        raw = _read("graph_builder", "expected_graph.json")
        nodes = raw["nodes"][:-1] + [{**raw["nodes"][-1], "stated_total_cents": 999}]
        raw = {**raw, "nodes": nodes}
        issues = find_inconsistencies(raw)
        self.assertTrue(any(i.code == "PRICE_MISMATCH" for i in issues))

    def test_llm_stub_matches_expected(self):
        sample = _read_llm("sample_messages.json")
        msgs = [ChatMessage(**m) for m in sample["messages"]]
        got = StubLLMClient().complete(msgs).model_dump()
        expected = _read_llm("expected_stub_response.json")
        self.assertEqual(got, expected)

    def test_end_to_end_chain(self):
        bundle = CollectedBundle.model_validate(_read("data_collection", "artifact_bundle.json"))
        ev = DataIngestionService().ingest(bundle)
        bp = EvidenceAggregationService().aggregate(ev)
        snap, _issues = GraphBuilderService().build(bp)
        result = compute({"nodes": snap["nodes"], "edges": snap["edges"]})
        self.assertTrue(result["success"])
        self.assertEqual(
            result["suggested_transfers"],
            _read("computation", "expected_compute.json")["suggested_transfers"],
        )


if __name__ == "__main__":
    unittest.main()
