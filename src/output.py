from pathlib import Path

from .engine import TemplateEngine
from .engine.context import flatten_context


def generate_pdf(data: dict, components: list) -> bytes:
    """Render a PDF from experiment data and a components list."""
    context = flatten_context(data) # nested state (original input) to flatten of all fields
    engine = TemplateEngine(components)
    return engine.render("pdf", context) 


def generate_pdf_to_file(data: dict, components: list, path: str) -> str: # will be deprecated after setting up R2, replace with upload_pdf_to_s3
    """Render PDF and write it to *path*, creating parent directories as needed."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = generate_pdf(data, components)
    with open(path, "wb") as f:
        f.write(pdf_bytes)
    print(f"PDF saved to {path}")
    return path
