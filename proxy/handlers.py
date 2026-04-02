from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

from config.settings import Settings
from logger.schema import build_record
from logger.writer import write_log
from normalizer.normalize import normalize
from proxy.client import LLMClient, UpstreamHTTPError
from utils.ids import generate_id
from utils.timing import elapsed_ms

LogWriter = Callable[[dict[str, Any], str], None]


async def handle_chat_completion(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    baseline_client: LLMClient = request.app.state.baseline_client
    candidate_client: LLMClient = request.app.state.candidate_client
    log_writer: LogWriter = request.app.state.log_writer

    payload = await request.json()
    trace_id = generate_id()
    baseline_start = perf_counter()

    try:
        baseline_response = await baseline_client.chat(payload)
    except UpstreamHTTPError as exc:
        return JSONResponse(status_code=exc.status_code, content=exc.payload)
    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={"error": {"message": "Baseline upstream timed out", "type": "timeout_error"}},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=502,
            content={"error": {"message": str(exc), "type": type(exc).__name__}},
        )

    baseline_latency = elapsed_ms(baseline_start)
    asyncio.create_task(
        process_candidate(
            trace_id=trace_id,
            request_payload=payload,
            baseline_response=baseline_response,
            baseline_latency=baseline_latency,
            candidate_client=candidate_client,
            settings=settings,
            log_writer=log_writer,
        )
    )
    return JSONResponse(status_code=200, content=baseline_response)


async def process_candidate(
    *,
    trace_id: str,
    request_payload: dict[str, Any],
    baseline_response: dict[str, Any],
    baseline_latency: int,
    candidate_client: LLMClient,
    settings: Settings,
    log_writer: LogWriter,
) -> None:
    baseline_norm = normalize(baseline_response)
    log_writer(
        build_record(
            trace_id=trace_id,
            record_type="baseline",
            model=settings.baseline_model,
            normalized=baseline_norm,
            latency=baseline_latency,
            status="ok",
            raw_request=request_payload,
            raw_response=baseline_response,
        ),
        settings.log_file,
    )

    candidate_start = perf_counter()
    candidate_response: dict[str, Any] | None = None
    candidate_error: Exception | None = None

    try:
        candidate_response = await candidate_client.chat(request_payload)
        candidate_status = "ok"
    except Exception as exc:
        candidate_error = exc
        candidate_status = "error"

    candidate_latency = elapsed_ms(candidate_start)
    candidate_norm = normalize(candidate_response)
    log_writer(
        build_record(
            trace_id=trace_id,
            record_type="candidate",
            model=settings.candidate_model,
            normalized=candidate_norm,
            latency=candidate_latency,
            status=candidate_status,
            error=candidate_error,
            raw_request=request_payload,
            raw_response=candidate_response,
        ),
        settings.log_file,
    )
