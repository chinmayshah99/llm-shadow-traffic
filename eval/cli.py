from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from eval.tool_match import tool_match


def load_records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        grouped[record["trace_id"]][record["type"]] = record

    pairs = [
        (pair.get("baseline"), pair.get("candidate"))
        for pair in grouped.values()
        if pair.get("baseline") and pair.get("candidate")
    ]
    matched_pairs = [
        (base, cand)
        for base, cand in pairs
        if base.get("status") == "ok" and cand.get("status") == "ok"
    ]
    tool_comparable = [
        (base, cand)
        for base, cand in matched_pairs
        if base.get("tool_name") is not None and cand.get("tool_name") is not None
    ]
    tool_matches = sum(1 for base, cand in tool_comparable if tool_match(base, cand))

    baseline_latencies = [record["latency_ms"] for record in records if record["type"] == "baseline"]
    candidate_latencies = [record["latency_ms"] for record in records if record["type"] == "candidate"]

    return {
        "total_records": len(records),
        "trace_count": len(grouped),
        "paired_traces": len(pairs),
        "successful_pairs": len(matched_pairs),
        "tool_comparable_pairs": len(tool_comparable),
        "tool_match_percent": (tool_matches / len(tool_comparable) * 100) if tool_comparable else None,
        "baseline_avg_latency_ms": mean(baseline_latencies) if baseline_latencies else None,
        "candidate_avg_latency_ms": mean(candidate_latencies) if candidate_latencies else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze LLM shadow logs.")
    parser.add_argument("--file", required=True, help="Path to JSONL log file.")
    args = parser.parse_args()

    records = load_records(Path(args.file))
    summary = summarize(records)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
