# AGENTS.md

Guidelines for AI agents working in this repo.

## Running the project

```bash
uv run python -m src              # generate PDF (CLI)
uv run python -m src --editor     # start visual editor at http://localhost:8765
PYTHONPATH=. uv run python tests/test_engine.py  # run tests (or: make test)
```

Always use `uv run` — the venv is managed by uv, not the system Python.

## Key files

| File | Purpose |
|------|---------|
| `src/engine/template_engine.py` | Stateless engine — parse, validate, build_context. Zero rendering deps. |
| `src/engine/components.py` | Component dataclasses (Text, Shape, PageBreak) — pure data, no rendering |
| `src/engine/context.py` | `flatten_context()` / `group_variables()` — converts experiment JSON to `{{field}}` dict |
| `src/engine/parser.py` | `{{field}}` interpolation and extraction |
| `src/output.py` | PDF rendering (`render_pdf`) + CLI entry (`generate_pdf`, `generate_pdf_to_file`) |
| `src/config.py` | `Config` (CLI) and `EditorConfig` (editor); reads `.env` |
| `src/__main__.py` | Entry point — `python -m src` for CLI, `--editor` flag for dev server |
| `src/editor/server.py` | FastAPI dev server; imports `render_pdf` from `output.py` |
| `mock/data/` | Sample experiment JSON payloads (have `exp_tmpl_id`) |
| `mock/pdf/` | Sample component arrays for PDF templates |

## Architecture: engine is standalone

`src/engine/` has **zero** rendering dependencies. Deleting `src/editor/` leaves a fully
functional CLI PDF generator. The dependency chain is:

```
src/engine/   ← pure: parse / validate / build_context
src/output.py ← PDF rendering (reportlab); imported by CLI and editor
src/editor/   ← dev tool only; imports render_pdf from output.py
```

- `TemplateEngine(components)` — parse component dicts, extract `{{fields}}`, pre-process context
- `render_pdf(components, context)` — ReportLab drawing loop; lives in `output.py`
- `generate_pdf(data, components)` — flattens experiment JSON, runs engine + render; CLI entry point

## Coordinate system

ReportLab origin is **bottom-left** (y=0 at page bottom). Letter page height = 792pt.

## Rendering pipeline

1. `output.generate_pdf(data, components)` flattens context via `flatten_context(data)`
2. `TemplateEngine(components)` parses component list — raises immediately on bad component
3. `engine.build_context(context)` pre-processes `{{template}}` self-reference — expands any `{{fields}}` nested inside the `template` value
4. `render_pdf(engine.components, ctx)` draws all components; `PageBreakComponent` triggers `showPage()`

**Critical**: `_switch_template` in `server.py` must call `build_context` (not just `flatten_context`) so that `_context["template"]` is fully expanded before the editor canvas renders it. Skipping this step causes `{{template}}` to appear un-interpolated in the canvas while the PDF export works fine.

## Context flattening rules

- `userForm` / `workerForm` questions → keyed by question `id`, value = `default` or `[Label]`
- `calculations` keys → exposed directly (no prefix)
- Top-level scalars → included directly
- Other nested dicts → `parent_key` notation

## DATA_JSON validation rules (editor)

`DATA_JSON` in `.env` must be a path to a JSON **object** (not an array) with a valid
`exp_tmpl_id` string field. Component array files (`mock/pdf/`) are **not** valid as DATA_JSON.
If invalid, the server raises a clear `RuntimeError` at startup — not a generic AttributeError.

## Template switching (`_switch_template`)

`_switch_template(exp_tmpl_id, exp_data=None)` is the single function for both:
- **File preload** (`DATA_JSON` set): pass `exp_data=data` to skip the DB lookup
- **Manual select** (dropdown): omit `exp_data`; queries `experiment_templates` by id

Never INSERT/DELETE from `experiment_templates` — that table is owned by the external
experiment manager service.

## No fallbacks — fail loudly

**Never add silent fallbacks. Always raise an error or flash a visible message.**

