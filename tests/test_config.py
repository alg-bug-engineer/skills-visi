from app.config import Settings


def test_qwen_timeout_defaults_to_360_seconds():
    assert Settings().qwen_timeout_s == 360.0
