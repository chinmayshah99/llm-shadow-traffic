from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from eval.report_models import BatchReport, LatencyStats, ReportData, ShadowReport


class HtmlRenderer(Protocol):
    def render(self, report: ReportData) -> str:
        ...


def _import_duckdb() -> Any:
    try:
        import duckdb
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "duckdb is required for HTML reports. Install it with `uv sync --extra analysis`."
        ) from exc
    return duckdb


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _round(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _percent(part: int, whole: int) -> float | None:
    if whole == 0:
        return None
    return round(part / whole * 100, 2)


def _duckdb_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _scalar(connection: Any, query: str, params: list[Any] | None = None) -> Any:
    return connection.execute(query, params or []).fetchone()[0]


def _rows(connection: Any, query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    columns = [item[0] for item in connection.execute(query, params or []).description]
    return [dict(zip(columns, row, strict=True)) for row in connection.fetchall()]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _first_present(mapping: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _normalize_batch_row(row: dict[str, Any]) -> dict[str, Any]:
    response = row.get("response") or {}
    body = response.get("body") or {}
    choices = body.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    tool_calls = message.get("tool_calls") or []
    first_tool = tool_calls[0] if tool_calls else {}
    function = first_tool.get("function") or {}
    usage = body.get("usage") or {}
    error = row.get("error")
    status_code = response.get("status_code")
    latency_ms = _first_present(
        row,
        ["latency_ms", "duration_ms", "elapsed_ms"],
    )
    if latency_ms is None and isinstance(response, dict):
        latency_ms = _first_present(response, ["latency_ms", "duration_ms", "elapsed_ms"])
    if latency_ms is None and isinstance(body, dict):
        latency_ms = _first_present(body, ["latency_ms", "duration_ms", "elapsed_ms"])

    success = False
    if isinstance(status_code, int):
        success = 200 <= status_code < 300 and not error
    elif response:
        success = not error

    normalized = {
        "custom_id": row.get("custom_id") or row.get("id") or "",
        "status": "error" if error or (isinstance(status_code, int) and status_code >= 400) else "ok",
        "status_code": status_code,
        "model": body.get("model"),
        "text": message.get("content"),
        "tool_name": function.get("name"),
        "latency_ms": latency_ms,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "error_code": error.get("code") if isinstance(error, dict) else None,
        "error_message": error.get("message") if isinstance(error, dict) else None,
        "success": success,
    }
    normalized["detected_fields"] = [
        name
        for name in ["custom_id", "model", "text", "tool_name", "latency_ms", "total_tokens"]
        if normalized.get(name) not in (None, "")
    ]
    return normalized


class ReportService:
    def build_shadow_report(self, path: Path) -> ShadowReport:
        duckdb = _import_duckdb()
        connection = duckdb.connect(database=":memory:")
        try:
            path_literal = _duckdb_string_literal(str(path))
            connection.execute(
                f"""
                CREATE VIEW shadow_records AS
                SELECT *
                FROM read_json({path_literal}, format='newline_delimited')
                """,
            )
            connection.execute(
                """
                CREATE VIEW paired_records AS
                SELECT
                  trace_id,
                  max(CASE WHEN type = 'baseline' THEN timestamp END) AS baseline_timestamp,
                  max(CASE WHEN type = 'candidate' THEN timestamp END) AS candidate_timestamp,
                  max(CASE WHEN type = 'baseline' THEN model END) AS baseline_model,
                  max(CASE WHEN type = 'candidate' THEN model END) AS candidate_model,
                  max(CASE WHEN type = 'baseline' THEN latency_ms END) AS baseline_latency_ms,
                  max(CASE WHEN type = 'candidate' THEN latency_ms END) AS candidate_latency_ms,
                  max(CASE WHEN type = 'baseline' THEN status END) AS baseline_status,
                  max(CASE WHEN type = 'candidate' THEN status END) AS candidate_status,
                  max(CASE WHEN type = 'baseline' THEN tool_name END) AS baseline_tool_name,
                  max(CASE WHEN type = 'candidate' THEN tool_name END) AS candidate_tool_name,
                  max(CASE WHEN type = 'baseline' THEN error_type END) AS baseline_error_type,
                  max(CASE WHEN type = 'candidate' THEN error_type END) AS candidate_error_type,
                  max(CASE WHEN type = 'baseline' THEN error_message END) AS baseline_error_message,
                  max(CASE WHEN type = 'candidate' THEN error_message END) AS candidate_error_message,
                  max(CASE WHEN type = 'baseline' THEN text END) AS baseline_text,
                  max(CASE WHEN type = 'candidate' THEN text END) AS candidate_text,
                  max(CASE WHEN type = 'baseline' THEN CAST(tool_args AS VARCHAR) END) AS baseline_tool_args,
                  max(CASE WHEN type = 'candidate' THEN CAST(tool_args AS VARCHAR) END) AS candidate_tool_args
                FROM shadow_records
                GROUP BY trace_id
                """
            )

            total_records = int(_scalar(connection, "SELECT count(*) FROM shadow_records"))
            total_traces = int(_scalar(connection, "SELECT count(DISTINCT trace_id) FROM shadow_records"))
            paired_traces = int(
                _scalar(
                    connection,
                    """
                    SELECT count(*)
                    FROM paired_records
                    WHERE baseline_timestamp IS NOT NULL AND candidate_timestamp IS NOT NULL
                    """,
                )
            )
            successful_pairs = int(
                _scalar(
                    connection,
                    """
                    SELECT count(*)
                    FROM paired_records
                    WHERE baseline_timestamp IS NOT NULL
                      AND candidate_timestamp IS NOT NULL
                      AND baseline_status = 'ok'
                      AND candidate_status = 'ok'
                    """,
                )
            )
            candidate_total = int(
                _scalar(connection, "SELECT count(*) FROM shadow_records WHERE type = 'candidate'")
            )
            candidate_error_count = int(
                _scalar(
                    connection,
                    "SELECT count(*) FROM shadow_records WHERE type = 'candidate' AND status = 'error'",
                )
            )

            tool_stats = connection.execute(
                """
                SELECT
                  count(*) AS comparable_pairs,
                  sum(
                    CASE
                      WHEN baseline_tool_name = candidate_tool_name THEN 1
                      ELSE 0
                    END
                  ) AS matching_pairs
                FROM paired_records
                WHERE baseline_timestamp IS NOT NULL
                  AND candidate_timestamp IS NOT NULL
                  AND baseline_status = 'ok'
                  AND candidate_status = 'ok'
                  AND baseline_tool_name IS NOT NULL
                  AND candidate_tool_name IS NOT NULL
                """
            ).fetchone()
            tool_comparable_pairs = int(tool_stats[0] or 0)
            tool_match_count = int(tool_stats[1] or 0)

            status_breakdown = _rows(
                connection,
                """
                SELECT type, status, count(*) AS count
                FROM shadow_records
                GROUP BY type, status
                ORDER BY type, status
                """,
            )
            top_tools = _rows(
                connection,
                """
                SELECT type, tool_name, count(*) AS count
                FROM shadow_records
                WHERE tool_name IS NOT NULL
                GROUP BY type, tool_name
                ORDER BY count DESC, type ASC, tool_name ASC
                LIMIT 10
                """,
            )
            worst_latency_deltas = _rows(
                connection,
                """
                SELECT
                  trace_id,
                  baseline_latency_ms,
                  candidate_latency_ms,
                  candidate_latency_ms - baseline_latency_ms AS latency_delta_ms,
                  baseline_status,
                  candidate_status,
                  baseline_tool_name,
                  candidate_tool_name
                FROM paired_records
                WHERE baseline_latency_ms IS NOT NULL AND candidate_latency_ms IS NOT NULL
                ORDER BY latency_delta_ms DESC, trace_id ASC
                LIMIT 10
                """,
            )
            tool_mismatches = _rows(
                connection,
                """
                SELECT
                  trace_id,
                  baseline_tool_name,
                  candidate_tool_name,
                  baseline_tool_args,
                  candidate_tool_args
                FROM paired_records
                WHERE baseline_timestamp IS NOT NULL
                  AND candidate_timestamp IS NOT NULL
                  AND baseline_status = 'ok'
                  AND candidate_status = 'ok'
                  AND baseline_tool_name IS NOT NULL
                  AND candidate_tool_name IS NOT NULL
                  AND baseline_tool_name <> candidate_tool_name
                ORDER BY coalesce(candidate_timestamp, baseline_timestamp) DESC, trace_id ASC
                LIMIT 10
                """,
            )
            candidate_errors = _rows(
                connection,
                """
                SELECT
                  trace_id,
                  candidate_error_type,
                  candidate_error_message,
                  candidate_latency_ms,
                  baseline_status,
                  candidate_status
                FROM paired_records
                WHERE candidate_status = 'error'
                ORDER BY candidate_timestamp DESC, trace_id ASC
                LIMIT 10
                """,
            )
            recent_pairs = _rows(
                connection,
                """
                SELECT
                  trace_id,
                  baseline_status,
                  candidate_status,
                  baseline_latency_ms,
                  candidate_latency_ms,
                  baseline_tool_name,
                  candidate_tool_name,
                  baseline_text,
                  candidate_text
                FROM paired_records
                WHERE baseline_timestamp IS NOT NULL AND candidate_timestamp IS NOT NULL
                ORDER BY coalesce(candidate_timestamp, baseline_timestamp) DESC, trace_id ASC
                LIMIT 10
                """,
            )

            return ShadowReport(
                total_records=total_records,
                total_traces=total_traces,
                paired_traces=paired_traces,
                successful_pairs=successful_pairs,
                candidate_error_count=candidate_error_count,
                candidate_error_rate=_percent(candidate_error_count, candidate_total),
                tool_comparable_pairs=tool_comparable_pairs,
                tool_match_count=tool_match_count,
                tool_match_percent=_percent(tool_match_count, tool_comparable_pairs),
                baseline_latency=self._latency_stats(connection, "baseline"),
                candidate_latency=self._latency_stats(connection, "candidate"),
                status_breakdown=status_breakdown,
                top_tools=top_tools,
                worst_latency_deltas=worst_latency_deltas,
                tool_mismatches=tool_mismatches,
                candidate_errors=candidate_errors,
                recent_pairs=recent_pairs,
            )
        finally:
            connection.close()

    def build_batch_report(self, path: Path) -> BatchReport:
        rows = [_normalize_batch_row(row) for row in _load_jsonl(path)]
        row_count = len(rows)
        success_count = sum(1 for row in rows if row["success"])
        error_count = sum(1 for row in rows if row["status"] == "error")

        model_counts: dict[str, int] = {}
        detected_fields = {
            field
            for row in rows
            for field in row["detected_fields"]
        }
        sample_rows = [
            {
                "custom_id": row["custom_id"],
                "status": row["status"],
                "status_code": row["status_code"],
                "model": row["model"],
                "tool_name": row["tool_name"],
                "text": row["text"] if row["text"] is None or len(str(row["text"])) <= 120 else f"{str(row['text'])[:117]}...",
                "total_tokens": row["total_tokens"],
                "error_message": (
                    row["error_message"]
                    if row["error_message"] is None or len(str(row["error_message"])) <= 120
                    else f"{str(row['error_message'])[:117]}..."
                ),
            }
            for row in rows[:10]
        ]
        for row in rows:
            if row["model"]:
                model_counts[row["model"]] = model_counts.get(row["model"], 0) + 1

        model_distribution = [
            {"model": model, "count": count}
            for model, count in sorted(model_counts.items(), key=lambda item: (-item[1], item[0]))
        ]

        return BatchReport(
            row_count=row_count,
            success_count=success_count,
            error_count=error_count,
            error_rate=_percent(error_count, row_count),
            latency=self._batch_latency_stats(rows),
            model_distribution=model_distribution,
            sample_rows=sample_rows,
            detected_fields=sorted(detected_fields),
            limited_fields_detected=not {
                "custom_id",
                "model",
                "text",
                "tool_name",
                "latency_ms",
                "total_tokens",
            }.issubset(detected_fields),
        )

    def build_report(
        self,
        *,
        file_path: Path,
        out_path: Path,
        batch_file: Path | None = None,
        title: str | None = None,
        renderer: HtmlRenderer,
    ) -> ReportData:
        report = ReportData(
            title=title or "LLM Shadow Analysis Report",
            generated_at=_now_iso(),
            shadow=self.build_shadow_report(file_path),
            batch=self.build_batch_report(batch_file) if batch_file else None,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(renderer.render(report), encoding="utf-8")
        return report

    def _latency_stats(self, connection: Any, record_type: str) -> LatencyStats:
        row = connection.execute(
            """
            SELECT
              avg(latency_ms) AS avg_ms,
              quantile_cont(latency_ms, 0.5) AS p50_ms,
              quantile_cont(latency_ms, 0.95) AS p95_ms
            FROM shadow_records
            WHERE type = ?
            """,
            [record_type],
        ).fetchone()
        return LatencyStats(
            avg_ms=_round(row[0]),
            p50_ms=_round(row[1]),
            p95_ms=_round(row[2]),
        )

    def _batch_latency_stats(self, rows: list[dict[str, Any]]) -> LatencyStats | None:
        latencies = [float(row["latency_ms"]) for row in rows if row.get("latency_ms") is not None]
        if not latencies:
            return None

        duckdb = _import_duckdb()
        connection = duckdb.connect(database=":memory:")
        try:
            connection.execute("CREATE TABLE batch_latency(latency_ms DOUBLE)")
            connection.executemany(
                "INSERT INTO batch_latency(latency_ms) VALUES (?)",
                [(latency,) for latency in latencies],
            )
            row = connection.execute(
                """
                SELECT
                  avg(latency_ms) AS avg_ms,
                  quantile_cont(latency_ms, 0.5) AS p50_ms,
                  quantile_cont(latency_ms, 0.95) AS p95_ms
                FROM batch_latency
                """
            ).fetchone()
        finally:
            connection.close()

        return LatencyStats(
            avg_ms=_round(row[0]),
            p50_ms=_round(row[1]),
            p95_ms=_round(row[2]),
        )
