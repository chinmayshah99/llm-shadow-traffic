from __future__ import annotations

from pydantic import Field
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
