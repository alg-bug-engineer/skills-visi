import pytest
from httpx import ASGITransport, AsyncClient

from app.config import PROJECT_ROOT, Settings, get_settings
from app.main import app


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    app.dependency_overrides.clear()


def test_tts_configured_uses_qwen_api_key_without_workspace(monkeypatch):
    monkeypatch.setenv("QWEN_API_KEY", "key")
    monkeypatch.setenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("QWEN_TTS_WORKSPACE_ID", "")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.tts_configured is True
    assert settings.tts_workspace is None


def test_tts_does_not_reuse_non_dashscope_qwen_key():
    settings = Settings(
        qwen_api_key="llm-key",
        qwen_base_url="https://llm-bxzi9xzwajjsz3y8.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        dashscope_api_key="",
    )

    assert settings.tts_api_key == ""
    assert settings.tts_configured is False


def test_tts_prefers_dashscope_key_when_llm_uses_other_provider():
    settings = Settings(
        qwen_api_key="llm-key",
        qwen_base_url="https://llm-bxzi9xzwajjsz3y8.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        dashscope_api_key="dashscope-key",
    )

    assert settings.tts_api_key == "dashscope-key"
    assert settings.tts_configured is True


def test_tts_workspace_used_only_when_explicitly_set():
    settings = Settings(
        qwen_api_key="key",
        qwen_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        qwen_tts_workspace_id="ws-tts",
    )

    assert settings.tts_configured is True
    assert settings.tts_workspace == "ws-tts"


def test_env_example_documents_qwen_tts_reuse():
    text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "QWEN_API_KEY" in text
    assert "DASHSCOPE_API_KEY" in text
    assert "QWEN_TTS_MODEL" in text
    assert "TTS_ENABLED" in text
    assert "QWEN_BASE_URL 是 DashScope" in text


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
