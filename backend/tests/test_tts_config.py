"""TTS 配置回归：workspace 不应复用 LLM 的 DASHSCOPE_WORKSPACE_ID。

背景：Qwen-TTS Realtime WS 对 LLM 的 workspace 可能返回 "Workspace access denied"，
导致前端静默降级、完全无声。TTS 仅需 API Key，workspace 默认不下发。
"""

from intersection_agent.config import Settings


def test_tts_configured_requires_only_api_key():
    s = Settings(dashscope_api_key="sk-test", dashscope_workspace_id="")
    assert s.tts_configured is True


def test_tts_configured_false_without_api_key():
    s = Settings(dashscope_api_key="", dashscope_workspace_id="ws-x")
    assert s.tts_configured is False


def test_tts_does_not_reuse_llm_workspace():
    # LLM workspace 设了，但 TTS 不复用它（默认下发 None）
    s = Settings(
        dashscope_api_key="sk-test",
        dashscope_workspace_id="ws-llm-only",
    )
    assert s.tts_workspace is None


def test_tts_workspace_used_only_when_explicitly_set():
    s = Settings(
        dashscope_api_key="sk-test",
        dashscope_workspace_id="ws-llm-only",
        qwen_tts_workspace_id="ws-tts",
    )
    assert s.tts_workspace == "ws-tts"
