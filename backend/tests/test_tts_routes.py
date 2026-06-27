"""Tests for TTS API route."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from intersection_agent.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_tts_synthesize_returns_audio(app):
    fake_audio = b"fake-mp3-bytes"
    mock_service = AsyncMock()
    mock_service.available = True
    mock_service.synthesize = AsyncMock(return_value=fake_audio)

    with patch("intersection_agent.api.tts_routes.get_tts_service", return_value=mock_service):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/v1/tts/synthesize",
                json={"text": "开始分析运行数据。", "cue_id": "step:3:data"},
            )

    assert res.status_code == 200
    assert res.content == fake_audio
    assert "audio" in res.headers.get("content-type", "")
