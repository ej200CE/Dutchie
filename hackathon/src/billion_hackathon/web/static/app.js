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
$("btn-session-refresh").onclick = async () => {
  const j = await fetchSession();
  $("tx-collection").value = JSON.stringify(j.collected, null, 2);
  show($("out-collection"), { session_id: j.session_id });
};

$("btn-load-weekend-coll").onclick = async () => {
  const r = await fetch("/api/pipeline/from-example", {
    method: "POST",
    credentials: "same-origin",
  });
  const j = await r.json();
  $("tx-collection").value = JSON.stringify(j.collected, null, 2);
  show($("out-collection"), { session_id: j.session_id, loaded: "weekend example" });
};

$("form-note").onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const r = await fetch("/api/collect/note", {
    method: "POST",
    credentials: "same-origin",
    body: fd,
  });
  const j = await r.json();
  $("tx-collection").value = JSON.stringify(j.bundle, null, 2);
  show($("out-collection"), j);
};

$("form-upload").onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const r = await fetch("/api/collect/upload", {
    method: "POST",
    credentials: "same-origin",
    body: fd,
  });
  const j = await r.json();
  $("tx-collection").value = JSON.stringify(j.bundle, null, 2);
  show($("out-collection"), j);
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
$("btn-graph-load-session").onclick = async () => {
  const j = await fetchSession();
  if (!j.last_blueprint) {
    show($("out-graph"), { error: "No last_blueprint in session" });
    return;
  }
  $("tx-graph-in").value = JSON.stringify(j.last_blueprint, null, 2);
};

$("btn-graph-run").onclick = async () => {
  const raw = $("tx-graph-in").value.trim();
  const blueprint = raw ? JSON.parse(raw) : null;
  const r = await fetch("/api/dev/graph", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blueprint }),
  });
  const j = await r.json();
  show($("out-graph"), j);
};

/* --- Compute --- */
$("btn-compute-load-session").onclick = async () => {
  const j = await fetchSession();
  if (!j.last_graph) {
    show($("out-compute"), { error: "No last_graph in session" });
    return;
  }
  const g = { nodes: j.last_graph.nodes, edges: j.last_graph.edges };
  $("tx-compute-in").value = JSON.stringify(g, null, 2);
};

$("btn-compute-run").onclick = async () => {
  const graph = JSON.parse($("tx-compute-in").value || "{}");
  const r = await fetch("/api/dev/compute", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ graph }),
  });
  const j = await r.json();
  show($("out-compute"), j);
};

/* --- LLM --- */
$("btn-llm-sample").onclick = () => {
  $("tx-llm-in").value = JSON.stringify(
    {
      messages: [
        { role: "system", content: "You extract expense hints as JSON." },
        {
          role: "user",
          content: "Alice paid €120 for groceries; Bob and Carol split.",
        },
      ],
    },
    null,
    2,
  );
};

$("btn-llm-run").onclick = async () => {
  const body = JSON.parse($("tx-llm-in").value || "{}");
  const r = await fetch("/api/dev/llm", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const j = await r.json();
  show($("out-llm"), j);
};

/* --- Pipeline --- */
$("btn-example").onclick = async () => {
  const r = await fetch("/api/pipeline/from-example", {
    method: "POST",
    credentials: "same-origin",
  });
  show($("out-pipeline"), await r.json());
};

$("btn-run").onclick = async () => {
  const note = $("tx-pipeline-note").value.trim() || null;
  const r = await fetch("/api/pipeline/run", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  show($("out-pipeline"), await r.json());
};

/* boot */
activateTab("collection");
fetchSession().then((j) => {
  $("tx-collection").value = JSON.stringify(j.collected, null, 2);
});
