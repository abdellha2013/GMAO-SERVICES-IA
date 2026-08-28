"use strict";

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

const LS_KEYS = { url: "gmao_api_url", token: "gmao_api_token", theme: "gmao_theme" };

const cfg = {
  baseUrl: localStorage.getItem(LS_KEYS.url) || "http://localhost:8000",
  token: localStorage.getItem(LS_KEYS.token) || ""
};

let selectedFiles = [];
let isUploading = false;
let pendingDeleteId = null;

const SECTION_TITLES = {
  dashboard: "Tableau de bord",
  documents: "Documents indexés",
  "ingest-files": "Ingestion de fichiers",
  "ingest-db": "Ingestion base de données",
  rag: "Recherche intelligente",
  strategies: "Stratégies disponibles",
  settings: "Connexion à l'API"
};

function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function toast(message, type = "info", duration = 4200) {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  const icons = { ok: "✅", err: "❌", info: "ℹ️", warn: "⚠️" };
  el.innerHTML = `<span>${icons[type] || icons.info}</span><span>${escapeHtml(message)}</span>`;
  $("#toasts").appendChild(el);
  setTimeout(() => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 260);
  }, duration);
}

function setBusy(btn, busy, busyLabel) {
  if (!btn) return;
  if (busy) {
    btn.dataset.label = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spin">⏳</span> ${escapeHtml(busyLabel || "Chargement…")}`;
  } else {
    btn.disabled = false;
    if (btn.dataset.label) btn.innerHTML = btn.dataset.label;
  }
}

function apiUrl(path) {
  return `${cfg.baseUrl.replace(/\/+$/, "")}/api/v1/${path.replace(/^\/+/, "")}`;
}

async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (cfg.token) headers.set("Authorization", `Bearer ${cfg.token}`);

  let resp;
  try {
    resp = await fetch(apiUrl(path), { ...options, headers });
  } catch {
    throw new Error("API injoignable — vérifiez l'URL dans l'onglet Connexion.");
  }

  let data = null;
  const text = await resp.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }

  if (!resp.ok) {
    const detail =
      typeof data === "object" && data !== null && data.detail
        ? typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail)
        : typeof data === "string"
          ? data.slice(0, 300)
          : `HTTP ${resp.status}`;
    if (resp.status === 401) {
      throw new Error("Non autorisé (401) — vérifiez votre clé API dans l'onglet Connexion.");
    }
    throw new Error(detail);
  }
  return data;
}

function jsonToHtml(obj) {
  const raw = JSON.stringify(obj, null, 2) ?? String(obj);
  return escapeHtml(raw).replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false)\b|\bnull\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
    (match) => {
      let cls = "j-num";
      if (/^"/.test(match)) cls = /:$/.test(match.trimEnd()) ? "j-key" : "j-str";
      else if (/true|false/.test(match)) cls = "j-bool";
      else if (/null/.test(match)) cls = "j-null";
      return `<span class="${cls}">${match}</span>`;
    }
  );
}

