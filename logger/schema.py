from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_record(
    *,
    trace_id: str,
    record_type: str,
    model: str,
    normalized: dict[str, Any],
    latency: int,
    status: str,
    raw_request: dict[str, Any],
    raw_response: dict[str, Any] | None,
    error: Exception | None = None,
) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "timestamp": now_iso(),
        "type": record_type,
        "model": model,
        "text": normalized["text"],
        "tool_name": normalized["tool_name"],
        "tool_args": normalized["tool_args"],
        "tool_calls": normalized["tool_calls"],
        "latency_ms": latency,
        "status": status,
        "error_type": type(error).__name__ if error else None,
        "error_message": str(error) if error else None,
        "raw_request": raw_request,
        "raw_response": raw_response,
    }
