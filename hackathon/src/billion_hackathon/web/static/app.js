const $ = (id) => document.getElementById(id);

function show(el, data) {
  el.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

async function fetchSession() {
  const r = await fetch("/api/dev/session", { credentials: "same-origin" });
  return r.json();
}

function activateTab(name) {
  document.querySelectorAll(".tab").forEach((b) => {
    const on = b.dataset.tab === name;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".tab-panel").forEach((p) => {
    const on = p.id === `panel-${name}`;
    p.classList.toggle("active", on);
    p.toggleAttribute("hidden", !on);
  });
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => activateTab(btn.dataset.tab));
});

/* --- Collection --- */

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function trunc(s, n) {
  s = String(s ?? "");
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function fmtBytes(b) {
  if (b == null) return "—";
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

function fmtTs(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

function renderCollectionView(bundle) {
  const view = $("collection-view");
  if (!bundle || !bundle.items || bundle.items.length === 0) {
    view.innerHTML = '<p class="empty-state">Nothing collected yet — drop files or add a note above.</p>';
    return;
  }

  const images = bundle.items.filter((i) => i.kind === "image");
  const docs   = bundle.items.filter((i) => i.kind === "file");
  const notes  = bundle.items.filter((i) => i.kind === "note");
  const locs   = images.filter((i) => i.gps_lat != null && i.gps_lon != null);

  let html = '<div class="stat-bar">';
  if (images.length) html += `<span class="stat stat-img">🖼 ${images.length} image${images.length !== 1 ? "s" : ""}</span>`;
  if (docs.length)   html += `<span class="stat stat-doc">📄 ${docs.length} document${docs.length !== 1 ? "s" : ""}</span>`;
  if (notes.length)  html += `<span class="stat stat-note">📝 ${notes.length} note${notes.length !== 1 ? "s" : ""}</span>`;
  if (locs.length)   html += `<span class="stat stat-geo">📍 ${locs.length} with GPS</span>`;
  html += "</div>";

  if (images.length) {
    html += `<div class="cat-section">
      <h3 class="cat-title">Images <span class="cat-count">${images.length}</span></h3>
      <div class="img-grid">`;
    for (const img of images) {
      const exifTs  = fmtTs(img.exif_timestamp);
      const uploadTs = fmtTs(img.created_at);
      const tsLabel = exifTs
        ? `<span class="ts ts-exif" title="EXIF timestamp">📷 ${esc(exifTs)}</span>`
        : `<span class="ts ts-upload" title="Upload time">${esc(uploadTs)}</span>`;
      const gpsHtml = (img.gps_lat != null && img.gps_lon != null)
        ? `<a class="gps-link" href="https://www.openstreetmap.org/?mlat=${img.gps_lat}&mlon=${img.gps_lon}#map=15/${img.gps_lat}/${img.gps_lon}" target="_blank" rel="noopener">
             📍 ${img.gps_lat.toFixed(4)}, ${img.gps_lon.toFixed(4)}
           </a>`
        : "";
      html += `<div class="img-card">
        <div class="img-thumb-wrap">
          <img src="/api/collect/file/${esc(img.id)}" class="img-thumb" alt="${esc(img.original_filename || img.id)}" loading="lazy" />
        </div>
        <div class="img-meta">
          <span class="fname" title="${esc(img.original_filename || "")}">${esc(trunc(img.original_filename || img.id, 22))}</span>
          ${tsLabel}
          ${gpsHtml}
        </div>
      </div>`;
    }
    html += "</div></div>";
  }

  if (docs.length) {
    html += `<div class="cat-section">
      <h3 class="cat-title">Documents <span class="cat-count">${docs.length}</span></h3>
      <div class="doc-list">`;
    for (const doc of docs) {
      const ts = fmtTs(doc.created_at);
      html += `<div class="doc-item">
        <span class="doc-icon">📄</span>
        <span class="fname">${esc(doc.original_filename || doc.id)}</span>
        <span class="fmeta">${esc(fmtBytes(doc.file_size))} · ${esc(doc.mime_type || "unknown")}</span>
        <span class="ts">${esc(ts || "")}</span>
      </div>`;
    }
    html += "</div></div>";
  }

  if (notes.length) {
    html += `<div class="cat-section">
      <h3 class="cat-title">Notes <span class="cat-count">${notes.length}</span></h3>
      <div class="note-list">`;
    for (const note of notes) {
      const ts = fmtTs(note.created_at);
      html += `<div class="note-item">
        <span class="note-text">${esc(note.text || "")}</span>
        <span class="ts">${esc(ts || "")}</span>
      </div>`;
    }
    html += "</div></div>";
  }

  if (locs.length) {
    html += `<div class="cat-section">
      <h3 class="cat-title">Locations <span class="cat-count">${locs.length}</span></h3>
      <div class="loc-list">`;
    for (const img of locs) {
      const ts = fmtTs(img.exif_timestamp || img.created_at);
      html += `<div class="loc-item">
        <a class="gps-link" href="https://www.openstreetmap.org/?mlat=${img.gps_lat}&mlon=${img.gps_lon}#map=15/${img.gps_lat}/${img.gps_lon}" target="_blank" rel="noopener">
          📍 ${img.gps_lat.toFixed(6)}, ${img.gps_lon.toFixed(6)}
        </a>
        <span class="fname">${esc(trunc(img.original_filename || img.id, 24))}</span>
        ${ts ? `<span class="ts">${esc(ts)}</span>` : ""}
      </div>`;
    }
    html += "</div></div>";
  }

  view.innerHTML = html;
}

function updateCollectionUI(bundle) {
  renderCollectionView(bundle);
  $("tx-collection").value = JSON.stringify(bundle, null, 2);
}

async function uploadFiles(fileList) {
  const fd = new FormData();
  for (const f of fileList) fd.append("files", f);
  const r = await fetch("/api/collect/upload", { method: "POST", credentials: "same-origin", body: fd });
  const j = await r.json();
  updateCollectionUI(j.bundle);
}

/* Drop zone */
const dropZone = $("drop-zone");
const filePick = $("file-pick");

dropZone.addEventListener("click", (e) => {
  if (e.target !== filePick && !e.target.closest("label")) filePick.click();
});
dropZone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") filePick.click(); });
dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("drag-over"); });
dropZone.addEventListener("dragleave", (e) => { if (!dropZone.contains(e.relatedTarget)) dropZone.classList.remove("drag-over"); });
dropZone.addEventListener("drop", async (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  if (e.dataTransfer.files.length) await uploadFiles(e.dataTransfer.files);
});
filePick.addEventListener("change", async () => {
  if (filePick.files.length) { await uploadFiles(filePick.files); filePick.value = ""; }
});

$("btn-session-refresh").onclick = async () => {
  const j = await fetchSession();
  updateCollectionUI(j.collected);
};

$("btn-load-scenario1").onclick = async () => {
  const r = await fetch("/api/collect/scenario1", { method: "POST", credentials: "same-origin" });
  const j = await r.json();
  updateCollectionUI(j.bundle);
};

$("btn-load-weekend-coll").onclick = async () => {
  const r = await fetch("/api/pipeline/from-example", { method: "POST", credentials: "same-origin" });
  const j = await r.json();
  updateCollectionUI(j.collected);
};

$("btn-clear-coll").onclick = async () => {
  const r = await fetch("/api/collect/clear", { method: "POST", credentials: "same-origin" });
  const j = await r.json();
  updateCollectionUI(j.bundle);
};

$("form-note").onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const r = await fetch("/api/collect/note", { method: "POST", credentials: "same-origin", body: fd });
  const j = await r.json();
  updateCollectionUI(j.bundle);
  e.target.reset();
};

