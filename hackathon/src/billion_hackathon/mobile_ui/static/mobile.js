/* ── Mobile app JS ───────────────────────────────────────────────────── */

const S = {
  eventName: '',
  participants: [],
  sessionId: null,
  itemCount: 0,
  graph: null,      // { event_id, nodes: [], edges: [] }
  compute: null,    // { success, per_person: [], suggested_transfers: [] }
  confirmations: {},
  confirmIdx: 0,
};

// ── Utilities ──────────────────────────────────────────────────────────

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmtCents(c) {
  if (c == null) return '—';
  return `€${(c / 100).toFixed(2)}`;
}

function slugify(s) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || 'item';
}

function uniqueId(prefix, nodes) {
  const ids = new Set((nodes || []).map(n => n.id));
  let i = 1;
  while (ids.has(`${prefix}_${i}`)) i++;
  return `${prefix}_${i}`;
}

// ── Screen navigation ─────────────────────────────────────────────────

function show(id) {
  document.querySelectorAll('.screen').forEach(el => {
    el.classList.add('hidden');
    el.classList.remove('active');
  });
  const target = document.getElementById(id);
  target.classList.remove('hidden');
  target.classList.add('active');
  window.scrollTo(0, 0);
}

// ── API wrapper ────────────────────────────────────────────────────────

