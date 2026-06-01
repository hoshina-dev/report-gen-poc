# AGENTS.md

Guidelines for AI agents working in this repo.

## Running the project

```bash
uv run python -m src              # generate PDF
uv run python -m src --editor     # start visual editor at http://localhost:8765
uv run python tests/test_engine.py  # run tests
```

Always use `uv run` — the venv is managed by uv, not the system Python.

## Key files

| File | Purpose |
|------|---------|
| `src/engine/template_engine.py` | Core renderer — PDF and HTML output |
| `src/engine/components.py` | Component dataclasses (Text, Shape, PageBreak) |
| `src/engine/context.py` | `flatten_context()` — converts JSON payload to `{{field}}` dict |
| `src/engine/parser.py` | `{{field}}` interpolation and extraction |
| `src/output.py` | Production entry point — splits layout from context, calls engine |
| `src/editor/server.py` | FastAPI dev server; data path from `DATA_JSON` env var |
| `data/1.json` | Local sample payload for dev and editor |

## Coordinate system

ReportLab origin is **bottom-left** (y=0 at page bottom).
The HTML preview flips y: `css_top = 792 - rect_y - rect_height`.
Always keep these in sync when touching rendering code.

## Rendering pipeline

1. `output.generate_pdf(data)` splits `data` into components and context (via `flatten_context`)
2. `TemplateEngine(components)` parses the component list — raises immediately on any bad component
3. `engine.render("pdf"|"html", context)` interpolates `{{fields}}` and draws

## Context flattening rules

- `userForm` / `workerForm` questions → keyed by `id`, value = `default` or `[Label]`
- `calculations` keys → exposed directly (no prefix)
- Other nested dicts → `parent_key` notation
- Top-level scalars → included directly
- `components` key is excluded (layout, not data)

## No fallbacks — fail loudly

**Never add silent fallbacks. Always raise an error or flash a visible message.**

- **Engine**: `TemplateEngine.render()` raises `ValueError` if called with no components. There is no "render template text directly" mode. Components are required.
- **Engine init**: If a component dict is malformed (missing `id`, missing `rect`, unknown `type`), `component_from_dict` raises immediately — no skipping, no defaulting to a partial object.
- **Colors**: Invalid hex colors raise from `HexColor()` directly — no silent fallback to black.
- **Server `_load()`**: Raises `RuntimeError` if `DATA_JSON` is missing or has no `exp_tmpl_id`. The server must not start in a broken state.
- **Server save**: `_save_layout()` raises if the DB `UPDATE` matches 0 rows — the template row must exist before saving.
- **JS fetch calls**: Every `fetch()` checks `res.ok`. On failure, call `flash("ERROR: ...", "error")` with the server's `detail` message. No `catch (_) {}`, no `console.error`-only handlers, no silent ignores.
- **JS canvas**: Empty components list renders an empty canvas — no ghost text, no fallback render.
- **JS inspector**: Component fields are read directly without `|| default` guards — components always carry all required fields when created by `addTextComponent` / `addShapeComponent`.

The rule: **if something is wrong, the user must see it immediately.** A silent fallback hides bugs.

## What to avoid

- Don't add `border` or `padding` to `.canvas-comp` elements in the editor — use `outline` so it draws outside the box and never shifts component positions
- Don't add the `calculations_` prefix to calculation keys — they're exposed directly
- Don't commit anything under `always-ignore/` — that directory is local-only scratch space
- `editor/` is optional and never imported in the production path; keep it that way
- Don't add `try/except` that swallows exceptions silently — log + re-raise or raise `HTTPException` with a clear `detail`
- Don't use `data.get("key", default)` for required fields — use `data["key"]` and let `KeyError` surface

## Tests

`tests/test_engine.py` covers component parsing, field extraction, HTML rendering, and PDF byte output.
Run it before pushing engine changes.
