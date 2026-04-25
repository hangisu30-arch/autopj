import json
from pathlib import Path


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise ValueError(f"Config file not found: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)