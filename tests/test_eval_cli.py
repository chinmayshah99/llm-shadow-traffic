from eval.cli import summarize


def test_summarize_groups_and_computes_tool_match() -> None:
    summary = summarize(
        [
            {
                "trace_id": "t1",
                "type": "baseline",
                "status": "ok",
                "tool_name": "search",
                "latency_ms": 10,
            },
            {
                "trace_id": "t1",
                "type": "candidate",
                "status": "ok",
                "tool_name": "search",
                "latency_ms": 20,
            },
            {
                "trace_id": "t2",
                "type": "baseline",
                "status": "ok",
                "tool_name": None,
                "latency_ms": 30,
            },
            {
                "trace_id": "t2",
                "type": "candidate",
                "status": "error",
                "tool_name": None,
                "latency_ms": 40,
            },
        ]
    )
    assert summary["paired_traces"] == 2
    assert summary["successful_pairs"] == 1
    assert summary["tool_comparable_pairs"] == 1
    assert summary["tool_match_percent"] == 100.0
