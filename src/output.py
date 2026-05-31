"""
Output handler for the PDF Report Generator.

In production the job receives a JSON payload (from Argo / environment) that
contains both the template layout and the data context.  This module is the
single call-site: it hands everything to the TemplateEngine and returns bytes.

Expected JSON shape (example):
{
    "template": "{{full_name}} ({{country}}, plan: {{plan}})",
    "components": [
        {
            "id": "title",
            "type": "text",
            "content": "Report",
            "rect": [50, 750, 500, 30],
            "style": {"font": "Helvetica-Bold", "size": 24}
        },
        {
            "id": "body",
            "type": "text",
            "content": "{{template}}",
            "rect": [50, 650, 512, 80],
            "style": {"font": "Helvetica", "size": 12}
        }
    ],
    ... (all other keys become the data context for {{field}} interpolation)
}

The engine separates "template" + "components" (layout) from everything else
(data).  Missing {{fields}} are left as-is unless strict=True.
"""

from pathlib import Path

from .engine import TemplateEngine
from .engine.context import flatten_context


def generate_pdf(data: dict) -> bytes:
    """
    Generate a PDF from a full job payload dict.

    Args:
        data: The full JSON payload.  Must contain at least a ``components``
              list (or a ``template`` string).  All other fields become the
              rendering context.

    Returns:
        Raw PDF bytes.
    """
    # Split layout definition from data context
    layout = {
        "template": data.get("template", ""),
        "components": data.get("components", []),
    }
    context = flatten_context(data)

    engine = TemplateEngine(layout)
    return engine.render("pdf", context)


def generate_pdf_to_file(data: dict, path: str) -> str:
    """Render PDF and write it to *path*, creating parent directories as needed."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = generate_pdf(data)
    with open(path, "wb") as f:
        f.write(pdf_bytes)
    print(f"PDF saved to {path}")
    return path
