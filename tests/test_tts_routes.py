import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings, get_settings
from app.main import app


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    app.dependency_overrides.clear()


def test_tts_configured_uses_qwen_api_key_without_workspace(monkeypatch):
    monkeypatch.setenv("QWEN_API_KEY", "key")
    monkeypatch.setenv("QWEN_TTS_WORKSPACE_ID", "")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.tts_configured is True
    assert settings.tts_workspace is None


def test_tts_workspace_used_only_when_explicitly_set():
    settings = Settings(qwen_api_key="key", qwen_tts_workspace_id="ws-tts")

    assert settings.tts_configured is True
    assert settings.tts_workspace == "ws-tts"


@pytest.mark.asyncio
async def test_tts_synthesize_returns_wav(monkeypatch):
    from app.api import routes

    class FakeTtsService:
        available = True

        async def synthesize_wav(self, text: str) -> bytes:
            assert text == "诊断对象识别。"
            return b"RIFFfake-wav"

    monkeypatch.setattr(routes, "get_tts_service", lambda: FakeTtsService())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/tts/synthesize",
            json={"text": "诊断对象识别。", "cue_id": "act1"},
        )

    assert response.status_code == 200
    assert response.content == b"RIFFfake-wav"
    assert response.headers["content-type"].startswith("audio/wav")
