"use strict";
// ParlTopics demo UI. Vanilla JS, no build step. All data comes from the FastAPI backend (/api/*).

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const LEVEL = { country: "Federal", canton: "Cantonal" };
const QUOTES = { de: ["„", "“"], fr: ["« ", " »"], it: ["« ", " »"] };

const S = {
  app: null, presetId: null, topicName: "", runId: null, items: [], live: false, controller: null,
  filters: { parl: "", level: "", lang: "", year: "" }, kwOnly: false, show: { rejected: false, below: false },
  selected: -1, detailId: null, pending: [], definitionUsed: "", hasKeywords: false, pool: [],
  mode: "adhoc", scheme: "aps", labelNames: {}, loadSeq: 0,
  limit: 300, collection: "", collections: [], coll: null, task: "all", prevVisit: null, job: null, confirmJob: null, jobBody: null,
};
const enc = encodeURIComponent;
const DAY_MS = 86400000;
const ADHOC_HEAD = ["Parl.", "Number", "Date", "Lang", "Title", "Label", "Confidence", "Evidence", "Review"];
const STD_HEAD = ["Parl.", "Number", "Date", "Lang", "Title", "Labels (confidence)", "Evidence (top label)", "Review"];

// "apertus-v1-5-70b" → "Apertus v1.5 70B"; other model ids are shown as they are
const modelLabel = (id) => (id || "").replace(/^apertus-v(\d+)-(\d+)-(\d+b)(.*)$/i, (_, a, b, size, rest) => `Apertus v${a}.${b} ${size.toUpperCase()}${rest}`);

function renderScopeChip() {
  const chip = $("sampleChip");
  const offline = S.app.mode !== "live";
  chip.textContent = offline ? "Cached results" : "Sample data";
  chip.title = offline ? "Model offline: these are stored results from an earlier run"
    : `Demo pool: a fixed sample of ${S.app.pool.n} affairs. Pick a parliament under Collection for complete results.`;
  chip.classList.toggle("hidden", !offline && !!S.collection);
  $("fParlWrap").classList.toggle("hidden", !!S.collection);
  $("fLevelWrap").classList.toggle("hidden", !!S.collection);
}

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

// ---------- state & presets ----------
async function loadState() {
  S.app = await api("/api/state");
  const live = S.app.mode === "live";
  $("modelName").textContent = live ? `${modelLabel(S.app.model)} · ${S.app.endpoint_label || S.app.endpoint_host}` : "Model offline · cached results";
  $("modelName").title = `${S.app.model} via ${S.app.endpoint_host}`;
  $("modelBadge").classList.toggle("off", !live);
  $("offlineBanner").classList.toggle("hidden", live);
  $("classifyBtn").disabled = !live;
  renderScopeChip();
  if (!S.pool.length) S.pool = await api("/api/pool");
  S.collections = await api("/api/collections");
  S.topics = await loadTopics();
  renderCollections();
  $("classifyBtn").title = live ? "Classify the demo pool (Enter)" : "Model endpoint unreachable";
  renderPresets();
  renderSchemes();
  const preferred = S.app.presets.find((p) => p.id === S.app.default_preset && p.run);
  if (!S.presetId && !S.runId) selectPreset((preferred || S.app.presets.find((p) => p.run) || S.app.presets[0] || {}).id);
}

function renderPresets() {
  const first = S.app.presets.filter((p) => p.id === S.app.default_preset);
  const ordered = [...first, ...S.app.presets.filter((p) => p.id !== S.app.default_preset)];
  $("presetChips").innerHTML = ordered.map((p) =>
    `<button type="button" class="chip${p.id === S.presetId ? " on" : ""}" data-preset="${esc(p.id)}">${esc(p.name)}</button>`).join("");
  const own = (S.topics || []).filter((t) => !t.preset).length;
  $("topicsBtn").textContent = own ? `My topics (${own})` : "My topics";
}

// ---------- collections (whole parliaments) ----------
const currentCollection = () => S.collections.find((c) => c.body_key === S.collection) || { targets: [] };

function renderCollections() {
  const el = $("fColl"); const cur = S.collection;
  el.innerHTML = `<option value="">Demo pool · ${S.app.pool.n}</option>` + S.collections.map((c) =>
    `<option value="${esc(c.body_key)}" title="${esc(c.level)}, ${c.n.toLocaleString("en")} affairs since ${esc((c.since || "").slice(0, 4))}">${esc(c.body_key)} · ${c.n.toLocaleString("en")}</option>`).join("");
  el.value = cur;
}

function lastVisit(body) {
  // previous visit of this collection, for "What's new"; per browser only, page works without it
  try {
    const key = `parltopics.lastVisit.${body}`;
    const prev = localStorage.getItem(key);
    localStorage.setItem(key, new Date().toISOString());
    return prev;
  } catch (e) { return null; }
}

function selectCollection(body) {
  if (S.live || S.job) { $("fColl").value = S.collection; return; }
  Object.assign(S, { collection: body, coll: null, confirmJob: null, items: [], runId: null, selected: -1 });
  S.prevVisit = body ? lastVisit(body) : null;
  S.filters.parl = ""; S.filters.level = ""; S.filters.shelf = ""; $("fParl").value = ""; $("fLevel").value = ""; $("fShelf").value = "";
  renderScopeChip(); renderSchemes();
  closeDetail();
  $("classifyBtn").title = body ? `Index ${body} for this topic (Enter)` : "Classify the demo pool (Enter)";
  renderPresets();
  if (S.mode === "standard") return selectScheme(S.scheme);
  selectPreset(S.presetId || (S.app.presets.find((p) => p.id === S.app.default_preset) || S.app.presets[0] || {}).id);
}

// ---------- saved topics: every topic that was indexed somewhere, searchable ----------
// a convenience list: if it cannot be loaded, the page still works and the list says so
const loadTopics = () => api("/api/topics").catch(() => null);
function renderTopics() {
  const q = $("topicsSearch").value.trim().toLowerCase();
  if (S.topics === null) {
    $("topicsList").innerHTML = `<div class="cap" style="padding:10px 4px">Saved topics could not be loaded. Restart the server and reload the page.</div>`;
    return;
  }
  const list = (S.topics || []).filter((t) => !q || `${t.name} ${t.definition}`.toLowerCase().includes(q));
  $("topicsList").innerHTML = list.length ? list.map((t) => {
    const cov = t.collections.map((c) => `<span class="cov${c.body_key === S.collection ? " here" : ""}">${esc(c.body_key)} ${c.done >= c.total
      ? "✓" : `${c.done.toLocaleString("en")} / ${c.total.toLocaleString("en")}`}</span>`).join("");
    return `<button type="button" class="topitem" data-topic="${esc(t.target)}"><span class="tn">${esc(t.name)}${t.preset ? ` <span class="tag">preset</span>` : ""}</span>
      <span class="td">${esc(t.definition)}</span><span class="tc">${cov}</span></button>`;
  }).join("") : `<div class="cap" style="padding:10px 4px">${q ? "No saved topic matches." : "No saved topics yet. Use <b>+ New topic</b> and index it on a parliament."}</div>`;
}

function toggleTopics(open) {
  $("topicsPop").classList.toggle("hidden", !open);
  $("topicsBtn").setAttribute("aria-expanded", String(open));
  if (open) { $("topicsSearch").value = ""; renderTopics(); $("topicsSearch").focus(); }
}

function openSavedTopic(target) {
  const t = (S.topics || []).find((x) => x.target === target);
  toggleTopics(false);
  if (!t) return;
  if (t.preset) return selectPreset(target.slice(7).replace(/\.yaml$/, ""));
  return selectOwnTopic(t);
}

function selectOwnTopic(t) {
  if (!t) return;
  S.presetId = null;
  $("topicName").value = t.name;
  $("topicDef").value = t.definition || "";
  $("topicInclude").value = (t.include || []).join("\n");
  $("topicExclude").value = (t.exclude || []).join("\n");
  S.definitionUsed = t.definition || ""; S.hasKeywords = false;
  renderPresets();
  if (!S.collection) {  // demo pool: the saved topic is ready in the form; Classify runs it live
    Object.assign(S, { items: [], runId: null, coll: null, confirmJob: null });
    return render();
  }
  return loadCollection(t.target, { topic: { name: t.name, definition: t.definition, include: t.include, exclude: t.exclude } });
}

function targetBody(target) {
  if (target.startsWith("scheme:")) return { scheme: target.slice(7) };
  if (target.startsWith("topics/")) return { preset_id: target.slice(7).replace(/\.yaml$/, "") };
  return null;
}

async function loadCollection(target, body) {
  const seq = ++S.loadSeq;
  const t = (currentCollection().targets || []).find((x) => x.target === target);
  if (!t || !t.done) {
    const req = body || targetBody(target);
    const est = t || await api(`/api/collections/${enc(S.collection)}/estimate`, { method: "POST", body: JSON.stringify(req) });
    if (seq !== S.loadSeq) return;
    Object.assign(S, { items: [], runId: null, coll: est, topicName: est.name, selected: -1, confirmJob: { body: req, est } });
    return render();
  }
  const d = await api(`/api/collections/${enc(S.collection)}/results?target=${enc(target)}`);
  if (seq !== S.loadSeq) return;
  Object.assign(S, { items: d.items, runId: null, coll: d, topicName: d.name, selected: -1, pending: [], confirmJob: null });
  if (body) S.confirmJob = d.pending ? { body, est: d, partial: true } : null;
  renderPresets(); fillFilterOptions(); render();
}

