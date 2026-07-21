/* Vanilla-JS SPA over the /v1 proxy: login, ranking with client-side
   re-ranking sliders, memo detail, editors, outreach board, interview. */
"use strict";

const CATEGORIES = [
  "individual_experience",
  "schools",
  "network_ties",
  "prior_collaboration",
  "problem_realness",
  "product_defensibility",
  "market",
  "traction",
  "ideal_match",
];

const MEMO_SECTIONS = [
  ["company_snapshot", "Company snapshot"],
  ["investment_hypotheses", "Investment hypotheses"],
  ["swot", "SWOT"],
  ["team_and_history", "Team & history"],
  ["problem_and_product", "Problem & product"],
  ["technology_and_defensibility", "Technology & defensibility"],
  ["market_tam_sam_som", "Market (TAM/SAM/SOM)"],
  ["competition", "Competition"],
  ["traction_and_kpis", "Traction & KPIs"],
];

const OUTREACH_STATUSES = [
  "draft", "approved", "sent", "bounced", "replied", "consented", "declined",
  "interview_scheduled", "interview_started", "interviewed", "closed",
  "opted_out", "expired",
];

const view = document.getElementById("view");
const nav = document.getElementById("nav");

function sessionToken() { return localStorage.getItem("session"); }

function interviewSession() {
  let sid = sessionStorage.getItem("iv-session");
  if (!sid) {
    sid = Array.from(crypto.getRandomValues(new Uint8Array(16)))
      .map((b) => b.toString(16).padStart(2, "0")).join("");
    sessionStorage.setItem("iv-session", sid);
  }
  return sid;
}

async function api(path, options = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
  const token = sessionToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, Object.assign({}, options, { headers }));
  const body = await response.json().catch(() => ({}));
  if (response.status === 401 && !path.startsWith("/v1/interview/")) {
    localStorage.removeItem("session");
    location.hash = "#/login";
  }
  return { ok: response.ok, status: response.status, body };
}

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

function parseVariant(value) {
  if (typeof value !== "string") return value;
  try { return JSON.parse(value); } catch { return null; }
}

/* Mirror of app/rescoring.py::client_final_score — keep the two in sync. */
function rerankScore(weights, row) {
  let total = 0;
  let acc = 0;
  for (const name of CATEGORIES) {
    const scoreCol = name === "ideal_match" ? "ideal_match" : `s_${name}`;
    const score = row[scoreCol];
    const weight = weights[`w_${name}`];
    if (typeof score === "number" && typeof weight === "number") {
      total += weight;
      acc += weight * score;
    }
  }
  if (total <= 0) return null;
  return Math.round((acc / total) * 10) / 10;
}

function chip(text, cls) { return `<span class="chip ${cls || ""}">${esc(text)}</span>`; }

function scoreBar(value, label) {
  const width = Math.max(0, Math.min(100, value == null ? 0 : value));
  return `<div class="bar-row"><span class="bar-label">${esc(label)}</span>
    <div class="bar"><div class="bar-fill" style="width:${width}%"></div></div>
    <span class="bar-value">${value == null ? "–" : esc(value)}</span></div>`;
}

/* ---------- login ---------- */

function renderLogin(message) {
  nav.hidden = true;
  view.innerHTML = `<section class="card narrow">
    <h1>Partner login</h1>
    <p class="muted">Fixtures demo password: <code>demo</code></p>
    <form id="login-form">
      <input type="password" id="password" placeholder="Password" autofocus>
      <button type="submit">Log in</button>
    </form>
    <p class="error">${esc(message || "")}</p>
  </section>`;
  document.getElementById("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const password = document.getElementById("password").value;
    const result = await api("/v1/login", { method: "POST", body: JSON.stringify({ password }) });
    if (result.ok) {
      localStorage.setItem("session", result.body.token);
      location.hash = "#/ranking";
    } else {
      renderLogin("Wrong password.");
    }
  });
}

/* ---------- ranking ---------- */

let rankingState = { ventures: [], weights: null, thesisId: null };

