"""Qwen-TTS Realtime (DashScope WebSocket) synthesis."""

from __future__ import annotations

import asyncio
import base64
import logging
import struct
import threading
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import dashscope
from dashscope.audio.qwen_tts_realtime import (
    AudioFormat,
    QwenTtsRealtime,
    QwenTtsRealtimeCallback,
)

from intersection_agent.config import get_settings
from intersection_agent.utils.speakable import truncate_speakable

if TYPE_CHECKING:
    from intersection_agent.config import Settings

logger = logging.getLogger(__name__)

_SENTINEL = object()
_RESPONSE_DONE_EVENTS = frozenset({"response.done", "session.finished"})


def pcm_to_wav(pcm: bytes, *, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw PCM16LE mono into a WAV container for browser playback."""
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


class _CollectCallback(QwenTtsRealtimeCallback):
    """Gather PCM chunks until response.done."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self._done = threading.Event()
        self._error: Exception | None = None

    def on_open(self) -> None:
        return

    def on_close(self, close_status_code, close_msg) -> None:
        self._done.set()

    def on_event(self, response: dict[str, Any]) -> None:
        try:
            event_type = response.get("type")
            if event_type == "response.audio.delta":
                self._chunks.append(base64.b64decode(response["delta"]))
            elif event_type == "error":
                self._error = RuntimeError(response.get("error", response))
                self._done.set()
            elif event_type in _RESPONSE_DONE_EVENTS:
                self._done.set()
        except Exception as exc:
            self._error = exc
            self._done.set()

    def wait(self, timeout: float = 30.0) -> bytes:
        if not self._done.wait(timeout):
            raise TimeoutError("Qwen TTS realtime synthesis timed out")
        if self._error:
            raise self._error
        return b"".join(self._chunks)


class _StreamCallback(QwenTtsRealtimeCallback):
    """Push PCM chunks to an asyncio queue for streaming responses."""

    def __init__(self, queue: asyncio.Queue[Any], loop: asyncio.AbstractEventLoop) -> None:
        self._queue = queue
        self._loop = loop
        self._error: Exception | None = None
        self._done = threading.Event()

    def on_open(self) -> None:
        return

    def on_close(self, close_status_code, close_msg) -> None:
        self._finish()

    def on_event(self, response: dict[str, Any]) -> None:
        try:
            event_type = response.get("type")
            if event_type == "response.audio.delta":
                chunk = base64.b64decode(response["delta"])
                self._loop.call_soon_threadsafe(self._queue.put_nowait, chunk)
            elif event_type == "error":
                self._error = RuntimeError(response.get("error", response))
                self._finish()
            elif event_type in _RESPONSE_DONE_EVENTS:
                self._finish()
        except Exception as exc:
            self._error = exc
            self._finish()

    def _finish(self) -> None:
        if self._done.is_set():
            return
        self._done.set()
        self._loop.call_soon_threadsafe(self._queue.put_nowait, _SENTINEL)

    def wait(self, timeout: float = 30.0) -> None:
        self._done.wait(timeout)


class QwenTtsRealtimeService:
    """Synthesize short voice cues via Qwen-TTS Realtime (commit mode)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def available(self) -> bool:
        return bool(self._settings.tts_enabled and self._settings.tts_configured)

    def _session_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "voice": self._settings.qwen_tts_voice,
            "response_format": AudioFormat.PCM_24000HZ_MONO_16BIT,
            "mode": self._settings.qwen_tts_mode,
            "language_type": "Chinese",
        }
        if self._settings.qwen_tts_sample_rate != 24000:
            kwargs["sample_rate"] = self._settings.qwen_tts_sample_rate
        return kwargs

    def _connect_client(self, callback: QwenTtsRealtimeCallback) -> QwenTtsRealtime:
        dashscope.api_key = self._settings.dashscope_api_key
        client = QwenTtsRealtime(
            model=self._settings.qwen_tts_model,
            callback=callback,
            url=self._settings.qwen_tts_ws_url,
            workspace=self._settings.dashscope_workspace_id or None,
        )
        client.connect()
        client.update_session(**self._session_kwargs())
        return client

    def _synthesize_sync(self, text: str) -> tuple[bytes, float | None]:
        speak_text = truncate_speakable(text)
        if not speak_text:
            raise ValueError("empty speakable text")

        callback = _CollectCallback()
        client = self._connect_client(callback)
        try:
            client.append_text(speak_text)
            if self._settings.qwen_tts_mode == "commit":
                client.commit()
            pcm = callback.wait(timeout=30.0)
            delay = client.get_first_audio_delay()
            client.finish()
            return pcm, delay
        finally:
            client.close()

    async def synthesize_wav(self, text: str) -> bytes:
        """Return WAV bytes for a single voice cue."""
        if not self.available:
            raise RuntimeError("TTS is disabled or not configured")
        pcm, delay = await asyncio.to_thread(self._synthesize_sync, text)
        if delay is not None:
            logger.info("qwen_tts.first_audio_delay_ms=%s text_len=%s", delay, len(text))
        if not pcm:
            raise RuntimeError("Qwen TTS returned empty audio")
        return pcm_to_wav(pcm, sample_rate=self._settings.qwen_tts_sample_rate)

    async def stream_pcm(self, text: str) -> AsyncIterator[bytes]:
        """Yield PCM chunks as they arrive from Qwen Realtime."""
        if not self.available:
            raise RuntimeError("TTS is disabled or not configured")
        speak_text = truncate_speakable(text)
        if not speak_text:
            raise ValueError("empty speakable text")

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Any] = asyncio.Queue()
        error_holder: list[Exception] = []

        def worker() -> None:
            client: QwenTtsRealtime | None = None
            try:
                callback = _StreamCallback(queue, loop)
                client = self._connect_client(callback)
                client.append_text(speak_text)
                if self._settings.qwen_tts_mode == "commit":
                    client.commit()
                callback.wait(timeout=30.0)
                if callback._error:
                    error_holder.append(callback._error)
                client.finish()
            except Exception as exc:
                error_holder.append(exc)
                loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)
            finally:
                if client is not None:
                    client.close()

        thread = threading.Thread(target=worker, name="qwen-tts-stream", daemon=True)
        thread.start()

        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            yield item

        thread.join(timeout=5.0)
        if error_holder:
            raise error_holder[0]


@lru_cache
def get_tts_service() -> QwenTtsRealtimeService:
    """Shared Qwen TTS service singleton."""
    return QwenTtsRealtimeService()
