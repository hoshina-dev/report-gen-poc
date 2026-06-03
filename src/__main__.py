"""
Entry point: python -m src

Default (no flags): run the PDF report generator.
--editor flag:      start the visual template editor (dev only).
                    Safe to delete the entire editor/ package — the CLI will
                    print a clear error instead of crashing.

Production flow:
  1. Load DATA_JSON + COMPONENTS_JSON
  2. Generate PDF bytes
  3. If R2 is configured (S3_BUCKET set): upload to R2, send success webhook
     Otherwise: write to PDF_OUTPUT (local dev)
  4. On any failure: send failure webhook (if WEBHOOK_URL set), exit 1
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import Config, R2Config
from .output import generate_pdf_to_file, generate_pdf_to_r2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _load_json(value: str) -> object:
    """Load JSON from an inline string or a file path."""
    if value.strip().startswith("{") or value.strip().startswith("["):
        return json.loads(value)
    with Path(value).open() as f:
        return json.load(f)


def _send_webhook(
    webhook_url: str,
    exp_id: str,
    *,
    status: str,
    r2_key: str | None = None,
    error: str | None = None,
) -> None:
    """POST job result to experiment-manager. Retries 3×; never raises."""
    if not webhook_url:
        logger.info("WEBHOOK_URL not set — skipping webhook (status=%s)", status)
        return

    payload: dict = {
        "status": status,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if r2_key is not None:
        payload["r2_key"] = r2_key
    if error is not None:
        payload["error"] = error

    url = webhook_url.replace("{exp_id}", exp_id)

    for attempt in range(1, 4):
        try:
            resp = requests.patch(url, json=payload, timeout=30)
            resp.raise_for_status()
            logger.info("Webhook sent: status=%s url=%s", status, url)
            return
        except Exception as exc:
            logger.warning("Webhook attempt %d/3 failed: %s", attempt, exc)
            if attempt < 3:
                time.sleep(2)

    logger.error("Failed to send webhook after 3 attempts — url=%s", url)


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

    exp_id: str = data.get("id", "")
    if not exp_id:
        if R2Config.is_configured():
            raise RuntimeError("data missing required 'id' field — cannot build R2 key or webhook URL")
        logger.warning("data missing 'id' field")

    if not R2Config.is_configured():
        generate_pdf_to_file(data, components, cfg.pdf_output)
        logger.info("PDF written locally: %s", cfg.pdf_output)
        return 0

    r2_key: str | None = None
    error: str | None = None
    try:
        r2_key = generate_pdf_to_r2(data, components, R2Config.from_env())
        logger.info("PDF uploaded to R2: %s", r2_key)
    except Exception as exc:
        logger.error("PDF pipeline failed: %s", exc, exc_info=True)
        error = str(exc)
    finally:
        _send_webhook(
            cfg.webhook_url,
            exp_id,
            status="success" if error is None else "failed",
            r2_key=r2_key,
            error=error,
        )

    return 0 if error is None else 1


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
