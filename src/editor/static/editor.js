/**
 * PDF Template Editor — main JS
 */

// ── State ────────────────────────────────────────────────────────────────
let templateData = { template: "", components: [] };
let editorContext = {};   // flat context from 1.json (for WYSIWYG canvas)
let selectedId = null;
let dragId = null;
let dragOffset = { x: 0, y: 0 };

// ── DOM refs ─────────────────────────────────────────────────────────────
const varSelect       = document.getElementById("variable-select");
const btnCopyVar      = document.getElementById("btn-copy-var");
const copyFeedback    = document.getElementById("copy-feedback");
const componentsList  = document.getElementById("components-list");
const canvasPage      = document.getElementById("canvas-page");
const inspectorEmpty  = document.getElementById("inspector-empty");
const inspectorProps  = document.getElementById("inspector-properties");

// ── Init ─────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  await loadContext();   // context first so canvas renders WYSIWYG on load
  loadTemplate();
  loadVariables();
  setupListeners();
});

function setupListeners() {
  document.getElementById("btn-save")     .addEventListener("click", saveTemplate);
  document.getElementById("btn-export")   .addEventListener("click", exportPDF);
  document.getElementById("btn-add-text") .addEventListener("click", addTextComponent);
  document.getElementById("btn-add-shape").addEventListener("click", addShapeComponent);
  document.getElementById("btn-delete")   .addEventListener("click", deleteSelected);

  // Clicking the blank canvas background deselects
  canvasPage.addEventListener("click", () => selectComponent(null));

  // Copy variable button
  btnCopyVar.addEventListener("click", () => {
    const val = varSelect.value;
    if (!val) return;
    navigator.clipboard.writeText(`{{${val}}}`).then(() => {
      copyFeedback.style.display = "block";
      setTimeout(() => copyFeedback.style.display = "none", 1500);
    });
  });

  // Inspector fields → update component on change
  ["prop-x","prop-y","prop-width","prop-height",
   "prop-content","prop-font","prop-size","prop-align","prop-bold","prop-italic",
   "prop-shape-type","prop-stroke-width","prop-fill"]
    .forEach(id => document.getElementById(id).addEventListener("change", onInspectorChange));

  // Shape color picker ↔ hex text
  syncColorPair("prop-color", "prop-color-hex");
  // Text color picker ↔ hex text
  syncColorPair("prop-text-color", "prop-text-color-hex");
}

// ── Load context (for WYSIWYG canvas interpolation) ──────────────────────
async function loadContext() {
  try {
    const res  = await fetch("/api/context");
    const data = await res.json();
    editorContext = data.context || {};
  } catch (e) { console.error("loadContext:", e); }
}

/**
 * Build a resolved context for canvas display:
 * - includes all fields from 1.json
 * - adds "template" key = templateData.template with fields resolved
 */
function buildDisplayContext() {
  const ctx = { ...editorContext };
  if (templateData.template) {
    ctx.template = interpolate(templateData.template, editorContext);
  }
  return ctx;
}

/** Keep a color-picker and its hex text input in sync */
function syncColorPair(pickerId, hexId) {
  const picker = document.getElementById(pickerId);
  const hexIn  = document.getElementById(hexId);
  picker.addEventListener("input", e => {
    hexIn.value = e.target.value;
    onInspectorChange(e);
  });
  hexIn.addEventListener("change", e => {
    if (/^#[0-9a-fA-F]{6}$/.test(e.target.value)) {
      picker.value = e.target.value;
      onInspectorChange(e);
    }
  });
}

/** Simple {{field}} resolver (client-side) */
function interpolate(text, ctx) {
  return text.replace(/\{\{(\w+)\}\}/g, (_, k) => (k in ctx ? ctx[k] : `{{${k}}}`));
}

