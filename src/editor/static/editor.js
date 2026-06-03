/**
 * PDF Template Editor — main JS
 */

// ── State ────────────────────────────────────────────────────────────────
let templateData = { components: [] };
let editorContext = {};   // flat context from DATA_JSON (for WYSIWYG canvas)
let selectedId = null;
let dragId = null;
let dragPageIdx = 0;
let activePage = 0;
let dragOffset = { x: 0, y: 0 };

// ── DOM refs ─────────────────────────────────────────────────────────────
const varSelect       = document.getElementById("variable-select");
const btnCopyVar      = document.getElementById("btn-copy-var");
const copyFeedback    = document.getElementById("copy-feedback");
const componentsList  = document.getElementById("components-list");
const canvasContainer = document.getElementById("canvas-container");
const inspectorEmpty  = document.getElementById("inspector-empty");
const inspectorProps  = document.getElementById("inspector-properties");

// ── Init ─────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  await loadTemplates();   // populate dropdown before checkStatus shows it
  await checkStatus();     // locks/unlocks UI based on whether DATA_JSON is preloaded
  await loadContext();
  await loadTemplate();
  await loadVariables();
  setupListeners();
});

function setupListeners() {
  document.getElementById("btn-save")          .addEventListener("click", saveTemplate);
  document.getElementById("btn-export")        .addEventListener("click", exportPDF);
  document.getElementById("btn-add-text")      .addEventListener("click", addTextComponent);
  document.getElementById("btn-add-shape")     .addEventListener("click", addShapeComponent);
  document.getElementById("btn-add-pagebreak") .addEventListener("click", addPageBreak);
  document.getElementById("btn-delete")        .addEventListener("click", deleteSelected);
  document.getElementById("template-select")   .addEventListener("change", onTemplateChange);

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

  // Right-panel tab switching
  document.getElementById("tab-btn-inspector").addEventListener("click", () => {
    document.getElementById("tab-inspector").style.display = "block";
    document.getElementById("tab-pages").style.display     = "none";
    document.getElementById("tab-btn-inspector").classList.add("tab-btn-active");
    document.getElementById("tab-btn-pages").classList.remove("tab-btn-active");
  });
  document.getElementById("tab-btn-pages").addEventListener("click", () => {
    document.getElementById("tab-inspector").style.display = "none";
    document.getElementById("tab-pages").style.display     = "block";
    document.getElementById("tab-btn-pages").classList.add("tab-btn-active");
    document.getElementById("tab-btn-inspector").classList.remove("tab-btn-active");
    renderPagesList();
  });

  // Active page tracks scroll position
  canvasContainer.addEventListener("scroll", () => {
    const top    = canvasContainer.scrollTop;
    const bottom = top + canvasContainer.clientHeight;
    let bestPage = activePage, bestVisible = 0;
    canvasContainer.querySelectorAll(".canvas-page").forEach(page => {
      const pt = page.offsetTop, pb = pt + page.offsetHeight;
      const visible = Math.max(0, Math.min(pb, bottom) - Math.max(pt, top));
      if (visible > bestVisible) { bestVisible = visible; bestPage = parseInt(page.dataset.page); }
    });
    if (bestPage !== activePage) { activePage = bestPage; updateActivePageVisuals(); renderPagesList(); }
  });
}

// ── Load context (for WYSIWYG canvas interpolation) ──────────────────────
async function loadContext() {
  const res = await fetch("/api/context");
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    flash(`ERROR: Failed to load context — ${err.detail}`, "error");
    return;
  }
  const data = await res.json();
  editorContext = data.context;
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
  // Allow only valid 3- or 6-digit hex colors; fall back to black
  const c    = /^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(comp.color) ? comp.color : "#000000";
  // Coerce to a finite positive number; fall back to 1
  const sw   = (isFinite(comp.stroke_width) && comp.stroke_width > 0) ? Number(comp.stroke_width) : 1;
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
  } else {
    flash(`ERROR: Unknown shape_type "${comp.shape_type}" on component ${comp.id}`, "error");
  }
  return `<svg width="${w}" height="${h}" style="display:block;overflow:visible">${inner}</svg>`;
}

// ── Load template from server ─────────────────────────────────────────────
async function loadTemplate() {
  const res = await fetch("/api/template");
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    flash(`ERROR: Failed to load template — ${err.detail}`, "error");
    return;
  }
  templateData = await res.json();
  render(true);
}