/* --- Ingestion --- */
$("btn-ingest-load-session").onclick = async () => {
  const j = await fetchSession();
  $("tx-ingest-in").value = JSON.stringify({ collected: j.collected }, null, 2);
};

$("btn-ingest-run").onclick = async () => {
  const raw = $("tx-ingest-in").value.trim();
  const body = raw ? JSON.parse(raw) : { collected: null };
  if (body.collected === undefined) body.collected = null;
  const r = await fetch("/api/dev/ingest", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const j = await r.json();
  show($("out-ingest"), j);
};

$("btn-ingest-load-scenario1").onclick = async () => {
  const r = await fetch("/api/scenario1/evidence", { credentials: "same-origin" });
  const j = await r.json();
  if (j.error) { show($("out-ingest"), j); return; }
  $("tx-aggregate-in").value = JSON.stringify(j, null, 2);
  show($("out-ingest"), j);
};

/* --- Aggregation --- */
$("btn-agg-load-session").onclick = async () => {
  const j = await fetchSession();
  if (!j.last_evidence) {
    show($("out-aggregate"), { error: "No last_evidence in session" });
    return;
  }
  $("tx-aggregate-in").value = JSON.stringify(j.last_evidence, null, 2);
};

$("btn-agg-run").onclick = async () => {
  const raw = $("tx-aggregate-in").value.trim();
  const evidence = raw ? JSON.parse(raw) : null;
  const r = await fetch("/api/dev/aggregate", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ evidence }),
  });
  const j = await r.json();
  show($("out-aggregate"), j);
};