- **Engine init**: Malformed component dicts raise immediately from `component_from_dict` — no skipping
- **Engine render**: `render_pdf()` raises `ValueError` if called with no components
- **Colors**: Invalid hex colors raise from `HexColor()` — no silent fallback to black
- **Server `_load()`**: Raises `RuntimeError` if `DATA_JSON` is invalid (wrong type, missing `exp_tmpl_id`)
- **Server save**: `_save_layout()` raises if the DB `UPDATE` matches 0 rows
- **JS fetch calls**: Every `fetch()` checks `res.ok`; on failure call `flash("ERROR: ...", "error")` — no silent ignores

## Editor UI architecture (`src/editor/static/`)

### Page model
Components are stored as a **flat positional array** with `pagebreak` sentinels as delimiters. Page membership is implicit (position-dependent), not stored on each component. Always use `splitIntoPages(components)` or `getPageRange(pageIdx)` to work with pages — never assume a `page` field on a component.

### Active page tracking
`activePage` (integer, 0-indexed) is editor state in `editor.js`. It is updated:
- **On scroll**: most-visible-page algorithm using `offsetTop` in a `scroll` listener
- **On component click**: `selectComponent(id)` scans `splitIntoPages` to find which page the component belongs to
- Do **not** set `activePage` from page-background clicks — too confusing

Visual feedback: `updateActivePageVisuals()` is a lightweight DOM update (outline + label color only) without a full re-render. Call it instead of `render()` when only the active indicator needs to change.

### Scroll preservation
`render(resetScroll = false)` and `renderCanvas(resetScroll = false)` save and restore `canvasContainer.scrollTop`. Only pass `true` from `loadTemplate()`. All interactive re-renders (select, drag, inspector field change) omit the flag so scroll position is preserved.

### Insert at active page
`+ Text`, `+ Shape`, and `+ Page` buttons use `getPageRange(activePage)` to find the insertion point in the flat array. New components are inserted at `range.end` (just before the pagebreak or at the end of the array for the last page).

### Page reorder / delete helpers
- `swapPages(i, j)` — splits flat array into `chunks[]` + `seps[]` (pagebreak sentinels), swaps `chunks[i]` and `chunks[j]`, rebuilds
- `deletePage(idx)` — removes `chunks[idx]` and `seps[Math.min(idx, seps.length-1)]` (after page if not last, before if last); clamps `activePage`; clears `selectedId` if the selected component was on that page

### Right panel tabs
Two tabs: **Inspector** (existing property editor) and **Pages** (ordering UI). Tab switching shows/hides `#tab-inspector` / `#tab-pages`. CSS uses the flush-tab pattern: active tab gets `border-bottom: 1px solid #fff` to erase the divider and merge visually with the panel content below.

### CSS cache busting
Static CSS is versioned: `<link rel="stylesheet" href="/static/style.css?v=N">`. Bump `N` in `index.html` whenever CSS changes aren't loading. For layout-critical values that must apply immediately, set them inline via JS (`element.style.xxx`) — inline styles can't be cached.

### Active color
`#beffb6` (green) is the active-page accent color. Used for: canvas page outline (`outline: 2px solid #beffb6`), page label text, and `.page-card-active` border/background in the Pages tab. Do not replace with blue.

## What to avoid

- Don't add `border` or `padding` to `.canvas-comp` elements — use `outline`
- Don't set `activePage` from page-background click events — confusing UX
- Don't call `render()` just to update the active-page highlight — use `updateActivePageVisuals()` instead
- Don't assume components have a `page` field — page membership is positional, use `splitIntoPages()`
- Don't use blue (`#2196F3`, `#64b5f6`) for active-page indicators — use `#beffb6`
- Don't add the `calculations_` prefix to calculation keys — they're exposed directly
- Don't commit anything under `always-ignore/` — local-only scratch space
- Don't add `try/except` that swallows exceptions silently — log + re-raise or raise `HTTPException`
- Don't use `data.get("key", default)` for required fields — use `data["key"]` and let `KeyError` surface
- Don't add rendering code to `src/engine/` — rendering belongs in `output.py` or `editor/`

## Tests

`tests/test_engine.py` covers: Rect, field extraction, template interpolation, PDF byte output,
no-components error, and shape component rendering.

Import style: `from src.engine import ...` and `from src.output import render_pdf`.
Run with `PYTHONPATH=.` (set in Makefile `make test`).
