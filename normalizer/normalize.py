from __future__ import annotations

import json
from typing import Any


def normalize(response: dict[str, Any] | None) -> dict[str, Any]:
    if not response:
        return {"text": None, "tool_name": None, "tool_args": None}

    message = (
        response.get("choices", [{}])[0].get("message", {})
        if response.get("choices")
        else {}
    )
    text = message.get("content")

    tool_name = None
    tool_args: Any = None
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        first_tool = tool_calls[0] or {}
        function = first_tool.get("function", {})
        tool_name = function.get("name")
        raw_args = function.get("arguments")
        if raw_args is not None:
            try:
                tool_args = json.loads(raw_args)
            except (TypeError, json.JSONDecodeError):
                tool_args = raw_args

    return {"text": text, "tool_name": tool_name, "tool_args": tool_args}
