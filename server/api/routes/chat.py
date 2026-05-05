from fastapi import APIRouter, Depends

from api.deps import require_api_key
from api.schemas import ChatRequest, ChatResponse
from core.jarvis_adapter import handle_text

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
async def chat(req: ChatRequest) -> ChatResponse:
    reply = await handle_text(req.text, req.session_id)
    return ChatResponse(reply=reply, session_id=req.session_id)
