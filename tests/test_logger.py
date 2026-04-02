import json

from logger.schema import build_record
from logger.writer import write_log


def test_build_record_includes_request_and_response() -> None:
    record = build_record(
        trace_id="trace-1",
        record_type="baseline",
        model="baseline-model",
        normalized={"text": "hello", "tool_name": None, "tool_args": None},
        latency=12,
        status="ok",
        raw_request={"messages": []},
        raw_response={"choices": []},
    )
    assert record["raw_request"] == {"messages": []}
    assert record["raw_response"] == {"choices": []}


def test_build_record_populates_error_metadata() -> None:
    record = build_record(
        trace_id="trace-1",
        record_type="candidate",
        model="candidate-model",
        normalized={"text": None, "tool_name": None, "tool_args": None},
        latency=13,
        status="error",
        raw_request={"messages": []},
        raw_response=None,
        error=RuntimeError("boom"),
    )
    assert record["error_type"] == "RuntimeError"
    assert record["error_message"] == "boom"


def test_write_log_writes_jsonl(tmp_path) -> None:
    path = tmp_path / "logs.jsonl"
    write_log({"trace_id": "abc"}, str(path))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{"trace_id": "abc"}]
