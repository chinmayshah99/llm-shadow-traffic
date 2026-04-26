from __future__ import annotations

from collections import defaultdict
from typing import Any

from eval.judges import DEFAULT_JUDGE_FACTORY, JudgeResult
from eval.semantic import SemanticBackend


def evaluate_records(
    records: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    semantic_backend: SemanticBackend,
) -> dict[str, Any]:
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        grouped[record["trace_id"]][record["type"]] = record

    judges = [DEFAULT_JUDGE_FACTORY.create(judge) for judge in config["judges"]]
    results: list[dict[str, Any]] = []
    judge_summary: dict[str, dict[str, int]] = {
        judge.name: {"passed": 0, "failed": 0} for judge in judges
    }

    paired_count = 0
    success_count = 0
    for trace_id, pair in grouped.items():
        baseline = pair.get("baseline")
        candidate = pair.get("candidate")
        if not baseline or not candidate:
            continue
        paired_count += 1

        if baseline.get("status") != "ok" or candidate.get("status") != "ok":
            results.append(
                {
                    "trace_id": trace_id,
                    "status": "skipped",
                    "reason": "non_ok_pair",
                    "baseline_status": baseline.get("status"),
                    "candidate_status": candidate.get("status"),
                    "judges": [],
                }
            )
            continue

        success_count += 1
        judge_results: list[JudgeResult] = [
            judge.evaluate(baseline, candidate, semantic_backend=semantic_backend)
            for judge in judges
        ]
        for result in judge_results:
            key = "passed" if result.passed else "failed"
            judge_summary[result.name][key] += 1

        results.append(
            {
                "trace_id": trace_id,
                "status": "evaluated",
                "passed": all(result.passed for result in judge_results),
                "judges": [result.to_dict() for result in judge_results],
            }
        )

    return {
        "summary": {
            "paired_traces": paired_count,
            "successful_pairs": success_count,
            "evaluated_pairs": sum(1 for result in results if result["status"] == "evaluated"),
            "fully_passing_pairs": sum(
                1 for result in results if result["status"] == "evaluated" and result["passed"]
            ),
            "judge_summary": judge_summary,
        },
        "results": results,
    }