async function classifyCollection() {
  if (S.app.mode !== "live" || S.job) return;
  const body = S.mode === "standard" ? { scheme: S.scheme } : presetUnchanged() ? { preset_id: S.presetId } : { topic: topicFromForm() };
  if (body.topic && !body.topic.name) { $("topicName").focus(); return; }
  if (body.topic) { S.presetId = null; renderPresets(); }
  try {
    const est = await api(`/api/collections/${enc(S.collection)}/estimate`, { method: "POST", body: JSON.stringify(body) });
    S.definitionUsed = body.topic ? (body.topic.definition || `Affairs whose main subject is ${body.topic.name}.`) : S.definitionUsed;
    return loadCollection(est.target, body);
  } catch (e) { alertStrip(`Could not estimate: ${e.message}`); }
}

async function startJob() {
  const { body } = S.confirmJob;
  S.confirmJob = null; S.jobBody = body;
  try {
    S.job = await api(`/api/collections/${enc(S.collection)}/jobs`, { method: "POST", body: JSON.stringify(body) });
    render(); pollJob();
  } catch (e) { alertStrip(`Could not start indexing: ${e.message}`); }
}

function pollJob() {
  const j = S.job;
  if (!j) return;
  $("progress").classList.remove("hidden");
  $("progWhat").textContent = `Indexing ${j.body_key} for`;
  $("progTopic").textContent = j.name;
  $("progDone").textContent = j.done.toLocaleString("en");
  $("progTotal").textContent = j.total.toLocaleString("en");
  $("progBar").style.width = `${(100 * j.done) / (j.total || 1)}%`;
  $("progEta").textContent = j.eta_min != null ? ` · ≈ ${j.eta_min} min left${j.rate_now ? ` · ${j.rate_now} affairs/min` : ""} · you can stop and continue later` : "";
  if (j.status === "running") {
    setTimeout(async () => {
      try { S.job = await api(`/api/jobs/${j.job_id}`); } catch (e) { S.job = { ...j, status: "failed", error: e.message }; }
      pollJob();
    }, 3000);
    return;
  }
  finishJob(j);
}

async function finishJob(j) {
  $("progress").classList.add("hidden"); $("progEta").textContent = "";
  S.job = null;
  S.collections = await api("/api/collections");
  S.topics = await loadTopics();
  renderPresets();
  if (j.body_key !== S.collection) return render();
  await loadCollection(j.target, j.status === "done" ? null : S.jobBody);
  if (j.status === "failed") alertStrip(`Indexing stopped: ${j.error}. Finished affairs are kept; start again to continue.`);
}

function selectPreset(id) {
  const p = S.app.presets.find((x) => x.id === id);
  if (!p) return render();
  S.presetId = id;
  $("topicName").value = p.name;
  $("topicDef").value = p.definition.trim();
  $("topicInclude").value = (p.include || []).join("\n");
  $("topicExclude").value = (p.exclude || []).join("\n");
  renderPresets();
  S.definitionUsed = p.definition.trim();
  S.hasKeywords = Object.keys(p.keywords || {}).length > 0;
  if (S.collection) return loadCollection(`topics/${id}.yaml`);
  if (p.run) loadRun(p.run.run_id);
  else { S.loadSeq += 1; S.items = []; S.runId = null; S.topicName = p.name; render(); }
}

async function loadRun(runId) {
  const seq = ++S.loadSeq;
  const data = await api(`/api/runs/${encodeURIComponent(runId)}`);
  if (seq !== S.loadSeq) return;  // a newer preset/scheme was selected meanwhile
  Object.assign(S, { runId, items: data.items, topicName: data.topic_name, selected: -1, pending: [] });
  const when = (data.run.finished_at || data.run.started_at || "").slice(0, 16).replace("T", " ");
  $("offlineText").innerHTML = `Showing cached results from run <span class="mono">${esc(runId)}</span> · ${esc(when)}. Live classification is paused.`;
  fillFilterOptions();
  render();
}

// ---------- classify (live, streamed) ----------
function topicFromForm() {
  const lines = (id) => $(id).value.split("\n").map((s) => s.trim()).filter(Boolean);
  return { name: $("topicName").value.trim(), definition: $("topicDef").value.trim(), include: lines("topicInclude"), exclude: lines("topicExclude") };
}

function presetUnchanged() {
  const p = S.app.presets.find((x) => x.id === S.presetId);
  if (!p) return false;
  const t = topicFromForm();
  return t.name === p.name && t.definition === p.definition.trim() &&
    t.include.join("\n") === (p.include || []).join("\n") && t.exclude.join("\n") === (p.exclude || []).join("\n");
}

async function classify() {
  if (S.collection) return classifyCollection();
  if (S.app.mode !== "live" || S.live) return;
  const body = S.mode === "standard" ? { scheme: S.scheme } : presetUnchanged() ? { preset_id: S.presetId } : { topic: topicFromForm() };
  if (body.topic) {
    S.presetId = null; renderPresets();
    if (!body.topic.name) { $("topicName").focus(); return; }
  }
  S.controller = new AbortController();
  S.live = true; S.items = []; S.selected = -1; S.runId = null; S.definitionUsed = "";
  S.pending = S.pool.map((r) => ({ ...r, prediction_id: null, placeholder: true }));
  closeDetail();
  $("classifyBtn").disabled = true; $("classifyBtn").firstChild.textContent = "Classifying… ";
  $("progress").classList.remove("hidden");
  $("progWhat").textContent = "Classifying pool for";
  $("progTopic").textContent = body.scheme ? schemeName(body.scheme) : body.topic ? body.topic.name : $("topicName").value;
  render();
  try {
    const r = await fetch("/api/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: S.controller.signal });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) { handleEvent(JSON.parse(buf.slice(0, nl))); buf = buf.slice(nl + 1); }
    }
  } catch (e) {
    if (e.name !== "AbortError") alertStrip(`Classification stopped: ${e.message}`);
  } finally {
    S.live = false; S.controller = null; S.pending = [];
    $("progress").classList.add("hidden");
    $("classifyBtn").disabled = S.app.mode !== "live"; $("classifyBtn").firstChild.textContent = "Classify ";
    S.app = await api("/api/state"); renderPresets();
    render();
  }
}

function handleEvent(ev) {
  if (ev.type === "run") {
    Object.assign(S, { runId: ev.run_id, topicName: ev.topic_name, definitionUsed: ev.definition, hasKeywords: ev.has_keywords });
    $("progTotal").textContent = ev.n;
    render();
  }
  if (ev.type === "item") {
    if (ev.item.run_id && ev.item.run_id !== S.runId) return;
    S.items.push(ev.item);
    S.pending = S.pending.filter((r) => r.affair_id !== ev.item.affair_id);
    $("progDone").textContent = ev.done;
    $("progBar").style.width = `${(100 * ev.done) / Number($("progTotal").textContent || 1)}%`;
    fillFilterOptions(); render();
  }
}

// ---------- filtering & grouping ----------
const isMatch = (i) => i.status === "ok" && i.label === "match";
const shown = (i) => isMatch(i) && i.confidence >= S.app.match_threshold;
const level = (i) => LEVEL[i.body_type] || "Municipal";
const reviewState = (i) => i.review_decision === "confirm" || (i.review_decision === "correct" && i.review_label === "match") ? "confirmed"
  : i.review_decision ? "rejected" : "";

const newSince = () => S.prevVisit || new Date(Date.now() - 30 * DAY_MS).toISOString().slice(0, 10);
const isNew = (i) => (S.prevVisit ? (i.first_seen_at || "") > S.prevVisit : (i.begin_date || "") >= newSince());

function passesFilters(i) {
  const f = S.filters;
  return (!f.parl || i.body_key === f.parl) && (!f.level || level(i) === f.level) && (!f.lang || i.lang === f.lang) &&
    (!f.year || (i.begin_date || "") >= f.year) && (!S.kwOnly || !S.hasKeywords || i.keyword_absent === true) &&
    (S.task !== "new" || isNew(i));
}

function groups() {
  const pool = S.items.filter(passesFilters);
  return {
    suggested: pool.filter(shown),
    rejected: pool.filter((i) => i.status === "evidence_failed"),
    below: pool.filter((i) => isMatch(i) && !shown(i)),
    confirmed: pool.filter((i) => shown(i) && reviewState(i) === "confirmed"),
  };
}

const PAGE = 300;  // rows drawn at once; whole collections have thousands
const moreRow = (n, cols) => (n > S.limit ? `<tr class="more"><td colspan="${cols}"><button class="btn" type="button" data-act="more">Show ${Math.min(PAGE, n - S.limit)} more</button> <span class="cap">${S.limit.toLocaleString("en")} of ${n.toLocaleString("en")} shown</span></td></tr>` : "");

const byConfidence = (a, b) => (b.confidence ?? 0) - (a.confidence ?? 0);
const byDate = (a, b) => String(b.begin_date || "").localeCompare(String(a.begin_date || "")) || byConfidence(a, b);

function visibleRows() {
  if (S.mode === "standard") {
    const shownGroups = stdGroups().shown;
    if (S.task === "queue") return shownGroups.filter((g) => g.labels.every((l) => !reviewState(l))).sort(byConfidence);
    return S.collection ? [...shownGroups].sort(byDate) : shownGroups;
  }
  const g = groups();
  if (S.task === "queue") return g.suggested.filter((i) => !reviewState(i)).sort(byConfidence);
  const order = (list) => (S.collection ? [...list].sort(byDate) : list);
  return [...order(g.suggested), ...(S.show.below ? order(g.below) : []), ...(S.show.rejected ? order(g.rejected) : [])];
}

