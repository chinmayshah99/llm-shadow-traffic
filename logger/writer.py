from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_log(record: dict[str, Any], log_file: str) -> None:
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
