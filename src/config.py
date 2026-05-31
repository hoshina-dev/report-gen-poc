import os
from dataclasses import dataclass




@dataclass
class Config:
    output_dir: str
    json_input: str
    editor_host: str
    editor_port: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            output_dir=os.environ.get("OUTPUT_DIR", "generated"),
            json_input=os.environ.get("JSON_INPUT", "data/1.json"),
            editor_host=os.environ.get("EDITOR_HOST", "127.0.0.1"),
            editor_port=int(os.environ.get("EDITOR_PORT", "8765")),
        )