/** Build inline SVG markup for a shape component (canvas display) */
function shapeToSvg(comp) {
  const w    = comp.rect[2];
  const h    = comp.rect[3];
  const c    = comp.color        || "#000000";
  const sw   = comp.stroke_width || 1;
  const fill = comp.fill ? c : "none";
  const half = sw / 2;
  let inner  = "";

  if (comp.shape_type === "rect") {
    inner = `<rect x="${half}" y="${half}" width="${Math.max(0, w - sw)}" height="${Math.max(0, h - sw)}"
      stroke="${c}" stroke-width="${sw}" fill="${fill}"/>`;
  } else if (comp.shape_type === "line") {
    inner = `<line x1="0" y1="${h / 2}" x2="${w}" y2="${h / 2}"
      stroke="${c}" stroke-width="${sw}"/>`;
  } else if (comp.shape_type === "circle") {
    const r = Math.max(0, Math.min(w, h) / 2 - half);
    inner = `<circle cx="${w / 2}" cy="${h / 2}" r="${r}"
      stroke="${c}" stroke-width="${sw}" fill="${fill}"/>`;
  }
  return `<svg width="${w}" height="${h}" style="display:block;overflow:visible">${inner}</svg>`;
}

// ── Load template from server ─────────────────────────────────────────────
async function loadTemplate() {
  try {
    const res = await fetch("/api/template");
    templateData = await res.json();
    render();
  } catch (e) { console.error("loadTemplate:", e); }
}

// ── Load variable groups for dropdown ────────────────────────────────────
async function loadVariables() {
  try {
    const res  = await fetch("/api/variables");
    const data = await res.json();

    varSelect.innerHTML = '<option value="" disabled selected>— pick a variable —</option>';
    for (const group of data.groups || []) {
      const og = document.createElement("optgroup");
      og.label = group.name;
      for (const v of group.variables) {
        const opt = document.createElement("option");
        opt.value       = v.id;
        opt.textContent = `{{${v.id}}} — ${v.label}`;
        og.appendChild(opt);
      }
      varSelect.appendChild(og);
    }
  } catch (e) { console.error("loadVariables:", e); }
}

// ── Save ─────────────────────────────────────────────────────────────────
async function saveTemplate() {
  try {
    await fetch("/api/template", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(templateData),
    });
    flash("Saved ✓");
  } catch (e) { flash("Save failed", "error"); }
}

// ── Add text component ────────────────────────────────────────────────────
function addTextComponent() {
  const id = `text_${Date.now()}`;
  templateData.components.push({
    id,
    type: "text",
    content: "{{template}}",
    rect: [50, 680, 512, 60],
    style: { font: "Helvetica", size: 12, bold: false, italic: false, align: "left" },
  });
  render();
  selectComponent(id);
}

// ── Add shape component ───────────────────────────────────────────────────
function addShapeComponent() {
  const id = `shape_${Date.now()}`;
  templateData.components.push({
    id,
    type: "shape",
    shape_type: "rect",
    rect: [50, 680, 200, 60],
    color: "#000000",
    stroke_width: 1,
    fill: false,
  });
  render();
  selectComponent(id);
}

// ── Delete selected component ─────────────────────────────────────────────
function deleteSelected() {
  if (!selectedId) return;
  templateData.components = templateData.components.filter(c => c.id !== selectedId);
  selectedId = null;
  render();
}

// ── Inspector change → update component ──────────────────────────────────
function onInspectorChange(e) {
  if (!selectedId) return;
  const comp = templateData.components.find(c => c.id === selectedId);
  if (!comp) return;

  const id  = e.target.id;
  const val = e.target.type === "checkbox" ? e.target.checked : e.target.value;

  switch (id) {
    // position (all types)
    case "prop-x":            comp.rect[0] = +val; break;
    case "prop-y":            comp.rect[1] = +val; break;
    case "prop-width":        comp.rect[2] = +val; break;
    case "prop-height":       comp.rect[3] = +val; break;
    // text
    case "prop-content":      comp.content      = val;  break;
    case "prop-font":         comp.style.font   = val;  break;
    case "prop-size":         comp.style.size   = +val; break;
    case "prop-align":        comp.style.align  = val;  break;
    case "prop-bold":         comp.style.bold   = val;  break;
    case "prop-italic":       comp.style.italic = val;  break;
    // text color
    case "prop-text-color":
    case "prop-text-color-hex": comp.style.color = val; break;
    // shape
    case "prop-shape-type":   comp.shape_type   = val;  break;
    case "prop-color":
    case "prop-color-hex":    comp.color        = val;  break;
    case "prop-stroke-width": comp.stroke_width = +val; break;
    case "prop-fill":         comp.fill         = val;  break;
  }
  render();
  populateInspector(comp);
}

