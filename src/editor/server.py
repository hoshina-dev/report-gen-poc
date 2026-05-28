"""
FastAPI editor server — dev-only, not included in the Docker/Argo image.

Data source: data/1.json (hardcoded for fast local testing)

On load  : reads the whole file.
           "template" + "components" keys → layout definition.
           Everything else              → data context for {{field}} preview.

On save  : writes ONLY "template" and "components" back to the file.
           All other fields are left untouched.
"""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import Config
from ..engine import TemplateEngine
from ..engine.context import flatten_context, group_variables

logger = logging.getLogger(__name__)

app = FastAPI(title="PDF Template Editor", version="0.1.0")

# ── File path (hardcoded for dev) ──────────────────────────────────────────
JSON_PATH = Path(__file__).parents[2] / "data" / "1.json"

# ── In-memory state ────────────────────────────────────────────────────────
# Layout: only "template" + "components"
_layout: dict[str, Any] = {"template": "", "components": []}

# Context: flattened view of everything else in 1.json
_context: dict[str, str] = {}

# Raw file data (needed for group_variables)
_raw_data: dict[str, Any] = {}


# ── Startup: load 1.json ───────────────────────────────────────────────────


def _load() -> None:
    """Load layout, context and raw data from 1.json."""
    global _layout, _context, _raw_data
    if not JSON_PATH.exists():
        logger.warning("1.json not found at %s", JSON_PATH)
        return
    try:
        with JSON_PATH.open() as f:
            data = json.load(f)

        _raw_data = data
        _layout = {
            "template": data.get("template", ""),
            "components": data.get("components", []),
        }
        _context = flatten_context(data)

        logger.info(
            "Loaded 1.json — template: %d chars, components: %d, context fields: %s",
            len(_layout["template"]),
            len(_layout["components"]),
            sorted(_context.keys()),
        )
    except Exception as exc:
        logger.error("Failed to load 1.json: %s", exc)


def _save_layout(template: str, components: list) -> None:
    """
    Persist template + components to 1.json.
    All other keys in the file are preserved as-is.
    """
    if not JSON_PATH.exists():
        logger.error("Cannot save: 1.json not found at %s", JSON_PATH)
        return
    try:
        with JSON_PATH.open() as f:
            data = json.load(f)

        data["template"] = template
        data["components"] = components

        with JSON_PATH.open("w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(
            "Saved template (%d chars, %d components) to 1.json",
            len(template),
            len(components),
        )
    except Exception as exc:
        logger.error("Failed to save 1.json: %s", exc)


_load()


# ── Pydantic models ────────────────────────────────────────────────────────


class TemplateRequest(BaseModel):
    template: str = ""
    components: list[dict] = []


class RenderRequest(BaseModel):
    context: dict[str, Any] = {}


class MoveRequest(BaseModel):
    component_id: str
    x: float
    y: float
    width: float | None = None
    height: float | None = None


# ── Routes ─────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index():
    html_file = Path(__file__).parent / "static" / "index.html"
    if html_file.exists():
        return html_file.read_text()
    return "<h1>Template Editor</h1><p>static/index.html not found.</p>"


@app.get("/api/template")
async def get_template():
    """Return the current layout (template string + components list)."""
    return _layout


@app.post("/api/template")
async def save_template(req: TemplateRequest):
    """
    Persist layout.  Only 'template' and 'components' are written to 1.json;
    all other fields in the file are untouched.
    """
    global _layout
    _layout = {"template": req.template, "components": req.components}
    _save_layout(req.template, req.components)
    return {"status": "ok", "components": len(req.components)}


@app.post("/api/component/move")
async def move_component(req: MoveRequest):
    """Update a component's position (drag-drop)."""
    for comp in _layout.get("components", []):
        if comp.get("id") == req.component_id:
            rect = comp.get("rect", [0, 0, 100, 20])
            comp["rect"] = [
                req.x,
                req.y,
                req.width if req.width is not None else rect[2],
                req.height if req.height is not None else rect[3],
            ]
            return {"status": "ok", "rect": comp["rect"]}
    raise HTTPException(
        status_code=404, detail=f"Component '{req.component_id}' not found"
    )


@app.get("/api/context")
async def get_context():
    """Return the flattened data context derived from 1.json."""
    return {"status": "ok", "context": _context}


@app.post("/api/render/pdf")
async def render_pdf(req: RenderRequest):
    """Render current layout to PDF, save to output_dir, and stream as download."""
    try:
        engine = TemplateEngine(_layout)
        ctx = {**_context, **(req.context or {})}
        pdf_bytes = engine.render("pdf", ctx)

        cfg = Config.from_env()
        out = Path(cfg.output_dir) / "output.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(pdf_bytes)
        logger.info("PDF saved to %s", out)

        # return Response(
        #     content=pdf_bytes,
        #     media_type="application/pdf",
        #     headers={"Content-Disposition": "attachment; filename=output.pdf"},
        # )
        return {"status": "ok", "path": str(out), "size": len(pdf_bytes)}
    except Exception as exc:
        logger.error("PDF render failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/fields/extract")
async def extract_fields():
    """Return all {{fields}} found in the current layout."""
    try:
        engine = TemplateEngine(_layout)
        return {"status": "ok", "fields": sorted(engine.fields)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/variables")
async def get_variables():
    """
    Return available {{fields}} grouped by source (userForm, workerForm, calculations).
    Used by the editor left-panel dropdown.
    """
    return {"status": "ok", "groups": group_variables(_raw_data)}


@app.post("/api/reload")
async def reload_json():
    """Re-read 1.json from disk (useful if you edited it externally)."""
    _load()
    return {"status": "ok", "context_fields": sorted(_context.keys())}


# ── Static files ───────────────────────────────────────────────────────────

_static = Path(__file__).parent / "static"
if _static.exists():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")
