"""FastAPI entry: dev UI (tabs per module) + JSON API."""

from __future__ import annotations

import base64
import io
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("billion.main")

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator
from PIL import Image

from billion_hackathon.contracts.collected import CollectedBundle
from billion_hackathon.contracts.evidence import EvidenceBundle
from billion_hackathon.contracts.graph_blueprint import GraphBlueprint
from billion_hackathon.modules.computation.engine import compute
from billion_hackathon.modules.data_collection.service import DataCollectionService
from billion_hackathon.modules.data_ingestion.image_ocr import (
    classify_image_hint,
    extract_ocr_text,
)
from billion_hackathon.modules.data_ingestion.image_preprocess import preprocess_image_bytes
from billion_hackathon.modules.data_ingestion.image_segmentation import segment_people
from billion_hackathon.modules.data_ingestion.service import DataIngestionService
from billion_hackathon.modules.evidence_aggregation.service import EvidenceAggregationService
from billion_hackathon.modules.graph_builder.inconsistency import find_inconsistencies
from billion_hackathon.modules.graph_builder.service import GraphBuilderService
from billion_hackathon.modules.llm.client import ChatMessage, get_llm_client

PKG = Path(__file__).resolve().parent
HACKATHON_DIR = PKG.parent.parent
REPO_ROOT = HACKATHON_DIR.parent
# Tokens and keys: copy repo-root `.env.example` → `.env` (never commit `.env`).
load_dotenv(REPO_ROOT / ".env")
WEB = PKG / "web"
UPLOAD_ROOT = HACKATHON_DIR / "var" / "uploads"
SCENARIO_CACHE_FILE = HACKATHON_DIR / "var" / "scenario_cache.json"
STORY1_DIR = REPO_ROOT / "Story" / "1"
STORY2_DIR = REPO_ROOT / "Story" / "2"

templates = Jinja2Templates(directory=str(WEB / "templates"))

app = FastAPI(title="Billion hackathon", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(WEB / "static")), name="static")


@dataclass
class HackathonSession:
    bundle: CollectedBundle
    last_evidence: EvidenceBundle | None = None
    last_blueprint: GraphBlueprint | None = None
    last_graph: dict[str, Any] | None = None


def _load_scenario_cache() -> dict[str, Any]:
    if SCENARIO_CACHE_FILE.exists():
        try:
            return json.loads(SCENARIO_CACHE_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_scenario_cache(cache: dict[str, Any]) -> None:
    SCENARIO_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCENARIO_CACHE_FILE.write_text(json.dumps(cache, indent=2))


app.state.sessions: dict[str, HackathonSession] = {}
app.state.scenario_cache: dict[str, Any] = _load_scenario_cache()


def _get_session(request: Request, session_id: str | None) -> tuple[str, HackathonSession]:
    sid = session_id or request.cookies.get("session_id")
    if not sid or sid not in app.state.sessions:
        sid = uuid.uuid4().hex
        app.state.sessions[sid] = HackathonSession(
            CollectedBundle(event_id=f"evt_{sid[:8]}"),
        )
    return sid, app.state.sessions[sid]


def _session_payload(s: HackathonSession) -> dict[str, Any]:
    return {
        "collected": s.bundle.model_dump(mode="json"),
        "last_evidence": s.last_evidence.model_dump(mode="json") if s.last_evidence else None,
        "last_blueprint": s.last_blueprint.model_dump(mode="json") if s.last_blueprint else None,
        "last_graph": s.last_graph,
    }


def _set_cookie(resp: JSONResponse, sid: str) -> JSONResponse:
    resp.set_cookie("session_id", sid, httponly=True, samesite="lax")
    return resp


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"title": "Billion hackathon · dev"},
    )


@app.get("/api/dev/session")
async def dev_session(request: Request) -> JSONResponse:
    sid, s = _get_session(request, None)
    return _set_cookie(JSONResponse({"session_id": sid, **_session_payload(s)}), sid)


class PipelineBody(BaseModel):
    event_id: str | None = None
    note: str | None = None


