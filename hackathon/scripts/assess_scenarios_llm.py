#!/usr/bin/env python3
"""Run ingest → aggregate → graph on Story/1 and/or Story/2 with your real LLM (no stub).

Load credentials from the repo root `.env` (same as the app):
  BILLION_LLM_PROVIDER=openai
  BILLION_LLM_API_KEY=sk-...
  BILLION_LLM_MODEL=gpt-4o   (optional)
  BILLION_LLM_BASE_URL=      (optional; default OpenAI)

Usage (from the `hackathon` directory):
  uv run python scripts/assess_scenarios_llm.py
  uv run python scripts/assess_scenarios_llm.py --story 1
  uv run python scripts/assess_scenarios_llm.py --story 2
  uv run python scripts/assess_scenarios_llm.py --no-aggregate
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Load .env before anything imports the LLM client
_REPO = Path(__file__).resolve().parent.parent.parent
_ENV = _REPO / ".env"
if _ENV.exists():
    from dotenv import load_dotenv

    load_dotenv(_ENV)
    os.environ.setdefault("PYTHONDOTENV", str(_ENV))

# Ensure we run with package on path
_SYS = Path(__file__).resolve().parent.parent / "src"
if str(_SYS) not in sys.path:
    sys.path.insert(0, str(_SYS))


def _check_llm() -> None:
    prov = os.environ.get("BILLION_LLM_PROVIDER", "stub").lower().strip()
    if prov == "stub" or not os.environ.get("BILLION_LLM_API_KEY", "").strip():
        print(
            "Set BILLION_LLM_PROVIDER=openai (or anthropic) and BILLION_LLM_API_KEY in the repo .env",
            file=sys.stderr,
        )
        print("  Refusing to run: this script is for real model assessment only.", file=sys.stderr)
        sys.exit(2)


STORY1_FILES = [
    ("selfe_of_three1_with_exif.jpg", "image/jpeg"),
    ("receipt1_with_exif.jpg", "image/jpeg"),
    ("screenshot1.jpg", "image/jpeg"),
]
STORY2_FILES = [
    ("photo-tabel2_with_exif.jpg", "image/jpeg"),
    ("receipt2_with_exif.jpg", "image/jpeg"),
    ("table-selfie2_with_exif.jpg", "image/jpeg"),
    ("transaction2_with_exif.jpg", "image/jpeg"),
]


def _load_bundle(name: str, event_id: str) -> "CollectedBundle":
    from billion_hackathon.contracts.collected import CollectedBundle
    from billion_hackathon.modules.data_collection.service import DataCollectionService

    root = _REPO / "Story" / name
    if not root.is_dir():
        print(f"Missing {root}", file=sys.stderr)
        sys.exit(1)

    tmp = _REPO / "hackathon" / ".cache" / "assess_scenarios_uploads"
    tmp.mkdir(parents=True, exist_ok=True)
    svc = DataCollectionService(tmp)
    bundle = CollectedBundle(event_id=event_id)
    files = STORY1_FILES if name == "1" else STORY2_FILES
    for fname, mime in files:
        p = root / fname
        if not p.exists():
            print(f"Missing image {p}", file=sys.stderr)
            sys.exit(1)
        svc.add_upload(bundle, fname, p.read_bytes(), mime)
    return bundle


async def _run_one(story: str) -> None:
    from billion_hackathon.modules.data_ingestion.service import DataIngestionService
    from billion_hackathon.modules.evidence_aggregation.service import EvidenceAggregationService
    from billion_hackathon.modules.graph_builder.service import GraphBuilderService
    from billion_hackathon.modules.computation.engine import compute

    bundle = _load_bundle(
        story,
        "evt_assess_1" if story == "1" else "evt_assess_2",
    )
    prov = os.environ.get("BILLION_LLM_PROVIDER", "").lower()
    model = os.environ.get("BILLION_LLM_MODEL", "default")
    print(f"=== Story {story}  provider={prov}  model={model}  files={len(bundle.items)}", flush=True)

    ingest = DataIngestionService()
    evidence = await ingest.aingest(bundle)
    ev_dump = [e.model_dump(mode="json") for e in evidence.items]
    out_dir = _REPO / "hackathon" / ".cache" / "assess_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_tag = f"story{story}"
    (out_dir / f"{run_tag}_evidence.json").write_text(
        json.dumps({"event_id": evidence.event_id, "items": ev_dump}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Wrote {out_dir / f'{run_tag}_evidence.json'}")

    from collections import Counter

    ekind = Counter(e.kind for e in evidence.items)
    print("  evidence kinds:", dict(ekind), f"  items={len(evidence.items)}")

    agg = EvidenceAggregationService()
    try:
        blueprint = agg.aggregate(evidence)
    except Exception as ex:  # noqa: BLE001 — assessment script: show any failure
        print("  AGGREGATE ERROR:", ex, file=sys.stderr)
        raise
    bp_dump = blueprint.model_dump(mode="json")
    (out_dir / f"{run_tag}_blueprint.json").write_text(
        json.dumps(bp_dump, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Wrote {out_dir / f'{run_tag}_blueprint.json'}")

    graph, issues = GraphBuilderService().build(blueprint)
    (out_dir / f"{run_tag}_graph.json").write_text(
        json.dumps(graph, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Wrote {out_dir / f'{run_tag}_graph.json'}")

    persons = [n for n in graph.get("nodes", []) if n.get("kind") == "person"]
    goods = [n for n in graph.get("nodes", []) if n.get("kind") == "good"]
    print(f"  graph: {len(persons)} people, {len(goods)} goods, {len(issues)} inconsistencies")
    for p in persons:
        print("    -", p.get("id"), "|", p.get("display_name"))
    for g in goods:
        print("    -", g.get("id"), "|", g.get("display_name"), "|", g.get("stated_total_cents"))
    if issues:
        for i in issues:
            print("  issue:", i.code, i.severity, i.message[:120])

    result = compute({"nodes": graph["nodes"], "edges": graph["edges"]})
    print("  compute success:", result.get("success"), "suggested_transfers:", len(result.get("suggested_transfers") or []))
    (out_dir / f"{run_tag}_compute.json").write_text(
        json.dumps(result, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    _check_llm()
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", choices=("1", "2", "both"), default="both", help="Which story to run (default: both)")
    ap.add_argument("--no-aggregate", action="store_true", help="Only list env check (for debugging)")
    args = ap.parse_args()
    if args.no_aggregate:
        print("LLM check OK, provider is not stub.")
        return
    if args.story in ("1", "both"):
        asyncio.run(_run_one("1"))
    if args.story in ("2", "both"):
        asyncio.run(_run_one("2"))


if __name__ == "__main__":
    main()