function ventureCard(row, score) {
  return `<a class="venture card" href="#/venture/${esc(row.venture_id)}">
    <div class="venture-head">
      <strong>${esc(row.name)}</strong>
      <span class="final">${score == null ? "unscored" : esc(score)}</span>
    </div>
    <p class="muted">${esc(row.one_liner || "")}</p>
    <div class="chips">
      ${chip(row.status || "?", "")}
      ${chip(row.quality_tier || "?", "tier")}
      ${row.confidence == null ? "" : chip(`conf ${row.confidence}`, "conf")}
      ${(row.market_tags || []).map((t) => chip(t, "tag")).join("")}
    </div>
    ${scoreBar(score, "final")}
  </a>`;
}

function renderRankingList() {
  const weights = rankingState.weights || {};
  const scored = rankingState.ventures
    .map((row) => ({ row, score: rerankScore(weights, row) }))
    .sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  document.getElementById("ranking-list").innerHTML =
    scored.map(({ row, score }) => ventureCard(row, score)).join("") ||
    '<p class="muted">No pool-included ventures for this thesis.</p>';
}

function slider(name, value) {
  return `<label class="slider-row"><span>${esc(name.replace(/_/g, " "))}</span>
    <input type="range" min="0" max="100" step="1" data-weight="w_${esc(name)}"
      value="${Math.round((value || 0) * 100)}">
    <span class="slider-value" id="wv-${esc(name)}">${(value || 0).toFixed(2)}</span></label>`;
}

async function renderRanking() {
  nav.hidden = false;
  view.innerHTML = '<p class="muted">Loading ranking…</p>';
  const result = await api("/v1/ranking");
  if (!result.ok) { view.innerHTML = `<p class="error">${esc(result.body.error)}</p>`; return; }
  rankingState = {
    ventures: result.body.ventures,
    weights: result.body.weights || {},
    thesisId: result.body.thesis_id,
  };
  view.innerHTML = `<section class="split">
    <div>
      <h1>Ranked ventures</h1>
      <div id="ranking-list"></div>
    </div>
    <aside class="card">
      <h2>Weights</h2>
      <p class="muted">Sliders re-rank instantly, client-side.</p>
      <div id="sliders">
        ${CATEGORIES.map((n) => slider(n, rankingState.weights[`w_${n}`])).join("")}
      </div>
      <button id="save-weights">Save weights</button>
      <p id="weights-msg" class="muted"></p>
    </aside>
  </section>`;
  renderRankingList();
  document.getElementById("sliders").addEventListener("input", (event) => {
    const key = event.target.dataset.weight;
    if (!key) return;
    rankingState.weights[key] = Number(event.target.value) / 100;
    document.getElementById(`wv-${key.slice(2)}`).textContent =
      rankingState.weights[key].toFixed(2);
    renderRankingList();
  });
  document.getElementById("save-weights").addEventListener("click", async () => {
    const payload = {};
    for (const name of CATEGORIES) payload[`w_${name}`] = rankingState.weights[`w_${name}`] || 0;
    const saved = await api(`/v1/thesis/${rankingState.thesisId}/weights`, {
      method: "PUT", body: JSON.stringify(payload),
    });
    document.getElementById("weights-msg").textContent =
      saved.ok ? "Saved." : `Save failed: ${saved.body.error || saved.status}`;
  });
}

/* ---------- venture detail ---------- */

function bulletHtml(bullet) {
  if (bullet.missing) {
    return `<li class="missing">${esc(bullet.text)} ${chip(bullet.gap_field || "gap", "gap")}</li>`;
  }
  const links = (bullet.evidence || [])
    .map((e, i) => `<a href="${esc(e.source_url)}" target="_blank" rel="noopener">[${i + 1}]</a>`)
    .join(" ");
  return `<li>${esc(bullet.text)} ${links}</li>`;
}

function memoHtml(memo) {
  const sections = parseVariant(memo.sections) || {};
  const missing = [];
  const blocks = MEMO_SECTIONS.map(([key, title]) => {
    const section = sections[key] || {};
    const bullets = section.bullets || [];
    bullets.filter((b) => b.missing).forEach((b) => missing.push(b.gap_field || b.text));
    return `<article class="memo-section"><h3>${esc(title)}</h3>
      <ul>${bullets.map(bulletHtml).join("") || '<li class="muted">No data.</li>'}</ul></article>`;
  }).join("");
  const missingList = missing.length
    ? `<div class="card missing-card"><h3>Missing data → interview plan</h3>
       <ul>${missing.map((m) => `<li>${esc(m)}</li>`).join("")}</ul></div>` : "";
  return blocks + missingList;
}