async function apiFetch(method, path, body) {
  const opts = { method, credentials: 'same-origin' };
  if (body instanceof FormData) {
    opts.body = body;
  } else if (body) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

// ── Screen 1: Create event ─────────────────────────────────────────────

document.getElementById('btn-create-next').addEventListener('click', () => {
  const name = document.getElementById('inp-event-name').value.trim();
  const raw = document.getElementById('inp-participants').value;
  const parts = raw.split('\n').map(s => s.trim()).filter(Boolean);
  const err = document.getElementById('create-error');

  if (!name) { err.textContent = 'Please enter an occasion name.'; err.classList.remove('hidden'); return; }
  err.classList.add('hidden');

  S.eventName = name;
  S.participants = parts;
  document.getElementById('ev-title').textContent = name;
  show('s-evidence');
});

// ── Screen 2: Add evidence ─────────────────────────────────────────────

function updateItemCount(bundle) {
  S.itemCount = bundle?.items?.length ?? 0;
  const badge = document.getElementById('item-count');
  badge.textContent = `${S.itemCount} item${S.itemCount !== 1 ? 's' : ''}`;
  document.getElementById('btn-analyse').disabled = S.itemCount === 0;
  const clearBtn = document.getElementById('btn-clear-ev');
  clearBtn.classList.toggle('hidden', S.itemCount === 0);
  const grid = document.getElementById('thumb-grid');
  if (S.itemCount > 0) {
    grid.classList.remove('hidden');
    renderThumbs(bundle.items);
  } else {
    grid.classList.add('hidden');
    grid.innerHTML = '';
  }
}

function renderThumbs(items) {
  const grid = document.getElementById('thumb-grid');
  grid.innerHTML = items.map(item => {
    if (item.kind === 'image') {
      return `<div class="thumb-item">
        <img src="/api/collect/file/${esc(item.id)}" alt="${esc(item.original_filename)}" class="thumb-img" />
        <p class="thumb-label">${esc(item.original_filename)}</p>
      </div>`;
    }
    if (item.kind === 'note') {
      return `<div class="thumb-item thumb-note">
        <span class="text-2xl">📝</span>
        <p class="thumb-label">${esc(item.text?.slice(0, 40) ?? 'Note')}</p>
      </div>`;
    }
    return `<div class="thumb-item thumb-file">
      <span class="text-2xl">📄</span>
      <p class="thumb-label">${esc(item.original_filename ?? 'File')}</p>
    </div>`;
  }).join('');
}

async function uploadFiles(files) {
  if (!files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append('files', f);
  try {
    const data = await apiFetch('POST', '/api/collect/upload', fd);
    updateItemCount(data.bundle);
    setEvError('');
  } catch (e) {
    setEvError(`Upload failed: ${e.message}`);
  }
}

function setEvError(msg) {
  const el = document.getElementById('ev-error');
  if (msg) { el.textContent = msg; el.classList.remove('hidden'); }
  else el.classList.add('hidden');
}

document.getElementById('inp-camera').addEventListener('change', e => uploadFiles([...e.target.files]));
document.getElementById('inp-gallery').addEventListener('change', e => uploadFiles([...e.target.files]));

document.getElementById('btn-add-note').addEventListener('click', async () => {
  const ta = document.getElementById('inp-note');
  const text = ta.value.trim();
  if (!text) return;
  try {
    const fd = new FormData();
    fd.append('text', `EVENT: ${S.eventName}\nPEOPLE: ${S.participants.join(', ')}\n${text}`);
    const data = await apiFetch('POST', '/api/collect/note', fd);
    updateItemCount(data.bundle);
    ta.value = '';
    setEvError('');
  } catch (e) {
    setEvError(`Could not add note: ${e.message}`);
  }
});

document.getElementById('btn-clear-ev').addEventListener('click', async () => {
  try {
    const data = await apiFetch('POST', '/api/collect/clear');
    updateItemCount(data.bundle);
  } catch (e) {
    setEvError(`Clear failed: ${e.message}`);
  }
});

document.getElementById('btn-analyse').addEventListener('click', runPipeline);

// ── Screen 3: Processing ───────────────────────────────────────────────

const STATUS_LABELS = [
  'Reading receipts…',
  'Identifying people…',
  'Building expense graph…',
  'Calculating balances…',
];

async function runPipeline() {
  // Post participants as a note before running if we have them
  if (S.participants.length > 0 && S.itemCount === 0) return;

  show('s-processing');
  const label = document.getElementById('proc-label');
  let labelIdx = 0;
  const ticker = setInterval(() => {
    labelIdx = (labelIdx + 1) % STATUS_LABELS.length;
    label.textContent = STATUS_LABELS[labelIdx];
  }, 1800);

  try {
    // Post participant context as a note first (fire-and-forget; ignore errors)
    if (S.participants.length > 0) {
      const fd = new FormData();
      fd.append('text', `EVENT: ${S.eventName}\nPEOPLE: ${S.participants.join(', ')}`);
      await apiFetch('POST', '/api/collect/note', fd).catch(() => {});
    }

    const data = await apiFetch('POST', '/api/pipeline/run', {});
    S.graph = data.last_graph;
    S.compute = data.compute;
    S.confirmations = {};
    S.confirmIdx = 0;
    renderReview(data.inconsistencies ?? []);
    show('s-review');
  } catch (e) {
    show('s-evidence');
    setEvError(`Analysis failed: ${e.message}`);
  } finally {
    clearInterval(ticker);
  }
}

// ── Screen 4: Review graph ─────────────────────────────────────────────

let currentIssues = [];

function persons() { return (S.graph?.nodes ?? []).filter(n => n.kind === 'person'); }
function goods()   { return (S.graph?.nodes ?? []).filter(n => n.kind === 'good'); }
function cashFlows() { return (S.graph?.edges ?? []).filter(e => e.kind === 'cash_flow'); }
function contributions() { return (S.graph?.edges ?? []).filter(e => e.kind === 'contribution'); }

function nodeLabel(id) {
  const n = (S.graph?.nodes ?? []).find(n => n.id === id);
  return n ? (n.display_name || n.id) : id;
}

function renderReview(inconsistencies) {
  currentIssues = inconsistencies ?? [];
  renderIssues(currentIssues);
  renderPeople();
  renderGoods();
  renderConnections();
}

// ── View toggle ────────────────────────────────────────────────────────

GraphView.setSlot({
  svgId: 'mobile-graph-svg',
  editPanelId: 'mobile-graph-edit',
  issuesId: 'mobile-graph-issues',
});

function switchToGraph() {
  document.getElementById('review-list-view').classList.add('hidden');
  document.getElementById('review-graph-view').classList.remove('hidden');
  document.getElementById('btn-view-list').classList.remove('bg-bg1', 'text-fg');
  document.getElementById('btn-view-list').classList.add('text-fg3');
  document.getElementById('btn-view-graph').classList.remove('text-fg3');
  document.getElementById('btn-view-graph').classList.add('bg-bg1', 'text-fg');
  GraphView.load(S.graph, currentIssues);
  GraphView.onchange(g => { S.graph = g; validateAndRecompute(); });
}

function switchToList() {
  const updated = GraphView.getGraph();
  if (updated) S.graph = updated;
  GraphView.clearGraph();
  document.getElementById('review-graph-view').classList.add('hidden');
  document.getElementById('review-list-view').classList.remove('hidden');
  document.getElementById('btn-view-graph').classList.remove('bg-bg1', 'text-fg');
  document.getElementById('btn-view-graph').classList.add('text-fg3');
  document.getElementById('btn-view-list').classList.remove('text-fg3');
  document.getElementById('btn-view-list').classList.add('bg-bg1', 'text-fg');
  renderPeople();
  renderGoods();
  renderConnections();
}

document.getElementById('btn-view-list').addEventListener('click', switchToList);
document.getElementById('btn-view-graph').addEventListener('click', switchToGraph);

function renderIssues(issues) {
  const el = document.getElementById('review-issues');
  if (!issues.length) { el.innerHTML = ''; return; }
  el.innerHTML = issues.map(iss => {
    const color = iss.severity === 'error' ? 'border-red text-red' : 'border-yellow text-yellow';
    return `<div class="border ${color} rounded-xl px-4 py-2 text-sm">${esc(iss.message)}</div>`;
  }).join('');
}

function renderPeople() {
  const list = document.getElementById('people-list');
  list.innerHTML = persons().map(n => personCard(n)).join('');
  list.querySelectorAll('.btn-edit-node').forEach(btn => {
    btn.addEventListener('click', () => toggleEditNode(btn.dataset.id, 'person'));
  });
  list.querySelectorAll('.btn-delete-node').forEach(btn => {
    btn.addEventListener('click', () => deleteNode(btn.dataset.id));
  });
  list.querySelectorAll('.btn-save-node').forEach(btn => {
    btn.addEventListener('click', () => saveNode(btn.dataset.id));
  });
}

function personCard(n) {
  return `<div class="bg-bg1 border border-bg2 rounded-xl p-4" id="card-${esc(n.id)}">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <span class="w-8 h-8 rounded-full bg-blue flex items-center justify-center text-bg text-sm font-bold">
          ${esc((n.display_name || n.id)[0].toUpperCase())}
        </span>
        <span class="text-fg font-medium">${esc(n.display_name || n.id)}</span>
      </div>
      <button class="btn-edit-node text-fg3 text-sm underline" data-id="${esc(n.id)}">edit</button>
    </div>
    <div class="edit-panel hidden mt-3 flex flex-col gap-2" id="edit-${esc(n.id)}">
      <input type="text" value="${esc(n.display_name || n.id)}" placeholder="Name"
        class="edit-name bg-bg border border-bg2 rounded-lg px-3 py-2 text-fg text-sm focus:outline-none focus:border-blue" />
      <div class="flex gap-2">
        <button class="btn-save-node flex-1 bg-accent text-bg rounded-lg py-2 text-sm font-medium" data-id="${esc(n.id)}">Save</button>
        <button class="btn-delete-node bg-bg2 border border-red text-red rounded-lg px-3 py-2 text-sm" data-id="${esc(n.id)}">Delete</button>
      </div>
    </div>
  </div>`;
}

function renderGoods() {
  const list = document.getElementById('goods-list');
  list.innerHTML = goods().map(n => goodCard(n)).join('');
  list.querySelectorAll('.btn-edit-node').forEach(btn => {
    btn.addEventListener('click', () => toggleEditNode(btn.dataset.id, 'good'));
  });
  list.querySelectorAll('.btn-delete-node').forEach(btn => {
    btn.addEventListener('click', () => deleteNode(btn.dataset.id));
  });
  list.querySelectorAll('.btn-save-node').forEach(btn => {
    btn.addEventListener('click', () => saveNode(btn.dataset.id));
  });
}

function goodCard(n) {
  const total = n.stated_total_cents != null ? fmtCents(n.stated_total_cents) : '—';
  return `<div class="bg-bg1 border border-bg2 rounded-xl p-4" id="card-${esc(n.id)}">
    <div class="flex items-center justify-between">
      <div>
        <p class="text-fg font-medium">${esc(n.display_name || n.id)}</p>
        <p class="text-fg3 text-sm">${total}</p>
      </div>
      <button class="btn-edit-node text-fg3 text-sm underline" data-id="${esc(n.id)}">edit</button>
    </div>
    <div class="edit-panel hidden mt-3 flex flex-col gap-2" id="edit-${esc(n.id)}">
      <input type="text" value="${esc(n.display_name || n.id)}" placeholder="Name"
        class="edit-name bg-bg border border-bg2 rounded-lg px-3 py-2 text-fg text-sm focus:outline-none focus:border-blue" />
      <input type="number" value="${n.stated_total_cents ?? ''}" placeholder="Total (cents)"
        class="edit-total bg-bg border border-bg2 rounded-lg px-3 py-2 text-fg text-sm focus:outline-none focus:border-blue" />
      <div class="flex gap-2">
        <button class="btn-save-node flex-1 bg-accent text-bg rounded-lg py-2 text-sm font-medium" data-id="${esc(n.id)}">Save</button>
        <button class="btn-delete-node bg-bg2 border border-red text-red rounded-lg px-3 py-2 text-sm" data-id="${esc(n.id)}">Delete</button>
      </div>
    </div>
  </div>`;
}

function renderConnections() {
  const cfList = document.getElementById('cashflow-list');
  cfList.innerHTML = cashFlows().map(e => `
    <div class="bg-bg1 border border-bg2 rounded-xl px-4 py-3 flex items-center justify-between gap-3">
      <div class="text-sm">
        <span class="text-red">${esc(nodeLabel(e.from_id))}</span>
        <span class="text-fg3"> → </span>
        <span class="text-yellow">${esc(nodeLabel(e.to_id))}</span>
        <span class="text-fg3 ml-2">${fmtCents(e.amount_cents)}</span>
      </div>
      <button class="btn-delete-edge text-fg3 text-xs underline shrink-0" data-id="${esc(e.edge_id)}">remove</button>
    </div>`).join('') || '<p class="text-fg3 text-sm">None yet.</p>';

  const ctList = document.getElementById('contribution-list');
  ctList.innerHTML = contributions().map(e => `
    <div class="bg-bg1 border border-bg2 rounded-xl px-4 py-3 flex items-center justify-between gap-3">
      <div class="text-sm">
        <span class="text-blue">${esc(nodeLabel(e.person_id))}</span>
        <span class="text-fg3"> shared </span>
        <span class="text-green">${esc(nodeLabel(e.good_id))}</span>
        <span class="text-fg3 ml-2">×${e.value ?? 1}</span>
      </div>
      <button class="btn-delete-edge text-fg3 text-xs underline shrink-0" data-id="${esc(e.edge_id)}">remove</button>
    </div>`).join('') || '<p class="text-fg3 text-sm">None yet.</p>';

  document.querySelectorAll('.btn-delete-edge').forEach(btn => {
    btn.addEventListener('click', () => deleteEdge(btn.dataset.id));
  });
}

function toggleEditNode(id, kind) {
  const panel = document.getElementById(`edit-${id}`);
  const isOpen = !panel.classList.contains('hidden');
  // Close all others first
  document.querySelectorAll('.edit-panel').forEach(p => p.classList.add('hidden'));
  if (!isOpen) panel.classList.remove('hidden');
}

function saveNode(id) {
  const panel = document.getElementById(`edit-${id}`);
  const nameInput = panel.querySelector('.edit-name');
  const totalInput = panel.querySelector('.edit-total');
  const node = S.graph.nodes.find(n => n.id === id);
  if (!node) return;

  const oldId = node.id;
  const newName = nameInput.value.trim() || node.display_name;
  node.display_name = newName;

  if (totalInput) {
    const v = parseInt(totalInput.value);
    node.stated_total_cents = isNaN(v) ? null : v;
  }

  // Propagate id rename in edges if name used as id
  if (oldId !== id) {
    S.graph.edges.forEach(e => {
      if (e.from_id === oldId) e.from_id = id;
      if (e.to_id === oldId) e.to_id = id;
      if (e.person_id === oldId) e.person_id = id;
      if (e.good_id === oldId) e.good_id = id;
    });
  }

  panel.classList.add('hidden');
  renderPeople();
  renderGoods();
  renderConnections();
  validateAndRecompute();
}

function deleteNode(id) {
  S.graph.nodes = S.graph.nodes.filter(n => n.id !== id);
  S.graph.edges = S.graph.edges.filter(e =>
    e.from_id !== id && e.to_id !== id && e.person_id !== id && e.good_id !== id
  );
  renderPeople();
  renderGoods();
  renderConnections();
  validateAndRecompute();
}

function deleteEdge(edgeId) {
  S.graph.edges = S.graph.edges.filter(e => e.edge_id !== edgeId);
  renderConnections();
  validateAndRecompute();
}

async function validateAndRecompute() {
  try {
    const vData = await apiFetch('POST', '/api/dev/graph/validate', { graph: S.graph });
    renderIssues(vData.inconsistencies ?? []);
  } catch (_) {}
  try {
    const cData = await apiFetch('POST', '/api/dev/compute', { graph: S.graph });
    S.compute = cData.compute;
  } catch (_) {}
}

// Review tab switching
document.querySelectorAll('.review-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.review-tab').forEach(t => {
      t.classList.remove('active-tab');
      t.classList.add('text-fg3');
    });
    document.querySelectorAll('.review-pane').forEach(p => p.classList.add('hidden'));
    tab.classList.add('active-tab');
    tab.classList.remove('text-fg3');
    document.getElementById(tab.dataset.pane).classList.remove('hidden');
  });
});

