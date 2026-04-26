from __future__ import annotations

import pytest

from eval.judges import DEFAULT_JUDGE_FACTORY, RegexJudge, evaluate_judge
from eval.semantic import NullSemanticBackend, TokenOverlapSemanticBackend


def test_tool_call_judge_matches_exact_sequence() -> None:
    result = evaluate_judge(
        {"name": "tool-match", "type": "tool_call_match"},
        {
            "tool_calls": [
                {"name": "search_docs", "arguments": {"query": "python"}},
                {"name": "fetch_page", "arguments": {"id": "123"}},
            ]
        },
        {
            "tool_calls": [
                {"name": "search_docs", "arguments": {"query": "python"}},
                {"name": "fetch_page", "arguments": {"id": "123"}},
            ]
        },
        semantic_backend=NullSemanticBackend(),
    )

    assert result["passed"] is True


def test_regex_judge_matches_candidate_text() -> None:
    result = evaluate_judge(
        {
            "name": "ticket",
            "type": "regex_match",
            "field": "text",
            "pattern": "TICKET-[0-9]{6}",
        },
        {"text": "baseline"},
        {"text": "candidate TICKET-123456"},
        semantic_backend=NullSemanticBackend(),
    )

    assert result["passed"] is True


def test_semantic_judge_uses_backend_score() -> None:
    result = evaluate_judge(
        {
            "name": "semantic",
            "type": "semantic_match",
            "field": "text",
            "threshold": 0.5,
        },
        {"text": "restart service and inspect logs"},
        {"text": "inspect logs after restarting service"},
        semantic_backend=TokenOverlapSemanticBackend(),
    )

    assert result["passed"] is True
    assert result["details"]["score"] is not None


def test_tool_call_judge_supports_variable_capture_and_reuse() -> None:
    result = evaluate_judge(
        {
            "name": "variables",
            "type": "tool_call_match",
            "tool_calls": [
                {
                    "name": "fetch_doc",
                    "arguments": {"doc_id": {"var": "$doc_id", "match": "exact"}},
                },
                {
                    "name": "fetch_doc",
                    "arguments": {"doc_id": {"var": "$doc_id", "match": "exact"}},
                },
            ],
        },
        {
            "tool_calls": [
                {"name": "fetch_doc", "arguments": {"doc_id": "abc"}},
                {"name": "fetch_doc", "arguments": {"doc_id": "abc"}},
            ]
        },
        {
            "tool_calls": [
                {"name": "fetch_doc", "arguments": {"doc_id": "abc"}},
                {"name": "fetch_doc", "arguments": {"doc_id": "abc"}},
            ]
        },
        semantic_backend=NullSemanticBackend(),
    )

    assert result["passed"] is True


def test_tool_call_judge_supports_semantic_argument_matching() -> None:
    result = evaluate_judge(
        {
            "name": "semantic-args",
            "type": "tool_call_match",
            "tool_calls": [
                {
                    "name": "search_docs",
                    "arguments": {
                        "query": {"var": "$query", "match": "semantic", "threshold": 0.3},
                        "top_k": {"var": "$top_k", "match": "exact"},
                    },
                }
            ],
        },
        {
            "tool_calls": [
                {
                    "name": "search_docs",
                    "arguments": {
                        "query": "best way to rotate API keys safely",
                        "top_k": 5,
                    },
                }
            ]
        },
        {
            "tool_calls": [
                {
                    "name": "search_docs",
                    "arguments": {
                        "query": "safe way to rotate API keys",
                        "top_k": 5,
                    },
                }
            ]
        },
        semantic_backend=TokenOverlapSemanticBackend(),
    )

    assert result["passed"] is True


def test_tool_call_judge_respects_ordered_sequence() -> None:
    result = evaluate_judge(
        {"name": "ordered", "type": "tool_call_match"},
        {
            "tool_calls": [
                {"name": "search_docs", "arguments": {"query": "python"}},
                {"name": "fetch_page", "arguments": {"id": "123"}},
            ]
        },
        {
            "tool_calls": [
                {"name": "fetch_page", "arguments": {"id": "123"}},
                {"name": "search_docs", "arguments": {"query": "python"}},
            ]
        },
        semantic_backend=NullSemanticBackend(),
    )

    assert result["passed"] is False


def test_judge_factory_dispatches_to_strategy_class() -> None:
    judge = DEFAULT_JUDGE_FACTORY.create(
        {
            "name": "ticket",
            "type": "regex_match",
            "field": "text",
            "pattern": "TICKET-[0-9]{6}",
        }
    )

    assert isinstance(judge, RegexJudge)


def test_judge_factory_rejects_unsupported_type() -> None:
    with pytest.raises(ValueError, match="Unsupported judge type"):
        DEFAULT_JUDGE_FACTORY.create({"name": "unknown", "type": "not-real"})


def test_tool_call_judge_reports_variable_binding_mismatch() -> None:
    result = evaluate_judge(
        {
            "name": "variables",
            "type": "tool_call_match",
            "tool_calls": [
                {
                    "name": "fetch_doc",
                    "arguments": {"doc_id": {"var": "$doc_id", "match": "exact"}},
                },
                {
                    "name": "fetch_doc",
                    "arguments": {"doc_id": {"var": "$doc_id", "match": "exact"}},
                },
            ],
        },
        {
            "tool_calls": [
                {"name": "fetch_doc", "arguments": {"doc_id": "abc"}},
                {"name": "fetch_doc", "arguments": {"doc_id": "xyz"}},
            ]
        },
        {
            "tool_calls": [
                {"name": "fetch_doc", "arguments": {"doc_id": "abc"}},
                {"name": "fetch_doc", "arguments": {"doc_id": "abc"}},
            ]
        },
        semantic_backend=NullSemanticBackend(),
    )

    assert result["passed"] is False
    assert result["details"]["reason"] == "baseline_binding_mismatch"
