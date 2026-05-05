import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from api.deps import require_api_key
from api.schemas import SttResponse
from core.speech import transcribe_audio_bytes

router = APIRouter()


@router.post("/stt", response_model=SttResponse, dependencies=[Depends(require_api_key)])
async def stt(audio: UploadFile = File(...)) -> SttResponse:
    if audio.content_type not in {"audio/wav", "audio/x-wav", "audio/wave", "audio/mpeg"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {audio.content_type}",
        )
    data = await audio.read()
    transcript = await transcribe_audio_bytes(io.BytesIO(data))
    return SttResponse(transcript=transcript)
