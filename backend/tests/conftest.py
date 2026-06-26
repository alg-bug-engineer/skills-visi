"""Test fixtures."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

_tmp = tempfile.mkdtemp(prefix="intersection_agent_test_")
os.environ["MOCK_LLM"] = "1"
os.environ["MOCK_DB"] = "1"
os.environ["SKILL_DIR_PATH"] = str(Path(_tmp) / "skills")

from intersection_agent.main import create_app  # noqa: E402


@pytest.fixture
def skill_dir_path(tmp_path: Path) -> Path:
    """Isolated skill directory per test."""
    from intersection_agent.config import get_settings

    path = tmp_path / "skills"
    path.mkdir(parents=True, exist_ok=True)
    os.environ["SKILL_DIR_PATH"] = str(path)
    get_settings.cache_clear()
    return path


@pytest.fixture
async def client(skill_dir_path: Path):
    """Async HTTP test client."""
    from intersection_agent.api import routes
    from intersection_agent.config import get_settings
    from intersection_agent.services.orchestrator import Orchestrator
    from intersection_agent.services.skill_service import SkillService
    from intersection_agent.stores.session_store import SessionStore

    get_settings.cache_clear()
    routes._sessions = SessionStore()
    routes._orchestrator = Orchestrator()
    routes._skills = SkillService()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
