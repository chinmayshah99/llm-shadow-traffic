from __future__ import annotations

from common import run_example


run_example(
    title="Tool call semantic argument match example",
    records=[
        {
            "trace_id": "semantic-args-1",
            "type": "baseline",
            "status": "ok",
            "text": None,
            "tool_calls": [
                {
                    "name": "search_docs",
                    "arguments": {
                        "query": "best way to rotate API keys safely",
                        "top_k": 5,
                        "filters": {"product": "vault"},
                    },
                }
            ],
        },
        {
            "trace_id": "semantic-args-1",
            "type": "candidate",
            "status": "ok",
            "text": None,
            "tool_calls": [
                {
                    "name": "search_docs",
                    "arguments": {
                        "query": "safe way to rotate API keys",
                        "top_k": 5,
                        "filters": {"product": "vault"},
                    },
                }
            ],
        },
    ],
    config={
        "judges": [
            {
                "name": "tool-call-semantic-args",
                "type": "tool_call_match",
                "tool_calls": [
                    {
                        "name": "search_docs",
                        "arguments": {
                            "query": {
                                "var": "$query",
                                "match": "semantic",
                                "threshold": 0.3,
                                "rubric": "Pass when the search intent is the same.",
                            },
                            "top_k": {"var": "$top_k", "match": "exact"},
                            "filters": {"var": "$filters", "match": "exact"},
                        },
                    }
                ],
            }
        ]
    },
    semantic_backend="token-overlap",
)
