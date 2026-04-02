from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from config.settings import Settings
from logger.writer import write_log
from proxy.client import LLMClient
from proxy.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    baseline_http = httpx.AsyncClient()
    candidate_http = httpx.AsyncClient()

    app.state.settings = settings
    app.state.log_writer = write_log
    app.state.baseline_client = LLMClient(
        client=baseline_http,
        base_url=settings.baseline_url,
        model=settings.baseline_model,
        auth_header=settings.baseline_auth_header,
        timeout=settings.timeout,
    )
    app.state.candidate_client = LLMClient(
        client=candidate_http,
        base_url=settings.candidate_url,
        model=settings.candidate_model,
        auth_header=settings.candidate_auth_header,
        timeout=settings.timeout,
    )

    try:
        yield
    finally:
        await baseline_http.aclose()
        await candidate_http.aclose()


app = FastAPI(title="LLM Shadow Proxy", lifespan=lifespan)
app.include_router(router)
