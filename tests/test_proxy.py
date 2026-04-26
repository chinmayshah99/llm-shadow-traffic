import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from config.settings import Settings
from logger.writer import JsonlRotatingLogWriter, LogWriter
from proxy.client import LLMClient
from proxy.main import app as default_app
from proxy.service import ShadowService


class RecordingBackupSink:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, str]] = []

    def backup(self, local_path: Path, object_name: str) -> None:
        self.calls.append((local_path, object_name))


class FailingBackupSink:
    def backup(self, local_path: Path, object_name: str) -> None:
        raise RuntimeError("s3 unavailable")


class MemoryLogWriter:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def write(self, record: dict) -> None:
        self.records.append(record)

    def close(self) -> None:
        return None


class StubClient:
    def __init__(self, *, response: dict | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error

    async def chat(self, payload: dict) -> dict:
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


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
    log_writer: LogWriter | None = None,
) -> None:
    settings = Settings()
    baseline_http = httpx.AsyncClient(transport=make_transport(baseline_handler))
    candidate_http = httpx.AsyncClient(transport=make_transport(candidate_handler))
    writer = log_writer or JsonlRotatingLogWriter(log_file=settings.log_file)
    baseline_client = LLMClient(
        client=baseline_http,
        base_url=settings.baseline_url,
        model=settings.baseline_model,
        timeout=settings.timeout,
    )
    candidate_client = LLMClient(
        client=candidate_http,
        base_url=settings.candidate_url,
        model=settings.candidate_model,
        timeout=settings.timeout,
    )
    default_app.state.shadow_service = ShadowService(
        settings=settings,
        baseline_client=baseline_client,
        candidate_client=candidate_client,
        log_writer=writer,
    )


async def close_clients() -> None:
    default_app.state.shadow_service.log_writer.close()
    await default_app.state.shadow_service.baseline_client._client.aclose()
    await default_app.state.shadow_service.candidate_client._client.aclose()


async def wait_for_lines(path: Path, expected: int) -> list[dict]:
    for _ in range(50):
        if path.exists():
            lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
            if len(lines) >= expected:
                return lines
        await asyncio.sleep(0.01)
    return []


async def wait_for_rotated_files(directory: Path, expected: int) -> list[Path]:
    for _ in range(50):
        rotated_files = list(directory.glob("logs.*.jsonl"))
        if len(rotated_files) >= expected:
            return rotated_files
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


@pytest.mark.asyncio
async def test_proxy_rotation_can_trigger_backup(env: Path) -> None:
    sink = RecordingBackupSink()
    writer = JsonlRotatingLogWriter(log_file=str(env), max_bytes=1, backup_sink=sink)

    await configure_clients(
        baseline_handler=lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "baseline"}}]}),
        candidate_handler=lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "candidate"}}]}),
        log_writer=writer,
    )

    transport = httpx.ASGITransport(app=default_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})

    assert response.status_code == 200
    rotated_files = await wait_for_rotated_files(env.parent, 2)
    assert len(rotated_files) == 2
    assert len(sink.calls) == 2
    assert env.exists()
    assert env.read_text(encoding="utf-8") == ""
    await close_clients()


@pytest.mark.asyncio
async def test_proxy_backup_failures_do_not_drop_local_records(env: Path) -> None:
    writer = JsonlRotatingLogWriter(log_file=str(env), max_bytes=1, backup_sink=FailingBackupSink())

    await configure_clients(
        baseline_handler=lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "baseline"}}]}),
        candidate_handler=lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "candidate"}}]}),
        log_writer=writer,
    )

    transport = httpx.ASGITransport(app=default_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})

    assert response.status_code == 200
    rotated_files = await wait_for_rotated_files(env.parent, 2)
    assert len(rotated_files) == 2
    contents = [json.loads(path.read_text(encoding="utf-8").strip()) for path in rotated_files]
    assert {row["type"] for row in contents} == {"baseline", "candidate"}
    await close_clients()


@pytest.mark.asyncio
async def test_shadow_service_maps_baseline_timeout_to_504(env: Path) -> None:
    settings = Settings()
    service = ShadowService(
        settings=settings,
        baseline_client=StubClient(error=httpx.ReadTimeout("boom")),
        candidate_client=StubClient(response={"choices": [{"message": {"content": "candidate"}}]}),
        log_writer=MemoryLogWriter(),
    )

    result = await service.handle_chat_completion({"messages": []})

    assert result.status_code == 504
    assert result.payload == {
        "error": {"message": "Baseline upstream timed out", "type": "timeout_error"}
    }


@pytest.mark.asyncio
async def test_shadow_service_process_candidate_writes_candidate_error_record(env: Path) -> None:
    settings = Settings()
    writer = MemoryLogWriter()
    service = ShadowService(
        settings=settings,
        baseline_client=StubClient(response={"choices": [{"message": {"content": "baseline"}}]}),
        candidate_client=StubClient(error=RuntimeError("candidate exploded")),
        log_writer=writer,
    )

    await service.process_candidate(
        trace_id="trace-1",
        request_payload={"messages": [{"role": "user", "content": "hello"}]},
        baseline_response={"choices": [{"message": {"content": "baseline"}}]},
        baseline_latency=25,
    )

    assert [record["type"] for record in writer.records] == ["baseline", "candidate"]
    assert writer.records[1]["status"] == "error"
    assert writer.records[1]["error_message"] == "candidate exploded"
