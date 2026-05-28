# PDF Report Generator — Architecture

## Overview

A centralized template engine that parses a JSON payload into a PDF (or HTML
preview). The editor UI is a thin, optional layer on top of the same engine.

```
JSON payload
     │
     ▼
┌─────────────────────────────────────┐
│           TemplateEngine            │  engine/template_engine.py
│                                     │
│  ┌──────────────┐  ┌─────────────┐  │
│  │ components[] │  │  template   │  │  layout  (what to draw, where)
│  └──────────────┘  └─────────────┘  │
│                                     │
│  render(format, context)            │
└──────────┬──────────────────────────┘
           │
     ┌─────┴──────┐
     ▼            ▼
  PDF bytes    HTML string
  (ReportLab)  (editor preview)
```

## Dependency Graph

```
engine/          ← pure core, no external deps beyond ReportLab
  ├── template_engine.py   TemplateEngine class
  ├── components.py        Rect, TextComponent, ShapeComponent, PageBreakComponent
  ├── parser.py            {{field}} interpolation + extraction
  ├── context.py           flatten_context() — JSON → flat str dict
  └── __init__.py          public exports

output.py        ← production call-site; imports engine only
__main__.py      ← CLI entry point; conditionally imports editor/

editor/          ← dev-only, fully optional — safe to delete
  ├── cli.py               uvicorn launcher (port 8765)
  ├── server.py            FastAPI endpoints
  └── static/              HTML / JS / CSS
```

`editor/` is **never imported** unless `--editor` is passed.

## Data Flow

### Production
```
JSON_INPUT (env)
  └─► output.generate_pdf(data)
        ├─► flatten_context(data)        → context dict
        ├─► TemplateEngine(layout)       → parse components
        └─► engine.render("pdf", ctx)    → bytes → output.pdf
```

### Editor (dev)
```
data/1.json  (hardcoded path)
  ├─► layout  = {template, components}   ← editable via UI
  └─► context = flatten_context(rest)    ← read-only in UI

Save    → writes ONLY template + components back to 1.json
Preview → engine.render("html", context)
```

## Template JSON Shape

```json
{
  "template": "{{full_name}} from {{country}}, plan: {{plan}}",
  "components": [
    {
      "id": "title",
      "type": "text",
      "content": "Report",
      "rect": [50, 750, 500, 30],
      "style": { "font": "Helvetica-Bold", "size": 24, "align": "left" }
    },
    {
      "id": "body",
      "type": "text",
      "content": "{{template}}",
      "rect": [50, 650, 512, 80],
      "style": { "font": "Helvetica", "size": 12 }
    }
  ],

  "userForm":   { "questions": [{"id": "full_name", "label": "Full name", "default": "Alice"}] },
  "workerForm": { "questions": [...] },
  "calculations": { "delta_T": 4.2 }
}
```

`template` + `components` define **layout**. Everything else is **data**
fed into `{{field}}` placeholders via `flatten_context()`.

### flatten_context rules

| Source | Keys produced |
|--------|---------------|
| Top-level scalars | key directly (e.g. `plan`) |
| `userForm` / `workerForm` questions | question `id`; value = `default` or `[Label]` |
| `calculations` dict | key directly (e.g. `delta_T`) |
| Other nested dicts | `parent_key` notation (e.g. `meta_version`) |

## Component Types

| type        | key fields                              | notes                 |
|-------------|-----------------------------------------|-----------------------|
| `text`      | `content`, `rect`, `style`              | supports `{{fields}}` |
| `shape`     | `shape_type`, `rect`, `color`, `fill`   | rect / line / circle  |
| `pagebreak` | *(none)*                                | inserts a new page    |

### Rect format
`[x, y, width, height]` in points (1/72 inch).
ReportLab origin is **bottom-left**. HTML preview flips y automatically.

| Page   | Size (pts) |
|--------|------------|
| Letter | 612 × 792  |
| A4     | 595 × 842  |

## Editor API (FastAPI)

| Method | Path                  | Purpose                                  |
|--------|-----------------------|------------------------------------------|
| GET    | `/api/template`       | Fetch current layout                     |
| POST   | `/api/template`       | Save layout (template + components only) |
| POST   | `/api/component/move` | Drag-drop position update                |
| GET    | `/api/context`        | Flattened context from 1.json            |
| GET    | `/api/variables`      | Variables grouped by source (dropdown)   |
| POST   | `/api/render/pdf`     | Render PDF (returns byte size)           |
| POST   | `/api/fields/extract` | List all `{{fields}}` in current layout  |
| POST   | `/api/reload`         | Re-read 1.json from disk                 |

## Running

```bash
# Production (PDF from env var)
JSON_INPUT='{"template":"{{name}}","components":[...],"name":"Alice"}' uv run python -m src

# Dev fallback (uses data/1.json when JSON_INPUT is not set)
uv run python -m src

# Template editor
uv run python -m src --editor
# → http://localhost:8765
```
