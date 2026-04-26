import json
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

from eval.report import build_batch_report, build_report, build_shadow_report, render_report_html
from eval.report_renderer import ReportRenderer
from eval.report_service import ReportService


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_build_shadow_report_computes_metrics_and_tables(tmp_path: Path) -> None:
    shadow_file = _write_jsonl(
        tmp_path / "shadow.jsonl",
        [
            {
                "trace_id": "t1",
                "timestamp": "2026-04-01T00:00:01+00:00",
                "type": "baseline",
                "model": "baseline-model",
                "text": "baseline one",
                "tool_name": "search",
                "tool_args": {"q": "weather"},
                "latency_ms": 100,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "raw_request": {"messages": []},
                "raw_response": {"choices": []},
            },
            {
                "trace_id": "t1",
                "timestamp": "2026-04-01T00:00:02+00:00",
                "type": "candidate",
                "model": "candidate-model",
                "text": "candidate one",
                "tool_name": "search",
                "tool_args": {"q": "weather"},
                "latency_ms": 180,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "raw_request": {"messages": []},
                "raw_response": {"choices": []},
            },
            {
                "trace_id": "t2",
                "timestamp": "2026-04-01T00:01:01+00:00",
                "type": "baseline",
                "model": "baseline-model",
                "text": "baseline two",
                "tool_name": "search",
                "tool_args": {"q": "news"},
                "latency_ms": 120,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "raw_request": {"messages": []},
                "raw_response": {"choices": []},
            },
            {
                "trace_id": "t2",
                "timestamp": "2026-04-01T00:01:02+00:00",
                "type": "candidate",
                "model": "candidate-model",
                "text": "candidate two",
                "tool_name": "lookup",
                "tool_args": {"q": "news"},
                "latency_ms": 300,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "raw_request": {"messages": []},
                "raw_response": {"choices": []},
            },
            {
                "trace_id": "t3",
                "timestamp": "2026-04-01T00:02:01+00:00",
                "type": "baseline",
                "model": "baseline-model",
                "text": "baseline three",
                "tool_name": None,
                "tool_args": None,
                "latency_ms": 90,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "raw_request": {"messages": []},
                "raw_response": {"choices": []},
            },
            {
                "trace_id": "t3",
                "timestamp": "2026-04-01T00:02:02+00:00",
                "type": "candidate",
                "model": "candidate-model",
                "text": None,
                "tool_name": None,
                "tool_args": None,
                "latency_ms": 400,
                "status": "error",
                "error_type": "RuntimeError",
                "error_message": "candidate failed",
                "raw_request": {"messages": []},
                "raw_response": None,
            },
        ],
    )

    report = build_shadow_report(shadow_file)

    assert report.total_records == 6
    assert report.total_traces == 3
    assert report.paired_traces == 3
    assert report.successful_pairs == 2
    assert report.candidate_error_count == 1
    assert report.candidate_error_rate == pytest.approx(33.33, abs=0.01)
    assert report.tool_comparable_pairs == 2
    assert report.tool_match_count == 1
    assert report.tool_match_percent == 50.0
    assert report.baseline_latency.avg_ms == pytest.approx(103.33, abs=0.01)
    assert report.candidate_latency.p50_ms == 300.0
    assert report.worst_latency_deltas[0]["trace_id"] == "t3"
    assert report.tool_mismatches[0]["trace_id"] == "t2"
    assert report.candidate_errors[0]["candidate_error_message"] == "candidate failed"


