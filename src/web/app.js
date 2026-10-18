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
};
const ADHOC_HEAD = ["Parl.", "Number", "Date", "Lang", "Title", "Label", "Confidence", "Evidence", "Review"];
const STD_HEAD = ["Parl.", "Number", "Date", "Lang", "Title", "Labels (confidence)", "Evidence (top label)", "Review"];

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

// ---------- state & presets ----------
async function loadState() {
  S.app = await api("/api/state");
  const live = S.app.mode === "live";
  $("modelName").textContent = live ? `${S.app.model} · ${S.app.endpoint_host}` : "Model offline · cached results";
  $("modelBadge").classList.toggle("off", !live);
  $("offlineBanner").classList.toggle("hidden", live);
  $("classifyBtn").disabled = !live;
  $("sampleChip").classList.toggle("hidden", live);
  if (!S.pool.length) S.pool = await api("/api/pool");
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

function passesFilters(i) {
  const f = S.filters;
  return (!f.parl || i.body_key === f.parl) && (!f.level || level(i) === f.level) && (!f.lang || i.lang === f.lang) &&
    (!f.year || (i.begin_date || "") >= f.year) && (!S.kwOnly || !S.hasKeywords || i.keyword_absent === true);
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

function visibleRows() {
  if (S.mode === "standard") return stdGroups().shown;
  const g = groups();
  return [...g.suggested, ...(S.show.below ? g.below : []), ...(S.show.rejected ? g.rejected : [])];
}

const placeholderRows = () => (S.live ? S.pending.filter(passesFilters) : []);

function fillFilterOptions() {
  const keep = (id, values, fmt) => {
    const el = $(id); const cur = el.value; const first = el.options[0].outerHTML;
    el.innerHTML = first + values.map((v) => `<option value="${esc(v)}">${esc(fmt(v))}</option>`).join("");
    el.value = values.includes(cur) ? cur : "";
  };
  keep("fParl", [...new Set(S.items.map((i) => i.body_key))].sort(), (v) => v);
  const years = [...new Set(S.items.map((i) => (i.begin_date || "").slice(0, 4)).filter(Boolean))].sort();
  keep("fDate", years.slice(1).map((y) => `${y}-01-01`), (v) => `${v.slice(0, 4)} → today`);
}

// ---------- rendering ----------
function render() {
  $("thead").innerHTML = `<tr>${(S.mode === "standard" ? STD_HEAD : ADHOC_HEAD).map((h) => `<th>${h}</th>`).join("")}</tr>`;
  if (S.mode === "standard") return renderStandard();
  const g = groups();
  const rows = visibleRows();
  $("kwToggle").classList.toggle("hidden", !S.hasKeywords);
  const kw = S.kwOnly && S.hasKeywords ? ` · “Keyword absent” ON — every affair below is <i>suggested</i> for ${esc(S.topicName)} yet its text never contains the topic's core words.` : "";
  $("strip").innerHTML = S.items.length || S.live ? `
    <span><b>${g.suggested.length}</b> suggested</span><span>·</span>
    <span><b>${g.confirmed.length}</b> confirmed</span><span>·</span>
    <button type="button" class="linkbtn" data-show="rejected" aria-pressed="${S.show.rejected}"><b>${g.rejected.length}</b> rejected (evidence not found)</button><span>·</span>
    <button type="button" class="linkbtn" data-show="below" aria-pressed="${S.show.below}"><b>${g.below.length}</b> below threshold ${S.app.match_threshold.toFixed(2)}</button>
    <span class="spacer"></span>
    <span class="cap">Pool: <b>${S.pool.length || S.app.pool.n}</b> affairs${kw}</span>
    ${S.definitionUsed ? `<div class="defused">Definition used: <i>${esc(S.definitionUsed)}</i></div>` : ""}` : "";
  $("strip").classList.toggle("hidden", !S.items.length && !S.live);
  $("rows").innerHTML = rows.map((i, n) => rowHtml(i, n)).join("") + placeholderRows().map(placeholderHtml).join("");
  const empty = $("emptyState");
  if (!S.items.length && !S.live) {
    empty.innerHTML = S.app.mode === "live"
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
    <td>${esc(i.body_key)}</td><td class="mono muted">${esc(i.number)}</td><td class="muted nowrap">${esc(i.begin_date)}</td>
    <td><span class="lang">${esc((i.lang || "").toUpperCase())}</span></td>
    <td class="tbltitle" lang="${esc(i.lang)}">${esc(i.title)}</td>
    <td>${labelCell(i)}</td><td>${conf}</td><td class="evcell">${quote(i)}${badges(i)}</td><td>${reviewCell(i)}</td></tr>`;
}

function alertStrip(msg) {
  $("strip").classList.remove("hidden");
  $("strip").innerHTML = `<span role="alert"><b>${esc(msg)}</b></span>`;
}

// ---------- detail panel & review ----------
function highlight(text, span) {
  if (!span) return esc(text);
  const [a, b] = span;
  return `${esc(text.slice(0, a))}<mark>${esc(text.slice(a, b))}</mark>${esc(text.slice(b))}`;
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
      <label class="filter"><span class="cz">Correct label</span><select data-act="correct"><option value="">…</option><option value="match">This topic</option><option value="no_match">Not this topic</option></select></label>
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
    const label = r.kind === "official" ? `Official ${lang.toUpperCase()} version` : `Unofficial machine translation (${esc(r.model)})`;
    box.innerHTML = `<div class="meta-k">${label}</div><div class="cap">${esc(r.note)}${r.truncated ? " First part only." : ""}</div>
      <div class="textbox textbox-aid" lang="${esc(lang)}">${esc(r.text)}</div>`;
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
  render();
  if (S.mode === "standard" && S.detailId) openStandardDetail(S.detailId);
  else if (S.detailId === pid) openDetail(pid);
}

function move(delta) {
  const rows = visibleRows();
  if (!rows.length) return;
  S.selected = Math.max(0, Math.min(rows.length - 1, S.selected + delta));
  render();
  const tr = document.querySelector(`tr[data-n="${S.selected}"]`);
  if (tr) { tr.focus(); tr.scrollIntoView({ block: "nearest" }); }
  if (S.detailId) openDetail(rows[S.selected].prediction_id);
}

const selectedPid = () => S.detailId || (visibleRows()[S.selected] || {}).prediction_id;

// ---------- standard mode (APS / Curia Vista) ----------
const schemeName = (id) => ((S.app.schemes || []).find((x) => x.id === id) || {}).name || id;

function renderSchemes() {
  $("schemeSeg").innerHTML = (S.app.schemes || []).map((x) =>
    `<button type="button" data-scheme="${esc(x.id)}" class="${x.id === S.scheme ? "on" : ""}" aria-pressed="${x.id === S.scheme}">${esc(x.name)}</button>`).join("");
}

async function setMode(mode) {
  if (S.live) return;
  S.mode = mode;
  document.querySelectorAll("[data-mode]").forEach((x) => { x.classList.toggle("on", x.dataset.mode === mode); x.setAttribute("aria-pressed", String(x.dataset.mode === mode)); });
  document.querySelectorAll(".adhoc-only").forEach((x) => x.classList.toggle("hidden", mode !== "adhoc"));
  document.querySelectorAll(".std-only").forEach((x) => x.classList.toggle("hidden", mode !== "standard"));
  document.body.classList.toggle("std", mode === "standard");
  $("defBox").classList.add("hidden");
  $("kwToggle").classList.toggle("hidden", mode === "standard" || !S.hasKeywords);
  closeDetail();
  S.runId = null; S.items = []; S.selected = -1;
  render();
  if (mode === "standard") return selectScheme(S.scheme);
  selectPreset(S.presetId || (S.app.presets.find((p) => p.id === S.app.default_preset) || S.app.presets[0] || {}).id);
}

async function selectScheme(id) {
  S.scheme = id; renderSchemes();
  const seq = ++S.loadSeq;
  if (!S.labelNames[id]) S.labelNames[id] = await api(`/api/schemes/${encodeURIComponent(id)}/labels`);
  if (seq !== S.loadSeq || S.scheme !== id) return;
  const sc = (S.app.schemes || []).find((x) => x.id === id);
  S.topicName = schemeName(id); S.definitionUsed = ""; S.hasKeywords = false;
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
  const all = [...by.values()];
  for (const g of all) {
    g.labels.sort((a, b) => (a.rank || 9) - (b.rank || 9) || String(a.label).localeCompare(String(b.label)));
    const top = g.labels.find((l) => l.label !== "NONE_OTHER") || g.labels[0];
    if (top) Object.assign(g, { prediction_id: top.prediction_id, evidence: top.evidence, verify_ok: top.verify_ok, verify_method: top.verify_method });
  }
  return { all, shown: all.filter((g) => g.labels.length), failed: all.reduce((n, g) => n + g.failed, 0),
           none: all.filter((g) => g.labels.length && g.labels.every((l) => l.label === "NONE_OTHER")).length };
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
  const fallbackNote = S.scheme === "aps" ? " · APS has no Italian labels: Italian affairs show the German label" : "";
  $("strip").innerHTML = S.items.length || S.live ? `
    <span><b>${g.shown.length}</b> affairs labelled</span><span>·</span>
    <span><b>${g.shown.reduce((n, x) => n + x.labels.filter((l) => l.label !== "NONE_OTHER").length, 0)}</b> labels</span><span>·</span>
    <span><b>${g.none}</b> none / other</span><span>·</span>
    <span><b>${g.failed}</b> labels rejected (evidence not found)</span>
    <span class="spacer"></span><span class="cap">Pool: <b>${S.pool.length || S.app.pool.n}</b> affairs · scheme ${esc(schemeName(S.scheme))}${fallbackNote}</span>` : "";
  $("strip").classList.toggle("hidden", !S.items.length && !S.live);
  $("rows").innerHTML = g.shown.map((x, n) => `<tr tabindex="0" data-pid="${x.prediction_id}" data-n="${n}" class="${n === S.selected ? "sel" : ""}">
    <td>${esc(x.body_key)}</td><td class="mono muted">${esc(x.number)}</td><td class="muted nowrap">${esc(x.begin_date)}</td>
    <td><span class="lang">${esc((x.lang || "").toUpperCase())}</span></td><td class="tbltitle" lang="${esc(x.lang)}">${esc(x.title)}</td>
    <td><div class="labels">${paths(x).map((p) => p.none ? `<span class="path none">None / other</span>`
      : `<span class="path">${p.chap ? `<span class="chap">${esc(p.chap)}</span>` : ""}${p.chap && p.topic ? `<span class="arr">→</span>` : ""}${p.topic ? `<span class="topic">${esc(p.topic)}</span>` : ""}<span class="cf">${(p.conf ?? 0).toFixed(2)}</span></span>`).join("")}</div></td>
    <td class="evcell">${quote(x)}</td><td>${stdReview(x)}</td></tr>`).join("") + placeholderRows().map(placeholderHtml).join("");
  const empty = $("emptyState");
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

function prCurve(curve, chosen) {
  const W = 320, H = 220, P = 34;
  const x = (r) => P + r * (W - P - 10), y = (p) => H - P - p * (H - P - 10);
  const pts = curve.points.filter((p) => p.precision_corrected != null);
  const line = pts.map((p) => `${x(p.recall).toFixed(1)},${y(p.precision_corrected).toFixed(1)}`).join(" ");
  const ch = pts.find((p) => p.threshold === chosen);
  const b = curve.baseline_point;
  return `<svg class="pr" width="100%" viewBox="0 0 ${W} ${H}" role="img" aria-label="Precision-recall curve on the test split">
    <line x1="${P}" y1="${H - P}" x2="${W - 10}" y2="${H - P}" stroke="#D7D2C9"/><line x1="${P}" y1="10" x2="${P}" y2="${H - P}" stroke="#D7D2C9"/>
    <text x="${W / 2}" y="${H - 6}" text-anchor="middle">recall</text><text x="10" y="${H / 2}" transform="rotate(-90 10 ${H / 2})" text-anchor="middle">precision (corrected)</text>
    ${[0, 0.5, 1].map((t) => `<text x="${x(t)}" y="${H - P + 14}" text-anchor="middle">${t}</text><text x="${P - 6}" y="${y(t) + 4}" text-anchor="end">${t}</text>`).join("")}
    <polyline points="${line}" fill="none" stroke="#564B68" stroke-width="2"/>
    ${ch ? `<circle cx="${x(ch.recall)}" cy="${y(ch.precision_corrected)}" r="5" fill="#564B68"/><text x="${x(ch.recall) + 8}" y="${y(ch.precision_corrected) - 6}">ParlTopics t=${chosen}</text>` : ""}
    <rect x="${x(b.recall) - 4}" y="${y(b.precision) - 4}" width="8" height="8" fill="#8C8679"/><text x="${x(b.recall) - 8}" y="${y(b.precision) + 18}" text-anchor="end">Curia Vista area</text>
  </svg>`;
}

async function loadMetrics() {
  const grid = $("metricsGrid");
  let m;
  try { m = await api("/api/metrics"); } catch (e) { grid.innerHTML = `<div class="card wide"><div class="ctitle">No metrics yet</div><div class="csub">${esc(e.message)}</div></div>`; return; }
  const d = m.digitalisation_federal_2018;
  if (!d) { grid.innerHTML = `<div class="card wide"><div class="ctitle">No digitalisation evaluation in results/metrics.json</div></div>`; return; }
  const t = d.test.at_chosen_threshold, b = d.baselines_full_slice, q = d.test.quality;
  const cvt = (m.curia_vista_standard || {}).test;
  const xl = m.cross_language, ct = ((m.cost_time || {}).runs || [])[0];
  const adj = ((m.adjudication || {}).readings || {}).strict;
  const pending = (what) => `<span class="pending">pending — ${what}</span>`;
  grid.innerHTML = `
    <div class="card wide">
      <div style="display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap">
        <div style="flex:1;min-width:320px">
          <div class="ctitle">Digitalisation vs. PolitMonitor — federal affairs since 2018</div>
          <div class="csub">Test split: ${t.n_pos} tagged + ${t.n_neg} untagged affairs · population ${d.population.n.toLocaleString("en")} (prevalence ${(100 * d.population.prevalence).toFixed(1)}%) · precision is prevalence-corrected · threshold ${d.threshold.chosen_on_dev} fixed on dev · 95% CI</div>
          <div class="meta-k" style="margin-top:6px">Precision <span class="cap" style="text-transform:none;letter-spacing:0">share of suggestions that are correct</span></div>
          ${bar("ParlTopics", t.precision_corrected, t.precision_corrected_ci95)}
          ${bar(`Curia Vista “${b.curia_vista_area.area_names.join(" / ")}”`, b.curia_vista_area.precision, null, true)}
          ${bar("Keyword search", b.keyword_search_core.precision, null, true)}
          <div class="meta-k" style="margin-top:14px">Recall <span class="cap" style="text-transform:none;letter-spacing:0">share of tagged affairs that are found</span></div>
          ${bar("ParlTopics", t.recall, t.recall_ci95)}
          ${bar(`Curia Vista “${b.curia_vista_area.area_names.join(" / ")}”`, b.curia_vista_area.recall, null, true)}
          ${bar("Keyword search", b.keyword_search_core.recall, null, true)}
          <div class="cap" style="margin-top:10px">Baselines are exact counts on all ${d.population.n.toLocaleString("en")} affairs. After blind human review: ${adj ? `precision ${pct(adj.precision)} (${ci(adj.precision_ci95)}), recall ${pct(adj.recall)} (${ci(adj.recall_ci95)}) — strict rule, ${adj.answered.TP + adj.answered.FN + adj.answered.FP + adj.answered.TN} reviewed affairs, wide intervals` : pending("review sheet with the team's political-science reviewer")}.</div>
        </div>
        <div style="flex:0 0 360px">
          <div class="meta-k">Precision–recall curve (test)</div>
          ${prCurve(d.test_pr_curve, d.threshold.chosen_on_dev)}
        </div>
      </div>
    </div>
    <div class="card"><div class="ctitle">Quality checks</div><div class="csub">Test split, same run</div>
      <div class="kv"><span>Evidence verified on matches</span><span class="kvv">${q.evidence.verified}/${q.evidence.model_matches}</span></div>
      <div class="kv"><span>Evidence failures before → after retry</span><span class="kvv">${pct(q.evidence.failure_rate_first_attempt)} → ${pct(q.evidence.failure_rate_after_retry)}</span></div>
      <div class="kv"><span>Keyword-absent matches (tagged)</span><span class="kvv">${q.keyword_absent_shown.n} (${q.keyword_absent_shown.gold_positive})</span></div>
      <div class="kv"><span>Abstain · inconsistent</span><span class="kvv">${q.abstain} · ${q.inconsistent}</span></div>
      <div class="kv"><span>Excluded (lang missing / mismatch)</span><span class="kvv">${d.excluded_from_metrics.lang_missing} / ${d.excluded_from_metrics.lang_mismatch}</span></div></div>
    <div class="card"><div class="ctitle">Standard mode</div><div class="csub">Curia Vista areas (test${cvt ? `, n = ${cvt.n}` : ""}) · APS chapters</div>
      <div class="kv"><span>Curia Vista · at-least-one-correct</span>${cvt ? `<span class="kvv">${pct(cvt.at_least_one_correct.rate)} <span class="cap">${ci(cvt.at_least_one_correct.ci95)}</span></span>` : pending("S7")}</div>
      <div class="kv"><span>Curia Vista · micro-F1</span>${cvt ? `<span class="kvv">${cvt.micro.f1.toFixed(2)} <span class="cap">P ${cvt.micro.precision.toFixed(2)} · R ${cvt.micro.recall.toFixed(2)}</span></span>` : pending("S7")}</div>
      <div class="kv"><span>Labels per affair (gold · predicted)</span>${cvt ? `<span class="kvv">${cvt.cardinality.gold_mean.toFixed(1)} · ${cvt.cardinality.pred_mean.toFixed(1)}</span>` : pending("S7")}</div>
      <div class="kv"><span>APS · gold sample</span>${pending("partner labels")}</div></div>
    <div class="card"><div class="ctitle">Cross-language · cost</div><div class="csub">Same federal affairs in DE / FR / IT${xl ? ` (n = ${xl.adhoc.n})` : ""} · measured cost</div>
      <div class="kv"><span>Ad-hoc: all three languages agree</span>${xl ? `<span class="kvv">${pct(xl.adhoc.all_agree.rate)} <span class="cap">${ci(xl.adhoc.all_agree.ci95)}</span></span>` : pending("S9")}</div>
      <div class="kv"><span>Cohen's κ DE–FR · DE–IT · FR–IT</span>${xl ? `<span class="kvv">${Object.values(xl.adhoc.pairs).map((p) => p.kappa.toFixed(2)).join(" · ")}</span>` : pending("S9")}</div>
      <div class="kv"><span>Standard: same top label in all three</span>${xl ? `<span class="kvv">${pct(xl.standard.top_all_agree.rate)}</span>` : pending("S9")}</div>
      <div class="kv"><span>Model seconds per affair (p50 · p95)</span>${ct ? `<span class="kvv">${ct.model_seconds_per_affair.p50.toFixed(1)} · ${ct.model_seconds_per_affair.p95.toFixed(1)}</span>` : pending("S9")}</div>
      <div class="kv"><span>300k affairs at concurrency 8 · 32</span>${ct ? `<span class="kvv">${ct.estimate.hours_at_concurrency["8"].toFixed(0)} h · ${ct.estimate.hours_at_concurrency["32"].toFixed(0)} h</span>` : pending("S9")}</div></div>
    <div class="card wide"><div class="csub" style="margin:0">Model <span class="mono">${esc(d.model)}</span> · prompt <span class="mono">${esc(d.prompt_template)}</span> (version <span class="mono">${esc(d.prompt_version.slice(0, 12))}</span>) · runs <span class="mono">${esc(d.run_ids.join(", "))}</span> · commit <span class="mono">${esc((d.git_commit || "").slice(0, 7))}</span></div></div>`;
}

// ---------- events ----------
function openDef() { $("defBox").classList.remove("hidden"); $("defToggle").setAttribute("aria-expanded", "true"); }

document.addEventListener("click", (e) => {
  const t = e.target.closest("button, tr[data-pid], #scrim, select");
  if (!t) return;
  if (t.dataset.preset) return selectPreset(t.dataset.preset);
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
  if (t.id === "defToggle") { const open = $("defBox").classList.toggle("hidden"); t.setAttribute("aria-expanded", String(!open)); return; }
  if (t.id === "classifyBtn") return classify();
  if (t.id === "cancelBtn" && S.controller) return S.controller.abort();
  if (t.id === "retryBtn") return loadState();
  if (t.id === "kwToggle") {
    S.kwOnly = !S.kwOnly; t.setAttribute("aria-pressed", String(S.kwOnly));
    $("kwLabel").textContent = `Keyword absent ${S.kwOnly ? "ON" : "OFF"}`; return render();
  }
});

document.addEventListener("change", (e) => {
  const t = e.target;
  if (t.dataset.act === "correct" && t.value) return review(S.detailId, "correct", t.value);
  const map = { fParl: "parl", fLevel: "level", fLang: "lang", fDate: "year" };
  if (map[t.id]) { S.filters[map[t.id]] = t.value; S.selected = -1; render(); }
});

document.addEventListener("keydown", (e) => {
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
  if (!S.presetId) return updateDefHint();
  const p = S.app.presets.find((x) => x.id === S.presetId);
  if (p && $("topicName").value.trim() !== p.name) {
    S.presetId = null; renderPresets();
    ["topicDef", "topicInclude", "topicExclude"].forEach((id) => { $(id).value = ""; });
    openDef();
  }
  updateDefHint();
});

function updateDefHint() {
  const name = $("topicName").value.trim() || "…";
  $("topicDef").placeholder = `Optional. If empty: “Affairs whose main subject is ${name}.”`;
}

loadState().catch((e) => alertStrip(`Could not reach the ParlTopics server: ${e.message}`));