function breakdownHtml(scoreRow) {
  const bars = CATEGORIES.filter((n) => n !== "ideal_match")
    .map((n) => scoreBar(scoreRow[`s_${n}`], n.replace(/_/g, " ")))
    .join("");
  return bars + scoreBar(scoreRow.ideal_match, "ideal match");
}

function teamHtml(team) {
  return team.map((m) => `<div class="member">
      <strong>${esc(m.full_name)}</strong> ${m.is_founder_guess ? chip("founder?", "tier") : ""}
      <span class="muted">${esc(m.role_hint || "")} · ${esc(m.affiliation || "")}</span>
      <span class="muted">${m.github_login ? "@" + esc(m.github_login) : ""}
        ${m.orcid ? " · ORCID " + esc(m.orcid) : ""}</span>
    </div>`).join("");
}

async function renderVenture(ventureId) {
  nav.hidden = false;
  view.innerHTML = '<p class="muted">Loading venture…</p>';
  const [memo, scores, team] = await Promise.all([
    api(`/v1/venture/${ventureId}/memo`),
    api(`/v1/venture/${ventureId}/scores`),
    api(`/v1/venture/${ventureId}/team`),
  ]);
  const latest = (scores.body.scores || [])[0] || {};
  view.innerHTML = `<section>
    <a href="#/ranking" class="muted">← back to ranking</a>
    <div class="split">
      <div id="memo-pane">
        <h1>Investment memo</h1>
        ${memo.ok ? memoHtml(memo.body) : `<p class="muted">${esc(memo.body.error)}</p>`}
      </div>
      <aside>
        <div class="card"><h2>Score breakdown</h2>${breakdownHtml(latest)}
          <p class="muted">final ${esc(latest.final_score ?? "–")} ·
             confidence ${esc(latest.confidence ?? "–")}</p></div>
        <div class="card"><h2>Team</h2>${teamHtml(team.body.team || [])}</div>
        <div class="card">
          <button id="btn-outreach">Send outreach</button>
          <button id="btn-rescore" class="secondary">Rescore</button>
          <p id="action-msg" class="muted"></p>
        </div>
      </aside>
    </div>
  </section>`;
  document.getElementById("btn-outreach").addEventListener("click", async () => {
    const result = await api(`/v1/venture/${ventureId}/outreach`, {
      method: "POST", body: JSON.stringify({}),
    });
    const msg = document.getElementById("action-msg");
    if (result.ok) {
      msg.innerHTML = `Sent to ${esc(result.body.to_email)}. Demo interview link:
        <a href="${esc(result.body.interview_url)}">open interview</a>`;
    } else {
      msg.textContent = `Outreach failed: ${result.body.error || result.status}`;
    }
  });
  document.getElementById("btn-rescore").addEventListener("click", async () => {
    const result = await api(`/v1/venture/${ventureId}/rescore`, {
      method: "POST", body: JSON.stringify({}),
    });
    document.getElementById("action-msg").textContent = result.ok
      ? `Rescore ${result.body.status} (final ${result.body.final_score ?? "unchanged"})`
      : `Rescore failed: ${result.body.error || result.status}`;
  });
}

/* ---------- thesis + ideal editors ---------- */

