"""FastAPI demo: load fixtures, stub ingestion, graph patch, compute."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.compute_engine import compute
from app.demo_data import load_json, run_stub_ingestion
from app.graph_service import GraphState

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR.parent / "templates"))

app = FastAPI(title="Billion demo prototype", version="0.1.0")


class Session:
    event: dict | None = None
    evidences: list = []
    graph: GraphState | None = None
    compute_result: dict | None = None
    compute_locked: bool = False
    last_error: str | None = None


session = Session()


def _ctx(request: Request) -> dict:
    return {
        "request": request,
        "event": session.event,
        "evidences": session.evidences,
        "graph": session.graph.to_snapshot() if session.graph else None,
        "compute": session.compute_result,
        "locked": session.compute_locked,
        "error": session.last_error,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    session.last_error = None
    return templates.TemplateResponse(request, "index.html", _ctx(request))


@app.post("/actions/reset")
async def reset(request: Request):
    session.event = None
    session.evidences = []
    session.graph = None
    session.compute_result = None
    session.compute_locked = False
    session.last_error = None
    return RedirectResponse("/", status_code=303)


@app.post("/actions/load-event")
async def load_event(request: Request):
    session.last_error = None
    session.event = load_json("event-sample.json")  # type: ignore[assignment]
    if not session.graph:
        session.graph = GraphState(session.event["event_id"])
    else:
        session.graph.event_id = session.event["event_id"]
    return RedirectResponse("/", status_code=303)


@app.post("/actions/ingest-stubs")
async def ingest_stubs(request: Request):
    session.last_error = None
    if not session.event:
        session.last_error = "Load event first."
        return RedirectResponse("/", status_code=303)
    try:
        session.evidences = run_stub_ingestion(session.event)
    except Exception as e:  # noqa: BLE001
        session.last_error = str(e)
    return RedirectResponse("/", status_code=303)


@app.post("/actions/load-graph-sample")
async def load_graph_sample(request: Request):
    session.last_error = None
    if not session.event:
        session.event = load_json("event-sample.json")  # type: ignore[assignment]
    g = load_json("graph-sample.json")
    session.graph = GraphState(g["event_id"])
    session.graph.load_snapshot(g)
    session.compute_result = None
    session.compute_locked = False
    return RedirectResponse("/", status_code=303)


@app.post("/actions/apply-graph-patch")
async def apply_graph_patch(request: Request):
    session.last_error = None
    if not session.event:
        session.event = load_json("event-sample.json")  # type: ignore[assignment]
    patch = load_json("graph-patch-sample.json")
    if not session.graph:
        session.graph = GraphState(patch["event_id"])
    errs = session.graph.apply_patch(patch)
    if errs:
        session.last_error = "; ".join(errs)
    session.compute_result = None
    session.compute_locked = False
    return RedirectResponse("/", status_code=303)


@app.post("/actions/compute")
async def run_compute(request: Request):
    session.last_error = None
    if session.compute_locked:
        session.last_error = "Compute already run (demo: graph locked)."
        return RedirectResponse("/", status_code=303)
    if not session.graph:
        session.last_error = "No graph loaded."
        return RedirectResponse("/", status_code=303)
    session.compute_result = compute(session.graph.to_snapshot())
    if session.compute_result.get("success"):
        session.compute_locked = True
    else:
        session.last_error = str(session.compute_result.get("errors"))
    return RedirectResponse("/", status_code=303)


@app.get("/api/state")
async def api_state():
    return JSONResponse(
        {
            "event": session.event,
            "evidences": session.evidences,
            "graph": session.graph.to_snapshot() if session.graph else None,
            "compute": session.compute_result,
            "compute_locked": session.compute_locked,
            "error": session.last_error,
        }
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
