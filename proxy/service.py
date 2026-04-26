from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx

from config.settings import Settings
from logger.schema import build_record
from logger.writer import LogWriter
from normalizer.normalize import normalize
from proxy.client import LLMClient, UpstreamHTTPError
from utils.ids import generate_id
from utils.timing import elapsed_ms


@dataclass(slots=True)
class ServiceResponse:
    status_code: int
    payload: dict[str, Any]


class ShadowService:
    def __init__(
        self,
        *,
        settings: Settings,
        baseline_client: LLMClient,
        candidate_client: LLMClient,
        log_writer: LogWriter,
    ) -> None:
        self.settings = settings
        self.baseline_client = baseline_client
        self.candidate_client = candidate_client
        self.log_writer = log_writer

    async def handle_chat_completion(self, payload: dict[str, Any]) -> ServiceResponse:
        trace_id = generate_id()
        baseline_start = perf_counter()

        try:
            baseline_response = await self.baseline_client.chat(payload)
        except UpstreamHTTPError as exc:
            return ServiceResponse(status_code=exc.status_code, payload=exc.payload)
        except httpx.TimeoutException:
            return ServiceResponse(
                status_code=504,
                payload={
                    "error": {
                        "message": "Baseline upstream timed out",
                        "type": "timeout_error",
                    }
                },
            )
        except Exception as exc:
            return ServiceResponse(
                status_code=502,
                payload={
                    "error": {
                        "message": str(exc),
                        "type": type(exc).__name__,
                    }
                },
            )

        baseline_latency = elapsed_ms(baseline_start)
        asyncio.create_task(
            self.process_candidate(
                trace_id=trace_id,
                request_payload=payload,
                baseline_response=baseline_response,
                baseline_latency=baseline_latency,
            )
        )
        return ServiceResponse(status_code=200, payload=baseline_response)

    async def process_candidate(
        self,
        *,
        trace_id: str,
        request_payload: dict[str, Any],
        baseline_response: dict[str, Any],
        baseline_latency: int,
    ) -> None:
        baseline_norm = normalize(baseline_response)
        self.log_writer.write(
            build_record(
                trace_id=trace_id,
                record_type="baseline",
                model=self.settings.baseline_model,
                normalized=baseline_norm,
                latency=baseline_latency,
                status="ok",
                raw_request=request_payload,
                raw_response=baseline_response,
            )
        )

        candidate_start = perf_counter()
        candidate_response: dict[str, Any] | None = None
        candidate_error: Exception | None = None

        try:
            candidate_response = await self.candidate_client.chat(request_payload)
            candidate_status = "ok"
        except Exception as exc:
            candidate_error = exc
            candidate_status = "error"

        candidate_latency = elapsed_ms(candidate_start)
        candidate_norm = normalize(candidate_response)
        self.log_writer.write(
            build_record(
                trace_id=trace_id,
                record_type="candidate",
                model=self.settings.candidate_model,
                normalized=candidate_norm,
                latency=candidate_latency,
                status=candidate_status,
                error=candidate_error,
                raw_request=request_payload,
                raw_response=candidate_response,
            )
        )
