"""Load JSON fixtures from repo `fixtures/demo/`."""

from __future__ import annotations

import json
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent
REPO_FIXTURES = _APP_DIR.parent.parent / "fixtures" / "demo"


def fixtures_dir() -> Path:
    if not REPO_FIXTURES.is_dir():
        raise FileNotFoundError(
            f"Expected fixtures at {REPO_FIXTURES}. Run from repo root with fixtures committed."
        )
    return REPO_FIXTURES


def load_json(name: str) -> dict | list:
    path = fixtures_dir() / name
    return json.loads(path.read_text(encoding="utf-8"))


def run_stub_ingestion(event: dict) -> list[dict]:
    """Minimal ingestor: bundle → evidences (bunq-like + photo stub)."""
    bundle = load_json("source-descriptors-bundle.json")
    evidences: list[dict] = []
    for desc in bundle["descriptors"]:
        sk = desc["source_kind"]
        rel = desc.get("fixture_path") or ""
        path = fixtures_dir().parent.parent / rel
        if sk == "stub_bunq_json":
            raw = json.loads(path.read_text(encoding="utf-8"))
            for tx in raw.get("transactions", []):
                evidences.append(_evidence_from_tx(tx, event["event_id"]))
        elif sk == "stub_photo_json":
            raw = json.loads(path.read_text(encoding="utf-8"))
            for item in raw.get("items", []):
                evidences.append(_evidence_from_photo(item, event["event_id"]))
    return evidences


def _evidence_from_tx(tx: dict, event_id: str) -> dict:
    tid = tx["transaction_id"]
    return {
        "evidence_id": f"ev_{tid}",
        "event_id": event_id,
        "source_kind": "bank_transaction",
        "source_ref": tid,
        "time": {"kind": "instant", "at": tx["occurred_at"], "timezone": "UTC"},
        "location": None,
        "summary": f"Payment at {tx.get('merchant', '?')} (stub)",
        "confidence": 0.95,
        "extractor": {"name": "demo_stub_bunq", "version": "0.1.0"},
        "actor_mentions": [],
        "good_mentions": [
            {
                "mention_id": f"gm_{tid}",
                "description": tx.get("merchant", ""),
                "amount_cents": tx["amount_cents"],
                "currency": tx.get("currency", "EUR"),
                "merchant_guess": tx.get("merchant"),
            }
        ],
        "money_facts": [
            {
                "payer_participant_id": tx["payer_participant_id"],
                "amount_cents": tx["amount_cents"],
                "currency": tx.get("currency", "EUR"),
                "counterparty_guess": tx.get("merchant"),
                "raw_descriptor": tx.get("raw_descriptor", ""),
            }
        ],
        "relation_hints": [],
        "context_ids": [],
    }


def _evidence_from_photo(item: dict, event_id: str) -> dict:
    aid = item["asset_id"]
    return {
        "evidence_id": f"ev_{aid}",
        "event_id": event_id,
        "source_kind": "photo",
        "source_ref": aid,
        "time": {
            "kind": "instant",
            "at": item.get("exif_taken_at", ""),
            "timezone": "UTC",
        },
        "location": None,
        "summary": item.get("caption_stub", "Photo (stub)"),
        "confidence": 0.7,
        "extractor": {"name": "demo_stub_photo", "version": "0.1.0"},
        "actor_mentions": [],
        "good_mentions": [],
        "money_facts": [],
        "relation_hints": [],
        "context_ids": [],
    }