// Add nodes/edges buttons
document.getElementById('btn-add-person').addEventListener('click', () => openModal('modal-add-person'));
document.getElementById('btn-add-good').addEventListener('click', () => openModal('modal-add-good'));
document.getElementById('btn-add-cashflow').addEventListener('click', () => {
  populateSelect('modal-cf-from', persons());
  populateSelect('modal-cf-to', goods());
  openModal('modal-add-cashflow');
});
document.getElementById('btn-add-contribution').addEventListener('click', () => {
  populateSelect('modal-ct-person', persons());
  populateSelect('modal-ct-good', goods());
  openModal('modal-add-contribution');
});

document.getElementById('btn-recompute').addEventListener('click', async () => {
  const err = document.getElementById('review-error');
  try {
    const data = await apiFetch('POST', '/api/dev/compute', { graph: S.graph });
    S.compute = data.compute;
    err.classList.add('hidden');
  } catch (e) {
    err.textContent = `Compute error: ${e.message}`;
    err.classList.remove('hidden');
  }
});

document.getElementById('btn-review-next').addEventListener('click', () => {
  // Build confirm list from persons in graph (exclude inferred ones if desired)
  S.confirmIdx = 0;
  S.confirmations = {};
  persons().forEach(p => { S.confirmations[p.id] = null; });
  renderConfirm();
  show('s-confirm');
});

