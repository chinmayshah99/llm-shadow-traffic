from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_judge_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)

    if not isinstance(config, dict):
        raise ValueError("Judge config must be a JSON object.")

    judges = config.get("judges")
    if not isinstance(judges, list) or not judges:
        raise ValueError("Judge config must include a non-empty 'judges' list.")

    for index, judge in enumerate(judges):
        if not isinstance(judge, dict):
            raise ValueError(f"Judge entry at index {index} must be an object.")
        if not judge.get("name"):
            raise ValueError(f"Judge entry at index {index} is missing 'name'.")
        if not judge.get("type"):
            raise ValueError(f"Judge '{judge['name']}' is missing 'type'.")

    return config