def test_build_batch_report_handles_success_error_and_missing_optional_fields(tmp_path: Path) -> None:
    batch_file = _write_jsonl(
        tmp_path / "batch.jsonl",
        [
            {
                "custom_id": "req-1",
                "response": {
                    "status_code": 200,
                    "body": {
                        "model": "gpt-4o-mini",
                        "choices": [{"message": {"content": "hello"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    },
                    "latency_ms": 220,
                },
                "error": None,
            },
            {
                "custom_id": "req-2",
                "response": None,
                "error": {"code": "server_error", "message": "bad upstream"},
            },
        ],
    )

    report = build_batch_report(batch_file)

    assert report.row_count == 2
    assert report.success_count == 1
    assert report.error_count == 1
    assert report.error_rate == 50.0
    assert report.latency is not None
    assert report.latency.avg_ms == 220.0
    assert report.model_distribution == [{"model": "gpt-4o-mini", "count": 1}]
    assert report.sample_rows[1]["error_message"] == "bad upstream"
    assert report.limited_fields_detected is True


def test_render_and_write_report_html_with_optional_batch_section(tmp_path: Path) -> None:
    shadow_file = _write_jsonl(
        tmp_path / "shadow.jsonl",
        [
            {
                "trace_id": "trace-a",
                "timestamp": "2026-04-01T00:00:01+00:00",
                "type": "baseline",
                "model": "base",
                "text": "alpha",
                "tool_name": None,
                "tool_args": None,
                "latency_ms": 50,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "raw_request": {"messages": []},
                "raw_response": {"choices": []},
            },
            {
                "trace_id": "trace-a",
                "timestamp": "2026-04-01T00:00:02+00:00",
                "type": "candidate",
                "model": "cand",
                "text": "beta",
                "tool_name": None,
                "tool_args": None,
                "latency_ms": 70,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "raw_request": {"messages": []},
                "raw_response": {"choices": []},
            },
        ],
    )
    batch_file = _write_jsonl(
        tmp_path / "batch.jsonl",
        [
            {
                "custom_id": "batch-1",
                "response": {
                    "status_code": 200,
                    "body": {
                        "model": "gpt-4o-mini",
                        "choices": [{"message": {"content": "batched answer"}}],
                    },
                },
                "error": None,
            }
        ],
    )

    out_path = tmp_path / "report.html"
    report = build_report(
        file_path=shadow_file,
        out_path=out_path,
        batch_file=batch_file,
        title="Custom Report",
    )

    assert out_path.exists()
    html = out_path.read_text(encoding="utf-8")
    assert report.title == "Custom Report"
    assert "Shadow Summary" in html
    assert "Worst Candidate Latency Deltas" in html
    assert "Batch Summary" in html
    assert "Custom Report" in html
    assert "trace-a" in html
    assert "batch-1" in html


def test_render_report_html_without_batch_section(tmp_path: Path) -> None:
    shadow_file = _write_jsonl(
        tmp_path / "shadow.jsonl",
        [
            {
                "trace_id": "trace-b",
                "timestamp": "2026-04-01T00:00:01+00:00",
                "type": "baseline",
                "model": "base",
                "text": "alpha",
                "tool_name": None,
                "tool_args": None,
                "latency_ms": 50,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "raw_request": {"messages": []},
                "raw_response": {"choices": []},
            },
            {
                "trace_id": "trace-b",
                "timestamp": "2026-04-01T00:00:02+00:00",
                "type": "candidate",
                "model": "cand",
                "text": "beta",
                "tool_name": None,
                "tool_args": None,
                "latency_ms": 60,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "raw_request": {"messages": []},
                "raw_response": {"choices": []},
            },
        ],
    )

    report = build_report(
        file_path=shadow_file,
        out_path=tmp_path / "report-no-batch.html",
    )
    html = render_report_html(report)

    assert "Batch Summary" not in html


def test_report_service_and_renderer_keep_public_report_output_compatible(tmp_path: Path) -> None:
    shadow_file = _write_jsonl(
        tmp_path / "shadow.jsonl",
        [
            {
                "trace_id": "trace-c",
                "timestamp": "2026-04-01T00:00:01+00:00",
                "type": "baseline",
                "model": "base",
                "text": "alpha",
                "tool_name": None,
                "tool_args": None,
                "latency_ms": 40,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "raw_request": {"messages": []},
                "raw_response": {"choices": []},
            },
            {
                "trace_id": "trace-c",
                "timestamp": "2026-04-01T00:00:02+00:00",
                "type": "candidate",
                "model": "cand",
                "text": "beta",
                "tool_name": None,
                "tool_args": None,
                "latency_ms": 65,
                "status": "ok",
                "error_type": None,
                "error_message": None,
                "raw_request": {"messages": []},
                "raw_response": {"choices": []},
            },
        ],
    )

    out_path = tmp_path / "service-report.html"
    service = ReportService()
    renderer = ReportRenderer()

    report = service.build_report(
        file_path=shadow_file,
        out_path=out_path,
        renderer=renderer,
        title="Service Report",
    )

    html = out_path.read_text(encoding="utf-8")
    assert report.title == "Service Report"
    assert "Shadow Summary" in html
    assert "Recent Paired Traces" in html
    assert renderer.render(report) == html