// ── Screen 5: Confirm ──────────────────────────────────────────────────

function renderConfirm() {
  const personList = persons();
  if (!personList.length) { show('s-bill'); renderBill(); return; }

  // If all confirmed, go to bill
  if (S.confirmIdx >= personList.length) { show('s-bill'); renderBill(); return; }

  const person = personList[S.confirmIdx];
  document.getElementById('confirm-name').textContent = person.display_name || person.id;
  document.getElementById('confirm-instruction').textContent =
    S.confirmIdx === 0 ? 'First up:' : `Pass the phone to`;

  // Find this person's compute data
  const pp = (S.compute?.per_person ?? []).find(p => p.person_id === person.id);
  const net = pp?.net_cents ?? 0;
  const netEl = document.getElementById('confirm-net');
  netEl.textContent = fmtCents(Math.abs(net));
  netEl.className = `text-3xl font-bold ${net < 0 ? 'text-red' : net > 0 ? 'text-green' : 'text-fg'}`;

  // Their relevant transfers
  const transfers = (S.compute?.suggested_transfers ?? []).filter(
    t => t.from_person_id === person.id || t.to_person_id === person.id
  );
  const tEl = document.getElementById('confirm-transfers');
  tEl.innerHTML = transfers.map(t => {
    const isFrom = t.from_person_id === person.id;
    const other = nodeLabel(isFrom ? t.to_person_id : t.from_person_id);
    const verb = isFrom ? 'You pay' : 'You receive from';
    const color = isFrom ? 'text-red' : 'text-green';
    return `<div class="bg-bg1 border border-bg2 rounded-xl px-4 py-3 flex justify-between text-sm">
      <span class="text-fg2">${esc(verb)} <span class="text-fg font-medium">${esc(other)}</span></span>
      <span class="${color} font-semibold">${fmtCents(t.amount_cents)}</span>
    </div>`;
  }).join('') || `<p class="text-fg3 text-sm text-center py-2">No transfers for ${esc(person.display_name || person.id)}</p>`;

  // Progress dots
  const dots = document.getElementById('confirm-dots');
  dots.innerHTML = personList.map((_, i) => {
    const confirmed = S.confirmations[personList[i].id];
    const cls = i < S.confirmIdx ? 'bg-green' : i === S.confirmIdx ? 'bg-accent' : 'bg-bg2';
    return `<span class="w-2.5 h-2.5 rounded-full ${cls} inline-block"></span>`;
  }).join('');
}