@app.post("/api/pipeline/run")
async def run_pipeline(request: Request, body: PipelineBody) -> JSONResponse:
    sid, s = _get_session(request, None)
    if body.event_id:
        s.bundle.event_id = body.event_id
    if body.note:
        DataCollectionService(UPLOAD_ROOT).add_note(s.bundle, body.note)

    ingest = await DataIngestionService().aingest(s.bundle)
    blueprint = EvidenceAggregationService().aggregate(ingest)
    graph, issues = GraphBuilderService().build(blueprint)
    result = compute({"nodes": graph["nodes"], "edges": graph["edges"]})

    s.last_evidence = ingest
    s.last_blueprint = blueprint
    s.last_graph = graph

    payload = {
        "session_id": sid,
        **_session_payload(s),
        "inconsistencies": [i.model_dump() for i in issues],
        "compute": result,
    }
    return _set_cookie(JSONResponse(payload), sid)


@app.post("/api/collect/note")
async def collect_note(
    request: Request,
    session_id: str | None = Form(None),
    text: str = Form(...),
) -> JSONResponse:
    sid, s = _get_session(request, session_id)
    DataCollectionService(UPLOAD_ROOT).add_note(s.bundle, text)
    return _set_cookie(
        JSONResponse({"session_id": sid, "bundle": s.bundle.model_dump(mode="json")}),
        sid,
    )


@app.post("/api/collect/upload")
async def collect_upload(
    request: Request,
    session_id: str | None = Form(None),
    files: list[UploadFile] = File(...),
) -> JSONResponse:
    sid, s = _get_session(request, session_id)
    svc = DataCollectionService(UPLOAD_ROOT)
    for file in files:
        content = await file.read()
        svc.add_upload(s.bundle, file.filename or "upload", content, file.content_type)
    return _set_cookie(
        JSONResponse({"session_id": sid, "bundle": s.bundle.model_dump(mode="json")}),
        sid,
    )


@app.get("/api/collect/file/{item_id}", response_model=None)
async def get_collected_file(item_id: str, request: Request):
    _, s = _get_session(request, None)
    item = next((i for i in s.bundle.items if i.id == item_id), None)
    if item is None or not item.stored_path:
        return JSONResponse({"error": "not found"}, status_code=404)
    path = Path(item.stored_path)
    if not path.exists():
        return JSONResponse({"error": "file not on disk"}, status_code=404)
    return FileResponse(str(path), media_type=item.mime_type or "application/octet-stream")


@app.post("/api/collect/scenario1")
async def collect_scenario1(request: Request) -> JSONResponse:
    sid, s = _get_session(request, None)
    s.bundle.items.clear()
    s.last_evidence = None
    s.last_blueprint = None
    s.last_graph = None
    svc = DataCollectionService(UPLOAD_ROOT)
    for fname, mime in [
        ("selfe_of_three1_with_exif.jpg", "image/jpeg"),
        ("receipt1_with_exif.jpg", "image/jpeg"),
        ("screenshot1.jpg", "image/jpeg"),
    ]:
        path = STORY1_DIR / fname
        if path.exists():
            svc.add_upload(s.bundle, fname, path.read_bytes(), mime)
    return _set_cookie(
        JSONResponse({"session_id": sid, "bundle": s.bundle.model_dump(mode="json")}),
        sid,
    )


@app.post("/api/scenario1/ingest")
async def scenario1_ingest(request: Request) -> JSONResponse:
    sid, s = _get_session(request, None)
    svc = DataCollectionService(UPLOAD_ROOT)
    s.bundle.items.clear()
    for fname, mime in [
        ("selfe_of_three1_with_exif.jpg", "image/jpeg"),
        ("receipt1_with_exif.jpg", "image/jpeg"),
        ("screenshot1.jpg", "image/jpeg"),
    ]:
        path = STORY1_DIR / fname
        if path.exists():
            svc.add_upload(s.bundle, fname, path.read_bytes(), mime)
    evidence = await DataIngestionService().aingest(s.bundle)
    s.last_evidence = evidence
    s.last_blueprint = None
    s.last_graph = None
    app.state.scenario_cache["1_evidence"] = evidence.model_dump(mode="json")
    _save_scenario_cache(app.state.scenario_cache)
    return _set_cookie(
        JSONResponse({
            "session_id": sid,
            "bundle": s.bundle.model_dump(mode="json"),
            "evidence": app.state.scenario_cache["1_evidence"],
        }),
        sid,
    )


@app.get("/api/scenario1/evidence")
async def scenario1_evidence(request: Request) -> JSONResponse:
    cached = app.state.scenario_cache.get("1_evidence")
    if cached is None:
        return JSONResponse({"error": "No scenario 1 evidence cached — run it first"}, status_code=404)
    return JSONResponse(cached)


