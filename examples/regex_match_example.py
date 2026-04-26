from __future__ import annotations

from common import run_example


run_example(
    title="Regex match example",
    records=[
        {
            "trace_id": "regex-1",
            "type": "baseline",
            "status": "ok",
            "text": "Ticket created: TICKET-123456",
            "tool_calls": [],
        },
        {
            "trace_id": "regex-1",
            "type": "candidate",
            "status": "ok",
            "text": "Candidate says: TICKET-123456 is open",
            "tool_calls": [],
        },
    ],
    config={
        "judges": [
            {
                "name": "ticket-id-regex",
                "type": "regex_match",
                "field": "text",
                "pattern": "TICKET-[0-9]{6}",
            }
        ]
    },
)