/* --- Graph --- */
GraphView.onchange(async (graph) => {
  const r = await fetch("/api/dev/graph/validate", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ graph }),
  });
  const j = await r.json();
  GraphView.load(graph, j.inconsistencies || []);
  show($("out-graph"), graph);
  /* if pipeline result is visible, recompute settlement too */
  if (!$("pipeline-result").hidden) {
    const pr = await fetch("/api/dev/compute", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ graph }),
    });
    const pj = await pr.json();
    renderComputeResult(pj.compute ?? pj, null, $("pipeline-compute-result"));
  }
});

$("btn-graph-load-session-graph").onclick = async () => {
  GraphView.setSlot({ svgId: "graph-svg", editPanelId: "graph-edit-panel", issuesId: "graph-inconsistencies" });
  const j = await fetchSession();
  if (!j.last_graph) {
    show($("out-graph"), { error: "No last_graph in session — run Build graph first" });
    return;
  }
  GraphView.load(j.last_graph, []);
  show($("out-graph"), j.last_graph);
};

$("btn-graph-run").onclick = async () => {
  GraphView.setSlot({ svgId: "graph-svg", editPanelId: "graph-edit-panel", issuesId: "graph-inconsistencies" });
  const raw = $("tx-graph-in").value.trim();
  const blueprint = raw ? JSON.parse(raw) : null;
  const r = await fetch("/api/dev/graph", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blueprint }),
  });
  const j = await r.json();
  if (j.graph) {
    GraphView.load(j.graph, j.inconsistencies || []);
    show($("out-graph"), j.graph);
  } else {
    show($("out-graph"), j);
  }
};

/* --- Compute result renderer --- */
function fmtEur(cents) {
  if (cents == null) return "—";
  const abs = Math.abs(cents);
  const s = "€" + (abs / 100).toFixed(2);
  return cents < 0 ? "-" + s : s;
}

