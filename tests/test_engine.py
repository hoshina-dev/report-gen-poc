"""
Quick test of the Template Engine
Run: make test
"""

from pathlib import Path

from engine import Rect, TemplateEngine


def test_basic_template():
    """Test basic template with {{field}} interpolation"""
    template_dict = {
        "template": "Hello {{name}}, welcome to {{place}}!",
        "components": [
            {
                "id": "title",
                "type": "text",
                "content": "Report",
                "rect": [50, 750, 200, 30],
                "style": {"font": "Helvetica", "size": 24},
            },
            {
                "id": "content",
                "type": "text",
                "content": "{{template}}",
                "rect": [50, 650, 500, 100],
                "style": {"font": "Helvetica", "size": 12},
            },
        ],
    }

    engine = TemplateEngine(template_dict)
    context = {
        "name": "Alice",
        "place": "the PDF Generator",
        "template": "Hello Alice, welcome to the PDF Generator!",
    }

    # Test validation
    errors = engine.validate(context)
    assert not errors, f"Validation failed: {errors}"
    print("✅ Validation passed")

    # Test field extraction
    assert "name" in engine.fields
    assert "place" in engine.fields
    print(f"✅ Fields extracted: {sorted(engine.fields)}")

    # Test HTML rendering
    html = engine._render_html(context)
    assert "Alice" in html
    assert "PDF Generator" in html
    print("✅ HTML rendering works")

    # Test PDF rendering
    pdf_bytes = engine.render(format="pdf", context=context)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")
    print(f"✅ PDF rendering works ({len(pdf_bytes)} bytes)")

    # Save test PDF
    out = Path("generated/test_output.pdf")
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(pdf_bytes)
    print(f"✅ PDF saved to {out}")


def test_component_positioning():
    """Test component positioning with Rect"""
    rect = Rect(x=50, y=100, width=300, height=50)
    assert rect.x == 50
    assert [rect.x, rect.y, rect.width, rect.height] == [50, 100, 300, 50]

    # From list
    rect2 = Rect.from_list([100, 200, 200, 75])
    assert rect2.x == 100
    assert rect2.height == 75
    print("✅ Rect positioning works")


def test_field_extraction():
    """Test extracting all fields from template"""
    from engine.parser import extract_fields

    text = "User {{name}} from {{country}}, plan: {{plan}}"
    fields = extract_fields(text)
    assert "name" in fields
    assert "country" in fields
    assert "plan" in fields
    print(f"✅ Field extraction: {fields}")


if __name__ == "__main__":
    print("Testing Template Engine...\n")

    test_component_positioning()
    test_field_extraction()
    test_basic_template()

    print("\n✅ All tests passed!")
