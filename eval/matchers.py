from __future__ import annotations

import re
from typing import Any

from eval.semantic import SemanticBackend


def exact_match(expected: Any, actual: Any) -> bool:
    return expected == actual


def regex_match(pattern: str, actual: Any) -> bool:
    if not isinstance(actual, str):
        return False
    return re.search(pattern, actual) is not None


def semantic_match(
    baseline_text: Any,
    candidate_text: Any,
    *,
    backend: SemanticBackend,
    threshold: float,
    rubric: str | None = None,
) -> tuple[bool, float | None]:
    if not isinstance(baseline_text, str) or not isinstance(candidate_text, str):
        return False, None
    score = backend.score(baseline_text, candidate_text, rubric)
    if score is None:
        return False, None
    return score >= threshold, score
