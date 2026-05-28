"""
Component definitions for template engine.
Rect format: [x, y, width, height] in points (1/72 inch).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from reportlab.lib.colors import HexColor

from .parser import extract_fields, interpolate_template

_PAGE_H = 792  # letter page height in points, used for CSS y-flip


@dataclass
class Rect:
    x: float
    y: float
    width: float
    height: float

    @classmethod
    def from_list(cls, data: list[float]) -> "Rect":
        if len(data) != 4:
            raise ValueError(f"Rect requires 4 values, got {len(data)}")
        return cls(x=data[0], y=data[1], width=data[2], height=data[3])


@dataclass
class TextStyle:
    font: str = "Helvetica"
    size: int = 12
    bold: bool = False
    italic: bool = False
    align: Literal["left", "center", "right"] = "left"
    color: str = "#000000"


@dataclass
class Component(ABC):
    id: str
    type: str
    rect: Rect

    @property
    def template_fields(self) -> set[str]:
        """{{field}} names used by this component. Override in text-bearing subclasses."""
        return set()

    @abstractmethod
    def render_pdf(self, c: Any, context: dict) -> None:
        """Draw onto a ReportLab canvas. context is already interpolated."""

    @abstractmethod
    def render_html(self, context: dict) -> str:
        """Return an HTML fragment string. context is already interpolated."""


@dataclass
class TextComponent(Component):
    content: str = ""
    style: TextStyle = field(default_factory=TextStyle)

    @property
    def template_fields(self) -> set[str]:
        return set(extract_fields(self.content))

    def render_pdf(self, c: Any, context: dict) -> None:
        text = interpolate_template(self.content, context)

        font = self.style.font
        if self.style.bold and self.style.italic:
            font += "-BoldOblique"
        elif self.style.bold:
            font += "-Bold"
        elif self.style.italic:
            font += "-Oblique"

        c.setFont(font, self.style.size)
        try:
            c.setFillColor(HexColor(self.style.color))
        except Exception:
            pass

        size   = self.style.size
        line_h = size * 1.2
        max_w  = self.rect.width
        align  = self.style.align
        rx     = self.rect.x
        y      = self.rect.y + self.rect.height - size

        for para in text.split("\n"):
            if not para:
                y -= line_h
                continue
            words = para.split(" ")
            line  = ""
            for word in words:
                candidate = (line + " " + word).lstrip() if line else word
                if line and c.stringWidth(candidate, font, size) > max_w:
                    lx = rx
                    if align == "center":
                        lx = rx + (max_w - c.stringWidth(line, font, size)) / 2
                    elif align == "right":
                        lx = rx + max_w - c.stringWidth(line, font, size)
                    c.drawString(lx, y, line)
                    y -= line_h
                    line = word
                else:
                    line = candidate
            if line:
                lx = rx
                if align == "center":
                    lx = rx + (max_w - c.stringWidth(line, font, size)) / 2
                elif align == "right":
                    lx = rx + max_w - c.stringWidth(line, font, size)
                c.drawString(lx, y, line)
                y -= line_h

        c.setFillColor(HexColor("#000000"))  # reset fill after text

    def render_html(self, context: dict) -> str:
        text = (
            interpolate_template(self.content, context)
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        css_top = _PAGE_H - self.rect.y - self.rect.height
        pos = (
            f"position:absolute;left:{self.rect.x}px;top:{css_top}px;"
            f"width:{self.rect.width}px;height:{self.rect.height}px;"
        )
        style = (
            f"{pos}"
            f"font-size:{self.style.size}px;text-align:{self.style.align};"
            f"font-weight:{'bold' if self.style.bold else 'normal'};"
            f"font-style:{'italic' if self.style.italic else 'normal'};"
            f"color:{self.style.color};"
        )
        return f'<div class="comp" style="{style}">{text}</div>'


@dataclass
class ShapeComponent(Component):
    shape_type: Literal["rect", "line", "circle"] = "rect"
    color: str = "#000000"
    stroke_width: float = 1.0
    fill: bool = False

    def render_pdf(self, c: Any, context: dict) -> None:
        try:
            color = HexColor(self.color)
        except Exception:
            color = HexColor("#000000")
        c.setStrokeColor(color)
        c.setLineWidth(self.stroke_width)
        fill_flag = 1 if self.fill else 0
        if self.fill:
            c.setFillColor(color)

        x, y, w, h = self.rect.x, self.rect.y, self.rect.width, self.rect.height
        if self.shape_type == "rect":
            c.rect(x, y, w, h, stroke=1, fill=fill_flag)
        elif self.shape_type == "line":
            c.line(x, y + h / 2, x + w, y + h / 2)
        elif self.shape_type == "circle":
            r = min(w, h) / 2
            c.circle(x + w / 2, y + h / 2, r, stroke=1, fill=fill_flag)

    def render_html(self, context: dict) -> str:
        css_top = _PAGE_H - self.rect.y - self.rect.height
        w, h    = self.rect.width, self.rect.height
        pos     = (
            f"position:absolute;left:{self.rect.x}px;top:{css_top}px;"
            f"width:{w}px;height:{h}px;"
        )
        sw   = self.stroke_width
        half = sw / 2
        fill = self.color if self.fill else "none"

        if self.shape_type == "rect":
            inner = (
                f'<rect x="{half}" y="{half}" '
                f'width="{max(0, w - sw)}" height="{max(0, h - sw)}" '
                f'stroke="{self.color}" stroke-width="{sw}" fill="{fill}"/>'
            )
        elif self.shape_type == "line":
            inner = (
                f'<line x1="0" y1="{h / 2}" x2="{w}" y2="{h / 2}" '
                f'stroke="{self.color}" stroke-width="{sw}"/>'
            )
        elif self.shape_type == "circle":
            r = min(w, h) / 2 - half
            inner = (
                f'<circle cx="{w / 2}" cy="{h / 2}" r="{max(0, r)}" '
                f'stroke="{self.color}" stroke-width="{sw}" fill="{fill}"/>'
            )
        else:
            inner = ""

        return (
            f'<div style="{pos}overflow:visible;">'
            f'<svg width="{w}" height="{h}" style="overflow:visible">{inner}</svg>'
            f'</div>'
        )


@dataclass
class PageBreakComponent(Component):
    """Sentinel component — signals a page break. Rendering is handled by the engine."""

    def __init__(self, id: str = "pagebreak"):
        super().__init__(id=id, type="pagebreak", rect=Rect(0, 0, 0, 0))

    def render_pdf(self, c: Any, context: dict) -> None:
        pass  # engine calls showPage() + increments page counter

    def render_html(self, context: dict) -> str:
        return ""  # engine wraps new page div


def component_from_dict(data: dict) -> Component:
    comp_type = data.get("type")
    comp_id   = data.get("id", "unknown")

    if comp_type == "text":
        rect = Rect.from_list(data.get("rect", [0, 0, 100, 20]))
        s    = data.get("style", {})
        style = TextStyle(
            font=s.get("font", "Helvetica"),
            size=s.get("size", 12),
            bold=s.get("bold", False),
            italic=s.get("italic", False),
            align=s.get("align", "left"),
            color=s.get("color", "#000000"),
        )
        return TextComponent(id=comp_id, type="text", rect=rect,
                             content=data.get("content", ""), style=style)

    elif comp_type == "shape":
        rect = Rect.from_list(data.get("rect", [0, 0, 50, 50]))
        return ShapeComponent(
            id=comp_id, type="shape", rect=rect,
            shape_type=data.get("shape_type", "rect"),
            color=data.get("color", "#000000"),
            stroke_width=data.get("stroke_width", 1.0),
            fill=data.get("fill", False),
        )

    elif comp_type == "pagebreak":
        return PageBreakComponent(id=comp_id)

    else:
        raise ValueError(f"Unknown component type: {comp_type}")