_STORY2_FILES = [
    ("photo-tabel2_with_exif.jpg", "image/jpeg"),
    ("receipt2_with_exif.jpg", "image/jpeg"),
    ("table-selfie2_with_exif.jpg", "image/jpeg"),
    ("transaction2_with_exif.jpg", "image/jpeg"),
]


@app.post("/api/collect/scenario2")
async def collect_scenario2(request: Request) -> JSONResponse:
    sid, s = _get_session(request, None)
    s.bundle.items.clear()
    s.last_evidence = None
    s.last_blueprint = None
    s.last_graph = None
    svc = DataCollectionService(UPLOAD_ROOT)
    for fname, mime in _STORY2_FILES:
        path = STORY2_DIR / fname
        if path.exists():
            svc.add_upload(s.bundle, fname, path.read_bytes(), mime)
    return _set_cookie(
        JSONResponse({"session_id": sid, "bundle": s.bundle.model_dump(mode="json")}),
        sid,
    )


@app.post("/api/scenario2/ingest")
async def scenario2_ingest(request: Request) -> JSONResponse:
    sid, s = _get_session(request, None)
    svc = DataCollectionService(UPLOAD_ROOT)
    s.bundle.items.clear()
    for fname, mime in _STORY2_FILES:
        path = STORY2_DIR / fname
        if path.exists():
            svc.add_upload(s.bundle, fname, path.read_bytes(), mime)
    evidence = await DataIngestionService().aingest(s.bundle)
    s.last_evidence = evidence
    s.last_blueprint = None
    s.last_graph = None
    app.state.scenario_cache["2_evidence"] = evidence.model_dump(mode="json")
    _save_scenario_cache(app.state.scenario_cache)
    return _set_cookie(
        JSONResponse({
            "session_id": sid,
            "bundle": s.bundle.model_dump(mode="json"),
            "evidence": app.state.scenario_cache["2_evidence"],
        }),
        sid,
    )


@app.get("/api/scenario2/evidence")
async def scenario2_evidence(request: Request) -> JSONResponse:
    cached = app.state.scenario_cache.get("2_evidence")
    if cached is None:
        return JSONResponse({"error": "No scenario 2 evidence cached — run it first"}, status_code=404)
    return JSONResponse(cached)


@app.post("/api/collect/clear")
async def collect_clear(request: Request) -> JSONResponse:
    sid, s = _get_session(request, None)
    s.bundle.items.clear()
    s.last_evidence = None
    s.last_blueprint = None
    s.last_graph = None
    return _set_cookie(
        JSONResponse({"session_id": sid, "bundle": s.bundle.model_dump(mode="json")}),
        sid,
    )


@app.post("/api/pipeline/from-example")
async def pipeline_from_example(request: Request) -> JSONResponse:
    raw = json.loads(
        (PKG / "modules" / "data_collection" / "examples" / "artifact_bundle.json").read_text()
    )
    bundle = CollectedBundle.model_validate(raw)
    sid = uuid.uuid4().hex
    s = HackathonSession(bundle)
    app.state.sessions[sid] = s

    ingest = await DataIngestionService().aingest(s.bundle)
    blueprint = EvidenceAggregationService().aggregate(ingest)
    graph, issues = GraphBuilderService().build(blueprint)
    result = compute({"nodes": graph["nodes"], "edges": graph["edges"]})

    s.last_evidence = ingest
    s.last_blueprint = blueprint
    s.last_graph = graph

    payload = {
        "session_id": sid,
        "inconsistencies": [i.model_dump() for i in issues],
        "compute": result,
        **_session_payload(s),
    }
    return _set_cookie(JSONResponse(payload), sid)


# --- Per-module dev endpoints (tabs) ---


class DevIngestBody(BaseModel):
    collected: CollectedBundle | None = None


@app.post("/api/dev/ingest")
async def dev_ingest(request: Request, body: DevIngestBody) -> JSONResponse:
    sid, s = _get_session(request, None)
    bundle = body.collected if body.collected is not None else s.bundle
    ingest = await DataIngestionService().aingest(bundle)
    s.last_evidence = ingest
    s.last_blueprint = None   # new evidence invalidates old blueprint
    s.last_graph = None       # and old graph
    return _set_cookie(
        JSONResponse({"session_id": sid, "evidence": ingest.model_dump(mode="json")}),
        sid,
    )