function scopeHtml() {
  const c = S.coll;
  const pool = S.collection && c
    ? `Collection <b>${esc(S.collection)}</b>: <b>${c.n.toLocaleString("en")}</b> affairs${c.pending ? ` · <b>${c.done.toLocaleString("en")}</b> classified so far` : ""}`
    : `Pool: <b>${S.pool.length || S.app.pool.n}</b> affairs`;
  const task = S.task === "new" ? ` · What's new: ${S.prevVisit ? `added since your last visit (${esc(S.prevVisit.slice(0, 16).replace("T", " "))} UTC)` : `dated in the last 30 days (first visit)`}`
    : S.task === "queue" ? " · Review queue: unreviewed suggestions, highest confidence first · <b>C</b> confirm · <b>R</b> reject" : "";
  return `<span class="cap">${pool}${task}</span>`;
}

function confirmJobHtml() {
  const { est, partial } = S.confirmJob;
  const live = S.app.mode === "live";
  return `<h2>${partial ? `${esc(est.name)}: ${est.done.toLocaleString("en")} of ${est.total.toLocaleString("en")} affairs classified` : `${esc(est.name)} is not indexed on ${esc(S.collection)} yet`}</h2>
    <p>${est.pending.toLocaleString("en")} affairs to classify ≈ <b>${est.minutes} min</b> (${est.rate_measured ? "measured" : "assumed until a first run is measured:"} ≈ ${est.rate_per_min} affairs/min). Results appear when it is done; you can stop and continue later — finished affairs are never classified twice.</p>
    ${live ? `<button class="btn btn-primary" type="button" data-act="job-start">${partial ? "Continue" : "Index now"}</button>` : `<p class="cap">The model endpoint is unreachable, so nothing can be indexed now.</p>`}`;
}

const placeholderRows = () => (S.live ? S.pending.filter(passesFilters) : []);

// parliament names come from results/bodies.json (OpenParlData); grouped by level, sorted by name
const bodyName = (key) => { const b = (S.app.bodies || {})[key]; return b ? (b.name.de || b.name.en || key) : key; };
const bodyLevel = (key) => LEVEL[((S.app.bodies || {})[key] || {}).type] || "Municipal";
const bodyLabel = (key) => `${bodyName(key)} (${key})`;

function fillParliaments(keys) {
  const el = $("fParl"); const cur = el.value;
  const groups = ["Federal", "Cantonal", "Municipal"].map((lvl) => [lvl, keys.filter((k) => bodyLevel(k) === lvl)
    .sort((a, b) => bodyName(a).localeCompare(bodyName(b), "de"))]).filter(([, ks]) => ks.length);
  el.innerHTML = `<option value="">All</option>` + groups.map(([lvl, ks]) =>
    `<optgroup label="${lvl}">${ks.map((k) => `<option value="${esc(k)}">${esc(bodyLabel(k))}</option>`).join("")}</optgroup>`).join("");
  el.value = keys.includes(cur) ? cur : "";
}

function fillFilterOptions() {
  if (S.mode === "standard") fillShelves();
  const keep = (id, values, fmt) => {
    const el = $(id); const cur = el.value; const first = el.options[0].outerHTML;
    el.innerHTML = first + values.map((v) => `<option value="${esc(v)}">${esc(fmt(v))}</option>`).join("");
    el.value = values.includes(cur) ? cur : "";
  };
  fillParliaments([...new Set(S.items.map((i) => i.body_key))]);
  const years = [...new Set(S.items.map((i) => (i.begin_date || "").slice(0, 4)).filter(Boolean))].sort();
  keep("fDate", years.slice(1).map((y) => `${y}-01-01`), (v) => `${v.slice(0, 4)} → today`);
}

// ---------- rendering ----------
function render() {
  if (S.limitKey !== `${S.collection}|${S.mode}|${S.task}|${S.topicName}`) {  // new view → first page again
    S.limitKey = `${S.collection}|${S.mode}|${S.task}|${S.topicName}`; S.limit = PAGE;
  }
  $("thead").innerHTML = `<tr>${(S.mode === "standard" ? STD_HEAD : ADHOC_HEAD).map((h) => `<th>${h}</th>`).join("")}</tr>`;
  if (S.mode === "standard") return renderStandard();
  const g = groups();
  const rows = visibleRows();
  $("kwToggle").classList.toggle("hidden", !S.hasKeywords);
  const kwOn = S.kwOnly && S.hasKeywords;
  const notes = [kwOn ? `“Keyword absent” on — every affair below is <i>suggested</i> for ${esc(S.topicName)} yet its text never contains the topic's core words.` : "",
                 S.definitionUsed ? `Definition used: <i>${esc(S.definitionUsed)}</i>` : ""].filter(Boolean);
  $("kwNote").innerHTML = notes.join("<br>");
  $("kwNote").classList.toggle("hidden", !notes.length || (!S.items.length && !S.live));
  $("strip").innerHTML = S.items.length || S.live ? `
    <span><b>${g.suggested.length}</b> suggested</span><span>·</span>
    <span><b>${g.confirmed.length}</b> confirmed</span><span>·</span>
    <button type="button" class="linkbtn" data-show="rejected" aria-pressed="${S.show.rejected}"><b>${g.rejected.length}</b> rejected (evidence not found)</button><span>·</span>
    <button type="button" class="linkbtn" data-show="below" aria-pressed="${S.show.below}"><b>${g.below.length}</b> below threshold ${S.app.match_threshold.toFixed(2)}</button>
    <span>·</span>${scopeHtml()}` : "";
  $("stripBar").classList.toggle("hidden", !S.items.length && !S.live);
  $("rows").innerHTML = rows.slice(0, S.limit).map((i, n) => rowHtml(i, n)).join("") + moreRow(rows.length, 9) +
    placeholderRows().map(placeholderHtml).join("");
  const empty = $("emptyState");
  if (S.confirmJob && !S.job && (!rows.length || S.confirmJob.partial)) {
    empty.innerHTML = confirmJobHtml();
    empty.classList.remove("hidden");
    return;
  }
  if (S.job && !S.items.length) {
    empty.innerHTML = `<h2>Indexing ${esc(S.collection)}…</h2><p>Progress is shown above. Results appear here when it is done.</p>`;
    empty.classList.remove("hidden");
    return;
  }
  if (S.task === "queue" && !rows.length && S.items.length) {
    empty.innerHTML = `<h2>Review queue is empty</h2><p>Every suggestion in this view has a review. Switch to <b>Find all</b> to see them.</p>`;
  } else if (S.task === "new" && !rows.length && S.items.length) {
    empty.innerHTML = `<h2>Nothing new</h2><p>No suggested affairs ${S.prevVisit ? "were added since your last visit" : "are dated in the last 30 days"}.</p>`;
  } else if (!S.items.length && !S.live) {
    empty.innerHTML = S.app.mode === "live" && S.collection
      ? `<h2>Name your topic, then press Classify</h2><p>Give it a name and a one-line definition. Before anything runs you'll see how many of the ${currentCollection().n ? currentCollection().n.toLocaleString("en") : ""} ${esc(S.collection)} affairs need classifying and how long it takes.</p>`
      : S.app.mode === "live"
      ? `<h2>Type a topic, or pick a preset</h2><p>Give a topic a name and a one-line definition, then press <b>Classify</b>. The model reads every affair in the demo pool (${S.app.pool.n} affairs, DE/FR/IT, federal and cantonal) and suggests matches with a verified quote.</p>`
      : `<h2>No cached results for this topic</h2><p>The model endpoint is unreachable, so only stored runs can be shown. Pick a preset with cached results.</p>`;
  } else if (!rows.length && !S.live) {
    empty.innerHTML = `<h2>No matches in this pool</h2><p>Nothing is suggested with the current filters${S.kwOnly ? " and “keyword absent” on" : ""}. Widen the filters, or show the affairs below the threshold.</p>`;
  }
  empty.classList.toggle("hidden", !!rows.length || S.live);
}

function placeholderHtml(i) {
  return `<tr class="dim placeholder"><td>${esc(i.body_key)}</td><td></td><td class="muted nowrap">${esc(i.begin_date)}</td>
    <td>${i.lang ? `<span class="lang">${esc(i.lang.toUpperCase())}</span>` : ""}</td><td class="tbltitle">${esc(i.title)}</td>
    <td colspan="4"><span class="cap"><span class="spin spin-sm" aria-hidden="true"></span> Analyzing…</span></td></tr>`;
}

function quote(i) {
  if (!i.evidence) return "";
  const [o, c] = QUOTES[i.lang] || QUOTES.de;
  const words = i.evidence.replace(/[.…\s]+$/, "").split(/\s+/);
  const ev = words.length > 16 ? words.slice(0, 16).join(" ") : words.join(" ");
  return `<div class="ev" lang="${esc(i.lang)}">${o}…${esc(ev)}…${c}</div>`;
}

function badges(i) {
  const b = [];
  if (i.status === "evidence_failed") b.push(`<span class="badge b-grey">evidence not found</span>`);
  else if (i.verify_ok) b.push(`<span class="badge b-green">✓ evidence verified${i.verify_method === "fuzzy" ? " (fuzzy)" : ""}</span>`);
  if (S.hasKeywords && i.keyword_absent === true) b.push(`<span class="badge b-amber">⚑ keyword absent</span>`);
  if (S.hasKeywords && i.keyword_absent === true && i.tech_vocab_absent === true) b.push(`<span class="badge b-grey">tech vocab absent</span>`);
  if (i.title_only) b.push(`<span class="badge b-grey">title only</span>`);
  return b.length ? `<div class="badges">${b.join("")}</div>` : "";
}

