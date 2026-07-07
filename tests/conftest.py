import os

import pytest

os.environ.setdefault("LLM_MOCK", "true")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("ALLOW_DEMO_FALLBACK", "true")


@pytest.fixture
def overflow_fixtures():
    import json
    from pathlib import Path

    fixtures = Path(__file__).resolve().parent / "fixtures"
    metrics = json.loads((fixtures / "overflow_metrics.json").read_text(encoding="utf-8"))
    topology = json.loads((fixtures / "overflow_topology.json").read_text(encoding="utf-8"))
    return metrics, topology


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
