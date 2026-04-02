import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from config.settings import Settings
from logger.writer import write_log
from proxy.client import LLMClient
from proxy.main import app as default_app


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setenv("BASELINE_URL", "https://baseline.example")
    monkeypatch.setenv("CANDIDATE_URL", "https://candidate.example")
    monkeypatch.setenv("BASELINE_MODEL", "baseline-model")
    monkeypatch.setenv("CANDIDATE_MODEL", "candidate-model")
    monkeypatch.setenv("LOG_FILE", str(log_path))
    yield log_path


def make_transport(handler):
    return httpx.MockTransport(handler)


async def configure_clients(
    *,
    baseline_handler,
    candidate_handler,
) -> None:
    settings = Settings()
    baseline_http = httpx.AsyncClient(transport=make_transport(baseline_handler))
    candidate_http = httpx.AsyncClient(transport=make_transport(candidate_handler))
    default_app.state.settings = settings
    default_app.state.log_writer = write_log
    default_app.state.baseline_client = LLMClient(
        client=baseline_http,
        base_url=settings.baseline_url,
        model=settings.baseline_model,
        timeout=settings.timeout,
    )
    default_app.state.candidate_client = LLMClient(
        client=candidate_http,
        base_url=settings.candidate_url,
        model=settings.candidate_model,
        timeout=settings.timeout,
    )


async def close_clients() -> None:
    await default_app.state.baseline_client._client.aclose()
    await default_app.state.candidate_client._client.aclose()


async def wait_for_lines(path: Path, expected: int) -> list[dict]:
    for _ in range(50):
        if path.exists():
            lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
            if len(lines) >= expected:
                return lines
        await asyncio.sleep(0.01)
    return []


@pytest.mark.asyncio
async def test_proxy_returns_baseline_and_logs_both_records(env: Path) -> None:
    def baseline_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "baseline-model"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "baseline answer"}}]},
        )

    def candidate_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "candidate-model"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "candidate answer"}}]},
        )

    await configure_clients(baseline_handler=baseline_handler, candidate_handler=candidate_handler)

    transport = httpx.ASGITransport(app=default_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "baseline answer"

    lines = await wait_for_lines(env, 2)
    assert len(lines) == 2
    assert {line["type"] for line in lines} == {"baseline", "candidate"}
    assert all(line["raw_request"]["messages"][0]["content"] == "hello" for line in lines)
    await close_clients()


@pytest.mark.asyncio
async def test_proxy_logs_candidate_error_without_crashing(env: Path) -> None:
    def baseline_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "baseline answer"}}]})

    def candidate_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "candidate failed"}})

    await configure_clients(baseline_handler=baseline_handler, candidate_handler=candidate_handler)

    transport = httpx.ASGITransport(app=default_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/v1/chat/completions", json={"messages": []})

    assert response.status_code == 200
    lines = await wait_for_lines(env, 2)
    candidate_record = next(line for line in lines if line["type"] == "candidate")
    assert candidate_record["status"] == "error"
    assert candidate_record["raw_request"] == {"messages": []}
    assert candidate_record["raw_response"] is None
    await close_clients()


@pytest.mark.asyncio
async def test_proxy_passes_through_baseline_failure_and_skips_logging(env: Path) -> None:
    def baseline_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"error": {"message": "baseline failed", "type": "server_error"}})

    await configure_clients(
        baseline_handler=baseline_handler,
        candidate_handler=lambda _: httpx.Response(200, json={}),
    )

    transport = httpx.ASGITransport(app=default_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/v1/chat/completions", json={"messages": []})

    assert response.status_code == 502
    assert response.json()["error"]["message"] == "baseline failed"
    await asyncio.sleep(0.05)
    assert not env.exists()
    await close_clients()