// ── Load variable groups for dropdown ────────────────────────────────────
async function loadVariables() {
  const res = await fetch("/api/variables");
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    flash(`ERROR: Failed to load variables — ${err.detail}`, "error");
    return;
  }
  const data = await res.json();

  varSelect.innerHTML = '<option value="" disabled selected>— pick a variable —</option>';
  for (const group of data.groups) {
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
}

// ── Save ─────────────────────────────────────────────────────────────────
async function saveTemplate() {
  const res = await fetch("/api/template", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(templateData),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    flash(`ERROR: Save failed — ${err.detail}`, "error");
    return;
  }
  flash("Saved ✓");
}

// ── Add text component ────────────────────────────────────────────────────
function addTextComponent() {
  const id = `text_${Date.now()}`;
  const { end } = getPageRange(activePage);
  templateData.components.splice(end, 0, {
    id,
    type: "text",
    content: "",
    rect: [50, 680, 512, 60],
    style: { font: "Helvetica", size: 12, bold: false, italic: false, align: "left", color: "#000000" },
  });
  render();
  selectComponent(id);
}

// ── Add shape component ───────────────────────────────────────────────────
function addShapeComponent() {
  const id = `shape_${Date.now()}`;
  const { end } = getPageRange(activePage);
  templateData.components.splice(end, 0, {
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

// ── Add page break ────────────────────────────────────────────────────────
function addPageBreak() {
  const { end } = getPageRange(activePage);
  templateData.components.splice(end, 0, { id: `pb_${Date.now()}`, type: "pagebreak" });
  render();
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

// ── Swap two pages (any i, j) in the flat component sequence ─────────────
function swapPages(i, j) {
  if (i === j) return;
  // Split flat array into chunks (page content) and separators (pagebreak objects)
  const chunks = [];
  const seps   = [];
  let current  = [];
  for (const comp of templateData.components) {
    if (comp.type === "pagebreak") { chunks.push(current); seps.push(comp); current = []; }
    else current.push(comp);
  }
  chunks.push(current);

  [chunks[i], chunks[j]] = [chunks[j], chunks[i]];

  // Rebuild: chunk0, sep0, chunk1, sep1, ..., chunkN
  const result = [];
  for (let k = 0; k < chunks.length; k++) {
    result.push(...chunks[k]);
    if (k < seps.length) result.push(seps[k]);
  }
  templateData.components = result;
}

// ── Delete a page (chunk + one adjacent separator) ───────────────────────
function deletePage(idx) {
  const chunks = [];
  const seps   = [];
  let current  = [];
  for (const comp of templateData.components) {
    if (comp.type === "pagebreak") { chunks.push(current); seps.push(comp); current = []; }
    else current.push(comp);
  }
  chunks.push(current);
  if (chunks.length <= 1) return; // never delete the only page

  chunks.splice(idx, 1);
  seps.splice(Math.min(idx, seps.length - 1), 1);

  const result = [];
  for (let k = 0; k < chunks.length; k++) {
    result.push(...chunks[k]);
    if (k < seps.length) result.push(seps[k]);
  }
  templateData.components = result;

  if (activePage >= chunks.length) activePage = chunks.length - 1;
  // deselect if selected component was on deleted page
  if (selectedId && !templateData.components.find(c => c.id === selectedId)) selectedId = null;
}

// ── Pages-order panel ─────────────────────────────────────────────────────
function renderPagesList() {
  const list = document.getElementById("pages-order-list");
  if (!list) return;
  const pages = splitIntoPages(templateData.components);
  const total = pages.length;
  list.innerHTML = "";

  pages.forEach((pageComps, idx) => {
    const card = document.createElement("div");
    card.className = "page-card" + (idx === activePage ? " page-card-active" : "");

    const thumb = document.createElement("div");
    thumb.className = "page-card-thumb";
    thumb.textContent = idx + 1;

    const lbl = document.createElement("div");
    lbl.className = "page-card-label";
    lbl.textContent = `Page ${idx + 1}`;
    const sub = document.createElement("small");
    sub.textContent = `${pageComps.length} component${pageComps.length !== 1 ? "s" : ""}`;
    lbl.appendChild(sub);

    const btns = document.createElement("div");
    btns.className = "page-card-btns";

    const btnUp = document.createElement("button");
    btnUp.textContent = "▲";
    btnUp.title = "Move page up";
    btnUp.disabled = idx === 0;
    btnUp.addEventListener("click", () => { swapPages(idx, idx - 1); activePage = idx - 1; render(); });

    const btnDn = document.createElement("button");
    btnDn.textContent = "▼";
    btnDn.title = "Move page down";
    btnDn.disabled = idx === total - 1;
    btnDn.addEventListener("click", () => { swapPages(idx, idx + 1); activePage = idx + 1; render(); });

    btns.appendChild(btnUp);
    btns.appendChild(btnDn);

    const btnDel = document.createElement("button");
    btnDel.className = "page-card-delete";
    btnDel.title = "Delete page";
    btnDel.innerHTML = `<svg width="11" height="13" viewBox="0 0 11 13" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
      <path d="M1 3h9"/><path d="M3.5 3V2a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 .5.5v1"/>
      <path d="M2 3.5l.75 7.5h5.5L9 3.5"/><line x1="4.5" y1="5.5" x2="4.5" y2="9"/><line x1="6.5" y1="5.5" x2="6.5" y2="9"/>
    </svg>`;
    btnDel.disabled = total <= 1;
    btnDel.addEventListener("click", () => {
      if (pageComps.length > 0 && !confirm(`Delete Page ${idx + 1}? It has ${pageComps.length} component${pageComps.length !== 1 ? "s" : ""} that will be removed.`)) return;
      deletePage(idx);
      render();
    });

    card.appendChild(thumb);
    card.appendChild(lbl);
    card.appendChild(btns);
    card.appendChild(btnDel);
    list.appendChild(card);
  });
}

// ── Find the flat-array range [start, end) for a given page index ────────
function getPageRange(pageIdx) {
  let page = 0, start = 0;
  for (let i = 0; i < templateData.components.length; i++) {
    if (templateData.components[i].type === "pagebreak") {
      if (page === pageIdx) return { start, end: i };
      page++;
      start = i + 1;
    }
  }
  return { start, end: templateData.components.length };
}

// ── Update only the active-page outlines/labels without a full re-render ─
function updateActivePageVisuals() {
  canvasContainer.querySelectorAll(".canvas-page").forEach(page => {
    const isActive = parseInt(page.dataset.page) === activePage;
    page.style.outline      = isActive ? "2px solid #beffb6" : "";
    page.style.outlineOffset = isActive ? "3px" : "";
  });
  canvasContainer.querySelectorAll(".page-label").forEach(label => {
    const isActive = parseInt(label.dataset.page) === activePage;
    label.style.color = isActive ? "#beffb6" : "#ddd";
  });
}

// ── Split components into pages by pagebreak sentinels ───────────────────
function splitIntoPages(components) {
  const pages = [[]];
  for (const comp of components) {
    if (comp.type === "pagebreak") pages.push([]);
    else pages[pages.length - 1].push(comp);
  }
  return pages;
}

// ── Render canvas + component list ───────────────────────────────────────
function render(resetScroll = false) {
  if (resetScroll) activePage = 0;
  renderCanvas(resetScroll);
  renderList();
  renderPagesList();
}

function renderCanvas(resetScroll = false) {
  const savedScroll = resetScroll ? 0 : canvasContainer.scrollTop;
  canvasContainer.innerHTML = "";
  canvasContainer.style.display = "flex";
  canvasContainer.style.flexDirection = "column";
  canvasContainer.style.alignItems = "center";
  canvasContainer.style.justifyContent = "flex-start";

  const pages = splitIntoPages(templateData.components);
  const totalPages = pages.length;

  pages.forEach((pageComps, pageIdx) => {
    if (totalPages > 1) {
      const label = document.createElement("div");
      label.className = "page-label";
      label.dataset.page = pageIdx;
      label.textContent = `Page ${pageIdx + 1}`;
      label.style.color = pageIdx === activePage ? "#beffb6" : "#ddd";
      label.style.paddingBottom = "8px";
      label.style.paddingTop = "8px";
      canvasContainer.appendChild(label);
    }

    const page = document.createElement("div");
    page.className = "canvas-page";
    page.dataset.page = pageIdx;
    page.addEventListener("click", () => selectComponent(null));
    if (pageIdx === activePage) {
      page.style.outline = "2px solid #beffb6";
      page.style.outlineOffset = "3px";
    }

    const pageNum = document.createElement("div");
    pageNum.textContent = `Page ${pageIdx + 1} of ${totalPages}`;
    pageNum.style.cssText = `
      position: absolute;
      bottom: 30px;
      left: 0; right: 0;
      text-align: center;
      font-size: 10px;
      font-family: Helvetica, Arial, sans-serif;
      color: #000;
      pointer-events: none;
      user-select: none;
    `;
    page.appendChild(pageNum);

    pageComps.forEach(comp => {
      const el = document.createElement("div");
      el.className = "canvas-comp";
      el.dataset.id = comp.id;

      const selected = comp.id === selectedId;
      const cssTop = 792 - comp.rect[1] - comp.rect[3];
      const [rx, , rw, rh] = comp.rect;

      el.style.cssText = `
        position:absolute;
        left:${rx}px; top:${cssTop}px;
        width:${rw}px; height:${rh}px;
        cursor:move;
        overflow:visible;
        outline:${selected ? "2px solid #2196F3" : "1px dashed #ccc"};
        box-shadow:${selected ? "0 0 0 3px rgba(33,150,243,.2)" : "none"};
      `;

      if (comp.type === "shape") {
        el.innerHTML = shapeToSvg(comp);
      } else {
        el.style.fontFamily = comp.style.font;
        el.style.fontSize   = comp.style.size + "px";
        el.style.fontWeight = comp.style.bold   ? "bold"   : "normal";
        el.style.fontStyle  = comp.style.italic ? "italic" : "normal";
        el.style.textAlign  = comp.style.align;
        el.style.color      = comp.style.color;
        el.style.whiteSpace = "pre-wrap";
        el.textContent = interpolate(comp.content, editorContext);
      }

      el.addEventListener("mousedown", e => startDrag(e, comp.id, pageIdx));
      el.addEventListener("click",     e => { e.stopPropagation(); selectComponent(comp.id); });
      page.appendChild(el);
    });

    canvasContainer.appendChild(page);
  });

  canvasContainer.scrollTop = savedScroll;
}

function renderList() {
  componentsList.innerHTML = "";
  let pageNum = 1;

  templateData.components.forEach(comp => {
    if (comp.type === "pagebreak") {
      pageNum++;
      const sep = document.createElement("div");
      sep.className = "page-break-item";
      sep.innerHTML = `<span>── Page ${pageNum} ──</span>`;
      const del = document.createElement("button");
      del.textContent = "✕";
      del.title = "Remove page break";
      del.addEventListener("click", () => {
        templateData.components = templateData.components.filter(c => c.id !== comp.id);
        render();
      });
      sep.appendChild(del);
      componentsList.appendChild(sep);
      return;
    }
    const item = document.createElement("div");
    item.className = "component-item" + (comp.id === selectedId ? " selected" : "");
    const typeSpan = document.createElement("span");
    typeSpan.className = "comp-type";
    typeSpan.textContent = comp.type;
    const idSpan = document.createElement("span");
    idSpan.textContent = comp.id;
    item.appendChild(typeSpan);
    item.appendChild(document.createTextNode(" "));
    item.appendChild(idSpan);
    item.addEventListener("click", () => selectComponent(comp.id));
    componentsList.appendChild(item);
  });
}

// ── Select component → populate inspector ────────────────────────────────
function selectComponent(id) {
  selectedId = id;
  if (id) {
    const pages = splitIntoPages(templateData.components);
    for (let i = 0; i < pages.length; i++) {
      if (pages[i].some(c => c.id === id)) { activePage = i; break; }
    }
  }
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
    document.getElementById("prop-content").value  = comp.content;
    document.getElementById("prop-font").value     = comp.style.font;
    document.getElementById("prop-size").value     = comp.style.size;
    document.getElementById("prop-align").value    = comp.style.align;
    document.getElementById("prop-bold").checked   = comp.style.bold;
    document.getElementById("prop-italic").checked = comp.style.italic;
    document.getElementById("prop-text-color")    .value = comp.style.color;
    document.getElementById("prop-text-color-hex").value = comp.style.color;
  }

  if (isShape) {
    document.getElementById("prop-shape-type")  .value   = comp.shape_type;
    document.getElementById("prop-color")        .value   = comp.color;
    document.getElementById("prop-color-hex")    .value   = comp.color;
    document.getElementById("prop-stroke-width") .value   = comp.stroke_width;
    document.getElementById("prop-fill")         .checked = comp.fill;
  }
}

// ── Drag and drop ─────────────────────────────────────────────────────────
function startDrag(e, id, pageIdx) {
  e.preventDefault();
  dragId = id;
  dragPageIdx = pageIdx;
  activePage = pageIdx;
  const comp = templateData.components.find(c => c.id === id);
  if (!comp) return;

  const pageEl = canvasContainer.querySelector(`.canvas-page[data-page="${pageIdx}"]`);
  const rect   = pageEl.getBoundingClientRect();
  dragOffset.x = e.clientX - rect.left - comp.rect[0];
  dragOffset.y = e.clientY - rect.top  - (792 - comp.rect[1] - comp.rect[3]);

  document.addEventListener("mousemove", onDrag);
  document.addEventListener("mouseup",   stopDrag);
}

function onDrag(e) {
  if (!dragId) return;
  const comp = templateData.components.find(c => c.id === dragId);
  if (!comp) return;

  const pageEl = canvasContainer.querySelector(`.canvas-page[data-page="${dragPageIdx}"]`);
  const rect   = pageEl.getBoundingClientRect();
  const cssX = Math.max(0, Math.min(e.clientX - rect.left - dragOffset.x, 612 - comp.rect[2]));
  const cssY = Math.max(0, Math.min(e.clientY - rect.top  - dragOffset.y, 792 - comp.rect[3]));

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


// ── Lock / unlock the editor ──────────────────────────────────────────────
function setLocked(locked) {
  document.body.classList.toggle("editor-locked", locked);
  for (const id of ["btn-save", "btn-export", "btn-add-text", "btn-add-shape",
                     "btn-delete", "btn-copy-var"]) {
    const el = document.getElementById(id);
    if (el) el.disabled = locked;
  }
  document.getElementById("variable-select").disabled = locked;
}

// ── Template status check ─────────────────────────────────────────────────
async function checkStatus() {
  const res = await fetch("/api/status");
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    flash(`ERROR: Failed to check status — ${err.detail}`, "error");
    return;
  }
  const data = await res.json();

  if (!data.data_preloaded) {
    setLocked(true);
    document.getElementById("no-template-banner").style.display = "none";
    return;
  }

  if (data.exp_tmpl_id) {
    const sel = document.getElementById("template-select");
    const opt = sel.querySelector(`option[value="${data.exp_tmpl_id}"]`);
    if (opt) sel.value = data.exp_tmpl_id;
  }
  setLocked(false);

  const banner = document.getElementById("no-template-banner");
  if (!data.template_exists) {
    banner.style.display = "flex";
    document.getElementById("btn-create-template").addEventListener("click", async () => {
      const r = await fetch("/api/template/create", { method: "POST" });
      if (r.ok) {
        banner.style.display = "none";
        await loadTemplate();
        flash("Empty template created — start adding components");
      } else {
        const e = await r.json().catch(() => ({ detail: r.statusText }));
        flash(`ERROR: ${e.detail || "Failed to create template"}`, "error");
      }
    });
  } else {
    banner.style.display = "none";
  }
}

// ── Template selector (load from DB by exp_tmpl_id) ───────────────────────
async function loadTemplates() {
  const res = await fetch("/api/templates");
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    flash(`ERROR: Failed to load template list — ${err.detail}`, "error");
    return;
  }
  const data = await res.json();
  const sel  = document.getElementById("template-select");
  sel.innerHTML = '<option value="" disabled selected>Load template…</option>';
  for (const t of data.templates) {
    const opt   = document.createElement("option");
    opt.value   = t.id;
    opt.textContent = t.name || (t.id.slice(0, 8) + "…");
    sel.appendChild(opt);
  }
}

async function onTemplateChange(e) {
  const exp_tmpl_id = e.target.value;
  if (!exp_tmpl_id) return;
  const res = await fetch("/api/template/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ exp_tmpl_id }),
  });
  const data = await res.json();
  if (!res.ok) { flash(`ERROR: ${data.detail || "Load failed"}`, "error"); return; }

  const name = data.name || (exp_tmpl_id.slice(0, 8) + "…");
  setLocked(false);

  await loadContext();
  await loadTemplate();
  await loadVariables();
  flash(`Loaded: ${name} (${data.components} components)`);
}

// ── Export PDF ────────────────────────────────────────────────────────────
async function exportPDF() {
  const res = await fetch("/api/render/pdf", { method: "POST" });
  const data = await res.json();
  if (!res.ok) { flash(`ERROR: Export failed — ${data.detail}`, "error"); return; }
  flash(`PDF saved — ${(data.size / 1024).toFixed(1)} KB → ${data.path}`);
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