@app.post("/api/dev/ingest/audio_preview")
async def dev_ingest_audio_preview(request: Request) -> JSONResponse:
    sid, s = _get_session(request, None)
    audio_items = [it for it in s.bundle.items if it.kind == "audio"]
    if not audio_items:
        return _set_cookie(
            JSONResponse({"session_id": sid, "error": "No audio item in session bundle"}, status_code=404),
            sid,
        )
    last = audio_items[-1]
    one = CollectedBundle(event_id=s.bundle.event_id, items=[last])
    ev = await DataIngestionService().aingest(one)
    return _set_cookie(
        JSONResponse(
            {
                "session_id": sid,
                "audio_item_id": last.id,
                "audio_filename": last.original_filename,
                "evidence": ev.model_dump(mode="json"),
            }
        ),
        sid,
    )


@app.post("/api/dev/preprocess/inspect")
async def dev_preprocess_inspect(request: Request) -> JSONResponse:
    sid, s = _get_session(request, None)
    tasks = [asyncio.to_thread(_inspect_preprocess_item, it) for it in s.bundle.items]
    rows = await asyncio.gather(*tasks)
    return _set_cookie(JSONResponse({"session_id": sid, "items": rows}), sid)


def _inspect_preprocess_item(it) -> dict[str, Any]:
    t0 = time.perf_counter()
    log.info("preprocess.inspect start item=%s filename=%s kind=%s", it.id, it.original_filename, it.kind)
    if it.kind != "image" or not it.stored_path:
        out = {
            "item_id": it.id,
            "kind": it.kind,
            "filename": it.original_filename,
            "note": "no image preprocessing for this kind",
        }
        log.info(
            "preprocess.inspect done item=%s filename=%s elapsed_ms=%d note=no-image",
            it.id,
            it.original_filename,
            int((time.perf_counter() - t0) * 1000),
        )
        return out
    p = Path(it.stored_path)
    if not p.exists():
        out = {
            "item_id": it.id,
            "kind": it.kind,
            "filename": it.original_filename,
            "error": "file not found",
        }
        log.info(
            "preprocess.inspect done item=%s filename=%s elapsed_ms=%d error=file-not-found",
            it.id,
            it.original_filename,
            int((time.perf_counter() - t0) * 1000),
        )
        return out
    raw = p.read_bytes()
    t_pre = time.perf_counter()
    processed, processed_mime, diag = preprocess_image_bytes(
        raw,
        mime_type=it.mime_type or "image/jpeg",
        original_filename=it.original_filename,
    )
    pre_ms = int((time.perf_counter() - t_pre) * 1000)
    t_ocr = time.perf_counter()
    ocr_text, ocr_meta = extract_ocr_text(processed)
    ocr_ms = int((time.perf_counter() - t_ocr) * 1000)
    hint = classify_image_hint(it.original_filename, ocr_text)
    t_seg = time.perf_counter()
    seg_meta, seg_preview_raw, seg_preview_mime = segment_people(processed)
    seg_ms = int((time.perf_counter() - t_seg) * 1000)
    out = {
        "item_id": it.id,
        "kind": it.kind,
        "filename": it.original_filename,
        "mime_type": it.mime_type,
        "original_url": f"/api/collect/file/{it.id}",
        "processed_preview_data_url": _preview_data_url(processed, processed_mime),
        "segmentation_preview_data_url": _preview_data_url(seg_preview_raw, seg_preview_mime),
        "segmentation_meta": seg_meta,
        "preprocess": diag,
        "ocr_meta": ocr_meta,
        "ocr_text_head": (ocr_text[:600] if ocr_text else ""),
        "image_type_hint_local": hint,
    }
    total_ms = int((time.perf_counter() - t0) * 1000)
    log.info(
        "preprocess.inspect done item=%s filename=%s elapsed_ms=%d pre_ms=%d ocr_ms=%d seg_ms=%d ocr_engine=%s seg_engine=%s people=%s",
        it.id,
        it.original_filename,
        total_ms,
        pre_ms,
        ocr_ms,
        seg_ms,
        (ocr_meta or {}).get("engine", "none"),
        (seg_meta or {}).get("engine", "none"),
        (seg_meta or {}).get("people_count", 0),
    )
    return out


