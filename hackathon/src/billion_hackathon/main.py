"""FastAPI entry: dev UI (tabs per module) + JSON API."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from billion_hackathon.contracts.collected import CollectedBundle
from billion_hackathon.contracts.evidence import EvidenceBundle
from billion_hackathon.contracts.graph_blueprint import GraphBlueprint
from billion_hackathon.modules.computation.engine import compute
from billion_hackathon.modules.data_collection.service import DataCollectionService
from billion_hackathon.modules.data_ingestion.service import DataIngestionService
from billion_hackathon.modules.evidence_aggregation.service import EvidenceAggregationService
from billion_hackathon.modules.graph_builder.service import GraphBuilderService
from billion_hackathon.modules.llm.client import ChatMessage, get_llm_client

PKG = Path(__file__).resolve().parent
HACKATHON_DIR = PKG.parent.parent
REPO_ROOT = HACKATHON_DIR.parent
# Tokens and keys: copy repo-root `.env.example` → `.env` (never commit `.env`).
load_dotenv(REPO_ROOT / ".env")
WEB = PKG / "web"
UPLOAD_ROOT = HACKATHON_DIR / "var" / "uploads"
STORY1_DIR = REPO_ROOT / "Story" / "1"

templates = Jinja2Templates(directory=str(WEB / "templates"))

app = FastAPI(title="Billion hackathon", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(WEB / "static")), name="static")


@dataclass
class HackathonSession:
    bundle: CollectedBundle
    last_evidence: EvidenceBundle | None = None
    last_blueprint: GraphBlueprint | None = None
    last_graph: dict[str, Any] | None = None


app.state.sessions: dict[str, HackathonSession] = {}


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

    ingest = DataIngestionService().ingest(s.bundle)
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

    ingest = DataIngestionService().ingest(s.bundle)
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
    ingest = DataIngestionService().ingest(bundle)
    s.last_evidence = ingest
    return _set_cookie(
        JSONResponse({"session_id": sid, "evidence": ingest.model_dump(mode="json")}),
        sid,
    )


class DevAggregateBody(BaseModel):
    evidence: EvidenceBundle | None = None


@app.post("/api/dev/aggregate")
async def dev_aggregate(request: Request, body: DevAggregateBody) -> JSONResponse:
    sid, s = _get_session(request, None)
    ev = body.evidence if body.evidence is not None else s.last_evidence
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
    if bp is None:
        return _set_cookie(
            JSONResponse(
                {"error": "No blueprint: paste JSON or run Aggregate first"},
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
