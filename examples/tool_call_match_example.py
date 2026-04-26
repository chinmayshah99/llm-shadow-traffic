from __future__ import annotations

from common import run_example


run_example(
    title="Tool call exact match example",
    records=[
        {
            "trace_id": "tool-1",
            "type": "baseline",
            "status": "ok",
            "text": None,
            "tool_calls": [{"name": "search_docs", "arguments": {"query": "python"}}],
        },
        {
            "trace_id": "tool-1",
            "type": "candidate",
            "status": "ok",
            "text": None,
            "tool_calls": [{"name": "search_docs", "arguments": {"query": "python"}}],
        },
    ],
    config={
        "judges": [
            {
                "name": "tool-call-match",
                "type": "tool_call_match",
            }
        ]
    },
)