function labelCell(i) {
  const st = reviewState(i);
  if (i.status === "evidence_failed") return `<span class="chip chip-grey">Rejected · evidence not found</span>`;
  if (st === "confirmed") return `<span class="chip chip-topic">${esc(S.topicName)}</span>`;
  if (st === "rejected") return `<span class="chip chip-grey">Rejected by reviewer</span>`;
  return `<div class="labelcell"><span class="chip chip-topic">${esc(S.topicName)}</span><span class="ai">✦ AI suggestion</span></div>`;
}

function reviewCell(i) {
  const st = reviewState(i);
  if (st === "confirmed") return `<span class="chip chip-confirmed">✓ Confirmed</span>`;
  if (st === "rejected") return `<span class="chip chip-grey">Rejected</span>`;
  return `<span class="ai">✦ AI suggestion</span>`;
}

function rowHtml(i, n) {
  const conf = i.confidence == null ? "" : `<div class="conf"><span class="track"><span class="fill" style="width:${Math.round(i.confidence * 100)}%"></span></span><span class="num">${i.confidence.toFixed(2)}</span></div>`;
  return `<tr tabindex="0" data-pid="${i.prediction_id}" data-n="${n}" class="${n === S.selected ? "sel" : ""}${shown(i) ? "" : " dim"}">
    <td title="${esc(bodyLabel(i.body_key))}">${esc(i.body_key)}</td><td class="mono muted">${esc(i.number)}</td><td class="muted nowrap">${esc(i.begin_date)}</td>
    <td><span class="lang">${esc((i.lang || "").toUpperCase())}</span></td>
    <td class="tbltitle" lang="${esc(i.lang)}">${esc(i.title)}</td>
    <td>${labelCell(i)}</td><td>${conf}</td><td class="evcell">${quote(i)}${badges(i)}</td><td>${reviewCell(i)}</td></tr>`;
}

function alertStrip(msg) {
  $("stripBar").classList.remove("hidden");
  $("strip").innerHTML = `<span role="alert"><b>${esc(msg)}</b></span>`;
}

// ---------- detail panel & review ----------
// section headers of the assembled text (TITLE:, TEXT:, DOCUMENT (…):) in bold, so long texts are scannable
const sections = (html) => html.replace(/(^|\n\n)([A-ZÄÖÜ][A-ZÄÖÜ ]+(?: \([^)\n]*\))?):/g, '$1<b class="sec">$2</b>:');

function highlight(text, span) {
  if (!span) return sections(esc(text));
  const [a, b] = span;
  return sections(`${esc(text.slice(0, a))}<mark>${esc(text.slice(a, b))}</mark>${esc(text.slice(b))}`);
}

