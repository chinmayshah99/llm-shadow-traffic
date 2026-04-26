from __future__ import annotations

from common import run_example


run_example(
    title="Semantic text match example",
    records=[
        {
            "trace_id": "semantic-1",
            "type": "baseline",
            "status": "ok",
            "text": "Reset the service and check the deployment logs.",
            "tool_calls": [],
        },
        {
            "trace_id": "semantic-1",
            "type": "candidate",
            "status": "ok",
            "text": "Check deployment logs after restarting the service.",
            "tool_calls": [],
        },
    ],
    config={
        "judges": [
            {
                "name": "semantic-answer",
                "type": "semantic_match",
                "field": "text",
                "threshold": 0.5,
                "rubric": "Pass when the two responses mean the same thing.",
            }
        ]
    },
    semantic_backend="token-overlap",
)
