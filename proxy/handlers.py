from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from proxy.service import ShadowService


async def handle_chat_completion(request: Request) -> JSONResponse:
    service: ShadowService = request.app.state.shadow_service
    payload = await request.json()
    result = await service.handle_chat_completion(payload)
    return JSONResponse(status_code=result.status_code, content=result.payload)