async function renderThesis() {
  nav.hidden = false;
  view.innerHTML = '<p class="muted">Loading thesis…</p>';
  const result = await api("/v1/thesis");
  if (!result.ok) { view.innerHTML = `<p class="error">${esc(result.body.error)}</p>`; return; }
  const thesis = result.body.theses[0] || {};
  const ideal = result.body.ideals[0] || {};
  const profile = parseVariant(ideal.profile_json) || {};
  view.innerHTML = `<section class="split">
    <div class="card">
      <h1>Thesis</h1>
      <form id="thesis-form">
        <label>Name <input id="t-name" value="${esc(thesis.name || "")}"></label>
        <label>Sectors (comma-sep)
          <input id="t-sectors" value="${esc((thesis.sectors || []).join(", "))}"></label>
        <label>Geographies
          <input id="t-geos" value="${esc((thesis.geographies || []).join(", "))}"></label>
        <label>Stages <input id="t-stages" value="${esc((thesis.stages || []).join(", "))}"></label>
        <label>Notes <textarea id="t-notes">${esc(thesis.notes || "")}</textarea></label>
        <button type="submit">Save thesis</button>
      </form>
      <p id="thesis-msg" class="muted"></p>
    </div>
    <div class="card">
      <h1>Ideal candidate</h1>
      <p class="muted">Structured profile (validated against the frozen schema).</p>
      <textarea id="ideal-json" rows="18">${esc(JSON.stringify(profile, null, 2))}</textarea>
      <button id="save-ideal">Save ideal profile</button>
      <p id="ideal-msg" class="muted"></p>
    </div>
  </section>`;
  document.getElementById("thesis-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const split = (id) => document.getElementById(id).value
      .split(",").map((s) => s.trim()).filter(Boolean);
    const saved = await api("/v1/thesis", {
      method: "POST",
      body: JSON.stringify({
        thesis_id: thesis.thesis_id,
        name: document.getElementById("t-name").value,
        sectors: split("t-sectors"),
        geographies: split("t-geos"),
        stages: split("t-stages"),
        notes: document.getElementById("t-notes").value,
        is_active: true,
      }),
    });
    document.getElementById("thesis-msg").textContent =
      saved.ok ? "Saved." : `Save failed: ${saved.body.error || saved.status}`;
  });
  document.getElementById("save-ideal").addEventListener("click", async () => {
    const msg = document.getElementById("ideal-msg");
    let payload;
    try { payload = JSON.parse(document.getElementById("ideal-json").value); }
    catch { msg.textContent = "Not valid JSON."; return; }
    const saved = await api(`/v1/thesis/${ideal.thesis_id || thesis.thesis_id}/ideal-candidate`, {
      method: "PUT", body: JSON.stringify(payload),
    });
    msg.textContent = saved.ok
      ? `Saved (v${saved.body.version}).`
      : `Rejected: ${(saved.body.errors || [saved.body.error]).join("; ")}`;
  });
}

/* ---------- outreach board ---------- */

async function renderOutreach() {
  nav.hidden = false;
  view.innerHTML = '<p class="muted">Loading outreach…</p>';
  const result = await api("/v1/outreach");
  if (!result.ok) { view.innerHTML = `<p class="error">${esc(result.body.error)}</p>`; return; }
  const byStatus = {};
  for (const row of result.body.outreach) {
    (byStatus[row.status] = byStatus[row.status] || []).push(row);
  }
  view.innerHTML = `<h1>Outreach board</h1><div class="kanban">
    ${OUTREACH_STATUSES.map((status) => `<div class="kanban-col">
      <h3>${esc(status)} <span class="muted">${(byStatus[status] || []).length}</span></h3>
      ${(byStatus[status] || []).map((row) => `<div class="card kanban-card">
        <strong>${esc(row.subject || row.outreach_id)}</strong>
        <span class="muted">${esc(row.to_email || "")}</span>
        <span class="muted">${esc((row.last_event_at || "").slice(0, 16))}</span>
      </div>`).join("")}
    </div>`).join("")}
  </div>`;
}

/* ---------- interview (founder-facing) ---------- */

function transcriptHtml(entries) {
  return entries.map((e) =>
    `<div class="msg ${e.role === "assistant" ? "assistant" : "founder"}">${esc(e.text)}</div>`
  ).join("");
}

async function ivApi(token, path, options = {}) {
  const headers = { "Content-Type": "application/json", "X-Interview-Session": interviewSession() };
  const response = await fetch(`/v1/interview/${token}${path}`,
    Object.assign({}, options, { headers }));
  const body = await response.json().catch(() => ({}));
  return { ok: response.ok, status: response.status, body };
}