document.getElementById('btn-confirm-yes').addEventListener('click', () => {
  const personList = persons();
  if (S.confirmIdx < personList.length) {
    S.confirmations[personList[S.confirmIdx].id] = true;
    S.confirmIdx++;
  }
  renderConfirm();
});

document.getElementById('btn-confirm-edit').addEventListener('click', () => {
  S.confirmations = {};
  S.confirmIdx = 0;
  show('s-review');
});

// ── Screen 6: Final bill ───────────────────────────────────────────────

function renderBill() {
  document.getElementById('bill-title').textContent = S.eventName || 'Your bill';

  const transfers = S.compute?.suggested_transfers ?? [];
  const settled = document.getElementById('bill-settled');
  const tEl = document.getElementById('bill-transfers');

  if (!transfers.length) {
    settled.classList.remove('hidden');
    settled.classList.add('flex');
    tEl.innerHTML = '';
  } else {
    settled.classList.add('hidden');
    settled.classList.remove('flex');
    tEl.innerHTML = transfers.map(t => `
      <div class="bg-bg1 border border-bg2 rounded-xl p-4 flex items-center justify-between gap-3">
        <div class="text-sm flex-1">
          <span class="text-red font-medium">${esc(nodeLabel(t.from_person_id))}</span>
          <span class="text-fg3"> → </span>
          <span class="text-green font-medium">${esc(nodeLabel(t.to_person_id))}</span>
        </div>
        <span class="text-yellow font-semibold text-base">${fmtCents(t.amount_cents)}</span>
        <button class="btn-copy-transfer text-fg3 text-xs underline shrink-0"
          data-text="${esc(nodeLabel(t.from_person_id))} pays ${esc(nodeLabel(t.to_person_id))} ${fmtCents(t.amount_cents)}">
          Copy
        </button>
      </div>`).join('');

    document.querySelectorAll('.btn-copy-transfer').forEach(btn => {
      btn.addEventListener('click', () => {
        navigator.clipboard?.writeText(btn.dataset.text).then(() => {
          btn.textContent = 'Copied!';
          setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
        });
      });
    });
  }

  // Per-person breakdown
  const pp = S.compute?.per_person ?? [];
  document.getElementById('bill-per-person').innerHTML = pp.map(p => {
    const net = p.net_cents ?? 0;
    const color = net < 0 ? 'text-red' : net > 0 ? 'text-green' : 'text-fg3';
    return `<div class="flex items-center justify-between py-2 border-b border-bg2 last:border-0">
      <span class="text-fg text-sm font-medium">${esc(p.display_name || p.person_id)}</span>
      <span class="${color} text-sm font-semibold">${net >= 0 ? '+' : ''}${fmtCents(net)}</span>
    </div>`;
  }).join('') || '<p class="text-fg3 text-sm">No data.</p>';
}

