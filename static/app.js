"use strict";
const $ = id => document.getElementById(id);
const supported = /\.(jpe?g|png|tiff?|bmp|webp|heic|heif)$/i;
const storeKey = "stitkovnik-v1";
let rows = [], rules = {}, defaultRules = {}, token = "", busy = false, cancelled = false;
let filter = "all", selected = null, autoRotate = true;
const previews = new Map();
let duplicateCounts = {};

function refreshDuplicates() {
  duplicateCounts = { "S/N": new Map(), MAC: new Map() };
  for (const row of rows) for (const key of ["S/N", "MAC"]) {
    const value = row.fields[key]?.trim().toUpperCase();
    if (value) duplicateCounts[key].set(value, (duplicateCounts[key].get(value) || 0) + 1);
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function notice(text, success = false) {
  $("notice").textContent = text;
  $("notice").className = "notice" + (success ? " success" : "");
  $("notice").hidden = !text;
}
function persist() {
  try { localStorage.setItem(storeKey, JSON.stringify({ rows, rules, autoRotate })); }
  catch { notice("Úložiště prohlížeče je plné. Výsledky jsou v tabulce, ale před zavřením je exportujte."); }
}
function rowWarnings(row) {
  const result = [];
  if (row.error) result.push(row.error);
  if (!row.fields["S/N"]?.trim()) result.push("Chybí S/N");
  if (!row.fields.MAC?.trim()) result.push("Chybí MAC");
  else if (!/^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$/i.test(row.fields.MAC.trim())) result.push("MAC má neplatný formát nebo obsahuje více adres");
  if (row.fields["S/N"]?.includes("; ")) result.push("Více sériových čísel");
  if (row.confidence < 75 && !row.verified) result.push("Nižší jistota OCR");
  if (!row.verified) result.push(...(row.ocrWarnings || []));
  for (const key of ["S/N", "MAC"]) {
    const val = row.fields[key]?.trim().toUpperCase();
    if (val && duplicateCounts[key]?.get(val) > 1) result.push(`Duplicitní ${key}`);
  }
  return [...new Set(result)];
}
function state(row) {
  if (row.error) return ["error", "Chyba OCR"];
  if (rowWarnings(row).length) return ["review", "Ke kontrole"];
  return row.verified ? ["ready", "Ověřeno"] : ["extracted", "Rozpoznáno"];
}
function counts() {
  refreshDuplicates();
  $("countBadge").textContent = $("allCount").textContent = rows.length;
  $("reviewCount").textContent = rows.filter(r => ["review", "error"].includes(state(r)[0])).length;
  $("readyCount").textContent = rows.filter(r => state(r)[0] === "ready").length;
  $("exportButton").disabled = $("csvButton").disabled = !rows.length || busy;
  $("clearButton").disabled = !rows.length || busy;
  $("footerText").textContent = rows.length ? `${rows.length} obrázků · ${$("reviewCount").textContent} ke kontrole · export obsahuje všechny řádky` : "Připraveno na vaše obrázky";
}
function updateStatuses() {
  counts();
  document.querySelectorAll("#rows tr").forEach(tr => {
    const row = rows.find(r => r.id === tr.dataset.id);
    if (!row) return;
    const [kind, text] = state(row), badge = tr.querySelector(".status");
    badge.className = `status ${kind}`;
    badge.textContent = `${kind === "ready" ? "✓" : kind === "review" || kind === "error" ? "!" : "·"} ${text}`;
    badge.title = rowWarnings(row).join("\n");
  });
}
function render() {
  refreshDuplicates();
  const query = $("search").value.toLocaleLowerCase("cs");
  const visible = rows.filter(r => {
    const kind = state(r)[0];
    const matchesFilter = filter === "all" || (filter === "review" && ["review", "error"].includes(kind)) || (filter === "ready" && kind === "ready");
    return matchesFilter && [r.name, ...Object.values(r.fields), r.note || ""].join(" ").toLocaleLowerCase("cs").includes(query);
  });
  $("rows").replaceChildren();
  for (const row of visible) {
    const tr = el("tr"); tr.dataset.id = row.id;
    tr.append(el("td", "number", rows.indexOf(row) + 1));
    const file = el("td"), button = el("button", "file-button", row.name);
    button.title = row.name; button.onclick = () => openDetail(row.id); file.append(button); tr.append(file);
    for (const key of ["S/N", "MAC", "Model"]) {
      const td = el("td"), input = el("input", "cell-input" + (key === "MAC" || key === "S/N" ? " mono" : ""));
      input.value = row.fields[key] || ""; input.placeholder = "—"; input.setAttribute("aria-label", `${key}: ${row.name}`);
      input.oninput = () => { row.fields[key] = input.value; row.verified = false; persist(); updateStatuses(); };
      input.onchange = () => { if (filter !== "all" || $("search").value) render(); };
      td.append(input); tr.append(td);
    }
    const status = el("td"); status.append(el("span", "status")); tr.append(status);
    const action = el("td"), remove = el("button", "remove-button", "×");
    remove.title = "Odstranit řádek"; remove.setAttribute("aria-label", `Odstranit ${row.name}`); remove.disabled = busy;
    remove.onclick = () => { rows = rows.filter(r => r.id !== row.id); releasePreview(row.id); persist(); render(); };
    action.append(remove); tr.append(action); $("rows").append(tr);
  }
  $("emptyState").hidden = visible.length > 0;
  $("emptyState").querySelector("h3").textContent = rows.length ? "Žádné odpovídající štítky" : "Vaše první tabulka začíná obrázkem";
  $("emptyState").querySelector("p").textContent = rows.length ? "Zkuste jiný filtr nebo vyhledávání." : "Vyberte složku s fotografiemi a nechte aplikaci přečíst štítky.";
  $("emptyState").querySelector(".steps").hidden = !!rows.length;
  updateStatuses();
}
async function api(path, body, headers = {}) {
  const response = await fetch(path, { method: "POST", headers: { "X-App-Token": token, ...headers }, body });
  if (!response.ok) {
    let message = "Zpracování se nezdařilo.";
    try { message = (await response.json()).error || message; } catch {}
    throw new Error(message);
  }
  return response;
}
function releasePreview(id) { if (previews.has(id)) { URL.revokeObjectURL(previews.get(id)); previews.delete(id); } }
async function importFiles(files) {
  if (busy) return;
  const all = Array.from(files), accepted = all.filter(f => supported.test(f.name));
  if (!accepted.length) { notice("Ve výběru nejsou podporované obrázky. Použijte JPG, PNG, TIFF, BMP, WebP nebo HEIC."); return; }
  busy = true; cancelled = false;
  $("folderButton").disabled = $("filesButton").disabled = true;
  $("progressSection").hidden = false; $("progress").max = accepted.length; $("progress").value = 0;
  $("cancelButton").disabled = false; $("cancelButton").textContent = "Zastavit po tomto obrázku";
  notice(all.length > accepted.length ? `${all.length - accepted.length} nepodporovaných souborů bude přeskočeno.` : "");
  const batchRules = structuredClone(rules), batchRotate = autoRotate;
  let completed = 0, errors = 0, kept = 0, updated = 0;
  render();
  for (const file of accepted) {
    if (cancelled) break;
    const name = file.webkitRelativePath || file.name;
    const existing = $("updateExisting").checked ? rows.find(r => r.name === name) : null;
    if (existing?.verified) {
      releasePreview(existing.id); previews.set(existing.id, URL.createObjectURL(file));
      completed++; kept++; $("progress").value = completed;
      continue;
    }
    $("progressLabel").textContent = `Rozpoznávám štítek ${completed + 1} z ${accepted.length}`;
    $("progressDetail").textContent = name;
    let row;
    const id = existing?.id || crypto.randomUUID();
    try {
      if (file.size > 30 * 1024 * 1024) throw new Error("Obrázek přesahuje 30 MB.");
      const response = await api("/api/scan", file, { "X-Rules": JSON.stringify(batchRules).replace(/[^\x00-\x7F]/g, c => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0")), "X-Rotate": String(batchRotate) });
      row = { ...(await response.json()), id, name, verified: false, note: existing?.note || "" };
    } catch (error) {
      row = { id, name, fields: Object.fromEntries(Object.keys(batchRules).map(k => [k, ""])), text: "", error: error.message, confidence: 0, verified: false, note: "" };
      errors++;
    }
    releasePreview(id); previews.set(id, URL.createObjectURL(file));
    if (existing && !row.error) { rows[rows.indexOf(existing)] = row; updated++; }
    else if (!existing) rows.push(row);
    completed++;
    $("progress").value = completed; persist(); render();
  }
  busy = false; $("progressSection").hidden = true;
  $("folderButton").disabled = $("filesButton").disabled = false;
  $("folderInput").value = $("filesInput").value = "";
  notice(`${cancelled ? "Zpracování zastaveno." : "Hotovo."} Zpracováno ${completed} z ${accepted.length} obrázků.${updated ? ` Aktualizováno ${updated} řádků.` : ""}${kept ? ` Zachováno ${kept} ověřených řádků.` : ""}${errors ? ` ${errors} obrázků se nepodařilo přečíst; starší výsledky zůstaly zachované.` : " Údaje před exportem ověřte podle štítků."}${all.length > accepted.length ? ` Přeskočeno ${all.length - accepted.length} nepodporovaných souborů.` : ""}`, !errors);
  render();
}
function detailField(key, value) {
  const label = el("label", "field", key), input = el("input"); input.value = value; input.dataset.key = key;
  input.addEventListener("input", () => { $("verified").checked = false; }); label.append(input); $("detailFields").append(label);
}
function openDetail(id) {
  selected = id; const row = rows.find(r => r.id === id);
  $("detailTitle").textContent = row.name;
  const url = previews.get(id); $("preview").hidden = !url; $("previewMissing").hidden = !!url;
  if (url) $("preview").src = url; else $("preview").removeAttribute("src");
  $("preview").onerror = () => { $("preview").hidden = true; $("previewMissing").hidden = false; $("previewMissing").textContent = "Prohlížeč neumí tento formát zobrazit. OCR a export jsou stále dostupné."; };
  $("previewMissing").textContent = "Náhled je dostupný po novém načtení původního obrázku.";
  $("rawText").value = row.text; $("detailNote").value = row.note || ""; $("verified").checked = !!row.verified;
  $("detailWarnings").textContent = rowWarnings(row).join(" · ");
  $("confidenceLabel").textContent = `Jistota OCR: ${row.confidence ?? 0} %${row.rotation ? ` · použité otočení: ${row.rotation}°` : ""}. ${row.sources?.["S/N"]?.startsWith("Čárový") ? "S/N bylo načteno z čárového / QR kódu a přiřazeno k vytištěnému číslu. " : ""}Ani vysoká jistota nezaručuje správnost identifikátorů.`;
  $("detailFields").replaceChildren();
  Object.entries(row.fields).forEach(([k, v]) => detailField(k, v));
  $("detailDialog").showModal();
}
function ruleField(key, aliases) {
  const row = el("div", "rule-row"), label = el("label", "", key), input = el("input"), remove = el("button", "remove-button", "×");
  input.value = aliases.join(", "); input.dataset.key = key; input.id = "rule-" + crypto.randomUUID(); label.htmlFor = input.id;
  remove.disabled = ["S/N", "MAC"].includes(key); remove.title = "Odstranit pravidlo"; remove.onclick = () => row.remove();
  row.append(label, input, remove); $("rulesFields").append(row);
}
function renderRules(source) { $("rulesFields").replaceChildren(); Object.entries(source).forEach(([k, v]) => ruleField(k, v)); }
async function download(format) {
  try {
    const data = rows.map(r => ({ ...r, status: state(r)[1] + (rowWarnings(r).length ? ": " + rowWarnings(r).join(", ") : "") }));
    const response = await api(`/api/export/${format}`, JSON.stringify({ rows: data }), { "Content-Type": "application/json" });
    const url = URL.createObjectURL(await response.blob()), link = el("a");
    link.href = url; link.download = `stitky-kamer-${new Date().toLocaleDateString("sv-SE")}.${format}`; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000); notice(`Export ${format.toUpperCase()} je připravený ke stažení. Obsahuje všech ${rows.length} řádků.`, true);
  } catch (error) { notice(error.message); }
}
async function init() {
  try {
    const response = await fetch("/api/config"); if (!response.ok) throw new Error("Nepodařilo se připojit k aplikaci.");
    const config = await response.json(); token = config.token; defaultRules = config.rules; rules = structuredClone(defaultRules);
    try {
      const stored = JSON.parse(localStorage.getItem(storeKey));
      if (stored) { rows = Array.isArray(stored.rows) ? stored.rows : []; rules = stored.rules || rules; autoRotate = stored.autoRotate ?? true; }
    } catch { notice("Uloženou tabulku se nepodařilo obnovit."); }
    if (!config.ocr) notice("Chybí Tesseract OCR. Na macOS ho nainstalujete příkazem: brew install tesseract");
  } catch (error) { notice(error.message + " Spusťte aplikaci znovu."); }
  render();
}
$("folderButton").onclick = () => $("folderInput").click();
$("filesButton").onclick = () => $("filesInput").click();
$("folderInput").onchange = e => importFiles(e.target.files);
$("filesInput").onchange = e => importFiles(e.target.files);
$("cancelButton").onclick = () => { cancelled = true; $("cancelButton").disabled = true; $("cancelButton").textContent = "Dokončuji aktuální obrázek…"; };
$("dropzone").ondragover = e => { e.preventDefault(); if (!busy) $("dropzone").classList.add("drag"); };
$("dropzone").ondragleave = () => $("dropzone").classList.remove("drag");
$("dropzone").ondrop = e => { e.preventDefault(); $("dropzone").classList.remove("drag"); importFiles(e.dataTransfer.files); };
document.querySelectorAll("[data-close]").forEach(button => { button.onclick = () => $(button.dataset.close).close(); });
document.querySelectorAll(".tab").forEach(button => { button.onclick = () => { filter = button.dataset.filter; document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b === button)); render(); }; });
$("search").oninput = render;
$("exportButton").onclick = () => download("xlsx"); $("csvButton").onclick = () => download("csv");
$("clearButton").onclick = () => $("clearDialog").showModal();
$("confirmClear").onclick = () => { rows = []; for (const id of previews.keys()) releasePreview(id); persist(); $("clearDialog").close(); notice(""); render(); };
$("saveDetailButton").onclick = () => {
  const row = rows.find(r => r.id === selected); if (!row) return $("detailDialog").close();
  row.fields = Object.fromEntries(Array.from($("detailFields").querySelectorAll("input")).map(i => [i.dataset.key, i.value.trim()]));
  row.note = $("detailNote").value; row.text = $("rawText").value; row.verified = $("verified").checked;
  // Manual verification can rescue a failed OCR, but incomplete fields stay flagged.
  if (row.verified && row.fields["S/N"] && row.fields.MAC) delete row.error;
  persist(); render(); $("detailDialog").close();
};
$("rawText").oninput = () => { $("verified").checked = false; };
$("addFieldButton").onclick = () => {
  const key = prompt("Název dalšího údaje (např. IP adresa):")?.trim();
  if (!key) return;
  if (Array.from($("detailFields").querySelectorAll("input")).some(i => i.dataset.key === key)) return alert("Toto pole už existuje.");
  detailField(key, ""); $("verified").checked = false;
};
$("reparseButton").onclick = async () => {
  try {
    const response = await api("/api/reparse", JSON.stringify({ text: $("rawText").value, rules }), { "Content-Type": "application/json" });
    const result = await response.json(); $("detailFields").replaceChildren(); Object.entries(result.fields).forEach(([k, v]) => detailField(k, v));
    $("detailWarnings").textContent = result.warnings.join(" · "); $("verified").checked = false;
  } catch (error) { alert(error.message); }
};
$("rulesButton").onclick = () => { renderRules(rules); $("autoRotate").checked = autoRotate; $("rulesDialog").showModal(); };
$("resetRulesButton").onclick = () => { renderRules(defaultRules); $("autoRotate").checked = true; };
$("newRuleButton").onclick = () => {
  const key = prompt("Název nového sloupce:")?.trim(); if (!key) return;
  if (Array.from($("rulesFields").querySelectorAll("input")).some(i => i.dataset.key === key)) return alert("Toto pole už existuje.");
  ruleField(key, [key]);
};
$("saveRulesButton").onclick = async () => {
  const candidate = Object.fromEntries(Array.from($("rulesFields").querySelectorAll("input")).map(i => [i.dataset.key, i.value.split(",").map(a => a.trim()).filter(Boolean)]));
  try {
    await api("/api/reparse", JSON.stringify({ text: "", rules: candidate }), { "Content-Type": "application/json" });
    rules = candidate; autoRotate = $("autoRotate").checked; persist(); $("rulesDialog").close(); notice("Pravidla byla uložena. Použijí se při příštím načtení obrázků.", true);
  } catch (error) { alert(error.message); }
};
init();
