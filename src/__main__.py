"""
Entry point: python -m src

Default (no flags): run the PDF report generator.
--editor flag:      start the visual template editor (dev only).
                    Safe to delete the entire editor/ package — the CLI will
                    print a clear error instead of crashing.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .config import Config
from .output import generate_pdf_to_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


def _run_generator() -> int:
    raw = os.environ.get("JSON_INPUT")
    if raw:
        data = json.loads(raw)
    else:
        fallback = Path(__file__).parents[1] / "data" / "1.json"
        if fallback.exists():
            logging.getLogger(__name__).info(
                "No JSON_INPUT env var — using %s", fallback
            )
            with fallback.open() as f:
                data = json.load(f)
        else:
            logging.getLogger(__name__).warning(
                "No JSON_INPUT and no fallback file — using minimal example"
            )
            data = {
                "template": "{{full_name}} ({{country}}) — plan: {{plan}}",
                "components": [
                    {
                        "id": "title",
                        "type": "text",
                        "content": "Report",
                        "rect": [50, 750, 500, 30],
                        "style": {"font": "Helvetica-Bold", "size": 24},
                    },
                    {
                        "id": "body",
                        "type": "text",
                        "content": "{{template}}",
                        "rect": [50, 680, 512, 60],
                        "style": {"font": "Helvetica", "size": 12},
                    },
                ],
                "full_name": "Hoshina Suzuki",
                "country": "Japan",
                "plan": "premium",
            }

    cfg = Config.from_env()
    generate_pdf_to_file(data, f"{cfg.output_dir}/output.pdf")
    return 0


def _run_editor() -> int:
    """Start the visual template editor (dev only)."""
    try:
        from .editor.cli import start_editor
    except ImportError:
        print(
            "ERROR: editor package not found.\n"
            "The editor/ directory is optional and not included in production.\n"
            "To use the editor, ensure you are running from the full source tree.",
            file=sys.stderr,
        )
        return 1

    start_editor(reload=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF Report Generator")
    parser.add_argument(
        "--editor",
        action="store_true",
        help="Start the visual template editor (dev only)",
    )
    args = parser.parse_args()

    if args.editor:
        return _run_editor()
    return _run_generator()


if __name__ == "__main__":
    sys.exit(main())
