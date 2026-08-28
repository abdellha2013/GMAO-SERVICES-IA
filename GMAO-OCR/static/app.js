"use strict";

/* ── État global ─────────────────────────────────────────── */
const state = {
  file: null,        // File sélectionné (original)
  fileName: "",
  fileType: "",
  fileBytes: null,   // ArrayBuffer du fichier original
  lastRaster: null,  // { pngBase64, sourceFormat, size, decoders }
  lastScan: null,    // JSON du scan
};

const $ = (id) => document.getElementById(id);

/* ── Helpers ────────────────────────────────────────────── */
function fmtBytes(n) {
  if (n < 1024) return `${n} o`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} Ko`;
  return `${(n / (1024 * 1024)).toFixed(2)} Mo`;
}

function setStatus(msg, kind = "") {
  const el = $("status-line");
  el.textContent = msg;
  el.className = "status-line " + kind;
}

function busy(on) {
  $("btn-raster").disabled = !state.file || on;
  $("btn-scan").disabled = !state.file || on;
  if (on) setStatus("Traitement en cours…", "busy");
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = String(s ?? "");
  return d.innerHTML;
}

/* ── Chargement fichier ─────────────────────────────────── */
async function loadFile(file) {
  if (!file) return;
  state.file = file;
  state.fileName = file.name;
  state.fileType = file.type || "(inconnu)";
  state.fileBytes = await file.arrayBuffer();
  state.lastRaster = null;
  state.lastScan = null;

  $("meta-name").textContent = file.name;
  $("meta-type").textContent = file.type || "application/octet-stream";
  $("meta-size").textContent = fmtBytes(file.size);

  const prev = $("preview-original");
  if (file.type === "image/svg+xml" || file.name.toLowerCase().endsWith(".svg")) {
    const blob = new Blob([file], { type: "image/svg+xml" });
    prev.src = URL.createObjectURL(blob);
  } else {
    prev.src = URL.createObjectURL(file);
  }
  await inspectDims(prev);
  $("source-meta").hidden = false;
  $("raster-preview").innerHTML = '<span class="placeholder">Lancez une rasterisation&hellip;</span>';
  $("raster-table").hidden = true;
  $("raster-meta").textContent = "";
  $("decode-box").innerHTML = '<span class="placeholder">Aucun essai de décodage&hellip;</span>';
  $("scan-box").innerHTML = '<span class="placeholder">Aucun scan effectué&hellip;</span>';
  busy(false);
  setStatus(`Fichier prêt : ${esc(file.name)}`);
}

function inspectDims(img) {
  return new Promise((resolve) => {
    if (img.complete && img.naturalWidth) {
      $("meta-dims").textContent = `${img.naturalWidth} × ${img.naturalHeight} px`;
      resolve();
      return;
    }
    img.onload = () => {
      $("meta-dims").textContent = `${img.naturalWidth} × ${img.naturalHeight} px`;
      resolve();
    };
    img.onerror = () => { $("meta-dims").textContent = "–"; resolve(); };
  });
}

async function loadSampleSvg() {
  const res = await fetch("/api/v1/debug/sample-svg");
  if (!res.ok) throw new Error(`Exemple introuvable (${res.status})`);
  const buffer = await res.arrayBuffer();
  const file = new File([buffer], "qr_equipement.svg", { type: "image/svg+xml" });
  await loadFile(file);
  setStatus("SVG d'exemple chargé.");
  return file;
}

/* ── Appels API ─────────────────────────────────────────── */
async function rasterise() {
  if (!state.file) return;
  busy(true);
  setStatus("Rasterisation / décodage en cours…");
  try {
    const fd = new FormData();
    fd.append("file", state.file, state.fileName);
    const res = await fetch("/api/v1/debug/raster", { method: "POST", body: fd });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);

    state.lastRaster = body;
    renderRaster(body);
    setStatus(`Rasterisé en PNG — ${body.taille.largeur}×${body.taille.hauteur}px`, "ok");
  } catch (err) {
    setStatus(`Rasterisation échouée : ${err.message}`, "err");
  } finally {
    busy(false);
  }
}

function renderRaster(body) {
  const box = $("raster-preview");
  box.innerHTML = `<img src="data:image/png;base64,${body.png_base64}" alt="PNG rasterisé" />`;
  $("raster-meta").textContent =
    `Format source : ${body.source_format} · Décode aperçu : ${body.decode_apercu.data || "aucun"}`;
  $("r-source").textContent = body.source_format;
  $("r-dims").textContent = `${body.taille.largeur} × ${body.taille.hauteur} px`;
  $("r-decoders").textContent = Object.entries(body.decoders)
    .filter(([, v]) => v).map(([k]) => k).join(", ") || "aucun";
  $("raster-table").hidden = false;

  const d = body.decode_apercu;
  $("decode-box").innerHTML = renderDecode(d);
}

function renderDecode(d) {
  if (!d.data) {
    return `<span class="err">Aucun QR détecté</span> · ${d.attempts} essai${d.attempts > 1 ? "s" : ""} (moteur : ${d.method})`;
  }
  return `<span class="ok">QR détecté</span> <span class="kv"><dt>Contenu</dt><dd class="link-out" id="decode-link">${esc(d.data)}</dd><dt>Essais</dt><dd>${d.attempts}</dd></span>`;
}

async function scan() {
  if (!state.file) return;
  busy(true);
  setStatus("Scan QR en cours…");
  try {
    const fd = new FormData();
    fd.append("file", state.file, state.fileName);
    const res = await fetch("/api/v1/qr/scan", { method: "POST", body: fd });
    const body = await res.json();
    if (!res.ok) throw { status: res.status, body };
    state.lastScan = body;
    renderScan(body);
    setStatus(body.success ? "Scan réussi." : "Scan effectué (échec métier).", body.success ? "ok" : "err");
  } catch (err) {
    state.lastScan = null;
    $("scan-box").innerHTML =
      `<div class="scan-err">HTTP ${err.status} — ${esc(err.body?.detail || "erreur")}</div>`;
    setStatus(`Échec HTTP ${err.status}`, "err");
  } finally {
    busy(false);
  }
}

function renderScan(body) {
  const box = $("scan-box");
  const cls = body.success ? "scan-ok" : "scan-err";
  const method = body.method ? `<span class="method-tag">${esc(body.method)}</span>` : "";

  let html = `<div class="${cls}">`;
  html += `<p><strong>${body.success ? "✓ Succès" : "✗ Échec"}</strong>${method}</p>`;
  html += `<dl class="kv" style="margin-top:8px">`;

  if (body.success) {
    html += `<dt>ID équipement</dt><dd>${esc(body.id_equipement)}</dd>`;
    html += `<dt>Lien</dt><dd class="link-out">${esc(body.lien_equipement)}</dd>`;
    if (body.equipement) {
      html += `<dt>Fiche</dt><dd>${esc(JSON.stringify(body.equipement))}</dd>`;
    }
    if (body.equipement_details_indisponibles) {
      html += `<dt>Détails</dt><dd>indisponibles (lien brut conservé)</dd>`;
    }
  } else {
    html += `<dt>Erreur</dt><dd>${esc(body.error || "inconnue")}</dd>`;
  }
  html += `</dl>`;

  html += `<details style="margin-top:10px"><summary>JSON brut</summary><pre class="json-view">${esc(JSON.stringify(body, null, 2))}</pre></details>`;
  html += `</div>`;
  box.innerHTML = html;
}

/* ── Health ─────────────────────────────────────────────── */
async function refreshHealth() {
  try {
    const r = await fetch("/api/v1/healthz");
    const h = await r.json();
    const dec = h.decoder === "none" ? "aucun" : h.decoder;
    $("pill-decoder").textContent = `Décodeur : ${dec}`;
    $("pill-decoder").className = "pill " + (h.decoder === "none" ? "pill-err" : "pill-ok");
    $("pill-laravel").textContent = `Laravel : ${h.laravel_configured ? "oui" : "non"}`;
    $("pill-laravel").className = "pill " + (h.laravel_configured ? "pill-ok" : "pill-dim");
    $("version").textContent = h.version;
    $("health").querySelector(".pill-waiting").textContent = "Service : OK";
    $("health").querySelector(".pill-waiting").className = "pill pill-ok";
  } catch {
    $("health").querySelector(".pill-waiting").textContent = "Service : hors ligne";
    $("health").querySelector(".pill-waiting").className = "pill pill-err";
  }
}

/* ── Événements ─────────────────────────────────────────── */
const dz = $("dropzone");
const input = $("file-input");

dz.addEventListener("click", (e) => {
  if (e.target.tagName !== "BUTTON") input.click();
});
$("btn-browse").addEventListener("click", (e) => { e.stopPropagation(); input.click(); });
input.addEventListener("change", () => loadFile(input.files[0]));

["dragover", "dragenter"].forEach((ev) =>
  dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("dragover"); })
);
["dragleave", "drop"].forEach((ev) =>
  dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("dragover"); })
);
dz.addEventListener("drop", (e) => {
  const f = e.dataTransfer.files[0];
  if (f) loadFile(f);
});

$("btn-sample").addEventListener("click", async () => {
  try { await loadSampleSvg(); } catch (err) {
    setStatus(err.message, "err");
  }
});
$("btn-raster").addEventListener("click", rasterise);
$("btn-scan").addEventListener("click", scan);

/* ── Init ───────────────────────────────────────────────── */
refreshHealth();
setInterval(refreshHealth, 30000);