"""Golden tests: each module's examples/ folder defines artifact → expected."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from billion_hackathon.contracts.collected import CollectedBundle
from billion_hackathon.contracts.evidence import EvidenceBundle, EvidenceItem
from billion_hackathon.modules.data_ingestion.consolidate_receipt_lines import (
    consolidate_receipt_lines_for_group_bill,
)
from billion_hackathon.contracts.graph_blueprint import GraphBlueprint
from billion_hackathon.modules.computation.engine import compute
from billion_hackathon.modules.data_collection.service import DataCollectionService
from billion_hackathon.modules.data_ingestion.service import DataIngestionService
from billion_hackathon.modules.evidence_aggregation.service import EvidenceAggregationService
from billion_hackathon.modules.graph_builder.inconsistency import find_inconsistencies
from billion_hackathon.modules.graph_builder.service import GraphBuilderService
from billion_hackathon.modules.llm.client import ChatMessage, StubLLMClient

STORY1 = Path("/home/klift/bunq-hackathon-7/billion_idea/Story/1")
STORY2 = Path("/home/klift/bunq-hackathon-7/billion_idea/Story/2")

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

    def test_evidence_aggregation_story2_rules(self):
        """Rule-based aggregation of Story/2: four people, one shared meal, one payer."""
        from billion_hackathon.modules.evidence_aggregation.service import _aggregate_rules
        ev = EvidenceBundle.model_validate(_read("evidence_aggregation", "story2_artifact_evidence.json"))
        got = _aggregate_rules(ev)
        person_ids = {
            n["id"]
            for o in got.operations
            if o.op == "add_node" and o.node and o.node.get("kind") == "person"
            for n in [o.node]
        }
        self.assertEqual(person_ids, {"e_evans", "group_pos_2", "group_pos_3", "group_pos_4"})
        goods = [o for o in got.operations if o.op == "add_node" and o.node and o.node.get("kind") == "good"]
        self.assertEqual(len(goods), 1)
        self.assertEqual(goods[0].node.get("stated_total_cents"), 22090)

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
        """With LLM stub, Story/1 file set maps to story-aligned gold evidence (Three friends, 3x beer)."""
        if not STORY1.exists():
            self.skipTest("Story/1 fixtures not available")

        raw = _read("data_ingestion", "story1_artifact_bundle.json")
        bundle = CollectedBundle.model_validate(raw)
        got = DataIngestionService().ingest(bundle)
        expected = EvidenceBundle.model_validate(_read("data_ingestion", "story1_expected_evidence.json"))
        self.assertEqual(got.model_dump(), expected.model_dump())

    def test_data_ingestion_story2_stub(self):
        """With LLM stub, Story/2 file set maps to story-aligned gold evidence (Four friends, one bill)."""
        if not STORY2.exists():
            self.skipTest("Story/2 fixtures not available")

        raw = _read("data_ingestion", "story2_artifact_bundle.json")
        bundle = CollectedBundle.model_validate(raw)
        got = DataIngestionService().ingest(bundle)
        expected = EvidenceBundle.model_validate(_read("data_ingestion", "story2_expected_evidence.json"))
        self.assertEqual(got.model_dump(), expected.model_dump())

    def test_consolidate_receipt_lines_merges_exploded_menu(self):
        """Many receipt_line rows from one image collapse to one (Scenario 2 menu explosion)."""
        spend = EvidenceItem(
            id="sp1",
            source_item_ids=[],
            kind="spend_hint",
            amount_cents=10_000,
            label="Bistro",
            payer_person_id="a",
            participant_person_ids=["a", "b", "c", "d"],
            confidence=0.9,
            extra={"good_id": "dinner_1"},
        )
        src = "receipt-img-1"
        rlines = [
            EvidenceItem(
                id=f"rl{i}",
                source_item_ids=[src],
                kind="receipt_line",
                amount_cents=amt,
                label=f"line{i}",
                confidence=0.8,
            )
            for i, amt in enumerate([10_000, 200, 300], start=1)
        ]
        b = EvidenceBundle(
            event_id="e1",
            items=[spend, *rlines],
        )
        out = consolidate_receipt_lines_for_group_bill(b)
        rls = [x for x in out.items if x.kind == "receipt_line"]
        self.assertEqual(len(rls), 1)
        self.assertEqual(rls[0].amount_cents, 10_000)
        self.assertEqual((rls[0].extra or {}).get("good_id"), "dinner_1")
        self.assertEqual(set(rls[0].participant_person_ids), {"a", "b", "c", "d"})

    def test_data_collection_marks_audio_upload_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = DataCollectionService(Path(tmp))
            bundle = CollectedBundle(event_id="evt_audio_kind")
            item = svc.add_upload(
                bundle,
                "memo.m4a",
                b"RIFF0000WAVEfmt ",
                "audio/m4a",
            )
            self.assertEqual(item.kind, "audio")

    def test_audio_ingestion_sidecar_transcript_to_spend_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = DataCollectionService(Path(tmp))
            bundle = CollectedBundle(event_id="evt_audio")
            item = svc.add_upload(
                bundle,
                "voice-note.m4a",
                b"RIFF0000WAVEfmt ",
                "audio/m4a",
            )
            Path(item.stored_path).with_suffix(".txt").write_text(
                "EXPENSE: 2400 cents for taxi payer=alice participants=alice,bob",
                encoding="utf-8",
            )
            ev = DataIngestionService().ingest(bundle)
            self.assertEqual(len(ev.items), 1)
            got = ev.items[0]
            self.assertEqual(got.kind, "spend_hint")
            self.assertEqual(got.amount_cents, 2400)
            self.assertEqual(got.payer_person_id, "alice")
            self.assertEqual(set(got.participant_person_ids), {"alice", "bob"})

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
