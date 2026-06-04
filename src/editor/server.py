"""
FastAPI editor server — dev-only, not included in the Docker/Argo image.

On load  : reads DATA_JSON, extracts exp_tmpl_id, fetches components from pdf_templates in DB.
On save  : writes components back to pdf_templates in DB.
"""

import json
import logging
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import EditorConfig
from ..engine import TemplateEngine
from ..engine.context import flatten_context, group_variables
from ..output import generate_pdf as _generate_pdf

logger = logging.getLogger(__name__)

app = FastAPI(title="PDF Template Editor", version="0.1.0")

# ── In-memory state ────────────────────────────────────────────────────────
_layout: dict[str, Any] = {"components": []}
_context: dict[str, str] = {}
_raw_data: dict[str, Any] = {}
_exp_tmpl_id: str = ""
_template_exists: bool = False
_data_preloaded: bool = False
_data_name: str = ""


# ── Postgres helper ────────────────────────────────────────────────────────


def _pg_conn():
    return psycopg2.connect(EditorConfig.from_env().data_source_name)


# ── Startup: load DATA_JSON + check DB ────────────────────────────────────


def _switch_template(exp_tmpl_id: str, exp_data: dict[str, Any] | None = None) -> None:
    """
    Switch the active template by exp_tmpl_id. Updates all in-memory state.

    exp_data: if provided (e.g. loaded from DATA_JSON file), use it as the experiment
              context instead of querying experiment_templates. Allows file-based data
              to take precedence over the DB copy.
    """
    global _layout, _context, _raw_data, _exp_tmpl_id, _template_exists, _data_preloaded, _data_name

    with (
        _pg_conn() as conn,
        conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur,
    ):
        if exp_data is None:
            # Dev: scan mock/data/*.json for a file whose exp_tmpl_id matches —
            # gives the editor real field values for canvas preview and PDF export.
            mock_dir = Path(__file__).parent.parent.parent / "mock" / "data"
            if mock_dir.exists():
                for mock_file in sorted(mock_dir.glob("*.json")):
                    try:
                        candidate = json.loads(mock_file.read_text())
                        if (
                            isinstance(candidate, dict)
                            and candidate.get("exp_tmpl_id") == exp_tmpl_id
                        ):
                            exp_data = candidate
                            logger.info("Auto-loaded mock data from %s", mock_file.name)
                            break
                    except (json.JSONDecodeError, OSError):
                        pass

            if exp_data is None:
                cur.execute(
                    "SELECT * FROM experiment_templates WHERE id = %s",
                    (exp_tmpl_id,),
                )
                exp_row = cur.fetchone()
                if exp_row is None:
                    raise RuntimeError(
                        f"No experiment_templates row found for id={exp_tmpl_id!r}. "
                        "The experiment must exist before its PDF template can be edited."
                    )
                data: dict[str, Any] = dict(exp_row)
            else:
                data = exp_data
        else:
            data = exp_data

        cur.execute(
            "SELECT components FROM pdf_templates WHERE exp_tmpl_id = %s",
            (exp_tmpl_id,),
        )
        pdf_row = cur.fetchone()

    _raw_data = data
    flat = flatten_context(data)
    _context = TemplateEngine([]).build_context(flat)
    _exp_tmpl_id = exp_tmpl_id
    _data_name = data.get("name", exp_tmpl_id[:8] + "…")
    _data_preloaded = True

    if pdf_row:
        _template_exists = True
        _layout = {"components": pdf_row["components"]}
        logger.info(
            "Switched to template %s (%d components)",
            exp_tmpl_id,
            len(_layout["components"]),
        )
    else:
        _template_exists = False
        _layout = {"components": []}
        logger.info("Switched to template %s — no PDF template in DB yet", exp_tmpl_id)


def _load() -> None:
    """Initialise state from DATA_JSON env var (if set), otherwise start blank."""
    global _layout, _context, _raw_data, _exp_tmpl_id, _template_exists, _data_preloaded, _data_name

    cfg = EditorConfig.from_env()
    if not cfg.data_json:
        _data_preloaded = False
        _data_name = ""
        _exp_tmpl_id = ""
        _layout = {"components": []}
        _context = {}
        _raw_data = {}
        _template_exists = False
        logger.info("No DATA_JSON set — editor started in template-select mode")
        return

    json_path = Path(cfg.data_json)
    if not json_path.exists():
        raise RuntimeError(f"DATA_JSON not found at {json_path}")

    with json_path.open() as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"DATA_JSON at {json_path} is not valid JSON: {exc}"
            ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            f"DATA_JSON at {json_path} must be a JSON object {{...}}, "
            f"got {type(data).__name__}. "
            "Component array files (mock/pdf/) cannot be used as DATA_JSON — "
            "only experiment data files (mock/data/) are valid."
        )

    exp_tmpl_id = data.get("exp_tmpl_id", "")
    if not exp_tmpl_id or not isinstance(exp_tmpl_id, str):
        raise RuntimeError(
            f"DATA_JSON at {json_path} is missing a valid 'exp_tmpl_id' string field. "
            "Every experiment data file must declare which PDF template it belongs to."
        )

    _switch_template(exp_tmpl_id, exp_data=data)


