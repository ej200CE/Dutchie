"""When the LLM is in stub mode, real vision is skipped — return story-aligned evidence.

This keeps `Load scenario 1/2` + Ingest + Aggregate aligned with `Story/1/Story1.md` and
`Story/2/Story2.md` (three friends at a bar; four at a restaurant) without an API key.
If `BILLION_LLM_PROVIDER` is not stub, this module is not used and real images are sent to the model.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from billion_hackathon.contracts.collected import CollectedBundle
from billion_hackathon.contracts.evidence import EvidenceBundle
from billion_hackathon.modules.llm.client import StubLLMClient, get_llm_client

log = logging.getLogger("billion.ingest")

_PKG = Path(__file__).resolve().parent.parent
_EXAMPLES = _PKG / "evidence_aggregation" / "examples"

# Filenames as uploaded by `/api/collect/scenario1` and `scenario1/ingest` (order = processing order)
SCENARIO1_FILES: tuple[str, ...] = (
    "selfe_of_three1_with_exif.jpg",
    "receipt1_with_exif.jpg",
    "screenshot1.jpg",
)
SCENARIO2_FILES: tuple[str, ...] = (
    "photo-tabel2_with_exif.jpg",
    "receipt2_with_exif.jpg",
    "table-selfie2_with_exif.jpg",
    "transaction2_with_exif.jpg",
)

_STORY1_NAME = "story1_artifact_evidence.json"
_STORY2_NAME = "story2_artifact_evidence.json"


def _ordered_collected_image_ids(
    bundle: CollectedBundle, expected: tuple[str, ...]
) -> list[str] | None:
    by_name: dict[str, str] = {}
    for it in bundle.items:
        if it.kind != "image" or not it.original_filename:
            continue
        by_name[it.original_filename] = it.id
    for name in expected:
        if name not in by_name:
            return None
    # Allow extra items only if we have at least the expected set; require exact set for images
    names = set(by_name)
    if names != set(expected):
        return None
    return [by_name[n] for n in expected]


def _load_template(name: str) -> dict:
    p = _EXAMPLES / name
    return json.loads(p.read_text(encoding="utf-8"))


def _rewire_source_ids(items: list[dict], source_ids: list[str]) -> None:
    for i, ev in enumerate(items):
        if i < len(source_ids):
            ev["source_item_ids"] = [source_ids[i]]


def scenario_stub_evidence_if_applicable(bundle: CollectedBundle) -> EvidenceBundle | None:
    """If bundle matches S1 or S2 exactly and the LLM is stub, return rich evidence; else None."""
    if not isinstance(get_llm_client(), StubLLMClient):
        return None

    s1 = _ordered_collected_image_ids(bundle, SCENARIO1_FILES)
    if s1 is not None and len(s1) == 3:
        data = _load_template(_STORY1_NAME)
        _rewire_source_ids(data["items"], s1)
        data["event_id"] = bundle.event_id
        log.info("stub: using %s (Story 1 — three friends, one round of beers)", _STORY1_NAME)
        return EvidenceBundle.model_validate(data)

    s2 = _ordered_collected_image_ids(bundle, SCENARIO2_FILES)
    if s2 is not None and len(s2) == 4:
        data = _load_template(_STORY2_NAME)
        _rewire_source_ids(data["items"], s2)
        data["event_id"] = bundle.event_id
        log.info("stub: using %s (Story 2 — four friends, one restaurant bill)", _STORY2_NAME)
        return EvidenceBundle.model_validate(data)

    return None