function fmtBytes(bytes) {
  if (!bytes) return "0 o";
  const units = ["o", "Ko", "Mo", "Go"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** i).toFixed(1)} ${units[i]}`;
}

function fmtDuration(ms) {
  if (ms == null) return "";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

function rawDetails(title, obj) {
  return `
    <details class="raw-json">
      <summary>${escapeHtml(title)}</summary>
      <pre>${jsonToHtml(obj)}</pre>
    </details>`;
}

function badge(text, kind = "neutral") {
  return `<span class="badge ${kind}">${escapeHtml(text)}</span>`;
}

function chunkCard(chunk, index, primaryScoreKey, secondaryScoreKey) {
  const rank = chunk.rank ?? index + 1;
  const score = chunk[primaryScoreKey];
  const pct = score != null ? Math.max(0, Math.min(100, score * 100)) : null;
  const secondary = secondaryScoreKey && chunk[secondaryScoreKey] != null
    ? `<span class="chunk-id">· ${escapeHtml(secondaryScoreKey)}: ${chunk[secondaryScoreKey].toFixed(3)}</span>`
    : "";
  return `
    <div class="card chunk-card">
      <div class="chunk-head">
        <span class="rank-badge">#${rank}</span>
        <span class="chunk-src">${escapeHtml(chunk.source_name || "—")}</span>
        ${badge(chunk.source_type || "?", "neutral")}
        ${chunk.id_document != null ? `<span class="chunk-id">doc #${chunk.id_document}</span>` : ""}
        ${chunk.retrieval_strategy ? `<span class="chunk-id">· ${escapeHtml(chunk.retrieval_strategy)}</span>` : ""}
        ${secondary}
        ${
          pct != null
            ? `<span class="score-wrap"><span class="score-bar"><span class="score-fill" style="width:${pct}%"></span></span><span class="score-val">${score.toFixed(3)}</span></span>`
            : ""
        }
      </div>
      <div class="chunk-content">${escapeHtml(chunk.content || "")}</div>
    </div>`;
}

function initTheme() {
  const saved = localStorage.getItem(LS_KEYS.theme);
  const theme = saved || (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  document.documentElement.dataset.theme = theme;
  updateThemeLabel();
}

function updateThemeLabel() {
  const dark = document.documentElement.dataset.theme === "dark";
  $("#themeLabel").textContent = dark ? "Thème clair" : "Thème sombre";
}

function setupTheme() {
  $("#themeToggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem(LS_KEYS.theme, next);
    updateThemeLabel();
  });
}

function switchSection(name) {
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.section === name));
  $$(".section").forEach((s) => s.classList.toggle("active", s.id === `section-${name}`));
  $("#pageTitle").textContent = SECTION_TITLES[name] || name;
  $("#sidebar").classList.remove("open");

  if (name === "documents") loadDocuments();
  if (name === "strategies") loadStrategies();
  if (name === "dashboard") refreshDashboard();
}

function setupRouter() {
  $$(".nav-item").forEach((btn) =>
    btn.addEventListener("click", () => switchSection(btn.dataset.section))
  );
  $("#burgerBtn").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
}

function setHealthPill(state, label) {
  const pill = $("#healthPill");
  pill.className = `health-pill ${state}`;
  $("#healthPillText").textContent = label;
}

async function checkHealth(baseUrlOverride) {
  const started = performance.now();
  try {
    const resp = await fetch(`${(baseUrlOverride || cfg.baseUrl).replace(/\/+$/, "")}/api/v1/health`);
    const ms = Math.round(performance.now() - started);
    const data = await resp.json();
    return { ok: resp.ok, data, ms };
  } catch {
    return { ok: false, data: null, ms: null };
  }
}

function applyHealth(data) {
  const overall = data?.status;
  const qdrantOk = data?.qdrant === "ok";
  const mysqlOk = data?.mysql === "ok";
  const healthy = overall === "healthy";

  if (healthy) setHealthPill("ok", "Opérationnel");
  else if (overall === "degraded") setHealthPill("warn", "Dégradé");
  else setHealthPill("err", "Hors ligne");

  $("#apiVersionBadge").textContent = data?.version ? `v${data.version}` : "v—";

  const setCard = (id, ok, okLabel, errMsg) => {
    const card = $(id);
    card.classList.toggle("status-ok", !!ok);
    card.classList.toggle("status-err", !ok);
    $("[data-value]", card).textContent = ok ? okLabel : "Erreur";
    $("[data-value]", card).title = ok ? "" : errMsg || "";
  };
  setCard("#cardApi", !!data, overall === "healthy" ? "Opérationnel" : overall || "Injoignable");
  setCard("#cardMysql", mysqlOk, "Connecté", data?.mysql);
  setCard("#cardQdrant", qdrantOk, "Connecté", data?.qdrant);

  return { healthy, mysqlOk, qdrantOk };
}

async function refreshDashboard() {
  const btn = $("#dashRefresh");
  setBusy(btn, true);

  const health = await checkHealth();
  const summary = applyHealth(health.data);
  $("#cardLatency [data-value]").textContent = health.ms != null ? `${health.ms} ms` : "—";

  let stats = null;
  if (summary.mysqlOk || summary.qdrantOk) {
    try {
      stats = await apiFetch("stats");
      $("#statDocs").textContent = stats.documents_count ?? "—";
      $("#statChunks").textContent = stats.chunks_count ?? "—";
      $("#statPoints").textContent = stats.qdrant_points ?? "—";
    } catch (e) {
      $("#statDocs").textContent = $("#statChunks").textContent = $("#statPoints").textContent = "—";
      toast(e.message, "err");
    }
  }

  $("#dashRaw").innerHTML = jsonToHtml({
    health: health.data || { erreur: "injoignable" },
    stats: stats || { erreur: "non disponible" }
  });

  setBusy(btn, false);
  return summary;
}

function setupDashboard() {
  $("#dashRefresh").addEventListener("click", () => refreshDashboard().catch((e) => toast(e.message, "err")));
}

async function loadDocuments() {
  const tbody = $("#docsTbody");
  setBusy($("#docsRefresh"), true);
  try {
    const data = await apiFetch("documents/");
    const docs = data.documents || [];
    $("#docsEmpty").classList.toggle("hidden", docs.length > 0);
    tbody.innerHTML = docs
      .map(
        (d) => `
        <tr>
          <td class="mono">#${d.id}</td>
          <td><button class="doc-name" data-id="${d.id}">${escapeHtml(d.name)}</button></td>
          <td>${badge(d.source_type || "?", "neutral")}</td>
          <td class="mono">${d.chunks_count ?? 0}</td>
          <td>${d.indexed ? badge("Indexé", "ok") : badge("Partiel", "warn")}</td>
          <td class="td-actions">
            <button class="btn btn-outline btn-sm" data-view="${d.id}">Voir</button>
            <button class="btn btn-ghost btn-sm" data-delete="${d.id}" title="Supprimer">🗑</button>
          </td>
        </tr>`
      )
      .join("");
  } catch (e) {
    tbody.innerHTML = "";
    $("#docsEmpty").classList.remove("hidden");
    toast(e.message, "err");
  }
  setBusy($("#docsRefresh"), false);
}

function openModal(id) { $(`#${id}`).classList.remove("hidden"); }
function closeModal(id) { $(`#${id}`).classList.add("hidden"); }

