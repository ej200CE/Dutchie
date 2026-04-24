"""Golden tests: each module's examples/ folder defines artifact → expected."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from billion_hackathon.contracts.collected import CollectedBundle
from billion_hackathon.contracts.evidence import EvidenceBundle
from billion_hackathon.contracts.graph_blueprint import GraphBlueprint
from billion_hackathon.modules.computation.engine import compute
from billion_hackathon.modules.data_collection.service import DataCollectionService
from billion_hackathon.modules.data_ingestion.service import DataIngestionService
from billion_hackathon.modules.evidence_aggregation.service import EvidenceAggregationService
from billion_hackathon.modules.graph_builder.inconsistency import find_inconsistencies
from billion_hackathon.modules.graph_builder.service import GraphBuilderService
from billion_hackathon.modules.llm.client import ChatMessage, StubLLMClient

STORY1 = Path("/home/klift/bunq-hackathon-7/billion_idea/Story/1")

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

    def test_evidence_aggregation_story1_rules(self):
        """Rule-based aggregation of Story/1 rich evidence (selfie + receipt + transaction)."""
        from billion_hackathon.modules.evidence_aggregation.service import _aggregate_rules
        ev = EvidenceBundle.model_validate(_read("evidence_aggregation", "story1_artifact_evidence.json"))
        got = _aggregate_rules(ev)
        expected = GraphBlueprint.model_validate(
            _read("evidence_aggregation", "story1_expected_blueprint.json")
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

    # ------------------------------------------------------------------
    # Story 1 — three friends at a bar
    # selfie (EXIF: 21:00, GPS Amsterdam), receipt (EXIF: 21:30, same GPS),
    # transaction screenshot (no EXIF)
    # ------------------------------------------------------------------

    def test_data_collection_story1(self):
        """DataCollectionService extracts correct EXIF fields from Story/1 images."""
        if not STORY1.exists():
            self.skipTest("Story/1 fixtures not available")

        uploads = [
            ("selfe_of_three1_with_exif.jpg", "image/jpeg"),
            ("receipt1_with_exif.jpg", "image/jpeg"),
            ("screenshot1.jpg", "image/jpeg"),
        ]
        expected = json.loads(
            (PKG / "modules" / "data_collection" / "examples" / "story1_expected_collection.json").read_text()
        )

        with tempfile.TemporaryDirectory() as tmp:
            svc = DataCollectionService(Path(tmp))
            bundle = CollectedBundle(event_id="evt_bar_story1")
            for fname, mime in uploads:
                svc.add_upload(bundle, fname, (STORY1 / fname).read_bytes(), mime)

            self.assertEqual(len(bundle.items), len(expected))
            for item, exp in zip(bundle.items, expected):
                self.assertEqual(item.kind, exp["kind"], f"{item.original_filename}: kind")
                self.assertEqual(item.mime_type, exp["mime_type"], f"{item.original_filename}: mime_type")
                self.assertEqual(item.original_filename, exp["original_filename"])
                self.assertEqual(item.file_size, exp["file_size"], f"{item.original_filename}: file_size")
                if exp["exif_timestamp"] is not None:
                    self.assertIsNotNone(item.exif_timestamp, f"{item.original_filename}: expected exif_timestamp")
                    self.assertEqual(item.exif_timestamp.isoformat(), exp["exif_timestamp"])
                else:
                    self.assertIsNone(item.exif_timestamp, f"{item.original_filename}: expected no exif_timestamp")
                self.assertEqual(item.gps_lat, exp["gps_lat"], f"{item.original_filename}: gps_lat")
                self.assertEqual(item.gps_lon, exp["gps_lon"], f"{item.original_filename}: gps_lon")

    def test_data_ingestion_story1_stub(self):
        """Stub ingestor produces presence_hint items from Story/1 EXIF metadata."""
        if not STORY1.exists():
            self.skipTest("Story/1 fixtures not available")

        raw = _read("data_ingestion", "story1_artifact_bundle.json")
        bundle = CollectedBundle.model_validate(raw)
        got = DataIngestionService().ingest(bundle)
        expected = EvidenceBundle.model_validate(_read("data_ingestion", "story1_expected_evidence.json"))
        self.assertEqual(got.model_dump(), expected.model_dump())

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
