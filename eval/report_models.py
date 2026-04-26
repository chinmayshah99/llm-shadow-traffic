from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LatencyStats:
    avg_ms: float | None
    p50_ms: float | None
    p95_ms: float | None


@dataclass
class ShadowReport:
    total_records: int
    total_traces: int
    paired_traces: int
    successful_pairs: int
    candidate_error_count: int
    candidate_error_rate: float | None
    tool_comparable_pairs: int
    tool_match_count: int
    tool_match_percent: float | None
    baseline_latency: LatencyStats
    candidate_latency: LatencyStats
    status_breakdown: list[dict[str, Any]]
    top_tools: list[dict[str, Any]]
    worst_latency_deltas: list[dict[str, Any]]
    tool_mismatches: list[dict[str, Any]]
    candidate_errors: list[dict[str, Any]]
    recent_pairs: list[dict[str, Any]]


@dataclass
class BatchReport:
    row_count: int
    success_count: int
    error_count: int
    error_rate: float | None
    latency: LatencyStats | None
    model_distribution: list[dict[str, Any]]
    sample_rows: list[dict[str, Any]]
    detected_fields: list[str]
    limited_fields_detected: bool


@dataclass
class ReportData:
    title: str
    generated_at: str
    shadow: ShadowReport
    batch: BatchReport | None
