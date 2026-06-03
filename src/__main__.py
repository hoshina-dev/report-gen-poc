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
import sys
from pathlib import Path

from .config import Config
from .output import generate_pdf_to_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


def _load_json(value: str) -> object:
    """Load JSON from an inline string or a file path."""
    if value.strip().startswith("{") or value.strip().startswith("["):
        return json.loads(value)
    with Path(value).open() as f:
        return json.load(f)


def _run_generator() -> int:
    cfg = Config.from_env()
    data = _load_json(cfg.data_json)
    components = _load_json(cfg.components_json)
    if not isinstance(data, dict):
        raise RuntimeError(
            f"DATA_JSON must be a JSON object, got {type(data).__name__}"
        )
    if not isinstance(components, list):
        raise RuntimeError(
            f"COMPONENTS_JSON must be a JSON array, got {type(components).__name__}"
        )
    generate_pdf_to_file(data, components, cfg.pdf_output)
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
