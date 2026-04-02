from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from proxy.handlers import handle_chat_completion

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    return await handle_chat_completion(request)
