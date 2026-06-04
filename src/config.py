import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _require(env_key: str) -> str:
    """Return the env value, raising a clear error if missing or empty."""
    val = os.environ.get(env_key, "").strip()
    if not val:
        raise RuntimeError(f"Missing required environment variable: {env_key}")
    return val


def _require_path(env_key: str) -> str:
    """Return the env value, raising if missing or (when a path) non-existent."""
    val = _require(env_key)
    if not val.startswith(("{", "[")):
        path = Path(val)
        if not path.exists():
            raise RuntimeError(f"{env_key} path does not exist: {path}")
    return val


@dataclass
class Config:
    """Core config — required by the generator. No editor or DB fields."""

    data_json: str
    components_json: str
    pdf_output: str
    # POST target after generation; empty string means skip (local dev).
    webhook_url: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            data_json=_require_path("DATA_JSON"),
            components_json=_require_path("COMPONENTS_JSON"),
            pdf_output=os.environ.get("PDF_OUTPUT", "") if R2Config.is_configured() else _require("PDF_OUTPUT"),
            webhook_url=os.environ.get("WEBHOOK_URL", ""),
        )


@dataclass
class R2Config:
    """Cloudflare R2 config — loaded only when S3_BUCKET is set (production)."""

    bucket: str
    endpoint: str
    access_key: str
    secret_key: str
    region: str = "auto"

    @classmethod
    def from_env(cls) -> "R2Config":
        return cls(
            bucket=_require("S3_BUCKET"),
            endpoint=_require("S3_ENDPOINT"),
            access_key=_require("S3_ACCESS_KEY"),
            secret_key=_require("S3_SECRET_KEY"),
            region=os.environ.get("S3_REGION", "auto"),
        )

    @staticmethod
    def is_configured() -> bool:
        return bool(os.environ.get("S3_BUCKET"))


@dataclass
class EditorConfig(Config):
    """Editor config — extends Config with editor server and DB fields."""

    editor_host: str
    editor_port: int
    data_source_name: str

    @classmethod
    def from_env(cls) -> "EditorConfig":
        # DATA_JSON is optional — if omitted, editor starts in template-select mode
        data_json_raw = os.environ.get("DATA_JSON", "").strip()
        if data_json_raw and not data_json_raw.startswith(("{", "[")):
            p = Path(data_json_raw)
            if not p.exists():
                raise RuntimeError(f"DATA_JSON path does not exist: {p}")
        return cls(
            data_json=data_json_raw,
            components_json=os.environ.get(
                "COMPONENTS_JSON", ""
            ),  # not used by editor; reads from DB
            pdf_output=os.environ.get("PDF_OUTPUT", "output.pdf"),
            webhook_url=os.environ.get("WEBHOOK_URL", ""),
            editor_host=_require("EDITOR_HOST"),
            editor_port=int(_require("EDITOR_PORT")),
            data_source_name=_require("DATA_SOURCE_NAME"),
        )