// ── Render canvas + component list ───────────────────────────────────────
function render() {
  renderCanvas();
  renderList();
}

function renderCanvas() {
  canvasPage.innerHTML = "";
  const ctx = buildDisplayContext();   // resolved values for WYSIWYG display

  // ── Fallback ghost: no real components → mirror the engine's default render
  const realComps = templateData.components.filter(c => c.type !== "pagebreak");
  if (realComps.length === 0 && templateData.template) {
    const ghost = document.createElement("div");
    ghost.style.cssText = `
      position:absolute; left:50px; top:42px; width:512px; height:700px;
      font-size:12px; color:#aaa; white-space:pre-wrap; overflow:hidden;
      border:1px dashed #ddd; padding:4px; pointer-events:none; box-sizing:border-box;
    `;
    ghost.textContent = interpolate("{{template}}", ctx);
    canvasPage.appendChild(ghost);
    return;
  }

  templateData.components.forEach(comp => {
    if (comp.type === "pagebreak") return;

    const el = document.createElement("div");
    el.className = "canvas-comp";
    el.dataset.id = comp.id;

    const selected = comp.id === selectedId;
    // Convert ReportLab y (bottom-left origin) → CSS top (top-left origin)
    const cssTop = 792 - comp.rect[1] - comp.rect[3];
    const [rx, ry, rw, rh] = comp.rect;

    // Use outline (not border) so it draws outside the box and never shifts content
    const outline    = selected ? "2px solid #2196F3" : "1px dashed #ccc";
    const selShadow  = selected ? "0 0 0 3px rgba(33,150,243,.2)" : "none";

    el.style.cssText = `
      position:absolute;
      left:${rx}px; top:${cssTop}px;
      width:${rw}px; height:${rh}px;
      cursor:move;
      overflow:visible;
      outline:${outline};
      box-shadow:${selShadow};
    `;

    if (comp.type === "shape") {
      el.innerHTML = shapeToSvg(comp);
    } else {
      el.style.fontFamily  = comp.style?.font    || "Helvetica";
      el.style.fontSize    = (comp.style?.size   || 12) + "px";
      el.style.fontWeight  = comp.style?.bold    ? "bold"   : "normal";
      el.style.fontStyle   = comp.style?.italic  ? "italic" : "normal";
      el.style.textAlign   = comp.style?.align   || "left";
      el.style.color       = comp.style?.color   || "#000000";
      el.style.whiteSpace  = "pre-wrap";
      el.textContent = interpolate(comp.content, ctx);
    }

    el.addEventListener("mousedown", e => startDrag(e, comp.id));
    el.addEventListener("click",     e => { e.stopPropagation(); selectComponent(comp.id); });
    canvasPage.appendChild(el);
  });
}

function renderList() {
  componentsList.innerHTML = "";
  templateData.components.forEach(comp => {
    if (comp.type === "pagebreak") return;
    const item = document.createElement("div");
    item.className = "component-item" + (comp.id === selectedId ? " selected" : "");
    item.innerHTML = `<span class="comp-type">${comp.type}</span> <span>${comp.id}</span>`;
    item.addEventListener("click", () => selectComponent(comp.id));
    componentsList.appendChild(item);
  });
}

// ── Select component → populate inspector ────────────────────────────────
function selectComponent(id) {
  selectedId = id;
  renderCanvas();
  renderList();

  if (!id) {
    inspectorEmpty.style.display = "block";
    inspectorProps.style.display  = "none";
    return;
  }

  const comp = templateData.components.find(c => c.id === id);
  if (!comp) return;

  inspectorEmpty.style.display = "none";
  inspectorProps.style.display  = "block";
  populateInspector(comp);
}

