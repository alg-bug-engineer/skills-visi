import os

import pytest

os.environ.setdefault("LLM_MOCK", "true")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("ALLOW_DEMO_FALLBACK", "true")


@pytest.fixture(autouse=True)
def reset_skill_registry():
    from app.runtime.registry import reset_registry

    reset_registry()
    yield
    reset_registry()


@pytest.fixture
def script_user_input() -> str:
    return (
        "文化西路与舜华路交叉口，六点十分到六点半，"
        "东向西排队溢出到上游，优先避免下游继续外溢。"
    )
