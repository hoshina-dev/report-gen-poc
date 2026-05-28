# AGENTS.md

Guidelines for AI agents working in this repo.

## Running the project

```bash
uv run python -m src              # generate PDF (falls back to data/1.json)
uv run python -m src --editor     # start visual editor at http://localhost:8765
uv run python test_engine.py      # run tests
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
| `src/editor/server.py` | FastAPI dev server; data path = `data/1.json` |
| `data/1.json` | Local sample payload for dev and editor |

## Coordinate system

ReportLab origin is **bottom-left** (y=0 at page bottom).
The HTML preview flips y: `css_top = 792 - rect_y - rect_height`.
Always keep these in sync when touching rendering code.

## Rendering pipeline

1. `output.generate_pdf(data)` splits `data` into layout (`template` + `components`) and context (everything else via `flatten_context`)
2. `TemplateEngine(layout)` parses the component list
3. `engine.render("pdf"|"html", context)` interpolates `{{fields}}` and draws

## Context flattening rules

- `userForm` / `workerForm` questions → keyed by `id`, value = `default` or `[Label]`
- `calculations` keys → exposed directly (no prefix)
- Other nested dicts → `parent_key` notation
- Top-level scalars → included directly

## What to avoid

- Don't add `border` or `padding` to `.canvas-comp` elements in the editor — use `outline` so it draws outside the box and never shifts component positions
- Don't add the `calculations_` prefix to calculation keys — they're exposed directly
- Don't commit anything under `always-ignore/` — that directory is local-only scratch space
- `editor/` is optional and never imported in the production path; keep it that way

## Tests

`test_engine.py` at the repo root covers component parsing, field extraction,
HTML rendering, and PDF byte output. Run it before pushing engine changes.