document.getElementById('btn-share').addEventListener('click', async () => {
  const transfers = S.compute?.suggested_transfers ?? [];
  const lines = transfers.map(t =>
    `${nodeLabel(t.from_person_id)} → ${nodeLabel(t.to_person_id)}: ${fmtCents(t.amount_cents)}`
  );
  const text = `${S.eventName}\n\n${lines.join('\n') || 'No transfers needed.'}`;

  if (navigator.share) {
    try { await navigator.share({ title: S.eventName, text }); } catch (_) {}
  } else {
    await navigator.clipboard?.writeText(text);
    alert('Summary copied to clipboard!');
  }
});

document.getElementById('btn-start-over').addEventListener('click', async () => {
  try { await apiFetch('POST', '/api/collect/clear'); } catch (_) {}
  S.eventName = '';
  S.participants = [];
  S.sessionId = null;
  S.itemCount = 0;
  S.graph = null;
  S.compute = null;
  S.confirmations = {};
  S.confirmIdx = 0;
  document.getElementById('inp-event-name').value = '';
  document.getElementById('inp-participants').value = '';
  updateItemCount({ items: [] });
  show('s-create');
});

// ── Modal helpers ──────────────────────────────────────────────────────

function openModal(id) {
  document.getElementById(id).classList.remove('hidden');
}

