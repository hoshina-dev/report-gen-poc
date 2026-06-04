"""
Editor startup - only imported when --editor flag is passed
"""

import logging
from pathlib import Path

import uvicorn

from ..config import EditorConfig

logger = logging.getLogger(__name__)


def start_editor(reload: bool = True) -> None:
    cfg = EditorConfig.from_env()
    host = cfg.editor_host
    port = cfg.editor_port

    logger.info(f"Starting Template Editor at http://{host}:{port}")
    logger.info("Open your browser to http://localhost:%d", port)

    # Use uvicorn CLI-style to support reload
    uvicorn.run(
        "src.editor.server:app",
        host=host,
        port=port,
        reload=reload,
        reload_dirs=[str(Path(__file__).parents[2])] if reload else None,
        log_level="info",
    )
