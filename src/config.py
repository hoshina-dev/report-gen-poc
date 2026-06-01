import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _require_path(env_key: str) -> str:
    """Return the env value for env_key, raising if missing or path not found."""
    val = os.environ.get(env_key, "").strip()
    if not val:
        raise RuntimeError(f"Missing required environment variable: {env_key}")
    if not val.startswith("{"):
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

    @classmethod
    def from_env(cls) -> "Config":
        required = ["DATA_JSON", "COMPONENTS_JSON", "PDF_OUTPUT"]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
        return cls(
            data_json=_require_path("DATA_JSON"),
            components_json=_require_path("COMPONENTS_JSON"),
            pdf_output=os.environ["PDF_OUTPUT"],
        )


@dataclass
class EditorConfig(Config):
    """Editor config — extends Config with editor server and DB fields."""
    editor_host: str
    editor_port: int
    data_source_name: str

    @classmethod
    def from_env(cls) -> "EditorConfig":
        required = ["DATA_JSON", "PDF_OUTPUT", "EDITOR_HOST", "EDITOR_PORT", "DATA_SOURCE_NAME"]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
        return cls(
            data_json=_require_path("DATA_JSON"),
            components_json=os.environ.get("COMPONENTS_JSON", ""),  # not used by editor; reads from DB
            pdf_output=os.environ["PDF_OUTPUT"],
            editor_host=os.environ["EDITOR_HOST"],
            editor_port=int(os.environ["EDITOR_PORT"]),
            data_source_name=os.environ["DATA_SOURCE_NAME"],
        )
