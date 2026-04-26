from __future__ import annotations

from eval.runner import evaluate_records
from eval.semantic import NullSemanticBackend


def test_evaluate_records_counts_pass_and_fail_by_judge() -> None:
    result = evaluate_records(
        [
            {
                "trace_id": "t1",
                "type": "baseline",
                "status": "ok",
                "text": "Ticket TICKET-123456",
                "tool_calls": [],
            },
            {
                "trace_id": "t1",
                "type": "candidate",
                "status": "ok",
                "text": "Ticket TICKET-123456",
                "tool_calls": [],
            },
            {
                "trace_id": "t2",
                "type": "baseline",
                "status": "ok",
                "text": "Ticket TICKET-654321",
                "tool_calls": [],
            },
            {
                "trace_id": "t2",
                "type": "candidate",
                "status": "ok",
                "text": "Missing identifier",
                "tool_calls": [],
            },
        ],
        {
            "judges": [
                {
                    "name": "ticket",
                    "type": "regex_match",
                    "field": "text",
                    "pattern": "TICKET-[0-9]{6}",
                }
            ]
        },
        semantic_backend=NullSemanticBackend(),
    )

    assert result["summary"]["paired_traces"] == 2
    assert result["summary"]["fully_passing_pairs"] == 1
    assert result["summary"]["judge_summary"]["ticket"] == {"passed": 1, "failed": 1}
