from fastapi import APIRouter, Depends
from fastapi.responses import Response

from api.deps import require_api_key
from api.schemas import TtsRequest
from core.speech import synthesize_speech

router = APIRouter()


@router.post("/tts", dependencies=[Depends(require_api_key)])
async def tts(req: TtsRequest) -> Response:
    audio_bytes, mime = await synthesize_speech(req.text, voice=req.voice)
    return Response(content=audio_bytes, media_type=mime)
