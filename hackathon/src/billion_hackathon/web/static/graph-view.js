/**
 * GraphView — D3 v7 force-directed graph for the graph_builder tab.
 *
 * Public API:
 *   GraphView.load(graph, inconsistencies)  — render a fresh graph
 *   GraphView.getGraph()                    — return current editable state
 *   GraphView.onchange(fn)                  — register callback fired after every edit
 */

const GraphView = (() => {
  /* ── palette (Gruvbox dark) ─────────────────────────── */
  const C = {
    personFill:  "#1d3a47",
    personStroke:"#83a598",
    goodFill:    "#3a2e00",
    goodStroke:  "#fabd2f",
    cashFlow:    "#fe8019",
    contrib:     "#8ec07c",
    p2p:         "#d3869b",
    selected:    "#ebdbb2",
    error:       "#fb4934",
    warning:     "#fabd2f",
    fg:          "#ebdbb2",
    fg2:         "#bdae93",
    bg:          "#282828",
    bg1:         "#3c3836",
    bg2:         "#504945",
  };

  /* ── state ──────────────────────────────────────────── */
  let _graph = { event_id: "", nodes: [], edges: [] };
  let _issues = [];
  let _selected = null;     // { type: "node"|"edge", id: string }
  let _changeFn = null;
  let _simulation = null;
  let _slot = { svgId: "graph-svg", editPanelId: "graph-edit-panel", issuesId: "graph-inconsistencies" };

  /* ── helpers ────────────────────────────────────────── */
  const svgEl    = () => document.getElementById(_slot.svgId);
  const panelEl  = () => document.getElementById(_slot.editPanelId);
  const issuesEl = () => document.getElementById(_slot.issuesId);

  function nodeById(id) { return _graph.nodes.find(n => n.id === id); }
  function edgeById(id) { return _graph.edges.find(e => e.edge_id === id); }

  function errorNodeIds() {
    const ids = new Set();
    _issues.forEach(i => (i.node_ids || []).forEach(id => ids.add(id)));
    return ids;
  }
  function errorEdgeIds() {
    const ids = new Set();
    _issues.forEach(i => (i.edge_ids || []).forEach(id => ids.add(id)));
    return ids;
  }

  function fmtCents(c) {
    if (c == null) return "—";
    return "€" + (c / 100).toFixed(2);
  }

  function slugify(s) {
    return s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  }

  function uniqueId(prefix) {
    let i = 1;
    while (_graph.nodes.find(n => n.id === `${prefix}_${i}`)) i++;
    return `${prefix}_${i}`;
  }

  function fireChange() {
    renderInconsistencies(_issues);
    renderEditPanel();
    if (_changeFn) _changeFn(_graph);
  }

  /* ── main render ────────────────────────────────────── */
  function render() {
    const svg = d3.select(svgEl());
    svg.selectAll("*").remove();

    const W = svgEl().clientWidth  || 600;
    const H = svgEl().clientHeight || 360;

    svg.attr("viewBox", `0 0 ${W} ${H}`);

    /* arrow markers */
    const defs = svg.append("defs");
    function mkMarker(id, color) {
      defs.append("marker")
        .attr("id", id)
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 10).attr("refY", 0)
        .attr("markerWidth", 7).attr("markerHeight", 7)
        .attr("orient", "auto")
        .append("path").attr("d", "M0,-5L10,0L0,5").attr("fill", color);
    }
    mkMarker("arrow-cash",   C.cashFlow);
    mkMarker("arrow-contrib",C.contrib);
    mkMarker("arrow-p2p",    C.p2p);
    mkMarker("arrow-error",  C.error);

    const errNodes = errorNodeIds();
    const errEdges = errorEdgeIds();

    /* build simulation node list (D3 mutates x/y in place) */
    const persons = _graph.nodes.filter(n => n.kind === "person");
    const goods   = _graph.nodes.filter(n => n.kind === "good");

    /* initial positions: persons left column, goods right column */
    const colPadY = 60;
    persons.forEach((n, i) => {
      if (n.x == null) { n.x = W * 0.28; n.y = colPadY + i * (H - 2 * colPadY) / Math.max(persons.length, 1); }
    });
    goods.forEach((n, i) => {
      if (n.x == null) { n.x = W * 0.72; n.y = colPadY + i * (H - 2 * colPadY) / Math.max(goods.length, 1); }
    });

    const allNodes = _graph.nodes;

    /* build link list for D3 (by node objects) */
    const linkData = _graph.edges
      .filter(e => e.kind === "cash_flow" || e.kind === "contribution")
      .map(e => {
        const src = e.kind === "cash_flow"
          ? allNodes.find(n => n.id === e.from_id)
          : allNodes.find(n => n.id === e.person_id);
        const tgt = e.kind === "cash_flow"
          ? allNodes.find(n => n.id === e.to_id)
          : allNodes.find(n => n.id === e.good_id);
        return src && tgt ? { source: src, target: tgt, edge: e } : null;
      })
      .filter(Boolean);

    /* simulation */
    if (_simulation) _simulation.stop();
    _simulation = d3.forceSimulation(allNodes)
      .force("link", d3.forceLink(linkData).id(d => d.id).distance(160).strength(0.4))
      .force("charge", d3.forceManyBody().strength(-250))
      .force("cx", d3.forceX(W / 2).strength(0.03))
      .force("cy", d3.forceY(H / 2).strength(0.03))
      .force("colX", d3.forceX()
        .x(d => d.kind === "person" ? W * 0.28 : W * 0.72)
        .strength(0.25))
      .alphaDecay(0.04)
      .on("tick", ticked);

    /* groups */
    const gLinks = svg.append("g").attr("class", "links");
    const gNodes = svg.append("g").attr("class", "nodes");

    /* ── edges ── */
    const linkSel = gLinks.selectAll("g.link")
      .data(linkData, d => d.edge.edge_id)
      .enter().append("g").attr("class", "link");

    linkSel.append("line")
      .attr("class", "edge-line")
      .attr("stroke", d => {
        if (errEdges.has(d.edge.edge_id)) return C.error;
        return d.edge.kind === "cash_flow" ? C.cashFlow : C.contrib;
      })
      .attr("stroke-width", d => d.edge.kind === "cash_flow" ? 2 : 1.5)
      .attr("stroke-dasharray", d => d.edge.kind === "contribution" ? "5,3" : null)
      .attr("marker-end", d => {
        if (errEdges.has(d.edge.edge_id)) return "url(#arrow-error)";
        return d.edge.kind === "cash_flow" ? "url(#arrow-cash)" : "url(#arrow-contrib)";
      })
      .attr("cursor", "pointer")
      .on("click", (ev, d) => { ev.stopPropagation(); selectItem("edge", d.edge.edge_id); });

    linkSel.append("text")
      .attr("class", "edge-label")
      .attr("text-anchor", "middle")
      .attr("font-size", "10px")
      .attr("fill", C.fg2)
      .text(d => {
        if (d.edge.kind === "cash_flow") return fmtCents(d.edge.amount_cents);
        return `×${d.edge.value ?? 1}`;
      });

    /* ── nodes ── */
    const nodeSel = gNodes.selectAll("g.node")
      .data(allNodes, d => d.id)
      .enter().append("g")
      .attr("class", "node")
      .attr("cursor", "pointer")
      .call(d3.drag()
        .on("start", (ev, d) => {
          if (!ev.active) _simulation.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on("drag", (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
        .on("end", (ev, d) => {
          if (!ev.active) _simulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        }))
      .on("click", (ev, d) => { ev.stopPropagation(); selectItem("node", d.id); });

    /* person = circle */
    nodeSel.filter(d => d.kind === "person")
      .append("circle")
      .attr("r", 28)
      .attr("fill", C.personFill)
      .attr("stroke", d => errNodes.has(d.id) ? C.error : (_selected?.id === d.id ? C.selected : C.personStroke))
      .attr("stroke-width", d => errNodes.has(d.id) || _selected?.id === d.id ? 3 : 1.5);

    /* good = rectangle */
    nodeSel.filter(d => d.kind === "good")
      .append("rect")
      .attr("x", -45).attr("y", -22).attr("width", 90).attr("height", 44)
      .attr("rx", 6)
      .attr("fill", C.goodFill)
      .attr("stroke", d => errNodes.has(d.id) ? C.error : (_selected?.id === d.id ? C.selected : C.goodStroke))
      .attr("stroke-width", d => errNodes.has(d.id) || _selected?.id === d.id ? 3 : 1.5);

    nodeSel.append("text")
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "middle")
      .attr("font-size", "11px")
      .attr("font-weight", "600")
      .attr("fill", C.fg)
      .text(d => d.display_name || d.id);

    /* amount sub-label for goods */
    nodeSel.filter(d => d.kind === "good" && d.stated_total_cents != null)
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "16px")
      .attr("font-size", "9px")
      .attr("fill", C.goodStroke)
      .text(d => fmtCents(d.stated_total_cents));

    /* deselect on canvas click */
    svg.on("click", () => { _selected = null; renderEditPanel(); renderHighlights(); });

    function ticked() {
      /* clamp nodes inside SVG */
      allNodes.forEach(d => {
        d.x = Math.max(50, Math.min(W - 50, d.x));
        d.y = Math.max(35, Math.min(H - 35, d.y));
      });

      linkSel.select("line")
        .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
        .attr("x2", d => {
          const dx = d.target.x - d.source.x, dy = d.target.y - d.source.y;
          const len = Math.sqrt(dx * dx + dy * dy) || 1;
          const r = d.target.kind === "person" ? 30 : 48;
          return d.target.x - (dx / len) * r;
        })
        .attr("y2", d => {
          const dx = d.target.x - d.source.x, dy = d.target.y - d.source.y;
          const len = Math.sqrt(dx * dx + dy * dy) || 1;
          const r = d.target.kind === "person" ? 30 : 25;
          return d.target.y - (dy / len) * r;
        });

      linkSel.select("text")
        .attr("x", d => (d.source.x + d.target.x) / 2)
        .attr("y", d => (d.source.y + d.target.y) / 2 - 6);

      nodeSel.attr("transform", d => `translate(${d.x},${d.y})`);
    }
  }

  function renderHighlights() {
    const errNodes = errorNodeIds();
    const errEdges = errorEdgeIds();

    d3.select(svgEl()).selectAll("g.node circle, g.node rect")
      .attr("stroke", function() {
        const d = d3.select(this.parentNode).datum();
        if (errNodes.has(d.id)) return C.error;
        if (_selected?.type === "node" && _selected.id === d.id) return C.selected;
        return d.kind === "person" ? C.personStroke : C.goodStroke;
      })
      .attr("stroke-width", function() {
        const d = d3.select(this.parentNode).datum();
        return (errNodes.has(d.id) || (_selected?.type === "node" && _selected.id === d.id)) ? 3 : 1.5;
      });

    d3.select(svgEl()).selectAll("g.link line")
      .attr("stroke", function() {
        const d = d3.select(this.parentNode).datum();
        if (errEdges.has(d.edge.edge_id)) return C.error;
        if (_selected?.type === "edge" && _selected.id === d.edge.edge_id) return C.selected;
        return d.edge.kind === "cash_flow" ? C.cashFlow : C.contrib;
      })
      .attr("stroke-width", function() {
        const d = d3.select(this.parentNode).datum();
        return (_selected?.type === "edge" && _selected.id === d.edge.edge_id) ? 3 : (d.edge.kind === "cash_flow" ? 2 : 1.5);
      });
  }

  /* ── selection & edit panel ─────────────────────────── */
  function selectItem(type, id) {
    _selected = { type, id };
    renderHighlights();
    renderEditPanel();
  }

  function renderEditPanel() {
    const panel = panelEl();
    if (!_selected) {
      panel.innerHTML = '<p class="graph-empty">Select a node or edge to edit.</p>';
      return;
    }

    if (_selected.type === "node") {
      const node = nodeById(_selected.id);
      if (!node) { panel.innerHTML = '<p class="graph-empty">Node not found.</p>'; return; }
      const isGood = node.kind === "good";
      panel.innerHTML = `
        <h4>${isGood ? "Good" : "Person"}</h4>
        <label>ID</label>
        <input type="text" id="ep-id" value="${esc(node.id)}" />
        <label>Display name</label>
        <input type="text" id="ep-name" value="${esc(node.display_name || "")}" />
        ${isGood ? `<label>Total (cents)</label>
        <input type="number" id="ep-total" value="${node.stated_total_cents ?? ""}" placeholder="optional" />` : ""}
        <div class="edit-actions">
          <button id="ep-save">Save</button>
          <button id="ep-del" class="btn-danger">Delete</button>
        </div>`;

      document.getElementById("ep-save").onclick = () => {
        const newId   = document.getElementById("ep-id").value.trim();
        const newName = document.getElementById("ep-name").value.trim();
        const newTotal = isGood ? (document.getElementById("ep-total").value.trim() || null) : null;

        if (newId && newId !== node.id) {
          /* rename: update all edge references */
          _graph.edges.forEach(e => {
            if (e.from_id    === node.id) e.from_id    = newId;
            if (e.to_id      === node.id) e.to_id      = newId;
            if (e.person_id  === node.id) e.person_id  = newId;
            if (e.good_id    === node.id) e.good_id    = newId;
          });
          node.id = newId;
          _selected.id = newId;
        }
        node.display_name = newName || node.id;
        if (isGood) node.stated_total_cents = newTotal != null ? parseInt(newTotal) : null;
        render();
        renderInconsistencies(_issues);
        renderEditPanel();
      };

      document.getElementById("ep-del").onclick = () => {
        _graph.nodes = _graph.nodes.filter(n => n.id !== node.id);
        _graph.edges = _graph.edges.filter(e =>
          e.from_id !== node.id && e.to_id !== node.id &&
          e.person_id !== node.id && e.good_id !== node.id
        );
        _selected = null;
        render();
        fireChange();
      };

    } else {
      const edge = edgeById(_selected.id);
      if (!edge) { panel.innerHTML = '<p class="graph-empty">Edge not found.</p>'; return; }
      const label = edge.kind === "cash_flow" ? "Cash flow" : "Contribution";
      const fromLabel = edge.kind === "cash_flow"
        ? `${edge.from_id} → ${edge.to_id}`
        : `${edge.person_id} → ${edge.good_id}`;

      panel.innerHTML = `
        <h4>${label}</h4>
        <label>Route</label>
        <div style="font-size:0.75rem;color:var(--fg2);margin-bottom:0.35rem">${esc(fromLabel)}</div>
        ${edge.kind === "cash_flow"
          ? `<label>Amount (cents)</label>
             <input type="number" id="ep-amount" value="${edge.amount_cents ?? ""}" />`
          : `<label>Share value</label>
             <input type="number" id="ep-val" step="0.1" min="0" value="${edge.value ?? 1}" />`}
        <div class="edit-actions">
          <button id="ep-save">Save</button>
          <button id="ep-del" class="btn-danger">Delete</button>
        </div>`;

      document.getElementById("ep-save").onclick = () => {
        if (edge.kind === "cash_flow") {
          edge.amount_cents = parseInt(document.getElementById("ep-amount").value) || 0;
        } else {
          edge.value = parseFloat(document.getElementById("ep-val").value) || 1.0;
        }
        render();
        fireChange();
      };

      document.getElementById("ep-del").onclick = () => {
        _graph.edges = _graph.edges.filter(e => e.edge_id !== edge.edge_id);
        _selected = null;
        render();
        fireChange();
      };
    }
  }

  /* ── inconsistency list ─────────────────────────────── */
  function renderInconsistencies(issues) {
    _issues = issues || [];
    const el = issuesEl();
    if (!_issues.length) { el.innerHTML = ""; return; }
    el.innerHTML = `<div class="inconsistency-list">${
      _issues.map(i => `
        <div class="inconsistency-item ${i.severity}">
          <span class="badge badge-${i.severity}">${esc(i.severity)}</span>
          <span>${esc(i.message)}</span>
        </div>`).join("")
    }</div>`;
  }

  /* ── toolbar add actions ────────────────────────────── */
  function addPerson() {
    const id = uniqueId("person");
    _graph.nodes.push({ id, kind: "person", display_name: id });
    render();
    fireChange();
    selectItem("node", id);
  }

  function addGood() {
    const id = uniqueId("good");
    _graph.nodes.push({ id, kind: "good", display_name: id, stated_total_cents: null });
    render();
    fireChange();
    selectItem("node", id);
  }

  function showAddEdgeForm(kind) {
    const panel = panelEl();
    const persons = _graph.nodes.filter(n => n.kind === "person");
    const goods   = _graph.nodes.filter(n => n.kind === "good");

    if (kind === "cash_flow") {
      if (!persons.length || !goods.length) {
        panel.innerHTML = '<p class="graph-empty">Need at least one person and one good first.</p>';
        return;
      }
      panel.innerHTML = `
        <h4>Add cash flow</h4>
        <label>Payer (person)</label>
        <select id="ep-from">${persons.map(p => `<option value="${esc(p.id)}">${esc(p.display_name||p.id)}</option>`).join("")}</select>
        <label>Good</label>
        <select id="ep-to">${goods.map(g => `<option value="${esc(g.id)}">${esc(g.display_name||g.id)}</option>`).join("")}</select>
        <label>Amount (cents)</label>
        <input type="number" id="ep-amount" value="0" />
        <div class="edit-actions"><button id="ep-add">Add</button></div>`;

      document.getElementById("ep-add").onclick = () => {
        const from = document.getElementById("ep-from").value;
        const to   = document.getElementById("ep-to").value;
        const amt  = parseInt(document.getElementById("ep-amount").value) || 0;
        const eid  = `cf-${to}-${from}`;
        if (!_graph.edges.find(e => e.edge_id === eid)) {
          _graph.edges.push({ kind: "cash_flow", edge_id: eid, from_id: from, to_id: to, target: "good", amount_cents: amt });
        }
        render(); fireChange(); selectItem("edge", eid);
      };

    } else {
      if (!persons.length || !goods.length) {
        panel.innerHTML = '<p class="graph-empty">Need at least one person and one good first.</p>';
        return;
      }
      panel.innerHTML = `
        <h4>Add contribution</h4>
        <label>Person</label>
        <select id="ep-person">${persons.map(p => `<option value="${esc(p.id)}">${esc(p.display_name||p.id)}</option>`).join("")}</select>
        <label>Good</label>
        <select id="ep-good">${goods.map(g => `<option value="${esc(g.id)}">${esc(g.display_name||g.id)}</option>`).join("")}</select>
        <label>Share value</label>
        <input type="number" id="ep-val" step="0.1" min="0" value="1" />
        <div class="edit-actions"><button id="ep-add">Add</button></div>`;

      document.getElementById("ep-add").onclick = () => {
        const pid  = document.getElementById("ep-person").value;
        const gid  = document.getElementById("ep-good").value;
        const val  = parseFloat(document.getElementById("ep-val").value) || 1.0;
        const eid  = `ct-${gid}-${pid}`;
        if (!_graph.edges.find(e => e.edge_id === eid)) {
          _graph.edges.push({ kind: "contribution", edge_id: eid, person_id: pid, good_id: gid, value: val });
        }
        render(); fireChange(); selectItem("edge", eid);
      };
    }
  }

  /* ── HTML escape ────────────────────────────────────── */
  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  /* ── public API ─────────────────────────────────────── */
  function load(graph, inconsistencies) {
    /* deep-copy so D3 can add x/y without mutating the source */
    _graph = JSON.parse(JSON.stringify(graph || { event_id: "", nodes: [], edges: [] }));
    _issues = inconsistencies || [];
    _selected = null;
    render();
    renderInconsistencies(_issues);
    renderEditPanel();
  }

  function getGraph() {
    return JSON.parse(JSON.stringify(_graph));
  }

  function onchange(fn) { _changeFn = fn; }

  function setSlot(config) {
    _slot = { ..._slot, ...config };
  }

  function clearGraph() {
    if (_simulation) { _simulation.stop(); _simulation = null; }
    const svg = svgEl();
    if (svg) d3.select(svg).selectAll("*").remove();
    const panel = panelEl();
    if (panel) panel.innerHTML = '<p class="graph-empty">Select a node or edge to edit.</p>';
    const issues = issuesEl();
    if (issues) issues.innerHTML = "";
    _graph = { event_id: "", nodes: [], edges: [] };
    _issues = [];
    _selected = null;
  }

  /* wire toolbar buttons for any tab that has add buttons */
  document.addEventListener("DOMContentLoaded", () => {
    const actions = [
      ["add-person",       addPerson],
      ["add-good",         addGood],
      ["add-cashflow",     () => showAddEdgeForm("cash_flow")],
      ["add-contribution", () => showAddEdgeForm("contribution")],
    ];
    for (const prefix of ["btn-graph", "btn-pipeline"]) {
      for (const [suffix, fn] of actions) {
        document.getElementById(`${prefix}-${suffix}`)?.addEventListener("click", fn);
      }
    }
  });

  /* ── read-only preview (pipeline tab) ──────────────── */
  function renderPreview(svgId, graph, issues) {
    const errNodes = new Set((issues || []).flatMap(i => i.node_ids || []));
    const errEdges = new Set((issues || []).flatMap(i => i.edge_ids || []));
    const g = JSON.parse(JSON.stringify(graph));
    const allNodes = g.nodes || [];
    const allEdges = g.edges || [];

    const svg = d3.select(document.getElementById(svgId));
    svg.selectAll("*").remove();
    const W = document.getElementById(svgId).clientWidth || 500;
    const H = document.getElementById(svgId).clientHeight || 280;
    svg.attr("viewBox", `0 0 ${W} ${H}`);

    const defs = svg.append("defs");
    function mkM(id, color) {
      defs.append("marker").attr("id", id)
        .attr("viewBox","0 -5 10 10").attr("refX",10).attr("refY",0)
        .attr("markerWidth",7).attr("markerHeight",7).attr("orient","auto")
        .append("path").attr("d","M0,-5L10,0L0,5").attr("fill",color);
    }
    mkM("pv-cash",   C.cashFlow);
    mkM("pv-contrib",C.contrib);
    mkM("pv-error",  C.error);

    const persons = allNodes.filter(n => n.kind === "person");
    const goods   = allNodes.filter(n => n.kind === "good");
    const pad = 50;
    persons.forEach((n,i) => { n.x = W*0.28; n.y = pad + i*(H-2*pad)/Math.max(persons.length,1); });
    goods  .forEach((n,i) => { n.x = W*0.72; n.y = pad + i*(H-2*pad)/Math.max(goods.length,1);   });

    const linkData = allEdges.filter(e => e.kind==="cash_flow"||e.kind==="contribution").map(e => {
      const src = e.kind==="cash_flow" ? allNodes.find(n=>n.id===e.from_id) : allNodes.find(n=>n.id===e.person_id);
      const tgt = e.kind==="cash_flow" ? allNodes.find(n=>n.id===e.to_id)   : allNodes.find(n=>n.id===e.good_id);
      return src && tgt ? {source:src, target:tgt, edge:e} : null;
    }).filter(Boolean);

    const sim = d3.forceSimulation(allNodes)
      .force("link",d3.forceLink(linkData).id(d=>d.id).distance(150).strength(0.4))
      .force("charge",d3.forceManyBody().strength(-200))
      .force("colX",d3.forceX().x(d=>d.kind==="person"?W*0.28:W*0.72).strength(0.3))
      .force("cy",d3.forceY(H/2).strength(0.05))
      .alphaDecay(0.05);

    const gL = svg.append("g"), gN = svg.append("g");

    const lSel = gL.selectAll("g").data(linkData).enter().append("g");
    lSel.append("line")
      .attr("stroke", d => errEdges.has(d.edge.edge_id)?C.error : d.edge.kind==="cash_flow"?C.cashFlow:C.contrib)
      .attr("stroke-width", d => d.edge.kind==="cash_flow"?2:1.5)
      .attr("stroke-dasharray", d => d.edge.kind==="contribution"?"5,3":null)
      .attr("marker-end", d => errEdges.has(d.edge.edge_id)?"url(#pv-error)":d.edge.kind==="cash_flow"?"url(#pv-cash)":"url(#pv-contrib)");
    lSel.append("text").attr("text-anchor","middle").attr("font-size","9px").attr("fill",C.fg2)
      .text(d => d.edge.kind==="cash_flow"?fmtCents(d.edge.amount_cents):`×${d.edge.value??1}`);

    const nSel = gN.selectAll("g").data(allNodes).enter().append("g");
    nSel.filter(d=>d.kind==="person").append("circle").attr("r",22)
      .attr("fill",C.personFill).attr("stroke",d=>errNodes.has(d.id)?C.error:C.personStroke).attr("stroke-width",1.5);
    nSel.filter(d=>d.kind==="good").append("rect").attr("x",-38).attr("y",-18).attr("width",76).attr("height",36).attr("rx",5)
      .attr("fill",C.goodFill).attr("stroke",d=>errNodes.has(d.id)?C.error:C.goodStroke).attr("stroke-width",1.5);
    nSel.append("text").attr("text-anchor","middle").attr("dominant-baseline","middle")
      .attr("font-size","10px").attr("font-weight","600").attr("fill",C.fg)
      .text(d=>d.display_name||d.id);

    sim.on("tick", () => {
      allNodes.forEach(d => { d.x=Math.max(45,Math.min(W-45,d.x)); d.y=Math.max(28,Math.min(H-28,d.y)); });
      lSel.select("line")
        .attr("x1",d=>d.source.x).attr("y1",d=>d.source.y)
        .attr("x2",d=>{ const dx=d.target.x-d.source.x,dy=d.target.y-d.source.y,len=Math.sqrt(dx*dx+dy*dy)||1,r=d.target.kind==="person"?24:40; return d.target.x-(dx/len)*r; })
        .attr("y2",d=>{ const dx=d.target.x-d.source.x,dy=d.target.y-d.source.y,len=Math.sqrt(dx*dx+dy*dy)||1,r=d.target.kind==="person"?24:20; return d.target.y-(dy/len)*r; });
      lSel.select("text").attr("x",d=>(d.source.x+d.target.x)/2).attr("y",d=>(d.source.y+d.target.y)/2-5);
      nSel.attr("transform",d=>`translate(${d.x},${d.y})`);
    });
  }

  return { load, getGraph, onchange, setSlot, clearGraph, renderPreview };
})();