function populateInspector(comp) {
  document.getElementById("prop-id").value     = comp.id;
  document.getElementById("prop-x").value      = comp.rect[0];
  document.getElementById("prop-y").value      = comp.rect[1];
  document.getElementById("prop-width").value  = comp.rect[2];
  document.getElementById("prop-height").value = comp.rect[3];

  const isText  = comp.type === "text";
  const isShape = comp.type === "shape";

  document.getElementById("text-props") .style.display = isText  ? "block" : "none";
  document.getElementById("shape-props").style.display = isShape ? "block" : "none";

  if (isText) {
    document.getElementById("prop-content").value  = comp.content        || "";
    document.getElementById("prop-font").value     = comp.style?.font    || "Helvetica";
    document.getElementById("prop-size").value     = comp.style?.size    || 12;
    document.getElementById("prop-align").value    = comp.style?.align   || "left";
    document.getElementById("prop-bold").checked   = comp.style?.bold    || false;
    document.getElementById("prop-italic").checked = comp.style?.italic  || false;
    const tc = comp.style?.color || "#000000";
    document.getElementById("prop-text-color")    .value = tc;
    document.getElementById("prop-text-color-hex").value = tc;
  }

  if (isShape) {
    const color = comp.color || "#000000";
    document.getElementById("prop-shape-type")  .value   = comp.shape_type   || "rect";
    document.getElementById("prop-color")        .value   = color;
    document.getElementById("prop-color-hex")    .value   = color;
    document.getElementById("prop-stroke-width") .value   = comp.stroke_width || 1;
    document.getElementById("prop-fill")         .checked = comp.fill         || false;
  }
}

// ── Drag and drop ─────────────────────────────────────────────────────────
function startDrag(e, id) {
  e.preventDefault();
  dragId = id;
  const comp = templateData.components.find(c => c.id === id);
  if (!comp) return;

  const rect  = canvasPage.getBoundingClientRect();
  const compX = comp.rect[0];
  const compY = 792 - comp.rect[1] - comp.rect[3]; // canvas CSS top
  dragOffset.x = e.clientX - rect.left - compX;
  dragOffset.y = e.clientY - rect.top  - compY;

  document.addEventListener("mousemove", onDrag);
  document.addEventListener("mouseup",   stopDrag);
}

function onDrag(e) {
  if (!dragId) return;
  const comp = templateData.components.find(c => c.id === dragId);
  if (!comp) return;

  const rect = canvasPage.getBoundingClientRect();
  const cssX = Math.max(0, Math.min(e.clientX - rect.left - dragOffset.x, 612 - comp.rect[2]));
  const cssY = Math.max(0, Math.min(e.clientY - rect.top  - dragOffset.y, 792 - comp.rect[3]));

  // Convert CSS top back to ReportLab y (bottom-left origin)
  comp.rect[0] = Math.round(cssX);
  comp.rect[1] = Math.round(792 - cssY - comp.rect[3]);

  renderCanvas();
}

function stopDrag() {
  dragId = null;
  document.removeEventListener("mousemove", onDrag);
  document.removeEventListener("mouseup",   stopDrag);
  if (selectedId) {
    const comp = templateData.components.find(c => c.id === selectedId);
    if (comp) populateInspector(comp);
  }
}


// ── Export PDF ────────────────────────────────────────────────────────────
async function exportPDF() {
  try {
    const res = await fetch("/api/render/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ context: {} }),
    });
    const data = await res.json();
    if (!res.ok) { flash(data.detail || "Export failed", "error"); return; }
    flash(`PDF saved — ${(data.size / 1024).toFixed(1)} KB → ${data.path}`);
  } catch (e) { flash("Export failed", "error"); }
}

// ── Toast ─────────────────────────────────────────────────────────────────
function flash(msg, type = "ok") {
  let toast = document.getElementById("toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.className   = `toast toast-${type}`;
  toast.style.display = "block";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => toast.style.display = "none", 2500);
}
