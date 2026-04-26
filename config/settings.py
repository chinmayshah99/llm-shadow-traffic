from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    baseline_url: str = Field(alias="BASELINE_URL")
    candidate_url: str = Field(alias="CANDIDATE_URL")
    baseline_model: str = Field(alias="BASELINE_MODEL")
    candidate_model: str = Field(alias="CANDIDATE_MODEL")
    baseline_api_key: str | None = Field(default=None, alias="BASELINE_API_KEY")
    candidate_api_key: str | None = Field(default=None, alias="CANDIDATE_API_KEY")
    baseline_auth_header_override: str | None = Field(default=None, alias="BASELINE_AUTH_HEADER")
    candidate_auth_header_override: str | None = Field(default=None, alias="CANDIDATE_AUTH_HEADER")
    timeout: float = Field(default=30.0, alias="TIMEOUT")
    log_file: str = Field(default="logs/logs.jsonl", alias="LOG_FILE")
    log_backup_method: Literal["none", "s3"] = Field(default="none", alias="LOG_BACKUP_METHOD")
    log_rotate_max_bytes: int = Field(default=25 * 1024 * 1024, alias="LOG_ROTATE_MAX_BYTES")
    s3_backup_bucket: str | None = Field(default=None, alias="S3_BACKUP_BUCKET")
    s3_backup_prefix: str = Field(default="", alias="S3_BACKUP_PREFIX")
    aws_region: str | None = Field(default=None, alias="AWS_REGION")
    s3_backup_kms_key_id: str | None = Field(default=None, alias="S3_BACKUP_KMS_KEY_ID")
    s3_backup_storage_class: str | None = Field(default=None, alias="S3_BACKUP_STORAGE_CLASS")

    @property
    def baseline_auth_header(self) -> str | None:
        if self.baseline_auth_header_override:
            return self.baseline_auth_header_override
        if self.baseline_api_key:
            return f"Bearer {self.baseline_api_key}"
        return None

    @property
    def candidate_auth_header(self) -> str | None:
        if self.candidate_auth_header_override:
            return self.candidate_auth_header_override
        if self.candidate_api_key:
            return f"Bearer {self.candidate_api_key}"
        return None

    @model_validator(mode="after")
    def validate_backup_settings(self) -> Settings:
        if self.log_rotate_max_bytes <= 0:
            raise ValueError("LOG_ROTATE_MAX_BYTES must be greater than 0")
        if self.log_backup_method == "s3" and not self.s3_backup_bucket:
            raise ValueError("S3_BACKUP_BUCKET is required when LOG_BACKUP_METHOD=s3")
        return self
