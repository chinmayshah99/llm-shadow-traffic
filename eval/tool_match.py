from __future__ import annotations

from typing import Any


def tool_match(base: dict[str, Any], cand: dict[str, Any]) -> bool:
    return base.get("tool_name") == cand.get("tool_name")