function setupModals() {
  $$(".modal-overlay").forEach((ov) => {
    ov.addEventListener("click", (e) => {
      if (e.target === ov) ov.classList.add("hidden");
    });
  });
  $$("[data-close]").forEach((btn) =>
    btn.addEventListener("click", () => closeModal(btn.dataset.close))
  );
}

async function viewDocument(id) {
  openModal("docModal");
  $("#docModalTitle").textContent = `Document #${id}`;
  $("#docMeta").innerHTML = `<div class="meta-box"><span class="mk">Chargement…</span></div>`;
  $("#docChunks").innerHTML = "";
  try {
    const data = await apiFetch(`documents/${id}`);
    const d = data.document || {};
    $("#docMeta").innerHTML = `
      <div class="meta-box"><span class="mk">ID</span><span class="mv">#${d.id}</span></div>
      <div class="meta-box"><span class="mk">Nom</span><span class="mv">${escapeHtml(d.name)}</span></div>
      <div class="meta-box"><span class="mk">Type</span><span class="mv">${escapeHtml(d.source_type)}</span></div>
      <div class="meta-box"><span class="mk">Chunks</span><span class="mv">${d.chunks_count}</span></div>
      <div class="meta-box"><span class="mk">Statut</span><span class="mv">${d.indexed ? "Indexé" : "Partiel"}</span></div>`;
    const chunks = data.chunks || [];
    $("#docChunks").innerHTML =
      chunks.length > 0
        ? chunks.map((c, i) => chunkCard(c, i, "score")).join("")
        : `<p class="hint">Aucun chunk vectorisé pour ce document.</p>`;
  } catch (e) {
    $("#docMeta").innerHTML = `<div class="alert err">❌ ${escapeHtml(e.message)}</div>`;
  }
}

function askDelete(id, name) {
  pendingDeleteId = id;
  $("#confirmText").innerHTML =
    `Voulez-vous vraiment supprimer <strong>${escapeHtml(name)}</strong> (id #${id}) ?<br>` +
    `Le document, ses chunks et ses vecteurs seront définitivement effacés.`;
  openModal("confirmModal");
}

