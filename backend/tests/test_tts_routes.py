"""Tests for TTS API route."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from intersection_agent.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_tts_synthesize_returns_wav(app):
    fake_audio = b"RIFFfake-wav"
    mock_service = AsyncMock()
    mock_service.available = True
    mock_service.synthesize_wav = AsyncMock(return_value=fake_audio)

    with patch("intersection_agent.api.tts_routes.get_tts_service", return_value=mock_service):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/v1/tts/synthesize",
                json={"text": "开始分析运行数据。", "cue_id": "step:3:data"},
            )

    assert res.status_code == 200
    assert res.content == fake_audio
    assert res.headers.get("content-type", "").startswith("audio/wav")


@pytest.mark.asyncio
async def test_tts_stream_returns_pcm(app):
    async def fake_stream(_text: str):
        yield b"\x00\x01"
        yield b"\x02\x03"

    mock_service = MagicMock()
    mock_service.available = True
    mock_service.stream_pcm = fake_stream

    with patch("intersection_agent.api.tts_routes.get_tts_service", return_value=mock_service):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/v1/tts/synthesize/stream",
                json={"text": "开始分析运行数据。", "cue_id": "step:3:data"},
            )

    assert res.status_code == 200
    assert res.content == b"\x00\x01\x02\x03"
    assert res.headers.get("x-audio-sample-rate") == "24000"
