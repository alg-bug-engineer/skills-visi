import json
import os
from pathlib import Path

import pytest

from app.config import get_settings
from app.services.agent_service import AgentService
from app.services.case_library import CaseLibraryService


@pytest.fixture
def case_library_path() -> Path:
    settings = get_settings()
    return settings.case_library_abs_path


def test_case_library_has_no_write_api(case_library_path: Path):
    service = CaseLibraryService(case_library_path)
    assert not hasattr(service, "append")
    assert not hasattr(service, "persist")
    assert not hasattr(service, "write")


@pytest.mark.asyncio
async def test_knowledge_qa_readonly_after_pipeline(case_library_path: Path, script_user_input, tmp_path, monkeypatch):
    if not case_library_path.exists():
        pytest.skip("knowledge_qa.jsonl 不存在")

    before = case_library_path.read_bytes()
    monkeypatch.setenv("USER_EXPERIENCE_PATH", str(tmp_path / "user_experience.jsonl"))
    monkeypatch.setenv("FEEDBACK_LOG_PATH", str(tmp_path / "plan_feedback.jsonl"))
    get_settings.cache_clear()

    service = AgentService(get_settings())
    await service.run(script_user_input, trace_id="readonly-test")

    after = case_library_path.read_bytes()
    assert before == after