async function confirmDelete() {
  if (pendingDeleteId == null) return;
  setBusy($("#confirmYes"), true, "Suppression…");
  try {
    await apiFetch(`documents/${pendingDeleteId}`, { method: "DELETE" });
    toast(`Document #${pendingDeleteId} supprimé.`, "ok");
    closeModal("confirmModal");
    loadDocuments();
  } catch (e) {
    toast(e.message, "err");
  }
  pendingDeleteId = null;
  setBusy($("#confirmYes"), false);
}

function setupDocuments() {
  $("#docsRefresh").addEventListener("click", loadDocuments);
  $("#confirmYes").addEventListener("click", confirmDelete);
  $("#docsTbody").addEventListener("click", async (e) => {
    const nameBtn = e.target.closest(".doc-name");
    if (nameBtn) return viewDocument(nameBtn.dataset.id);
    const viewBtn = e.target.closest("[data-view]");
    if (viewBtn) return viewDocument(viewBtn.dataset.view);
    const delBtn = e.target.closest("[data-delete]");
    if (delBtn) {
      const id = delBtn.dataset.delete;
      const name = delBtn.closest("tr")?.querySelector(".doc-name")?.textContent || `document ${id}`;
      askDelete(id, name);
    }
  });
}

const ALLOWED_EXT = [".pdf", ".docx", ".txt", ".md", ".markdown", ".csv", ".json", ".xlsx", ".html", ".htm"];

function addFiles(fileList) {
  for (const file of fileList) {
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (!ALLOWED_EXT.includes(ext)) {
      toast(`Format non supporté : ${file.name}`, "warn");
      continue;
    }
    if (selectedFiles.some((f) => f.file.name === file.name && f.file.size === file.size)) continue;
    selectedFiles.push({ file, status: "wait" });
  }
  renderFilesList();
}

function renderFilesList() {
  const list = $("#filesList");
  list.innerHTML = selectedFiles
    .map(
      (f, i) => `
      <li class="file-item">
        📄 <span class="fi-name" title="${escapeHtml(f.file.name)}">${escapeHtml(f.file.name)}</span>
        <span class="fi-size">${fmtBytes(f.file.size)}</span>
        <span class="fi-status ${f.status === "ok" ? "ok" : f.status === "err" ? "err" : "wait"}">${
          f.status === "ok" ? "✅ Ingesté" : f.status === "err" ? "❌ Échec" : isUploading && f.status === "busy" ? "⏳…" : "En attente"
        }</span>
        <button type="button" class="fi-remove" data-rm="${i}" ${isUploading ? "disabled" : ""}>✕</button>
      </li>`
    )
    .join("");
  $("#btnUpload").disabled = selectedFiles.length === 0 || isUploading;
  $("#btnClearFiles").disabled = selectedFiles.length === 0 || isUploading;
}

async function uploadFiles() {
  if (selectedFiles.length === 0 || isUploading) return;
  isUploading = true;
  renderFilesList();
  setBusy($("#btnUpload"), true, `Ingestion 0/${selectedFiles.length}…`);

  const results = [];
  let done = 0;
  for (let i = 0; i < selectedFiles.length; i++) {
    const item = selectedFiles[i];
    item.status = "busy";
    renderFilesList();
    setBusy($("#btnUpload"), true, `Ingestion ${done}/${selectedFiles.length}…`);
    const fd = new FormData();
    fd.append("file", item.file);
    try {
      const res = await apiFetch("ingest/file", { method: "POST", body: fd });
      results.push({ fichier: item.file.name, ...(res.results?.[0] || {}) });
      item.status = res.results?.[0]?.status === "ok" ? "ok" : "err";
    } catch (e) {
      results.push({ fichier: item.file.name, status: "error", error: e.message });
      item.status = "err";
    }
    done++;
    renderFilesList();
  }

  isUploading = false;
  setBusy($("#btnUpload"), false);
  renderFilesList();

  const okCount = results.filter((r) => r.status === "ok").length;
  const errCount = results.length - okCount;
  const summary = { total: results.length, succes: okCount, echecs: errCount };
  $("#ingestFilesResult").innerHTML = `
    <div class="alert ${errCount === 0 ? "ok" : okCount > 0 ? "warn" : "err"}">
      ${
        errCount === 0
          ? `✅ Ingestion terminée : ${okCount}/${results.length} fichier(s) indexé(s).`
          : `⚠️ Ingestion partielle : ${okCount} succès, ${errCount} échec(s).`
      }
    </div>
    ${rawDetails("Détail de l'ingestion", summary.total !== undefined ? { resume: summary, fichiers: results } : results)}`;
  toast(`${okCount}/${results.length} fichier(s) ingéré(s).`, errCount === 0 ? "ok" : "warn");

  loadDocuments().catch(() => {});
}

