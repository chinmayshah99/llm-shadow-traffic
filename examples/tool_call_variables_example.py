from __future__ import annotations

from common import run_example


run_example(
    title="Tool call variable match example",
    records=[
        {
            "trace_id": "vars-1",
            "type": "baseline",
            "status": "ok",
            "text": None,
            "tool_calls": [
                {
                    "name": "search_docs",
                    "arguments": {"query": "rotate API keys", "top_k": 5},
                }
            ],
        },
        {
            "trace_id": "vars-1",
            "type": "candidate",
            "status": "ok",
            "text": None,
            "tool_calls": [
                {
                    "name": "search_docs",
                    "arguments": {"query": "rotate API keys", "top_k": 5},
                }
            ],
        },
    ],
    config={
        "judges": [
            {
                "name": "tool-call-with-variables",
                "type": "tool_call_match",
                "tool_calls": [
                    {
                        "name": "search_docs",
                        "arguments": {
                            "query": {"var": "$query", "match": "exact"},
                            "top_k": {"var": "$top_k", "match": "exact"},
                        },
                    }
                ],
            }
        ]
    },
)
