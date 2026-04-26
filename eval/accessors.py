from __future__ import annotations

from typing import Any


def get_path(data: Any, path: str) -> Any:
    current = data
    for segment in path.split("."):
        if isinstance(current, list):
            if not segment.isdigit():
                return None
            index = int(segment)
            if index >= len(current):
                return None
            current = current[index]
            continue

        if not isinstance(current, dict):
            return None

        if segment not in current:
            return None
        current = current[segment]

    return current
