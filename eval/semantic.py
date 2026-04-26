from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol

STOPWORDS = {
    "a",
    "an",
    "and",
    "after",
    "for",
    "in",
    "of",
    "the",
    "to",
}


class SemanticBackend(Protocol):
    def score(self, baseline_text: str, candidate_text: str, rubric: str | None = None) -> float | None:
        ...


class NullSemanticBackend:
    def score(self, baseline_text: str, candidate_text: str, rubric: str | None = None) -> float | None:
        _ = (baseline_text, candidate_text, rubric)
        return None


class TokenOverlapSemanticBackend:
    def score(self, baseline_text: str, candidate_text: str, rubric: str | None = None) -> float | None:
        _ = rubric
        baseline_tokens = set(_tokenize(baseline_text))
        candidate_tokens = set(_tokenize(candidate_text))
        if not baseline_tokens and not candidate_tokens:
            return 1.0
        if not baseline_tokens or not candidate_tokens:
            return 0.0
        overlap = len(baseline_tokens & candidate_tokens)
        union = len(baseline_tokens | candidate_tokens)
        return overlap / union


def get_semantic_backend(name: str) -> SemanticBackend:
    if name == "null":
        return NullSemanticBackend()
    if name == "token-overlap":
        return TokenOverlapSemanticBackend()
    raise ValueError(f"Unsupported semantic backend: {name}")


def _tokenize(text: str) -> Iterable[str]:
    normalized_tokens: list[str] = []
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if token in STOPWORDS:
            continue
        normalized_tokens.append(_normalize_token(token))
    return normalized_tokens


def _normalize_token(token: str) -> str:
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token