function setupIngestFiles() {
  const zone = $("#dropZone");
  zone.addEventListener("click", () => $("#fileInput").click());
  $("#btnPickFiles").addEventListener("click", (e) => {
    e.stopPropagation();
    $("#fileInput").click();
  });
  $("#fileInput").addEventListener("change", (e) => {
    addFiles(e.target.files);
    e.target.value = "";
  });
  ["dragover", "dragenter"].forEach((ev) =>
    zone.addEventListener(ev, (e) => {
      e.preventDefault();
      zone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    zone.addEventListener(ev, (e) => {
      e.preventDefault();
      zone.classList.remove("dragover");
    })
  );
  zone.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));

  $("#btnUpload").addEventListener("click", uploadFiles);
  $("#btnClearFiles").addEventListener("click", () => {
    if (!isUploading) {
      selectedFiles = [];
      renderFilesList();
    }
  });
  $("#filesList").addEventListener("click", (e) => {
    const rm = e.target.closest("[data-rm]");
    if (rm && !isUploading) {
      selectedFiles.splice(Number(rm.dataset.rm), 1);
      renderFilesList();
    }
  });
}

async function ingestDatabase(e) {
  e.preventDefault();
  const payload = {
    driver: "mysql",
    host: $("#dbHost").value.trim(),
    port: Number($("#dbPort").value) || 3306,
    database: $("#dbName").value.trim(),
    user: $("#dbUser").value.trim(),
    password: $("#dbPass").value,
    table: $("#dbTable").value.trim(),
    chunk_size: Number($("#dbChunkSize").value) || 500,
    chunk_overlap: Number($("#dbChunkOverlap").value) || 50
  };
  const query = $("#dbQuery").value.trim();
  if (query) payload.query = query;
  const equip = $("#dbEquip").value.trim();
  if (equip !== "") payload.id_equipement = Number(equip);

  setBusy($("#btnDbIngest"), true, "Indexation en cours…");
  try {
    const res = await apiFetch("ingest/database", { method: "POST", body: JSON.stringify(payload) });
    const okCount = res.success_count ?? 0;
    const errCount = res.error_count ?? 0;
    $("#dbResult").innerHTML = `
      <div class="alert ${errCount === 0 ? "ok" : "warn"}">
        ${errCount === 0 ? "✅ Données indexées avec succès." : `⚠️ ${okCount} succès, ${errCount} échec(s).`}
      </div>
      ${(res.results || [])
        .map(
          (r) => `
        <div class="card chunk-card">
          <div class="chunk-head">
            ${badge(r.status === "ok" ? "Succès" : "Échec", r.status === "ok" ? "ok" : "err")}
            <span class="chunk-src">${escapeHtml(r.document_name || "—")}</span>
            <span class="chunk-id">${r.chunks_count ?? 0} chunk(s)</span>
            ${r.duration_ms != null ? `<span class="chunk-id">· ${fmtDuration(r.duration_ms)}</span>` : ""}
          </div>
          ${r.error ? `<div class="alert err">❌ ${escapeHtml(r.error)}</div>` : ""}
        </div>`
        )
        .join("")}
      ${rawDetails("Réponse brute /ingest/database", res)}`;
    toast("Ingestion base de données terminée.", errCount === 0 ? "ok" : "warn");
    loadDocuments().catch(() => {});
  } catch (err) {
    $("#dbResult").innerHTML = `<div class="alert err">❌ ${escapeHtml(err.message)}</div>`;
    toast(err.message, "err");
  }
  setBusy($("#btnDbIngest"), false);
}

function setupRagTabs() {
  $$(".seg-tab").forEach((tab) =>
    tab.addEventListener("click", () => {
      $$(".seg-tab").forEach((t) => t.classList.toggle("active", t === tab));
      $$(".rag-panel").forEach((p) =>
        p.classList.toggle("active", p.id === `rag-${tab.dataset.ragtab}`)
      );
    })
  );
}

