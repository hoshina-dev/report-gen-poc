"""
Core Template Engine — parses a template dict and renders to PDF or HTML.

Template dict shape:
{
    "template": "{{field}} ...",
    "components": [
        {"id": "...", "type": "text", "content": "...", "rect": [...], "style": {...}},
        ...
    ]
}
"""

from io import BytesIO
from typing import Any, Literal

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as rl_canvas

from .components import Component, PageBreakComponent, component_from_dict
from .parser import extract_fields, interpolate_template


class TemplateEngine:
    def __init__(self, template_dict: dict[str, Any]) -> None:
        self.template_text: str = template_dict.get("template", "")
        self.components: list[Component] = []
        for comp_data in template_dict.get("components", []):
            try:
                self.components.append(component_from_dict(comp_data))
            except Exception as exc:
                print(f"[TemplateEngine] skipping component {comp_data.get('id')!r}: {exc}")
        self.fields: set[str] = self._extract_all_fields()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(
        self,
        format: Literal["pdf", "html"] = "pdf",
        context: dict[str, Any] | None = None,
        *,
        strict: bool = False,
    ) -> Any:
        if context is None:
            context = {}
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
        if self.template_text:
            ctx["template"] = interpolate_template(self.template_text, context)
        return ctx

    def _extract_all_fields(self) -> set[str]:
        fields: set[str] = set(extract_fields(self.template_text))
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

        # Fallback: no components — render template text as body
        if not self.components and self.template_text:
            resolved = interpolate_template(self.template_text, context)
            c.setFont("Helvetica", 12)
            self._draw_wrapped(c, resolved, x=50, y=730, max_w=512,
                               font="Helvetica", size=12, line_h=18)
            c.setFont("Helvetica", 10)
            footer = "Page 1 of 1"
            c.drawString((page_width - c.stringWidth(footer, "Helvetica", 10)) / 2, 30, footer)
            c.save()
            return buf.getvalue()

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

    @staticmethod
    def _draw_wrapped(c, text: str, x: float, y: float,
                      max_w: float, font: str, size: int, line_h: float) -> float:
        """Word-wrap fallback for template-text-only renders."""
        words = text.split()
        line  = ""
        for word in words:
            candidate = line + word + " "
            if c.stringWidth(candidate, font, size) > max_w and line:
                c.drawString(x, y, line.rstrip())
                y   -= line_h
                line = word + " "
            else:
                line = candidate
        if line.rstrip():
            c.drawString(x, y, line.rstrip())
            y -= line_h
        return y

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

        # Fallback: no components — render template text as body
        if not self.components and self.template_text:
            resolved = (
                interpolate_template(self.template_text, context)
                .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            parts.append(
                f'<div style="position:absolute;left:50px;top:42px;'
                f'width:512px;height:700px;font-size:12px;white-space:pre-wrap;">'
                f'{resolved}</div>'
            )
            parts.append(f'<div style="{footer_style}">Page 1 of 1</div>')
            parts.append("</div></body></html>")
            return "\n".join(parts)

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
