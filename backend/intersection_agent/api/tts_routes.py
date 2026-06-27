"""TTS proxy routes (Aliyun ISI)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from intersection_agent.config import get_settings
from intersection_agent.services.aliyun_tts_service import get_tts_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts", tags=["tts"])


class TtsSynthesizeRequest(BaseModel):
    """Client voice cue synthesis request."""

    text: str = Field(..., min_length=1, max_length=300)
    cue_id: str | None = None


@router.post("/synthesize")
async def synthesize(body: TtsSynthesizeRequest) -> Response:
    """Synthesize a short voice cue; returns audio/mpeg."""
    settings = get_settings()
    if not settings.tts_enabled:
        raise HTTPException(status_code=503, detail="TTS disabled")
    service = get_tts_service()
    if not service.available:
        raise HTTPException(status_code=503, detail="TTS not configured")

    try:
        audio = await service.synthesize(body.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("tts.synthesize_failed cue_id=%s", body.cue_id)
        raise HTTPException(status_code=502, detail=f"TTS failed: {type(exc).__name__}") from exc

    media = "audio/mpeg" if settings.aliyun_nls_format == "mp3" else "audio/wav"
    return Response(content=audio, media_type=media)