async function renderInterview(token) {
  nav.hidden = true;
  view.innerHTML = '<p class="muted">Validating your interview link…</p>';
  const opened = await ivApi(token, "");
  if (!opened.ok) {
    view.innerHTML = `<section class="card narrow"><h1>Interview unavailable</h1>
      <p class="error">${esc(opened.body.error)}</p></section>`;
    return;
  }
  const info = opened.body;
  if (!info.consented) {
    view.innerHTML = `<section class="card narrow">
      <h1>${esc(info.fund_name)}</h1>
      <p>You were invited to a short interview about
         <strong>${esc(info.venture_name)}</strong>.</p>
      <p class="muted">We found you through public data (GitHub, arXiv/OpenAlex, Zefix).
        Your answers are stored only with your consent and you can request erasure
        at any time. ${esc(info.questions_total)} short questions.</p>
      <p><strong>${esc(info.consent_prompt)}</strong></p>
      <button id="consent-yes">I consent — start the interview</button>
      <button id="consent-no" class="secondary">I do not consent</button>
    </section>`;
    document.getElementById("consent-yes").addEventListener("click",
      () => sendConsent(token, "Yes, I consent to this interview and to my answers being stored."));
    document.getElementById("consent-no").addEventListener("click",
      () => sendConsent(token, "No, I do not consent."));
    return;
  }
  renderChat(token, info.transcript || []);
}

async function sendConsent(token, text) {
  const result = await ivApi(token, "/message", { method: "POST", body: JSON.stringify({ text }) });
  if (!result.ok) { renderInterview(token); return; }
  if (result.body.declined) {
    view.innerHTML = `<section class="card narrow"><h1>Thank you</h1>
      <p>${esc(result.body.assistant)}</p></section>`;
    return;
  }
  renderInterview(token);
}

function renderChat(token, transcript) {
  view.innerHTML = `<section class="card narrow chat">
    <h1>Founder interview</h1>
    <div id="chat-log">${transcriptHtml(transcript)}</div>
    <form id="chat-form">
      <input id="chat-input" placeholder="Type your answer… (or 'skip')" autocomplete="off">
      <button type="submit">Send</button>
      <button type="button" id="chat-skip" class="secondary">Skip</button>
      <button type="button" id="chat-complete" class="secondary">Complete</button>
    </form>
    <p id="chat-msg" class="muted"></p>
  </section>`;
  const log = document.getElementById("chat-log");
  log.scrollTop = log.scrollHeight;
  const send = async (text) => {
    if (!text) return;
    log.insertAdjacentHTML("beforeend", transcriptHtml([{ role: "founder", text }]));
    const result = await ivApi(token, "/message",
      { method: "POST", body: JSON.stringify({ text }) });
    if (result.ok) {
      log.insertAdjacentHTML("beforeend",
        transcriptHtml([{ role: "assistant", text: result.body.assistant }]));
    } else {
      document.getElementById("chat-msg").textContent = result.body.error || "Send failed.";
    }
    log.scrollTop = log.scrollHeight;
  };
  document.getElementById("chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    input.value = "";
    send(text);
  });
  document.getElementById("chat-skip").addEventListener("click", () => send("skip"));
  document.getElementById("chat-complete").addEventListener("click", async () => {
    const result = await ivApi(token, "/complete", { method: "POST" });
    if (result.ok) {
      view.innerHTML = `<section class="card narrow"><h1>Thank you!</h1>
        <p>Your interview is complete and your consent is on record.</p>
        <p class="muted">Rescore: ${esc(result.body.rescore_status)}</p></section>`;
    } else {
      document.getElementById("chat-msg").textContent =
        result.body.error || "Completion failed.";
    }
  });
}

/* ---------- router ---------- */

function route() {
  const hash = location.hash || "#/ranking";
  const interview = hash.match(/^#\/interview\/([0-9a-f]+)$/);
  if (interview) { renderInterview(interview[1]); return; }
  if (!sessionToken()) { renderLogin(); return; }
  const venture = hash.match(/^#\/venture\/([0-9a-f-]+)$/);
  if (venture) { renderVenture(venture[1]); return; }
  if (hash.startsWith("#/thesis")) { renderThesis(); return; }
  if (hash.startsWith("#/outreach")) { renderOutreach(); return; }
  if (hash.startsWith("#/login")) { renderLogin(); return; }
  renderRanking();
}

document.getElementById("logout").addEventListener("click", (event) => {
  event.preventDefault();
  localStorage.removeItem("session");
  location.hash = "#/login";
});

window.addEventListener("hashchange", route);
route();
