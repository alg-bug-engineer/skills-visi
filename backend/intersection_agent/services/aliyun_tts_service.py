"""Aliyun ISI RESTful text-to-speech."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

import httpx

from intersection_agent.config import get_settings
from intersection_agent.services.aliyun_token_manager import AliyunTokenManager
from intersection_agent.utils.speakable import truncate_speakable

if TYPE_CHECKING:
    from intersection_agent.config import Settings

logger = logging.getLogger(__name__)


class AliyunTtsService:
    """Synthesize short voice cues via NLS REST API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._tokens = AliyunTokenManager(self._settings)

    @property
    def available(self) -> bool:
        return bool(self._settings.tts_enabled and self._settings.tts_configured)

    async def synthesize(self, text: str) -> bytes:
        """Return MP3/WAV bytes for speakable text."""
        if not self.available:
            raise RuntimeError("TTS is disabled or not configured")
        speak_text = truncate_speakable(text)
        if not speak_text:
            raise ValueError("empty speakable text")

        token = self._tokens.get_token()
        host = self._settings.aliyun_nls_gateway_host
        url = f"https://{host}/stream/v1/tts"
        body = {
            "appkey": self._settings.aliyun_nls_appkey,
            "token": token,
            "text": speak_text,
            "format": self._settings.aliyun_nls_format,
            "sample_rate": self._settings.aliyun_nls_sample_rate,
            "voice": self._settings.aliyun_nls_voice,
            "speech_rate": self._settings.aliyun_nls_speech_rate,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=body,
                headers={"Content-Type": "application/json"},
            )
        content_type = response.headers.get("Content-Type", "")
        if "audio/mpeg" in content_type or "audio/" in content_type:
            return response.content
        detail = response.text[:500]
        logger.error("aliyun_tts.failed status=%s body=%s", response.status_code, detail)
        raise RuntimeError(f"TTS synthesis failed: {detail}")


@lru_cache
def get_tts_service() -> AliyunTtsService:
    """Shared TTS service singleton."""
    return AliyunTtsService()
