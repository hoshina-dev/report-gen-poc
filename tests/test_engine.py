"""
Stateless engine tests — no editor, no DB, no file I/O.
Run: make test
"""

from engine import Rect, TemplateEngine
from engine.parser import extract_fields


COMPONENTS = [
    {
        "id": "title",
        "type": "text",
        "content": "Report for {{name}}",
        "rect": [50, 750, 200, 30],
        "style": {"font": "Helvetica", "size": 24},
    },
    {
        "id": "body",
        "type": "text",
        "content": "{{template}}",
        "rect": [50, 650, 500, 100],
        "style": {"font": "Helvetica", "size": 12},
    },
]

CONTEXT = {
    "name": "Alice",
    "place": "the PDF Generator",
    "template": "Hello Alice, welcome to the PDF Generator!",
}


def test_pdf_render():
    engine = TemplateEngine(COMPONENTS)
    pdf = engine.render(format="pdf", context=CONTEXT)
    assert pdf.startswith(b"%PDF"), "Not a valid PDF"
    assert len(pdf) > 0
    print(f"✅ PDF render ({len(pdf)} bytes)")


def test_html_render():
    engine = TemplateEngine(COMPONENTS)
    html = engine._render_html(CONTEXT)
    assert "Alice" in html
    assert "PDF Generator" in html
    print("✅ HTML render")


def test_template_interpolation():
    engine = TemplateEngine(COMPONENTS)
    ctx = engine._build_context(CONTEXT)
    assert ctx["template"] == "Hello Alice, welcome to the PDF Generator!"
    print("✅ Template interpolation")


def test_no_components_raises():
    engine = TemplateEngine([])
    try:
        engine.render(format="pdf", context=CONTEXT)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "no components" in str(e).lower()
    print("✅ No-components raises ValueError")


def test_rect():
    r = Rect(x=50, y=100, width=300, height=50)
    assert [r.x, r.y, r.width, r.height] == [50, 100, 300, 50]
    r2 = Rect.from_list([100, 200, 200, 75])
    assert r2.height == 75
    print("✅ Rect")


def test_field_extraction():
    fields = extract_fields("{{name}} from {{country}}, plan: {{plan}}")
    assert {"name", "country", "plan"}.issubset(set(fields))
    print(f"✅ Field extraction: {fields}")


def test_shape_component():
    components = [
        {
            "id": "box",
            "type": "shape",
            "shape_type": "rect",
            "rect": [0, 0, 100, 50],
            "color": "#FF0000",
            "stroke_width": 1,
            "fill": True,
        }
    ]
    engine = TemplateEngine(components)
    pdf = engine.render(format="pdf", context={})
    assert pdf.startswith(b"%PDF")
    print("✅ Shape component")


if __name__ == "__main__":
    print("Testing Template Engine...\n")
    test_rect()
    test_field_extraction()
    test_template_interpolation()
    test_pdf_render()
    test_html_render()
    test_no_components_raises()
    test_shape_component()
    print("\n✅ All tests passed!")
