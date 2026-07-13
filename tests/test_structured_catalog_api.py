from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings


def test_structured_catalog_endpoint(tmp_path: Path, monkeypatch):
    industry = tmp_path / "knowledge_qa.jsonl"
    feedback = tmp_path / "plan_feedback.jsonl"
    experience = tmp_path / "user_experience.jsonl"
    structured = tmp_path / "structured"
    industry.write_text(
        '{"案例场景":"晚高峰排队溢出绿波","交通问题诊断":"下游承接","治理方案":"绿波协调","预期效果":"改善"}\n',
        encoding="utf-8",
    )
    feedback.write_text("", encoding="utf-8")
    experience.write_text("", encoding="utf-8")

    monkeypatch.setenv("CASE_LIBRARY_PATH", str(industry))
    monkeypatch.setenv("FEEDBACK_LOG_PATH", str(feedback))
    monkeypatch.setenv("USER_EXPERIENCE_PATH", str(experience))
    monkeypatch.setenv("STRUCTURED_CATALOG_PATH", str(structured))
    get_settings.cache_clear()

    with TestClient(app) as client:
        res = client.get("/api/v1/agent/structured-catalog")
        assert res.status_code == 200
        body = res.json()
        assert "industry_cases" in body
        assert "intersection_cases" in body
        assert "experiences" in body
        assert body["industry_cases"]
        assert body["industry_cases"][0]["structured_tags"]

    get_settings.cache_clear()
