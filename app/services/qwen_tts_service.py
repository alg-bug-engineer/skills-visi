from __future__ import annotations

import asyncio
import base64
import logging
import struct
import threading
from functools import lru_cache
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_DONE_EVENTS = frozenset({"response.done", "session.finished"})


def pcm_to_wav(
    pcm: bytes,
    *,
    sample_rate: int = 24000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        sample_rate * channels * sample_width,
        channels * sample_width,
        sample_width * 8,
        b"data",
        data_size,
    )
    return header + pcm


def _speakable(text: str, limit: int = 300) -> str:
    cleaned = " ".join(str(text or "").split())
    return cleaned[:limit]


class _CollectCallback:
    def __init__(self, callback_base: type) -> None:
        self._chunks: list[bytes] = []
        self._done = threading.Event()
        self._error: Exception | None = None

        class Callback(callback_base):  # type: ignore[misc, valid-type]
            def on_open(inner_self) -> None:
                return

            def on_close(inner_self, close_status_code, close_msg) -> None:
                self._done.set()

            def on_event(inner_self, response: dict[str, Any]) -> None:
                try:
                    event_type = response.get("type")
                    if event_type == "response.audio.delta":
                        self._chunks.append(base64.b64decode(response["delta"]))
                    elif event_type == "error":
                        self._error = RuntimeError(str(response.get("error", response)))
                        self._done.set()
                    elif event_type in _DONE_EVENTS:
                        self._done.set()
                except Exception as exc:  # noqa: BLE001 - callback boundary
                    self._error = exc
                    self._done.set()

        self.callback = Callback()

    def wait(self, timeout: float = 30.0) -> bytes:
        if not self._done.wait(timeout):
            raise TimeoutError("Qwen TTS realtime synthesis timed out")
        if self._error:
            raise self._error
        return b"".join(self._chunks)


class QwenTtsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def available(self) -> bool:
        return bool(self._settings.tts_enabled and self._settings.tts_configured)

    def _synthesize_sync(self, text: str) -> bytes:
        speak_text = _speakable(text)
        if not speak_text:
            raise ValueError("empty speakable text")

        try:
            import dashscope
            from dashscope.audio.qwen_tts_realtime import (
                AudioFormat,
                QwenTtsRealtime,
                QwenTtsRealtimeCallback,
            )
        except ImportError as exc:
            raise RuntimeError("dashscope is required for Qwen TTS") from exc

        dashscope.api_key = self._settings.tts_api_key
        collector = _CollectCallback(QwenTtsRealtimeCallback)
        client = QwenTtsRealtime(
            model=self._settings.qwen_tts_model,
            callback=collector.callback,
            url=self._settings.qwen_tts_ws_url,
            workspace=self._settings.tts_workspace,
        )
        try:
            client.connect()
            session_kwargs: dict[str, Any] = {
                "voice": self._settings.qwen_tts_voice,
                "response_format": AudioFormat.PCM_24000HZ_MONO_16BIT,
                "mode": self._settings.qwen_tts_mode,
                "language_type": "Chinese",
            }
            if self._settings.qwen_tts_sample_rate != 24000:
                session_kwargs["sample_rate"] = self._settings.qwen_tts_sample_rate
            client.update_session(**session_kwargs)
            client.append_text(speak_text)
            if self._settings.qwen_tts_mode == "commit":
                client.commit()
            pcm = collector.wait(timeout=30.0)
            delay = client.get_first_audio_delay()
            if delay is not None:
                logger.info("qwen_tts.first_audio_delay_ms=%s text_len=%s", delay, len(speak_text))
            client.finish()
            if not pcm:
                raise RuntimeError("Qwen TTS returned empty audio")
            return pcm
        finally:
            client.close()

    async def synthesize_wav(self, text: str) -> bytes:
        if not self.available:
            raise RuntimeError("TTS is disabled or not configured")
        pcm = await asyncio.to_thread(self._synthesize_sync, text)
        return pcm_to_wav(pcm, sample_rate=self._settings.qwen_tts_sample_rate)


@lru_cache
def get_tts_service() -> QwenTtsService:
    return QwenTtsService()
