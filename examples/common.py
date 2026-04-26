from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.config import load_judge_config
from eval.runner import evaluate_records
from eval.semantic import NullSemanticBackend, TokenOverlapSemanticBackend


def run_example(
    *,
    title: str,
    records: list[dict[str, Any]],
    config: dict[str, Any],
    semantic_backend: str = "null",
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "judge_config.json"
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        loaded_config = load_judge_config(config_path)

    backend = NullSemanticBackend() if semantic_backend == "null" else TokenOverlapSemanticBackend()
    result = evaluate_records(records, loaded_config, semantic_backend=backend)
    pair_result = next(item for item in result["results"] if item["status"] == "evaluated")

    print(title)
    print(json.dumps(result["summary"], indent=2))
    for judge in pair_result["judges"]:
        status = "PASS" if judge["passed"] else "FAIL"
        print(f"- {judge['name']}: {status}")
        print(f"  details: {json.dumps(judge['details'], sort_keys=True)}")