async function openDetail(pid) {
  if (S.mode === "standard") return openStandardDetail(pid);
  const d = await api(`/api/predictions/${pid}`);
  const item = S.items.find((i) => i.prediction_id === pid) || {};
  S.detailId = pid;
  const last = d.reviews[d.reviews.length - 1];
  const st = last ? reviewState({ review_decision: last.decision, review_label: last.corrected_label }) : "";
  const stateChip = st === "confirmed" ? `<span class="chip chip-confirmed">✓ Confirmed by reviewer</span>`
    : st === "rejected" ? `<span class="chip chip-grey">✕ Rejected by reviewer</span>` : `<span class="ai">✦ AI suggestion — needs confirmation</span>`;
  const rl = S.app.review_lang;
  const aid = rl && d.lang && d.lang !== rl
    ? `<div class="aid" id="readingAid"><button class="btn" type="button" data-act="reading">Show ${esc(rl.toUpperCase())} version</button>
       <span class="cap">The text above is the original (${esc(d.lang.toUpperCase())}); the evidence is checked against it.</span></div>` : "";
  const verified = d.status === "evidence_failed" ? `<span class="badge b-grey">evidence not found</span>`
    : d.verify_ok ? `<span class="badge b-green">✓ found in source text${d.verify_method === "fuzzy" ? " (fuzzy)" : ""}</span>` : "";
  $("detail").innerHTML = `
    <div class="dtop">
      <button class="iconbtn" type="button" data-act="close" aria-label="Close detail">✕</button>
      <span class="spacer"></span>
      <button class="iconbtn" type="button" data-act="prev" aria-label="Previous affair">↑</button>
      <button class="iconbtn" type="button" data-act="next" aria-label="Next affair">↓</button>
    </div>
    <div class="dbody">
      <div class="badges">
        ${d.type ? `<span class="chip chip-topic">${esc(d.type)}</span>` : ""}
        <span class="chip chip-grey">${esc(d.body_key)} · ${esc(LEVEL[d.body_type] || "Municipal")}</span>
        <span class="mono cap" style="align-self:center">${esc(d.number || "")}</span>
        <span class="lang">${esc((d.lang || "").toUpperCase())}</span>
        <span class="cap" style="align-self:center">${esc(d.begin_date || "")}</span>
      </div>
      <h1 lang="${esc(d.lang)}">${esc(d.title)}</h1>
      <div class="dgrid">
        <div><div class="meta-k">Suggested topic</div>
          <div class="badges"><span class="chip chip-topic">${esc(S.topicName)}</span>${stateChip}</div>
          <div class="cap" style="margin-top:6px">Model label: <b>${esc(d.label || d.status)}</b></div></div>
        <div><div class="meta-k">Model confidence</div>
          <div class="conf" style="margin-top:8px"><span class="track"><span class="fill" style="width:${Math.round((d.confidence || 0) * 100)}%"></span></span><span class="num">${d.confidence == null ? "—" : d.confidence.toFixed(2)}</span></div></div>
      </div>
      <div class="badges" style="align-items:center"><span class="meta-k">Evidence</span>${verified}${S.hasKeywords && item.keyword_absent === true ? `<span class="badge b-amber">⚑ keyword absent</span>` : ""}${d.title_only ? `<span class="badge b-grey">title only</span>` : ""}</div>
      <div class="textbox" lang="${esc(d.lang)}">${highlight(d.text || "", d.evidence_span)}</div>
      ${aid}
      <div class="rationale"><div class="meta-k">Model rationale — not evidence</div><div class="cap" style="font-size:13.5px">${esc(d.rationale)}</div></div>
      ${d.url ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">Open source page ↗</a>` : ""}
      <div class="reviewline" id="reviewLine" role="status" aria-live="polite">${last ? `Saved: <b>${esc(last.decision)}</b>${last.corrected_label ? ` → ${esc(last.corrected_label)}` : ""} · ${esc(last.created_at.slice(11, 16))} UTC · ${d.reviews.length} review${d.reviews.length > 1 ? "s" : ""} on record (latest counts)` : ""}</div>
    </div>
    <div class="dactions">
      <button class="btn btn-primary" type="button" data-act="confirm" aria-pressed="${st === "confirmed"}">${st === "confirmed" ? "✓ Confirmed" : "Confirm"} <span class="kbd"><b>C</b></span></button>
      <button class="btn${st === "rejected" ? " btn-on" : ""}" type="button" data-act="reject" aria-pressed="${st === "rejected"}">${st === "rejected" ? "✕ Rejected" : "Reject"} <span class="kbd"><b>R</b></span></button>
    </div>`;
  $("detail").classList.remove("hidden");
  $("scrim").classList.remove("hidden");
}

async function readingAid(pid, machine) {
  const box = $("readingAid");
  const lang = S.app.review_lang;
  box.innerHTML = `<span class="cap">Loading…</span>`;
  try {
    const r = machine
      ? await api(`/api/predictions/${pid}/translate?lang=${encodeURIComponent(lang)}`, { method: "POST" })
      : await api(`/api/predictions/${pid}/reading?lang=${encodeURIComponent(lang)}`);
    if (r.kind === "none") {
      box.innerHTML = `<button class="btn" type="button" data-act="translate"${S.app.mode === "live" ? "" : " disabled"}>Translate to ${esc(lang.toUpperCase())} with Apertus (unofficial)</button>
        <span class="cap">This parliament publishes no ${esc(lang.toUpperCase())} version.${S.app.mode === "live" ? "" : " Needs the model endpoint."}</span>`;
      return;
    }
    if (r.kind === "official") {
      box.innerHTML = `<div class="meta-k">Official ${esc(lang.toUpperCase())} version</div><div class="cap">${esc(r.note)}</div>
        <div class="textbox textbox-aid" lang="${esc(lang)}">${sections(esc(r.text))}</div>`;
      return;
    }
    const cut = r.cut_before || r.cut_after;
    box.innerHTML = `<div class="meta-k">Unofficial machine translation (${esc(r.model)})</div><div class="cap">${esc(r.note)}</div>
      ${r.evidence ? `<div class="meta-k" style="margin-top:10px">Proof sentence, translated</div>
        <div class="textbox textbox-aid textbox-ev" lang="${esc(lang)}"><mark>${esc(r.evidence)}</mark></div>` : ""}
      <div class="meta-k" style="margin-top:10px">${cut ? "Passage around the proof sentence, translated" : "Text, translated"}</div>
      ${cut ? `<div class="cap">Only this passage is translated; the full original is above.</div>` : ""}
      <div class="textbox textbox-aid" lang="${esc(lang)}">${r.cut_before ? "… " : ""}${sections(esc(r.text))}${r.cut_after ? " …" : ""}</div>`;
  } catch (e) {
    box.innerHTML = `<span class="cap" role="alert">Could not load: ${esc(e.message)}</span>`;
  }
}

function closeDetail() {
  S.detailId = null;
  $("detail").classList.add("hidden");
  $("scrim").classList.add("hidden");
}

async function review(pid, decision, correctedLabel) {
  if (!pid) return;
  const res = await api("/api/reviews", { method: "POST", body: JSON.stringify({ prediction_id: pid, decision, corrected_label: correctedLabel || null }) });
  const last = res.reviews[res.reviews.length - 1];
  const item = S.items.find((i) => i.prediction_id === pid);
  if (item) Object.assign(item, { review_decision: last.decision, review_label: last.corrected_label });
  const queueNext = S.task === "queue" && S.mode !== "standard" && S.detailId === pid;
  render();
  if (queueNext) {
    const next = visibleRows()[Math.max(0, Math.min(S.selected, visibleRows().length - 1))];
    return next ? openDetail(next.prediction_id) : closeDetail();
  }
  if (S.mode === "standard" && S.detailId) openStandardDetail(S.detailId);
  else if (S.detailId === pid) openDetail(pid);
}

function move(delta) {
  const rows = visibleRows();
  if (!rows.length) return;
  S.selected = Math.max(0, Math.min(rows.length - 1, S.selected + delta));
  if (S.selected >= S.limit) S.limit += PAGE;
  render();
  const tr = document.querySelector(`tr[data-n="${S.selected}"]`);
  if (tr) { tr.focus(); tr.scrollIntoView({ block: "nearest" }); }
  if (S.detailId) openDetail(rows[S.selected].prediction_id);
}

const selectedPid = () => S.detailId || (visibleRows()[S.selected] || {}).prediction_id;

// ---------- standard mode (APS / Curia Vista) ----------
const schemeName = (id) => ((S.app.schemes || []).find((x) => x.id === id) || {}).name || id;

// Curia Vista is the federal parliament's own scheme: offered for the demo pool and federal collections only
const schemesHere = () => (S.app.schemes || []).filter((x) => x.id !== "curia_vista" || !S.collection || currentCollection().level === "Federal");

function renderSchemes() {
  if (!schemesHere().some((x) => x.id === S.scheme)) S.scheme = (schemesHere()[0] || {}).id || S.scheme;
  $("schemeSeg").innerHTML = schemesHere().map((x) =>
    `<button type="button" data-scheme="${esc(x.id)}" class="${x.id === S.scheme ? "on" : ""}" aria-pressed="${x.id === S.scheme}">${esc(x.name)}</button>`).join("");
}

async function setMode(mode) {
  if (S.live) return;
  S.mode = mode;
  document.querySelectorAll("[data-mode]").forEach((x) => { x.classList.toggle("on", x.dataset.mode === mode); x.setAttribute("aria-pressed", String(x.dataset.mode === mode)); });
  document.querySelectorAll(".adhoc-only").forEach((x) => x.classList.toggle("hidden", mode !== "adhoc"));
  document.querySelectorAll(".std-only").forEach((x) => x.classList.toggle("hidden", mode !== "standard"));
  document.body.classList.toggle("std", mode === "standard");
  closeTopic();
  $("kwToggle").classList.toggle("hidden", mode === "standard" || !S.hasKeywords);
  closeDetail();
  S.runId = null; S.items = []; S.selected = -1;
  render();
  if (mode === "standard") return selectScheme(S.scheme);
  selectPreset(S.presetId || (S.app.presets.find((p) => p.id === S.app.default_preset) || S.app.presets[0] || {}).id);
}

async function selectScheme(id) {
  S.scheme = id; S.filters.shelf = ""; $("fShelf").value = ""; renderSchemes();
  const seq = ++S.loadSeq;
  if (!S.labelNames[id]) S.labelNames[id] = await api(`/api/schemes/${encodeURIComponent(id)}/labels`);
  if (seq !== S.loadSeq || S.scheme !== id) return;
  const sc = (S.app.schemes || []).find((x) => x.id === id);
  S.topicName = schemeName(id); S.definitionUsed = ""; S.hasKeywords = false;
  if (S.collection) return loadCollection(`scheme:${id}`);
  if (sc && sc.run) return loadRun(sc.run.run_id);
  S.loadSeq += 1; S.items = []; S.runId = null; render();
}

function labelText(sid, lang) {
  if (sid === "NONE_OTHER") return "None / other";
  const names = (S.labelNames[S.scheme] || {})[sid] || {};
  return names[lang] || names[S.app.scheme_label_fallback] || Object.values(names)[0] || sid;
}

function stdGroups() {
  const by = new Map();
  for (const i of S.items) {
    if (!passesFilters(i)) continue;
    if (!by.has(i.affair_id)) by.set(i.affair_id, { ...i, labels: [], failed: 0 });
    const g = by.get(i.affair_id);
    if (i.status === "ok" && i.label && !g.labels.some((l) => l.label === i.label)) g.labels.push(i);
    else if (i.status === "evidence_failed") g.failed += 1;
  }
  const shelf = S.filters.shelf;
  const onShelf = (l) => shelf && (l.label === shelf || String(l.label).startsWith(`${shelf}.`));
  const all = [...by.values()].filter((g) => !shelf || g.labels.some(onShelf));
  for (const g of all) {
    g.labels.sort((a, b) => (a.rank || 9) - (b.rank || 9) || String(a.label).localeCompare(String(b.label)));
    const top = g.labels.find((l) => shelf && l.label === shelf) || g.labels.find((l) => l.label !== "NONE_OTHER") || g.labels[0];
    if (top) Object.assign(g, { prediction_id: top.prediction_id, evidence: top.evidence, verify_ok: top.verify_ok, verify_method: top.verify_method });
  }
  return { all, shown: all.filter((g) => g.labels.length), failed: all.reduce((n, g) => n + g.failed, 0),
           none: all.filter((g) => g.labels.length && g.labels.every((l) => l.label === "NONE_OTHER")).length };
}

// "Shelf" filter: every category that occurs in the loaded results, with its number of affairs
function fillShelves() {
  const el = $("fShelf"); const cur = el.value;
  const count = new Map();
  const seen = new Set();
  for (const i of S.items) {
    if (i.status !== "ok" || !i.label || i.label === "NONE_OTHER" || seen.has(`${i.affair_id}|${i.label}`)) continue;
    seen.add(`${i.affair_id}|${i.label}`);
    count.set(i.label, (count.get(i.label) || 0) + 1);
  }
  const isTopic = (id) => (id.match(/\./g) || []).length >= 2;
  const opt = (id) => `<option value="${esc(id)}">${esc(labelText(id, "de"))} (${count.get(id)})</option>`;
  const byName = (a, b) => labelText(a, "de").localeCompare(labelText(b, "de"), "de");
  const ids = [...count.keys()];
  const chapters = ids.filter((id) => !isTopic(id)).sort(byName), topics = ids.filter(isTopic).sort(byName);
  el.innerHTML = `<option value="">All</option>` + (topics.length ? `<optgroup label="Topics">${topics.map(opt).join("")}</optgroup>` : "") +
    (chapters.length ? `<optgroup label="${topics.length ? "Chapters" : "Areas"}">${chapters.map(opt).join("")}</optgroup>` : "");
  el.value = count.has(cur) ? cur : "";
  S.filters.shelf = el.value;
}

function paths(g) {
  const isTopic = (l) => (l.label.match(/\./g) || []).length >= 2;
  const topics = g.labels.filter((l) => l.label !== "NONE_OTHER" && isTopic(l));
  const chapters = g.labels.filter((l) => l.label !== "NONE_OTHER" && !isTopic(l));
  const out = [];
  for (const c of chapters) {
    const sub = topics.filter((t) => t.label.startsWith(`${c.label}.`));
    if (!sub.length) out.push({ chap: labelText(c.label, g.lang), conf: c.confidence });
    for (const t of sub) out.push({ chap: labelText(c.label, g.lang), topic: labelText(t.label, g.lang), conf: t.confidence });
  }
  for (const t of topics.filter((t) => !chapters.some((c) => t.label.startsWith(`${c.label}.`)))) out.push({ topic: labelText(t.label, g.lang), conf: t.confidence });
  if (g.labels.some((l) => l.label === "NONE_OTHER")) out.push({ none: true });
  return out;
}

function stdReview(g) {
  const st = g.labels.map(reviewState);
  if (st.length && st.every((x) => x === "confirmed")) return `<span class="chip chip-confirmed">✓ Confirmed</span>`;
  if (st.some((x) => x === "rejected")) return `<span class="chip chip-grey">Partly rejected</span>`;
  if (st.some((x) => x === "confirmed")) return `<span class="chip chip-topic">Partly confirmed</span>`;
  return `<span class="ai">✦ AI suggestion</span>`;
}

function renderStandard() {
  const g = stdGroups();
  const fallbackNote = S.scheme === "aps" ? " · Italian affairs show German APS labels" : "";
  $("strip").innerHTML = S.items.length || S.live ? `
    <span><b>${g.shown.length}</b> ${g.shown.length === 1 ? "affair" : "affairs"} labelled</span><span>·</span>
    <span><b>${g.shown.reduce((n, x) => n + x.labels.filter((l) => l.label !== "NONE_OTHER").length, 0)}</b> labels</span><span>·</span>
    <span><b>${g.none}</b> none / other</span><span>·</span>
    <span><b>${g.failed}</b> labels rejected (evidence not found)</span>
    <span class="spacer"></span>${scopeHtml()}<span class="cap"> · scheme ${esc(schemeName(S.scheme))}${fallbackNote}</span>` : "";
  $("stripBar").classList.toggle("hidden", !S.items.length && !S.live);
  $("kwNote").classList.add("hidden");
  const empty = $("emptyState");
  if (S.confirmJob && !S.job && (!g.shown.length || S.confirmJob.partial)) {
    $("rows").innerHTML = "";
    empty.innerHTML = confirmJobHtml();
    return empty.classList.remove("hidden");
  }
  const all = visibleRows();
  $("rows").innerHTML = all.slice(0, S.limit).map((x, n) => `<tr tabindex="0" data-pid="${x.prediction_id}" data-n="${n}" class="${n === S.selected ? "sel" : ""}">
    <td>${esc(x.body_key)}</td><td class="mono muted">${esc(x.number)}</td><td class="muted nowrap">${esc(x.begin_date)}</td>
    <td><span class="lang">${esc((x.lang || "").toUpperCase())}</span></td><td class="tbltitle" lang="${esc(x.lang)}">${esc(x.title)}</td>
    <td><div class="labels">${paths(x).map((p) => p.none ? `<span class="path none">None / other</span>`
      : `<span class="path">${p.chap ? `<span class="chap">${esc(p.chap)}</span>` : ""}${p.chap && p.topic ? `<span class="arr">→</span>` : ""}${p.topic ? `<span class="topic">${esc(p.topic)}</span>` : ""}<span class="cf">${(p.conf ?? 0).toFixed(2)}</span></span>`).join("")}</div></td>
    <td class="evcell">${quote(x)}</td><td>${stdReview(x)}</td></tr>`).join("") + moreRow(all.length, 8) + placeholderRows().map(placeholderHtml).join("");
  if (!S.items.length && !S.live) empty.innerHTML = `<h2>No results for ${esc(schemeName(S.scheme))} yet</h2><p>${S.app.mode === "live" ? "Press <b>Classify</b> to label the demo pool with this scheme." : "The model endpoint is unreachable and no cached run exists for this scheme."}</p>`;
  empty.classList.toggle("hidden", !!g.shown.length || S.live);
}

async function openStandardDetail(pid) {
  const group = stdGroups().all.find((x) => x.labels.some((l) => l.prediction_id === pid));
  if (!group) return;
  const d = await api(`/api/predictions/${pid}`);
  S.detailId = pid;
  const rl = S.app.review_lang;
  const aid = rl && d.lang && d.lang !== rl ? `<div class="aid" id="readingAid"><button class="btn" type="button" data-act="reading">Show ${esc(rl.toUpperCase())} version</button></div>` : "";
  const items = group.labels.map((l) => {
    const st = reviewState(l);
    const name = l.label === "NONE_OTHER" ? "None / other" : labelText(l.label, group.lang);
    return `<div class="lbitem${l.prediction_id === pid ? " on" : ""}">
      <div class="badges" style="align-items:center;margin:0"><span class="chip chip-topic">${esc(name)}</span><span class="mono cap">${esc(l.label)}</span>
        <span class="cap">confidence ${(l.confidence ?? 0).toFixed(2)}</span>${st === "confirmed" ? `<span class="chip chip-confirmed">✓ Confirmed by reviewer</span>` : st === "rejected" ? `<span class="chip chip-grey">✕ Rejected by reviewer</span>` : `<span class="ai">✦ AI suggestion</span>`}</div>
      ${l.evidence ? `<div class="ev" lang="${esc(group.lang)}">${esc(l.evidence)}</div>` : ""}
      <div class="acts"><button class="btn btn-sm" type="button" data-act="show-label" data-pid="${l.prediction_id}">Highlight evidence</button>
        <button class="btn btn-sm btn-primary" type="button" data-act="confirm-label" data-pid="${l.prediction_id}" aria-pressed="${st === "confirmed"}">${st === "confirmed" ? "✓ Confirmed" : "Confirm"}</button>
        <button class="btn btn-sm${st === "rejected" ? " btn-on" : ""}" type="button" data-act="reject-label" data-pid="${l.prediction_id}" aria-pressed="${st === "rejected"}">${st === "rejected" ? "✕ Rejected" : "Reject"}</button></div></div>`;
  }).join("");
  $("detail").innerHTML = `
    <div class="dtop"><button class="iconbtn" type="button" data-act="close" aria-label="Close detail">✕</button><span class="spacer"></span>
      <button class="iconbtn" type="button" data-act="prev" aria-label="Previous affair">↑</button><button class="iconbtn" type="button" data-act="next" aria-label="Next affair">↓</button></div>
    <div class="dbody">
      <div class="badges">${d.type ? `<span class="chip chip-topic">${esc(d.type)}</span>` : ""}<span class="chip chip-grey">${esc(d.body_key)} · ${esc(LEVEL[d.body_type] || "Municipal")}</span>
        <span class="mono cap" style="align-self:center">${esc(d.number || "")}</span><span class="lang">${esc((d.lang || "").toUpperCase())}</span><span class="cap" style="align-self:center">${esc(d.begin_date || "")}</span></div>
      <h1 lang="${esc(d.lang)}">${esc(d.title)}</h1>
      <div class="meta-k">Suggested ${esc(schemeName(S.scheme))} labels — review each one</div>
      <div class="lblist">${items}</div>
      <div class="meta-k">Text (evidence of the selected label highlighted)</div>
      <div class="textbox" lang="${esc(d.lang)}">${highlight(d.text || "", d.evidence_span)}</div>
      ${aid}
      <div class="rationale"><div class="meta-k">Model rationale — not evidence</div><div class="cap" style="font-size:13.5px">${esc(d.rationale)}</div></div>
      ${d.url ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">Open source page ↗</a>` : ""}
    </div>`;
  $("detail").classList.remove("hidden");
  $("scrim").classList.remove("hidden");
}

// ---------- metrics ----------
const pct = (x) => (x == null ? "—" : `${(100 * x).toFixed(1)}%`);
const ci = (c) => (c ? `${(100 * c[0]).toFixed(0)}–${(100 * c[1]).toFixed(0)}%` : "");

function bar(label, value, ciArr, base) {
  const w = (x) => `${Math.max(0, Math.min(100, 100 * x))}%`;
  const whisk = ciArr ? `<span class="whisk" style="left:${w(ciArr[0])};width:calc(${w(ciArr[1])} - ${w(ciArr[0])})"></span>` : "";
  return `<div class="barrow"><span class="cap" style="font-weight:600;color:#4B473F">${esc(label)}</span>
    <span class="track"><span class="fill${base ? " base" : ""}" style="width:${w(value || 0)}"></span>${whisk}</span>
    <span class="mono">${pct(value)} <span class="cap">${ci(ciArr)}</span></span></div>`;
}

const pts = (x) => (x == null ? "—" : `${Math.round(100 * x)}%`);
const num = (x) => (x == null ? "—" : x.toLocaleString("en"));

function kpi(label, value, delta, text, good = true) {
  return `<div class="kpi"><div class="klabel">${label}</div><div class="kval">${value}${delta ? ` <span class="kdelta${good ? "" : " neutral"}">${delta}</span>` : ""}</div><div class="ktext">${text}</div></div>`;
}

function rangeRow(label, lo, hi, dots) {
  // a 0–100 % track: the shaded band is a pre-registered estimate's 95 % range, dots are measured values
  const w = (x) => `${Math.max(0, Math.min(100, 100 * x))}%`;
  return `<div class="rrow"><span class="rlabel">${label}</span><span class="rtrack">${lo != null ? `<span class="rband" style="left:${w(lo)};width:calc(${w(hi)} - ${w(lo)})"></span>` : ""}
    ${dots.map((d) => `<span class="rdot ${d.cls}" style="left:${w(d.v)}" title="${esc(d.t)}: ${pct(d.v)}"></span>`).join("")}</span></div>`;
}

async function loadMetrics() {
  const grid = $("metricsGrid");
  let m;
  try { m = await api("/api/metrics"); } catch (e) { grid.innerHTML = `<div class="card wide"><div class="ctitle">No metrics yet</div><div class="csub">${esc(e.message)}</div></div>`; return; }
  const d = m.digitalisation_federal_2018, fp = m.full_population || {}, sc = m.scale || {};
  if (!d || !fp.CHE) { grid.innerHTML = `<div class="card wide"><div class="ctitle">Metrics incomplete</div><div class="csub">Run <span class="mono">parltopics eval collection</span> for the collections.</div></div>`; return; }
  const che = fp.CHE, be = fp.BE, tg = fp.TG;
  const base = che.baselines_full_text || {}, cv = base.curia_vista_area, kwFull = base.keyword_search_core;
  const t = d.test.at_chosen_threshold, adj = ((m.adjudication || {}).readings || {}).strict;
  const xl = m.cross_language, cvs = (m.curia_vista_standard || {}).test, q = d.test.quality;
  const un = che.model_without_sample_affairs;
  const fed = (sc.measured_runs || []).find((r) => r.collection === "collection:CHE");
  const proj = sc.projection_all_affairs || {};
  const noKw = (che.found_without_core_keyword || {}).n + ((be || {}).found_without_core_keyword || {}).n;

  // comparison table: best value per column highlighted
  const cols = [["CHE", "precision"], ["CHE", "recall"], ["CHE", "f1"], ["BE", "precision"], ["BE", "recall"], ["TG", "precision"], ["TG", "recall"]];
  const rows = [
    { name: "<b>Unisono</b> (Apertus)", get: (b, k) => (fp[b] || {}).model?.[k] },
    { name: "Parliament's category<br><span class='cap'>Curia Vista “Medien und Kommunikation”</span>", get: (b, k) => (b === "CHE" && cv ? cv[k] : null) },
    { name: "Keyword search<br><span class='cap'>Digitalisierung · numérique · digitale …</span>", get: (b, k) => (b === "CHE" && kwFull ? kwFull[k] : (fp[b] || {}).keyword_search_core_model_text?.[k]) },
  ];
  const best = cols.map(([b, k]) => Math.max(...rows.map((r) => r.get(b, k) ?? -1)));
  const table = `<table class="ctab"><thead><tr><th rowspan="2">Method</th><th colspan="3">Federal · ${num(che.population.n)} affairs</th><th colspan="2">Bern · ${num((be || {}).population?.n)}</th><th colspan="2">Thurgau · ${num((tg || {}).population?.n)}</th></tr>
    <tr>${cols.map(([, k]) => `<th>${{ precision: "Precision", recall: "Recall", f1: "Balance (F1)" }[k]}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r, i) => `<tr class="${i === 0 ? "ours" : ""}"><td>${r.name}</td>${cols.map(([b, k], j) => { const v = r.get(b, k);
      return `<td class="${v != null && v === best[j] ? "best" : ""}">${v == null ? `<span class="cap">n/a</span>` : pts(v)}</td>`; }).join("")}</tr>`).join("")}</tbody></table>`;

  grid.innerHTML = `
    <div class="mhead wide"><div class="mh1">How well does Unisono find affairs about digitalisation?</div>
      <div class="csub" style="margin:4px 0 0">Compared with <b>PolitMonitor</b> — the list DVS tags by hand — on <b>every affair since 2018</b> of three parliaments, not a sample.
      Model ${esc(modelLabel(d.model))}, cut-off 0.9 fixed before testing, no tuning on these numbers.</div></div>

    <div class="kpis wide">
      ${kpi("Precision · federal", pts(che.model.precision), cv ? `+${Math.round(100 * (che.model.precision - cv.precision))} pts` : "",
        `Of 100 suggestions, <b>${Math.round(100 * che.model.precision)}</b> are on PolitMonitor's list. Parliament's category: ${Math.round(100 * cv.precision)}.`)}
      ${be ? kpi("Bern · precision / recall", `${pts(be.model.precision)} / ${pts(be.model.recall)}`, "", `Keyword search: ${pts(be.keyword_search_core_model_text.precision)} / ${pts(be.keyword_search_core_model_text.recall)}. All ${num(be.population.n)} cantonal affairs.`) : ""}
      ${kpi("Found without the keyword", num(noKw), "", "Tagged affairs found by Unisono whose text never says <i>Digitalisierung / numérique / digitale</i> — invisible to keyword search.")}
      ${xl ? kpi("Same answer in DE · FR · IT", pts(xl.adhoc.all_agree.rate), "", `The same ${xl.adhoc.n} federal affairs read in all three official languages.`) : ""}
      ${fed ? kpi("All federal affairs", `${Math.round(fed.minutes)} min`, "", `${num(fed.affairs)} affairs at ${fed.concurrency} parallel requests on the Swiss gateway.`) : ""}
    </div>

    <div class="card span2"><div class="ctitle">How we compare</div>
      <div class="csub">Same affairs, same reference list. Best value per column highlighted. “n/a”: cantons have no comparable category.</div>
      ${table}
      <div class="meta-k" style="margin-top:18px">Federal, at a glance</div>
      ${bar("Unisono · precision", che.model.precision)}${bar("Category · precision", cv.precision, null, true)}
      ${bar("Unisono · recall", che.model.recall)}${bar("Category · recall", cv.recall, null, true)}
    </div>

    <div class="card"><div class="ctitle">What the numbers mean</div><div class="csub">In plain words</div>
      <div class="explain"><b>Precision — how often a suggestion is right.</b> ${pts(che.model.precision)} federal: of 100 affairs we suggest, ${Math.round(100 * che.model.precision)} are on PolitMonitor's list.</div>
      <div class="explain"><b>Recall — how much of the list we find.</b> ${pts(che.model.recall)}: of 100 tagged affairs, we find ${Math.round(100 * che.model.recall)}.</div>
      <div class="explain"><b>The trade-off.</b> The parliament's category finds more (${pts(cv.recall)}), but ${Math.round(100 * (1 - cv.precision))} in 100 of its hits are not about digitalisation. Unisono suggests fewer — and every suggestion comes with a quote that code has checked in the original text.</div>
      <div class="explain"><b>“Right” means “on PolitMonitor's list”.</b> That list is hand-made and misses affairs: in our blind review, every affair we found that PolitMonitor had not tagged was digital. So our precision here is a floor.</div>
    </div>

    <div class="card span2"><div class="ctitle">Can you trust these numbers?</div>
      <div class="csub">Shaded band: the 95% range we predicted from a fixed test sample before running everything. Dots: what we then measured.</div>
      <div class="rlegend"><span><i class="rdot-k sample"></i>test sample (${t.n_pos + t.n_neg} affairs)</span><span><i class="rdot-k full"></i>all ${num(che.population.n)} federal affairs</span><span><i class="rdot-k untouched"></i>${num(un.n)} affairs never used in development</span></div>
      ${rangeRow("Precision", t.precision_corrected_ci95[0], t.precision_corrected_ci95[1], [{ v: t.precision_corrected, cls: "sample", t: "test sample" }, { v: che.model.precision, cls: "full", t: "all affairs" }, { v: un.precision, cls: "untouched", t: "never used" }])}
      ${rangeRow("Recall", t.recall_ci95[0], t.recall_ci95[1], [{ v: t.recall, cls: "sample", t: "test sample" }, { v: che.model.recall, cls: "full", t: "all affairs" }, { v: un.recall, cls: "untouched", t: "never used" }])}
      <div class="kv"><span>Test sample (pre-registered) → all federal affairs</span><span class="kvv">${pct(t.precision_corrected)} → ${pct(che.model.precision)} precision · ${pct(t.recall)} → ${pct(che.model.recall)} recall</span></div>
      <div class="kv"><span>Affairs never seen during development</span><span class="kvv">${pct(un.precision)} / ${pct(un.recall)}</span></div>
      ${adj ? `<div class="kv"><span>After blind review by a team member (MA, political science)</span><span class="kvv">precision ${pct(adj.precision)} <span class="cap">${ci(adj.precision_ci95)} · ${adj.answered.TP + adj.answered.FN + adj.answered.FP + adj.answered.TN} affairs, wide range</span></span></div>` : ""}
      ${xl ? `<div class="kv"><span>Language fairness: same answer in DE · FR · IT</span><span class="kvv">${pct(xl.adhoc.all_agree.rate)} <span class="cap">${ci(xl.adhoc.all_agree.ci95)}</span></span></div>` : ""}
      <div class="kv"><span>Proof quotes found in the text (test run)</span><span class="kvv">${q.evidence.verified}/${q.evidence.model_matches}</span></div>
    </div>

    <div class="card"><div class="ctitle">Cost & scale</div><div class="csub">Measured on the overnight runs · no price per token known, so hours and tokens</div>
      ${(sc.measured_runs || []).filter((r) => r.topic !== "Covid-19").map((r) => `<div class="kv"><span>${esc(r.collection.replace("collection:", ""))} · ${esc(r.topic)}</span><span class="kvv">${num(r.affairs)} in ${Math.round(r.minutes)} min <span class="cap">${Math.round(r.affairs_per_min)}/min</span></span></div>`).join("")}
      ${sc.openparldata_affairs ? `<div class="meta-k" style="margin-top:14px">All ${num(sc.openparldata_affairs)} OpenParlData affairs</div>
      ${proj.federal_texts ? `<div class="kv"><span>One topic</span><span class="kvv">≈ ${Math.round(proj.federal_texts.hours)}–${Math.round((proj.cantonal_texts || proj.federal_texts).hours)} h <span class="cap">${proj.federal_texts.tokens_in_millions}–${(proj.cantonal_texts || proj.federal_texts).tokens_in_millions} M tokens in</span></span></div>` : ""}
      ${proj.aps_two_stage ? `<div class="kv"><span>APS scheme (2 steps)</span><span class="kvv">≈ ${Math.round(proj.aps_two_stage.hours)} h</span></div>` : ""}
      <div class="kv"><span>Afterwards</span><span class="kvv">only new affairs · minutes per day</span></div>` : ""}
    </div>

    <div class="card"><div class="ctitle">Limits & edge cases</div><div class="csub">What we know does not work well yet</div>
      <ul class="limits">
        <li><b>Recall</b> is below the broad category (${pts(che.model.recall)} vs ${pts(cv.recall)}): we miss part of the list — partly because PolitMonitor tags broadly.</li>
        <li><b>Very long texts</b> (> ~12,000 characters) can make the model drift to the main subject; a fix was tested but not adopted (pre-set rule).</li>
        <li><b>Scanned PDFs</b> are noisy; quotes then fail the check more often (shown as “evidence not found”, never as a match).</li>
        <li><b>Title-only affairs</b> (some federal bills) give the model little to read.</li>
        <li><b>Broad custom definitions</b> pull in neighbours (e.g. “Wolf” also found cormorants) — a sharper definition and the review fix it.</li>
        <li><b>APS accuracy</b> is not measured yet: there is no hand-labelled reference.</li>
      </ul>
    </div>

    <div class="card"><div class="ctitle">Other checks</div><div class="csub">Parliament's own categories · quality</div>
      ${cvs ? `<div class="kv"><span>Curia Vista areas: at least one right</span><span class="kvv">${pct(cvs.at_least_one_correct.rate)} <span class="cap">n = ${cvs.n}</span></span></div>
      <div class="kv"><span>Curia Vista: areas named (ours · parliament)</span><span class="kvv">${cvs.cardinality.pred_mean.toFixed(1)} · ${cvs.cardinality.gold_mean.toFixed(1)}</span></div>` : ""}
      ${xl ? `<div class="kv"><span>Curia Vista: same top area in DE · FR · IT</span><span class="kvv">${pct(xl.standard.top_all_agree.rate)}</span></div>` : ""}
      <div class="kv"><span>Quote failures before → after one retry</span><span class="kvv">${pct(q.evidence.failure_rate_first_attempt)} → ${pct(q.evidence.failure_rate_after_retry)}</span></div>
    </div>

    <div class="card"><div class="ctitle">What's next</div><div class="csub">To make it a service people rely on</div>
      <ul class="limits">
        <li>OpenParlData API endpoint, nightly <span class="mono">update</span></li>
        <li>APS reference set labelled by domain experts</li>
        <li>A second, independent reviewer</li>
        <li>Check for party bias (needs author data)</li>
        <li>Reviewer accounts; rename / archive topics</li>
      </ul>
    </div>

    <div class="card wide"><div class="csub" style="margin:0">Sources: <span class="mono">results/metrics.json</span> · runs <span class="mono">${esc(che.runs.join(", "))}</span> (federal), test <span class="mono">${esc(d.run_ids.join(", "))}</span> · prompt <span class="mono">${esc(che.prompt_template)}</span> · decisions D46, D65, D71, D77 in docs/decisions.md</div></div>`;
}

// ---------- events ----------
// ---------- topic dialog: preset = read-only, new / own topic = editable ----------
const topicOpen = () => !$("topicModal").classList.contains("hidden");

function openTopic(mode) {  // "view" (preset) | "new" | "edit"
  const ro = mode === "view";
  ["mName", "topicDef", "topicInclude", "topicExclude"].forEach((id) => { $(id).readOnly = ro; });
  $("mName").value = mode === "new" ? "" : $("topicName").value;
  $("topicModalTitle").textContent = ro ? `Preset topic: ${$("topicName").value}` : mode === "new" ? "New topic" : "Your topic";
  $("templateBtn").classList.toggle("hidden", !ro);
  $("mClassify").classList.toggle("hidden", ro);
  $("defHint").innerHTML = ro
    ? "Preset topics are fixed so their results stay comparable over time. To change anything, use this one as a template for a new topic."
    : `Name the topic, say in one or two sentences what counts, optionally list what counts and what doesn't, then press <b>Classify</b>${S.collection ? ` (you'll see how long ${esc(S.collection)} takes before anything runs)` : ""}. English works for affairs in all languages.`;
  updateDefHint();
  $("topicModal").classList.remove("hidden");
  (ro ? $("templateBtn") : $("mName")).focus();
}

function closeTopic() { $("topicModal").classList.add("hidden"); }

function newTopic() {
  ["topicDef", "topicInclude", "topicExclude"].forEach((id) => { $(id).value = ""; });
  openTopic("new");
}

function topicAsTemplate() {
  const name = $("topicName").value;
  openTopic("edit");
  $("mName").value = `${name} (own version)`;
  $("mName").select();
}

function runTopic() {
  const name = $("mName").value.trim();
  if (!name) return $("mName").focus();
  $("topicName").value = name;
  if (!presetUnchanged()) { S.presetId = null; renderPresets(); }
  closeTopic();
  return classify();
}

document.addEventListener("click", (e) => {
  if (!$("topicsPop").classList.contains("hidden") && !e.target.closest(".popwrap")) toggleTopics(false);
  const t = e.target.closest("button, tr[data-pid], #scrim, select");
  if (!t) return;
  if (t.dataset.preset) return selectPreset(t.dataset.preset);
  if (t.dataset.topic) return openSavedTopic(t.dataset.topic);
  if (t.id === "topicsBtn") return toggleTopics($("topicsPop").classList.contains("hidden"));
  if (t.dataset.task) {
    S.task = t.dataset.task; S.selected = -1;
    document.querySelectorAll("[data-task]").forEach((x) => { x.classList.toggle("on", x === t); x.setAttribute("aria-pressed", String(x === t)); });
    return render();
  }
  if (t.dataset.act === "job-start") return startJob();
  if (t.dataset.act === "more") { S.limit += PAGE; return render(); }
  if (t.dataset.show) { S.show[t.dataset.show] = !S.show[t.dataset.show]; return render(); }
  if (t.dataset.view) {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === t));
    $("explore").classList.toggle("hidden", t.dataset.view !== "explore");
    $("metricsView").classList.toggle("hidden", t.dataset.view !== "metrics");
    if (t.dataset.view === "metrics") loadMetrics();
    return;
  }
  if (t.dataset.mode) return setMode(t.dataset.mode);
  if (t.dataset.scheme) return selectScheme(t.dataset.scheme);
  if (t.dataset.act === "confirm-label") return review(Number(t.dataset.pid), "confirm");
  if (t.dataset.act === "reject-label") return review(Number(t.dataset.pid), "reject");
  if (t.dataset.act === "show-label") return openStandardDetail(Number(t.dataset.pid));
  if (t.matches("tr[data-pid]")) { S.selected = Number(t.dataset.n); render(); return openDetail(Number(t.dataset.pid)); }
  if (t.id === "scrim" || t.dataset.act === "close") return closeDetail();
  if (t.dataset.act === "prev") return move(-1);
  if (t.dataset.act === "next") return move(1);
  if (t.dataset.act === "confirm") return review(S.detailId, "confirm");
  if (t.dataset.act === "reading") return readingAid(S.detailId, false);
  if (t.dataset.act === "translate") return readingAid(S.detailId, true);
  if (t.dataset.act === "reject") return review(S.detailId, "reject");
  if (t.id === "defToggle") return openTopic(S.presetId ? "view" : "edit");
  if (t.id === "newTopicBtn") return newTopic();
  if (t.dataset.act === "topic-close") return closeTopic();
  if (t.dataset.act === "topic-template") return topicAsTemplate();
  if (t.dataset.act === "topic-run") return runTopic();
  if (t.id === "classifyBtn") return classify();
  if (t.id === "cancelBtn" && S.job) return api(`/api/jobs/${S.job.job_id}/cancel`, { method: "POST" }).catch((err) => alertStrip(err.message));
  if (t.id === "cancelBtn" && S.controller) return S.controller.abort();
  if (t.id === "retryBtn") return loadState();
  if (t.id === "kwToggle") {
    S.kwOnly = !S.kwOnly; t.setAttribute("aria-pressed", String(S.kwOnly));
    return render();
  }
});

document.addEventListener("change", (e) => {
  const t = e.target;
  if (t.id === "fColl") return selectCollection(t.value);
  if (t.id === "fExport" && t.value) {
    const only = t.value; t.value = "";
    if (only === "confirmed" && S.mode !== "standard" && !groups().confirmed.length)
      return alertStrip("Nothing confirmed yet: open a suggestion and press C (or use the Review queue), then export again.");
    if (S.collection && S.coll) return void (location.href = `/api/collections/${enc(S.collection)}/export.xlsx?target=${enc(S.coll.target)}&only=${only}`);
    if (S.runId) return void (location.href = `/api/export.csv?run_id=${enc(S.runId)}`);
    return alertStrip("Nothing to export yet.");
  }
  const map = { fParl: "parl", fLevel: "level", fLang: "lang", fDate: "year", fShelf: "shelf" };
  if (map[t.id]) { S.filters[map[t.id]] = t.value; S.selected = -1; render(); }
});

document.addEventListener("keydown", (e) => {
  if (!$("topicsPop").classList.contains("hidden") && e.key === "Escape") return toggleTopics(false);
  if (topicOpen()) {
    if (e.key === "Escape") return closeTopic();
    if (e.key === "Enter" && e.target.id === "mName") { e.preventDefault(); return runTopic(); }
    return;
  }
  const typing = e.target.matches("input, textarea, select");
  if (e.key === "Enter" && !e.shiftKey && (!typing || e.target.id === "topicName")) {
    if (e.target.matches("tr[data-pid]")) return openDetail(Number(e.target.dataset.pid));
    e.preventDefault(); return classify();
  }
  if (typing) return;
  if (e.key === "Escape") return closeDetail();
  if (e.key === "ArrowDown") { e.preventDefault(); return move(1); }
  if (e.key === "ArrowUp") { e.preventDefault(); return move(-1); }
  if (e.key === "c" || e.key === "C") return review(selectedPid(), "confirm");
  if (e.key === "r" || e.key === "R") return review(selectedPid(), "reject");
});

$("topicName").addEventListener("input", () => {
  const p = S.app.presets.find((x) => x.id === S.presetId);
  if (p && $("topicName").value.trim() !== p.name) {  // typing another name starts a new topic, never an edited preset
    S.presetId = null; renderPresets();
    ["topicDef", "topicInclude", "topicExclude"].forEach((id) => { $(id).value = ""; });
  }
});

$("mName").addEventListener("input", updateDefHint);
$("topicsSearch").addEventListener("input", renderTopics);

function updateDefHint() {
  const name = $("mName").value.trim() || "…";
  $("topicDef").placeholder = `Optional. If empty: “Affairs whose main subject is ${name}.”`;
}

loadState().catch((e) => alertStrip(`Could not reach the Unisono server: ${e.message}`));