function renderComputeResult(result, errorMsg, target) {
  const el = target || $("compute-result");
  if (!result || errorMsg) {
    el.innerHTML = `<p class="compute-error">${esc(errorMsg || "Unknown error")}</p>`;
    return;
  }
  if (!result.success) {
    const errs = (result.errors || []).map(e =>
      `<div class="compute-error-item"><strong>${esc(e.code)}</strong>: ${esc(e.message)}</div>`
    ).join("");
    el.innerHTML = `<div class="compute-errors"><p class="compute-error">Computation failed:</p>${errs}</div>`;
    return;
  }

  const persons = result.per_person || [];
  const transfers = result.suggested_transfers || [];

  const cards = persons.map(p => {
    const net = p.net_cents;
    const cls = net > 0 ? "creditor" : net < 0 ? "debtor" : "balanced";
    const netLabel = net > 0 ? `+${fmtEur(net)}` : fmtEur(net);
    return `<div class="person-card ${cls}">
      <div class="person-card-name">${esc(p.display_name || p.person_id)}</div>
      <div class="person-card-rows">
        <span class="pcr-label">paid</span><span class="pcr-val">${fmtEur(p.paid_out_cents)}</span>
        <span class="pcr-label">share</span><span class="pcr-val">${fmtEur(p.fair_share_owed_cents)}</span>
        <span class="pcr-label">net</span><span class="pcr-val net-${cls}">${netLabel}</span>
      </div>
    </div>`;
  }).join("");

  const txRows = transfers.length
    ? transfers.map(t =>
        `<div class="transfer-row">
          <span class="tr-from">${esc(t.from_person_id)}</span>
          <span class="tr-arrow">→</span>
          <span class="tr-to">${esc(t.to_person_id)}</span>
          <span class="tr-amount">${fmtEur(t.amount_cents)}</span>
        </div>`
      ).join("")
    : `<p class="compute-balanced">All settled — no transfers needed.</p>`;

  el.innerHTML = `
    <div class="compute-result">
      <div class="person-cards">${cards}</div>
      <div class="transfers-section">
        <h3 class="transfers-title">Suggested transfers</h3>
        <div class="transfers-list">${txRows}</div>
      </div>
    </div>`;
}

/* --- Compute --- */
async function resolveGraph() {
  const override = $("tx-compute-in").value.trim();
  if (override) return JSON.parse(override);
  const live = GraphView.getGraph();
  if (live && live.nodes && live.nodes.length > 0) return { nodes: live.nodes, edges: live.edges };
  const j = await fetchSession();
  if (j.last_graph) return { nodes: j.last_graph.nodes, edges: j.last_graph.edges };
  return null;
}

$("btn-compute-run").onclick = async () => {
  const graph = await resolveGraph();
  if (!graph) {
    renderComputeResult(null, "No graph available — build one in the Graph tab first.");
    return;
  }
  const r = await fetch("/api/dev/compute", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ graph }),
  });
  const j = await r.json();
  renderComputeResult(j.compute ?? j);
  show($("out-compute"), j.compute ?? j);
};

/* --- Pipeline (Run tab) --- */
$("btn-pipeline-scenario1").onclick = async () => {
  const r = await fetch("/api/collect/scenario1", { method: "POST", credentials: "same-origin" });
  const j = await r.json();
  renderCollectionView(j.bundle);
  $("pipeline-collection-view").innerHTML = document.getElementById("collection-view").innerHTML;
};

$("btn-pipeline-clear").onclick = async () => {
  const r = await fetch("/api/collect/clear", { method: "POST", credentials: "same-origin" });
  const j = await r.json();
  updateCollectionUI(j.bundle);
  $("pipeline-collection-view").innerHTML = "";
  $("pipeline-result").hidden = true;
};

$("btn-pipeline-run").onclick = async () => {
  const btn = $("btn-pipeline-run");
  btn.disabled = true;
  btn.textContent = "Running…";
  try {
    const r = await fetch("/api/pipeline/run", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const j = await r.json();
    const graph = j.last_graph;
    const issues = j.inconsistencies || [];
    const computeData = j.compute;

    if (graph) {
      GraphView.setSlot({ svgId: "pipeline-svg", editPanelId: "pipeline-edit-panel", issuesId: "pipeline-graph-issues" });
      GraphView.load(graph, issues);
    }
    if (computeData) renderComputeResult(computeData, null, $("pipeline-compute-result"));
    $("pipeline-result").hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Run";
  }
};

$("btn-pipeline-recompute").onclick = async () => {
  const graph = GraphView.getGraph();
  if (!graph || !graph.nodes || graph.nodes.length === 0) {
    renderComputeResult(null, "No graph — run the pipeline first.", $("pipeline-compute-result"));
    return;
  }
  const r = await fetch("/api/dev/compute", {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ graph }),
  });
  const j = await r.json();
  renderComputeResult(j.compute ?? j, null, $("pipeline-compute-result"));
};

/* boot */
activateTab("collection");
fetchSession().then((j) => updateCollectionUI(j.collected));
