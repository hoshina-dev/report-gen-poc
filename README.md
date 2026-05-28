# PDF Report Generator

Python service that renders a JSON payload into a PDF report using a visual
template editor and a ReportLab-based engine.

## Quick Start

```bash
# Install dependencies
uv sync

# Run with fallback data (data/1.json)
uv run python -m src

# Run with real input
JSON_INPUT='{"template":"{{name}}","components":[...],"name":"Alice"}' uv run python -m src

# Open the visual template editor
uv run python -m src --editor
# → http://localhost:8765
```

## Input

The service reads from the `JSON_INPUT` environment variable (a JSON string).
When the variable is absent it falls back to `data/1.json` for local dev.

The JSON shape:

```json
{
  "template": "{{full_name}} — {{plan}}",
  "components": [ ... ],

  "userForm": { "questions": [{"id": "full_name", "label": "Full name", "default": "Alice"}] },
  "workerForm": { "questions": [...] },
  "calculations": { "delta_T": 4.2 }
}
```

`template` + `components` define the layout. Everything else is the data
context for `{{field}}` interpolation.

## Output

A PDF file written to `output.pdf` in the working directory. In production the
bytes would be uploaded to S3 (not yet wired).

## Project Layout

```
src/
  engine/           pure rendering core (ReportLab + HTML)
  editor/           dev-only visual editor (FastAPI + JS)
  output.py         production call-site
  __main__.py       CLI entry point

data/               sample JSON payloads for local dev
always-ignore/      local scratch files, never committed
```

`editor/` is fully optional — deleting it does not affect PDF generation.