function strategyBadges(info) {
  if (!info) return "";
  const parts = [];
  if (info.retrieval) parts.push(`récupération: ${info.retrieval}`);
  if (info.reranker) parts.push(`re-ranking: ${info.reranker}`);
  if (info.llm) parts.push(`llm: ${info.llm}`);
  return parts.map((p) => badge(p, "neutral")).join(" ");
}

async function runSearch(e) {
  e.preventDefault();
  const query = $("#sQuery").value.trim();
  if (!query) return;
  const payload = {
    query,
    top_k: Number($("#sTopK").value) || null,
    rerank: $("#sRerank").checked,
    generate: $("#sGenerate").checked
  };
  setBusy($("#btnSearch"), true, "Recherche en cours…");
  $("#searchResult").innerHTML = "";
  try {
    const res = await apiFetch("rag/search", { method: "POST", body: JSON.stringify(payload) });
    const results = res.results || [];
    const citations = res.citations || [];
    $("#searchResult").innerHTML = `
      ${res.answer ? `<div class="answer-box"><h4>Réponse générée</h4><p>${escapeHtml(res.answer)}</p></div>` : ""}
      ${
        !res.answer && payload.generate
          ? `<div class="alert warn">⚠️ Le LLM n'a pas généré de réponse — vérifiez la clé OPENAI_API_KEY / GOOGLE_API_KEY côté serveur.</div>`
          : ""
      }
      <div class="result-meta">
        ${badge(`${results.length} résultat(s)`, "neutral")}
        ${res.duration_ms != null ? badge(fmtDuration(res.duration_ms), "neutral") : ""}
        ${strategyBadges(res.strategy_info)}
      </div>
      ${
        citations.length > 0
          ? `<div class="citations-row">${citations
              .map(
                (c) =>
                  `<span class="chip on">📎 ${escapeHtml(c.source_name || c.chunk_id)}${
                    c.rerank_score != null ? ` · ${c.rerank_score.toFixed(2)}` : ""
                  }</span>`
              )
              .join("")}</div>`
          : ""
      }
      ${results.map((c, i) => chunkCard(c, i, "rerank_score", "retrieval_score")).join("")}
      ${rawDetails("Réponse brute /rag/search", res)}`;
  } catch (err) {
    $("#searchResult").innerHTML = `<div class="alert err">❌ ${escapeHtml(err.message)}</div>`;
    toast(err.message, "err");
  }
  setBusy($("#btnSearch"), false);
}

async function runRetrieve(e) {
  e.preventDefault();
  const query = $("#rQuery").value.trim();
  if (!query) return;
  const topK = Number($("#rTopK").value) || null;
  const payload = { query, ...(topK ? { top_k: topK } : {}) };
  setBusy($("#btnRetrieve"), true, "Récupération…");
  $("#retrieveResult").innerHTML = "";
  try {
    const res = await apiFetch("rag/retrieve", { method: "POST", body: JSON.stringify(payload) });
    const results = res.results || [];
    $("#retrieveResult").innerHTML = `
      <div class="result-meta">
        ${badge(`${results.length} chunk(s)`, "neutral")}
        ${res.total_candidates != null ? badge(`${res.total_candidates} candidat(s) avant filtrage`, "neutral") : ""}
        ${res.strategy_name ? badge(`stratégie: ${res.strategy_name}`, "neutral") : ""}
      </div>
      ${results.map((c, i) => chunkCard(c, i, "score")).join("")}
      ${rawDetails("Réponse brute /rag/retrieve", res)}`;
  } catch (err) {
    $("#retrieveResult").innerHTML = `<div class="alert err">❌ ${escapeHtml(err.message)}</div>`;
    toast(err.message, "err");
  }
  setBusy($("#btnRetrieve"), false);
}

async function runRerank(e) {
  e.preventDefault();
  const query = $("#rrQuery").value.trim();
  let candidates;
  try {
    candidates = JSON.parse($("#rrCandidates").value);
    if (!Array.isArray(candidates)) throw new Error("Le JSON doit être un tableau.");
  } catch (parseErr) {
    $("#rerankResult").innerHTML = `<div class="alert err">❌ JSON invalide : ${escapeHtml(parseErr.message)}</div>`;
    return;
  }
  const payload = { query, candidates };
  const topK = Number($("#rrTopK").value);
  if (topK) payload.top_k = topK;

  setBusy($("#btnRerank"), true, "Re-classement…");
  $("#rerankResult").innerHTML = "";
  try {
    const res = await apiFetch("rag/rerank", { method: "POST", body: JSON.stringify(payload) });
    const results = res.results || [];
    $("#rerankResult").innerHTML = `
      <div class="result-meta">${badge(`${results.length} chunk(s) re-classé(s)`, "neutral")}</div>
      ${results.map((c, i) => chunkCard(c, i, "rerank_score", "retrieval_score")).join("")}
      ${rawDetails("Réponse brute /rag/rerank", res)}`;
  } catch (err) {
    $("#rerankResult").innerHTML = `<div class="alert err">❌ ${escapeHtml(err.message)}</div>`;
    toast(err.message, "err");
  }
  setBusy($("#btnRerank"), false);
}

function setupRag() {
  setupRagTabs();
  $("#searchForm").addEventListener("submit", runSearch);
  $("#retrieveForm").addEventListener("submit", runRetrieve);
  $("#rerankForm").addEventListener("submit", runRerank);
}

const STRAT_CATEGORIES = [
  ["retrieval", "#stratRetrieval"],
  ["reranker", "#stratReranker"],
  ["llm", "#stratLlm"],
  ["embedding", "#stratEmbedding"]
];

async function loadStrategies() {
  const btn = $("#stratRefresh");
  setBusy(btn, true);
  try {
    const data = await apiFetch("strategies");
    STRAT_CATEGORIES.forEach(([key, sel]) => {
      const items = data[key] || [];
      $(sel).innerHTML =
        items.length > 0
          ? items.map((name) => `<span class="chip on">${escapeHtml(name)}</span>`).join("")
          : `<span class="hint">Aucune stratégie enregistrée.</span>`;
    });
  } catch (e) {
    STRAT_CATEGORIES.forEach(([, sel]) => ($(sel).innerHTML = ""));
    toast(e.message, "err");
  }
  setBusy(btn, false);
}

function initSettingsForm() {
  $("#cfgUrl").value = cfg.baseUrl;
  $("#cfgToken").value = cfg.token;
}

function setupSettings() {
  $("#cfgForm").addEventListener("submit", (e) => {
    e.preventDefault();
    cfg.baseUrl = $("#cfgUrl").value.replace(/\/+$/, "");
    cfg.token = $("#cfgToken").value.trim();
    localStorage.setItem(LS_KEYS.url, cfg.baseUrl);
    localStorage.setItem(LS_KEYS.token, cfg.token);
    toast("Configuration enregistrée.", "ok");
  });

  $("#tokenToggle").addEventListener("click", () => {
    const input = $("#cfgToken");
    input.type = input.type === "password" ? "text" : "password";
  });

  $("#btnTestConnexion").addEventListener("click", async () => {
    const url = $("#cfgUrl").value.replace(/\/+$/, "");
    const box = $("#cfgStatus");
    setBusy($("#btnTestConnexion"), true, "Test en cours…");
    const result = await checkHealth(url);
    setBusy($("#btnTestConnexion"), false);
    if (result.ok && result.data) {
      box.innerHTML = `<div class="alert ok">✅ API joignable — version ${escapeHtml(result.data.version)} (${result.ms} ms). MySQL: ${escapeHtml(result.data.mysql)} · Qdrant: ${escapeHtml(result.data.qdrant)}</div>`;
    } else {
      box.innerHTML = `<div class="alert err">❌ API injoignable sur ${escapeHtml(url)}</div>`;
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  setupTheme();
  setupRouter();
  setupModals();
  setupDashboard();
  setupDocuments();
  setupIngestFiles();
  $("#dbForm").addEventListener("submit", ingestDatabase);
  setupRag();
  setupSettings();
  initSettingsForm();

  const health = await checkHealth();
  applyHealth(health.data);
  refreshDashboard().catch(() => {});
});

