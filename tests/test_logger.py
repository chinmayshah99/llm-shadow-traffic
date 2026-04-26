import json
import logging
from pathlib import Path

import pytest

from logger.schema import build_record
from logger.writer import JsonlRotatingLogWriter, S3BackupSink


class RecordingBackupSink:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, str]] = []

    def backup(self, local_path: Path, object_name: str) -> None:
        self.calls.append((local_path, object_name))


class FailingBackupSink:
    def backup(self, local_path: Path, object_name: str) -> None:
        raise RuntimeError(f"failed to upload {object_name}")


class FakeS3Client:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def upload_file(self, filename: str, bucket: str, key: str, ExtraArgs: dict[str, str] | None = None) -> None:
        self.calls.append(
            {
                "filename": filename,
                "bucket": bucket,
                "key": key,
                "extra_args": ExtraArgs,
            }
        )


def test_build_record_includes_request_and_response() -> None:
    record = build_record(
        trace_id="trace-1",
        record_type="baseline",
        model="baseline-model",
        normalized={"text": "hello", "tool_name": None, "tool_args": None, "tool_calls": []},
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
        normalized={"text": None, "tool_name": None, "tool_args": None, "tool_calls": []},
        latency=13,
        status="error",
        raw_request={"messages": []},
        raw_response=None,
        error=RuntimeError("boom"),
    )
    assert record["error_type"] == "RuntimeError"
    assert record["error_message"] == "boom"


def test_writer_appends_jsonl_locally(tmp_path: Path) -> None:
    path = tmp_path / "logs.jsonl"
    writer = JsonlRotatingLogWriter(log_file=str(path))

    writer.write({"trace_id": "abc"})

    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{"trace_id": "abc"}]


def test_writer_rotates_and_backs_up_segments(tmp_path: Path) -> None:
    path = tmp_path / "logs.jsonl"
    sink = RecordingBackupSink()
    writer = JsonlRotatingLogWriter(log_file=str(path), max_bytes=1, backup_sink=sink)

    writer.write({"trace_id": "abc"})

    assert path.exists()
    assert path.read_text(encoding="utf-8") == ""
    assert len(sink.calls) == 1

    rotated_path, object_name = sink.calls[0]
    assert rotated_path.exists()
    assert rotated_path.name == object_name
    assert rotated_path.name.startswith("logs.")
    assert rotated_path.name.endswith(".0001.jsonl")
    assert json.loads(rotated_path.read_text(encoding="utf-8").strip()) == {"trace_id": "abc"}


def test_writer_logs_backup_failures_but_keeps_local_segments(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "logs.jsonl"
    writer = JsonlRotatingLogWriter(log_file=str(path), max_bytes=1, backup_sink=FailingBackupSink())

    with caplog.at_level(logging.ERROR):
        writer.write({"trace_id": "abc"})

    assert "Failed to back up rotated log segment" in caplog.text
    rotated_files = list(tmp_path.glob("logs.*.jsonl"))
    assert len(rotated_files) == 1
    assert json.loads(rotated_files[0].read_text(encoding="utf-8").strip()) == {"trace_id": "abc"}


def test_writer_close_rotates_final_segment(tmp_path: Path) -> None:
    path = tmp_path / "logs.jsonl"
    sink = RecordingBackupSink()
    writer = JsonlRotatingLogWriter(log_file=str(path), max_bytes=1024, backup_sink=sink)

    writer.write({"trace_id": "abc"})
    writer.close()

    assert not path.exists()
    assert len(sink.calls) == 1
    rotated_path, _ = sink.calls[0]
    assert json.loads(rotated_path.read_text(encoding="utf-8").strip()) == {"trace_id": "abc"}


def test_s3_backup_sink_uploads_with_prefix_and_extra_args(tmp_path: Path) -> None:
    path = tmp_path / "logs.20260406T120000000000Z.0001.jsonl"
    path.write_text('{"trace_id":"abc"}\n', encoding="utf-8")
    client = FakeS3Client()
    sink = S3BackupSink(
        bucket="shadow-backups",
        prefix="daily/logs",
        kms_key_id="kms-key",
        storage_class="STANDARD_IA",
        s3_client=client,
    )

    sink.backup(path, path.name)

    assert client.calls == [
        {
            "filename": str(path),
            "bucket": "shadow-backups",
            "key": "daily/logs/logs.20260406T120000000000Z.0001.jsonl",
            "extra_args": {
                "ServerSideEncryption": "aws:kms",
                "SSEKMSKeyId": "kms-key",
                "StorageClass": "STANDARD_IA",
            },
        }
    ]
