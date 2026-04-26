from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from config.settings import Settings


DEFAULT_LOG_ROTATE_MAX_BYTES = 25 * 1024 * 1024


class BackupSink(Protocol):
    def backup(self, local_path: Path, object_name: str) -> None:
        """Persist a completed log segment to backup storage."""


class LogWriter(Protocol):
    def write(self, record: dict[str, Any]) -> None:
        """Append a log record."""

    def close(self) -> None:
        """Flush or finalize any in-progress log segment."""


class NoopBackupSink:
    def backup(self, local_path: Path, object_name: str) -> None:
        return None


class S3BackupSink:
    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        region_name: str | None = None,
        kms_key_id: str | None = None,
        storage_class: str | None = None,
        s3_client: Any | None = None,
    ) -> None:
        if s3_client is None:
            import boto3

            session = boto3.session.Session(region_name=region_name)
            s3_client = session.client("s3")

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.kms_key_id = kms_key_id
        self.storage_class = storage_class
        self._client = s3_client

    def backup(self, local_path: Path, object_name: str) -> None:
        key = "/".join(part for part in (self.prefix, object_name) if part)
        extra_args: dict[str, str] = {}
        if self.kms_key_id:
            extra_args["ServerSideEncryption"] = "aws:kms"
            extra_args["SSEKMSKeyId"] = self.kms_key_id
        if self.storage_class:
            extra_args["StorageClass"] = self.storage_class

        if extra_args:
            self._client.upload_file(str(local_path), self.bucket, key, ExtraArgs=extra_args)
            return

        self._client.upload_file(str(local_path), self.bucket, key)


class JsonlRotatingLogWriter:
    def __init__(
        self,
        *,
        log_file: str,
        max_bytes: int = DEFAULT_LOG_ROTATE_MAX_BYTES,
        backup_sink: BackupSink | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._path = Path(log_file)
        self._max_bytes = max_bytes
        self._backup_sink = backup_sink or NoopBackupSink()
        self._logger = logger or logging.getLogger(__name__)
        self._lock = Lock()
        self._sequence = 0
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: dict[str, Any]) -> None:
        line = json.dumps(record) + "\n"
        with self._lock:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line)

            if self._path.stat().st_size >= self._max_bytes:
                self._rotate_locked(create_new_active=True)

    def close(self) -> None:
        with self._lock:
            if not self._path.exists() or self._path.stat().st_size == 0:
                return
            self._rotate_locked(create_new_active=False)

    def _rotate_locked(self, *, create_new_active: bool) -> None:
        if not self._path.exists() or self._path.stat().st_size == 0:
            return

        rotated_path, object_name = self._next_segment_path()
        self._path.replace(rotated_path)

        if create_new_active:
            self._path.touch()

        try:
            self._backup_sink.backup(rotated_path, object_name)
        except Exception:
            self._logger.exception("Failed to back up rotated log segment %s", rotated_path)

    def _next_segment_path(self) -> tuple[Path, str]:
        self._sequence += 1
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        rotated_name = f"{self._path.stem}.{timestamp}.{self._sequence:04d}{self._path.suffix}"
        rotated_path = self._path.with_name(rotated_name)
        return rotated_path, rotated_name


def create_backup_sink(settings: Settings) -> BackupSink:
    if settings.log_backup_method == "s3":
        return S3BackupSink(
            bucket=settings.s3_backup_bucket,
            prefix=settings.s3_backup_prefix,
            region_name=settings.aws_region,
            kms_key_id=settings.s3_backup_kms_key_id,
            storage_class=settings.s3_backup_storage_class,
        )
    return NoopBackupSink()


def create_log_writer(settings: Settings, backup_sink: BackupSink | None = None) -> LogWriter:
    return JsonlRotatingLogWriter(
        log_file=settings.log_file,
        max_bytes=settings.log_rotate_max_bytes,
        backup_sink=backup_sink or create_backup_sink(settings),
    )