def _save_layout(components: list) -> None:
    """Persist components to pdf_templates in DB."""
    if not _exp_tmpl_id:
        raise RuntimeError("Cannot save: no exp_tmpl_id loaded")
    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE pdf_templates SET components = %s::jsonb, updated_at = NOW() WHERE exp_tmpl_id = %s",
            (json.dumps(components), _exp_tmpl_id),
        )
        if cur.rowcount == 0:
            raise RuntimeError(
                f"UPDATE matched 0 rows for exp_tmpl_id={_exp_tmpl_id!r}. "
                "Template row does not exist — create it first via POST /api/template/create."
            )
    logger.info("Saved %d components to DB for %s", len(components), _exp_tmpl_id)


_load()


# ── Pydantic models ────────────────────────────────────────────────────────


class TemplateRequest(BaseModel):
    components: list[dict] = []


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
    """Return the current layout (components list)."""
    return _layout


@app.post("/api/template")
async def save_template(req: TemplateRequest):
    """Persist components to the pdf_templates DB row."""
    global _layout
    _layout = {"components": req.components}
    try:
        _save_layout(req.components)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except psycopg2.OperationalError as exc:
        raise HTTPException(status_code=503, detail=f"Postgres not reachable: {exc}")
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
    """Return the flattened data context derived from DATA_JSON."""
    return {"status": "ok", "context": _context}


@app.post("/api/render/pdf")
async def render_pdf():
    """Render current layout to PDF, save to PDF_OUTPUT path."""
    if not _layout["components"]:
        raise HTTPException(
            status_code=400,
            detail="No components in template — add components before exporting.",
        )
    try:
        pdf_bytes = _generate_pdf(_raw_data, _layout["components"])

        cfg = EditorConfig.from_env()
        out = Path(cfg.pdf_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(pdf_bytes)
        logger.info("PDF saved to %s", out)

        # return Response(
        #     content=pdf_bytes,
        #     media_type="application/pdf",
        #     headers={"Content-Disposition": "attachment; filename=output.pdf"},
        # )
        return {"status": "ok", "path": str(out), "size": len(pdf_bytes)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("PDF render failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/fields/extract")
async def extract_fields():
    """Return all {{fields}} found in the current layout."""
    engine = TemplateEngine(_layout["components"])
    return {"status": "ok", "fields": sorted(engine.fields)}


@app.get("/api/variables")
async def get_variables():
    """Return available {{fields}} grouped by source (userForm, workerForm, calculations)."""
    return {"status": "ok", "groups": group_variables(_raw_data)}


@app.post("/api/reload")
async def reload_json():
    """Re-read DATA_JSON and re-check DB."""
    try:
        _load()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except psycopg2.OperationalError as exc:
        raise HTTPException(status_code=503, detail=f"Postgres not reachable: {exc}")
    return {
        "status": "ok",
        "template_exists": _template_exists,
        "context_fields": sorted(_context.keys()),
    }


@app.get("/api/status")
async def get_status():
    """Return editor readiness state."""
    return {
        "template_exists": _template_exists,
        "exp_tmpl_id": _exp_tmpl_id,
        "components": len(_layout.get("components", [])),
        "data_preloaded": _data_preloaded,
        "data_name": _data_name,
    }


@app.post("/api/template/create")
async def create_template():
    """Insert an empty pdf_template row for the current exp_tmpl_id."""
    global _template_exists, _layout
    if not _exp_tmpl_id:
        raise HTTPException(status_code=400, detail="No exp_tmpl_id loaded")
    try:
        with _pg_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pdf_templates (exp_tmpl_id, components) VALUES (%s, %s::jsonb) ON CONFLICT DO NOTHING",
                (_exp_tmpl_id, "[]"),
            )
        _template_exists = True
        _layout = {"components": []}
        logger.info("Created empty pdf_template for %s", _exp_tmpl_id)
        return {"status": "ok", "exp_tmpl_id": _exp_tmpl_id}
    except psycopg2.OperationalError as exc:
        raise HTTPException(status_code=503, detail=f"Postgres not reachable: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Postgres template endpoints ────────────────────────────────────────────


@app.get("/api/templates")
async def list_templates():
    """List all pdf_templates from Postgres."""
    try:
        with (
            _pg_conn() as conn,
            conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur,
        ):
            cur.execute("""
                SELECT p.exp_tmpl_id, e.name
                FROM pdf_templates p
                JOIN experiment_templates e ON e.id = p.exp_tmpl_id
                ORDER BY p.created_at
            """)
            rows = cur.fetchall()
        templates = [
            {"id": str(row["exp_tmpl_id"]), "name": row["name"]} for row in rows
        ]
        return {"status": "ok", "templates": templates}
    except psycopg2.OperationalError as exc:
        raise HTTPException(status_code=503, detail=f"Postgres not reachable: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class LoadTemplateRequest(BaseModel):
    exp_tmpl_id: str


@app.post("/api/template/load")
async def load_template(req: LoadTemplateRequest):
    """Switch active template by exp_tmpl_id — loads context + components from DB."""
    try:
        _switch_template(req.exp_tmpl_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except psycopg2.OperationalError as exc:
        raise HTTPException(status_code=503, detail=f"Postgres not reachable: {exc}")
    return {
        "status": "ok",
        "exp_tmpl_id": req.exp_tmpl_id,
        "components": len(_layout["components"]),
        "name": _data_name,
    }


# ── Static files ───────────────────────────────────────────────────────────

_static = Path(__file__).parent / "static"
if _static.exists():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")