function closeModal(id) {
  document.getElementById(id).classList.add('hidden');
}

function populateSelect(selectId, nodes) {
  const sel = document.getElementById(selectId);
  sel.innerHTML = nodes.map(n => `<option value="${esc(n.id)}">${esc(n.display_name || n.id)}</option>`).join('');
}

document.querySelectorAll('.modal-cancel').forEach(btn => {
  btn.addEventListener('click', () => {
    btn.closest('.modal').classList.add('hidden');
  });
});

// Close modal on backdrop click
document.querySelectorAll('.modal').forEach(modal => {
  modal.addEventListener('click', e => {
    if (e.target === modal) modal.classList.add('hidden');
  });
});

document.getElementById('modal-person-save').addEventListener('click', () => {
  const name = document.getElementById('modal-person-name').value.trim();
  if (!name) return;
  const id = uniqueId('person', S.graph?.nodes);
  if (!S.graph) S.graph = { event_id: 'evt_mobile', nodes: [], edges: [] };
  S.graph.nodes.push({ id, kind: 'person', display_name: name });
  closeModal('modal-add-person');
  document.getElementById('modal-person-name').value = '';
  renderPeople();
  validateAndRecompute();
});

document.getElementById('modal-good-save').addEventListener('click', () => {
  const name = document.getElementById('modal-good-name').value.trim();
  const totalRaw = parseInt(document.getElementById('modal-good-total').value);
  if (!name) return;
  const id = uniqueId('good', S.graph?.nodes);
  if (!S.graph) S.graph = { event_id: 'evt_mobile', nodes: [], edges: [] };
  S.graph.nodes.push({ id, kind: 'good', display_name: name, stated_total_cents: isNaN(totalRaw) ? null : totalRaw });
  closeModal('modal-add-good');
  document.getElementById('modal-good-name').value = '';
  document.getElementById('modal-good-total').value = '';
  renderGoods();
  validateAndRecompute();
});

document.getElementById('modal-cf-save').addEventListener('click', () => {
  const from = document.getElementById('modal-cf-from').value;
  const to = document.getElementById('modal-cf-to').value;
  const amount = parseInt(document.getElementById('modal-cf-amount').value);
  if (!from || !to || isNaN(amount)) return;
  const edgeId = `cf_${to}_${from}_${Date.now()}`;
  S.graph.edges.push({ edge_id: edgeId, kind: 'cash_flow', from_id: from, to_id: to, amount_cents: amount });
  closeModal('modal-add-cashflow');
  document.getElementById('modal-cf-amount').value = '';
  renderConnections();
  validateAndRecompute();
});

document.getElementById('modal-ct-save').addEventListener('click', () => {
  const person = document.getElementById('modal-ct-person').value;
  const good = document.getElementById('modal-ct-good').value;
  const value = parseFloat(document.getElementById('modal-ct-value').value) || 1;
  if (!person || !good) return;
  const edgeId = `ct_${good}_${person}_${Date.now()}`;
  S.graph.edges.push({ edge_id: edgeId, kind: 'contribution', person_id: person, good_id: good, value });
  closeModal('modal-add-contribution');
  document.getElementById('modal-ct-value').value = '1';
  renderConnections();
  validateAndRecompute();
});

// ── Back buttons ───────────────────────────────────────────────────────

document.querySelectorAll('.back-btn').forEach(btn => {
  btn.addEventListener('click', () => show(btn.dataset.target));
});
