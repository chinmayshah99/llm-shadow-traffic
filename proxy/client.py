from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class UpstreamHTTPError(Exception):
    status_code: int
    payload: dict[str, Any]

    def __str__(self) -> str:
        return f"Upstream returned HTTP {self.status_code}"


class LLMClient:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        model: str,
        auth_header: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._auth_header = auth_header
        self._timeout = timeout

    async def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        body.setdefault("model", self._model)
        headers: dict[str, str] = {}
        if self._auth_header:
            headers["Authorization"] = self._auth_header

        response = await self._client.post(
            f"{self._base_url}/v1/chat/completions",
            json=body,
            headers=headers,
            timeout=self._timeout,
        )

        if response.is_success:
            return response.json()

        error_payload = self._parse_error_payload(response)
        raise UpstreamHTTPError(status_code=response.status_code, payload=error_payload)

    @staticmethod
    def _parse_error_payload(response: httpx.Response) -> dict[str, Any]:
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            pass

        return {
            "error": {
                "message": response.text or "Upstream request failed",
                "type": "upstream_error",
            }
        }
