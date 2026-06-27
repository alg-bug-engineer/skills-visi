"""TTS proxy routes (Qwen-TTS Realtime)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from intersection_agent.config import get_settings
from intersection_agent.services.qwen_tts_realtime_service import get_tts_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts", tags=["tts"])


class TtsSynthesizeRequest(BaseModel):
    """Client voice cue synthesis request."""

    text: str = Field(..., min_length=1, max_length=300)
    cue_id: str | None = None


@router.post("/synthesize")
async def synthesize(body: TtsSynthesizeRequest) -> Response:
    """Synthesize a short voice cue; returns audio/wav."""
    settings = get_settings()
    if not settings.tts_enabled:
        raise HTTPException(status_code=503, detail="TTS disabled")
    service = get_tts_service()
    if not service.available:
        raise HTTPException(status_code=503, detail="TTS not configured")

    try:
        audio = await service.synthesize_wav(body.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("tts.synthesize_failed cue_id=%s", body.cue_id)
        raise HTTPException(status_code=502, detail=f"TTS failed: {type(exc).__name__}") from exc

    return Response(content=audio, media_type="audio/wav")


@router.post("/synthesize/stream")
async def synthesize_stream(body: TtsSynthesizeRequest) -> StreamingResponse:
    """Stream PCM chunks for low-latency playback."""
    settings = get_settings()
    if not settings.tts_enabled:
        raise HTTPException(status_code=503, detail="TTS disabled")
    service = get_tts_service()
    if not service.available:
        raise HTTPException(status_code=503, detail="TTS not configured")

    async def pcm_iterator():
        async for chunk in service.stream_pcm(body.text):
            yield chunk

    return StreamingResponse(
        pcm_iterator(),
        media_type="application/octet-stream",
        headers={
            "X-Audio-Sample-Rate": str(settings.qwen_tts_sample_rate),
            "X-Audio-Channels": "1",
            "X-Audio-Sample-Width": "2",
            "Cache-Control": "no-cache",
        },
    )
