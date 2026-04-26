from __future__ import annotations

import json
from typing import Any


def _parse_tool_arguments(raw_args: Any) -> Any:
    if raw_args is None:
        return None

    try:
        return json.loads(raw_args)
    except (TypeError, json.JSONDecodeError):
        return raw_args


def normalize(response: dict[str, Any] | None) -> dict[str, Any]:
    if not response:
        return {"text": None, "tool_name": None, "tool_args": None, "tool_calls": []}

    message = (
        response.get("choices", [{}])[0].get("message", {})
        if response.get("choices")
        else {}
    )
    text = message.get("content")

    tool_name = None
    tool_args: Any = None
    tool_calls = message.get("tool_calls") or []
    normalized_tool_calls: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        tool_call = tool_call or {}
        function = tool_call.get("function", {})
        normalized_tool_calls.append(
            {
                "name": function.get("name"),
                "arguments": _parse_tool_arguments(function.get("arguments")),
            }
        )

    if normalized_tool_calls:
        first_tool = normalized_tool_calls[0]
        tool_name = first_tool.get("name")
        tool_args = first_tool.get("arguments")

    return {
        "text": text,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "tool_calls": normalized_tool_calls,
    }