def _preview_data_url(raw: bytes, mime: str) -> str:
    try:
        with Image.open(io.BytesIO(raw)) as img:
            thumb = img.convert("RGB")
            thumb.thumbnail((360, 360))
            buf = io.BytesIO()
            # Use PNG for inspector preview to avoid JPEG artifacts on screenshots.
            thumb.save(buf, format="PNG", optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/png;base64,{b64}"
    except Exception:
        b64 = base64.b64encode(raw[:120000]).decode("ascii")
        return f"data:{mime};base64,{b64}"


class DevAggregateBody(BaseModel):
    evidence: EvidenceBundle | None = None


@app.post("/api/dev/aggregate")
async def dev_aggregate(request: Request, body: DevAggregateBody) -> JSONResponse:
    sid, s = _get_session(request, None)
    if body.evidence is not None:
        ev = body.evidence
        s.last_evidence = ev          # keep session in sync with whatever was aggregated
    else:
        ev = s.last_evidence
    if ev is None:
        return _set_cookie(
            JSONResponse(
                {"error": "No evidence: paste JSON or run Ingest first"},
                status_code=400,
            ),
            sid,
        )
    blueprint = EvidenceAggregationService().aggregate(ev)
    s.last_blueprint = blueprint
    return _set_cookie(
        JSONResponse({"session_id": sid, "blueprint": blueprint.model_dump(mode="json")}),
        sid,
    )


class DevGraphBody(BaseModel):
    blueprint: GraphBlueprint | None = None


@app.post("/api/dev/graph")
async def dev_graph(request: Request, body: DevGraphBody) -> JSONResponse:
    sid, s = _get_session(request, None)
    bp = body.blueprint if body.blueprint is not None else s.last_blueprint
    if bp is None and s.last_evidence is not None:
        # Auto-aggregate: user skipped the Aggregation tab but evidence is available
        bp = EvidenceAggregationService().aggregate(s.last_evidence)
        s.last_blueprint = bp
    if bp is None:
        return _set_cookie(
            JSONResponse(
                {"error": "No blueprint or evidence in session — run Ingest (tab 2) first"},
                status_code=400,
            ),
            sid,
        )
    graph, issues = GraphBuilderService().build(bp)
    s.last_graph = graph
    return _set_cookie(
        JSONResponse(
            {
                "session_id": sid,
                "graph": graph,
                "inconsistencies": [i.model_dump() for i in issues],
            }
        ),
        sid,
    )


class DevGraphValidateBody(BaseModel):
    graph: dict[str, Any]


@app.post("/api/dev/graph/validate")
async def dev_graph_validate(request: Request, body: DevGraphValidateBody) -> JSONResponse:
    sid, s = _get_session(request, None)
    s.last_graph = body.graph
    issues = find_inconsistencies(body.graph)
    return _set_cookie(
        JSONResponse({"session_id": sid, "inconsistencies": [i.model_dump() for i in issues]}),
        sid,
    )


class DevComputeBody(BaseModel):
    graph: dict[str, Any]

    @field_validator("graph")
    @classmethod
    def _need_nodes_edges(cls, v: dict[str, Any]) -> dict[str, Any]:
        if "nodes" not in v or "edges" not in v:
            raise ValueError("graph must include 'nodes' and 'edges'")
        return v


@app.post("/api/dev/compute")
async def dev_compute(request: Request, body: DevComputeBody) -> JSONResponse:
    sid, _s = _get_session(request, None)
    result = compute(body.graph)
    return _set_cookie(JSONResponse({"session_id": sid, "compute": result}), sid)


class DevLLMBody(BaseModel):
    messages: list[dict[str, str]]


@app.post("/api/dev/llm")
async def dev_llm(request: Request, body: DevLLMBody) -> JSONResponse:
    sid, _s = _get_session(request, None)
    msgs = [ChatMessage(role=m["role"], content=m["content"]) for m in body.messages]
    out = get_llm_client().complete(msgs)
    return _set_cookie(JSONResponse({"session_id": sid, "llm": out.model_dump()}), sid)


@app.get("/api/examples/{name}")
async def get_example(name: str) -> JSONResponse:
    if name != "weekend":
        return JSONResponse({"error": "unknown example"}, status_code=404)
    base = PKG / "modules" / "data_collection" / "examples" / "artifact_bundle.json"
    return JSONResponse(json.loads(base.read_text()))
