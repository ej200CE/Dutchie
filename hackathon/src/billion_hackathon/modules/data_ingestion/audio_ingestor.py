"""Ingest audio CollectedItems via transcription, then text extraction."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from billion_hackathon.contracts.collected import CollectedItem
from billion_hackathon.contracts.evidence import EvidenceItem
from billion_hackathon.modules.data_ingestion.document_ingestor import _parse as _parse_doc_llm
from billion_hackathon.modules.data_ingestion.document_ingestor import _stub_from_text
from billion_hackathon.modules.data_ingestion.prompts import DOCUMENT_SYSTEM, DOCUMENT_USER_TMPL
from billion_hackathon.modules.llm.client import ChatMessage, LLMClient

log = logging.getLogger("billion.ingest")

_MAX_AUDIO_BYTES = 12 * 1024 * 1024


class AudioIngestor:
    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def ingest(
        self, item: CollectedItem, *, event_context: dict[str, Any] | None = None
    ) -> list[EvidenceItem]:
        if not item.stored_path:
            return [_fallback(item, "no stored_path")]
        p = Path(item.stored_path)
        if not p.exists():
            return [_fallback(item, "file not found on disk")]
        raw = p.read_bytes()
        if len(raw) > _MAX_AUDIO_BYTES:
            return [_fallback(item, f"audio too large ({len(raw)} bytes)")]

        transcript, mode = _transcribe(item, raw)
        if not transcript.strip():
            return [
                EvidenceItem(
                    id=f"ev-{item.id}",
                    source_item_ids=[item.id],
                    kind="free_text",
                    confidence=0.1,
                    raw_excerpt=f"[audio] unable to transcribe {item.original_filename or item.id}",
                    extra={"audio": {"mode": mode, "duration_hint_sec": None}},
                )
            ]

        if mode in ("stub", "sidecar"):
            out = _stub_from_text(item, transcript)
            for ev in out:
                ex = {**(ev.extra or {})}
                ex["audio"] = {"mode": mode}
                ex["extraction_mode"] = "ocr_assisted"
                ev.extra = ex
                ev.raw_excerpt = (ev.raw_excerpt or transcript)[:350]
            return out

        # Non-stub path: run transcript through same document extraction prompt/parse.
        ev_text = DOCUMENT_USER_TMPL.format(
            filename=item.original_filename or p.name,
            event_context=_event_context_text(event_context),
            content=transcript[:8000],
        )
        resp = self._client.complete(
            [
                ChatMessage(role="system", content=DOCUMENT_SYSTEM),
                ChatMessage(role="user", content=ev_text),
            ],
            max_tokens=2048,
        )
        if resp.model == "stub":
            out = _stub_from_text(item, transcript)
        else:
            out = _parse_doc_llm(item, resp.text)
        for ev in out:
            ex = {**(ev.extra or {})}
            ex["audio"] = {"mode": mode, "transcript_chars": len(transcript)}
            ex["extraction_mode"] = "raw_text_llm"
            ev.extra = ex
            if not ev.raw_excerpt:
                ev.raw_excerpt = transcript[:350]
        return out


def _event_context_text(event_context: dict[str, Any] | None) -> str:
    if not event_context:
        return "none"
    return json.dumps(event_context, ensure_ascii=True)


def _transcribe(item: CollectedItem, raw: bytes) -> tuple[str, str]:
    """Return transcript text and mode."""
    side = _sidecar_transcript(item)
    if side:
        return side, "sidecar"

    provider = os.environ.get("BILLION_LLM_PROVIDER", "stub").lower().strip()
    if provider != "openai" or not os.environ.get("BILLION_LLM_API_KEY", "").strip():
        return "", "stub"
    try:
        import httpx
    except Exception:
        return "", "stub"

    base_url = os.environ.get("BILLION_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    api_key = os.environ.get("BILLION_LLM_API_KEY", "")
    model = os.environ.get("BILLION_AUDIO_MODEL", "gpt-4o-mini-transcribe")
    name = item.original_filename or "audio.m4a"
    mime = item.mime_type or "audio/mpeg"
    try:
        r = httpx.post(
            f"{base_url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            data={"model": model},
            files={"file": (name, raw, mime)},
            timeout=90,
        )
        r.raise_for_status()
        data = r.json()
        text = str(data.get("text") or "").strip()
        return text, "openai_stt"
    except Exception as exc:
        log.warning("audio transcription failed: %s", exc)
        return "", "stub"


def _sidecar_transcript(item: CollectedItem) -> str:
    if not item.stored_path:
        return ""
    p = Path(item.stored_path)
    candidates = [
        p.with_suffix(".txt"),
        p.with_suffix(".md"),
        p.with_suffix(".srt"),
    ]
    for c in candidates:
        try:
            if c.exists():
                return c.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            continue
    return ""


def _fallback(item: CollectedItem, reason: str) -> EvidenceItem:
    return EvidenceItem(
        id=f"ev-{item.id}",
        source_item_ids=[item.id],
        kind="free_text",
        confidence=0.0,
        raw_excerpt=f"[audio-ingestor] {reason}",
        extra={"stub": True, "audio": {"mode": "fallback"}},
    )
