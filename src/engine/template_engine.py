"""
Core Template Engine — stateless renderer.

Takes a list of component dicts and a context dict; renders to PDF or HTML.
The context must include a "template" key if any component references {{template}}.
"""

from io import BytesIO
from typing import Any, Literal

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as rl_canvas

from .components import Component, PageBreakComponent, component_from_dict
from .parser import interpolate_template


class TemplateEngine:
    def __init__(self, components: list[dict[str, Any]]) -> None:
        self.components: list[Component] = []
        for comp_data in components:
            self.components.append(component_from_dict(comp_data))
        self.fields: set[str] = self._extract_all_fields()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(
        self,
        format: Literal["pdf", "html"],
        context: dict[str, Any],
        *,
        strict: bool = False,
    ) -> Any:
        if not self.components:
            raise ValueError(
                "TemplateEngine.render() called with no components. "
                "Add at least one component before rendering."
            )
        if strict:
            errors = self.validate(context)
            if errors:
                raise ValueError(f"Template validation errors: {errors}")
        if format == "pdf":
            return self._render_pdf(context)
        return self._render_html(context)

    def validate(self, context: dict[str, Any]) -> dict[str, str]:
        """Return missing-field errors. Empty dict means valid."""
        return {f: f"Missing required field: {f}" for f in self.fields - set(context.keys())}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_context(self, context: dict[str, Any]) -> dict[str, Any]:
        ctx = dict(context)
        raw_template = ctx.get("template", "")
        if raw_template:
            ctx["template"] = interpolate_template(raw_template, ctx)
        return ctx

    def _extract_all_fields(self) -> set[str]:
        fields: set[str] = set()
        for comp in self.components:
            fields.update(comp.template_fields)
        return fields

    def _count_pages(self) -> int:
        return sum(1 for c in self.components if isinstance(c, PageBreakComponent)) + 1

    # ------------------------------------------------------------------
    # PDF renderer
    # ------------------------------------------------------------------

    def _render_pdf(self, context: dict[str, Any]) -> bytes:
        context = self._build_context(context)
        buf = BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=letter)
        page_width, _ = letter
        c.setTitle("PDF Report")

        total_pages  = self._count_pages()
        current_page = 1

        def draw_page_number():
            label   = f"Page {current_page} of {total_pages}"
            label_w = c.stringWidth(label, "Helvetica", 10)
            c.setFont("Helvetica", 10)
            c.drawString((page_width - label_w) / 2, 30, label)

        for comp in self.components:
            if isinstance(comp, PageBreakComponent):
                draw_page_number()
                c.showPage()
                current_page += 1
                continue
            comp.render_pdf(c, context)

        draw_page_number()
        c.save()
        return buf.getvalue()

    # ------------------------------------------------------------------
    # HTML renderer (editor preview)
    # ------------------------------------------------------------------

    def _render_html(self, context: dict[str, Any]) -> str:
        context = self._build_context(context)

        page_style = (
            "width:612px;height:792px;position:relative;overflow:hidden;"
            "background:white;margin:20px auto;box-shadow:0 2px 8px rgba(0,0,0,0.4);"
        )
        footer_style = (
            "position:absolute;bottom:4px;width:100%;text-align:center;"
            "font-size:10px;color:#999;"
        )
        parts = [
            "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>",
            "<style>",
            "  body{margin:0;background:#888;font-family:Helvetica,Arial,sans-serif;}",
            "  .comp{position:absolute;overflow:hidden;box-sizing:border-box;white-space:pre-wrap;}",
            "</style></head><body>",
            f'<div style="{page_style}">',
        ]

        page_num = 1
        for comp in self.components:
            if isinstance(comp, PageBreakComponent):
                parts.append(f'<div style="{footer_style}">Page {page_num}</div>')
                parts.append("</div>")
                parts.append(f'<div style="{page_style}">')
                page_num += 1
                continue
            parts.append(comp.render_html(context))

        parts.append(f'<div style="{footer_style}">Page {page_num}</div>')
        parts.append("</div></body></html>")
        return "\n".join(parts)
