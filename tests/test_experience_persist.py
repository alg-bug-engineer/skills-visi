import json
from pathlib import Path

from app.services.experience_service import ExperienceService


def test_experience_persist_appends_jsonl(tmp_path: Path):
    log_path = tmp_path / "user_experience.jsonl"
    service = ExperienceService(log_path)
    records = service.persist_from_intent(
        trace_id="tr-001",
        user_experiences=[
            {
                "experience_type": "diagnostic",
                "content": "学校接送导致拥堵",
                "source_span": "学校接送",
                "tags": {"cause_dimension": "event"},
            }
        ],
        diagnosis_ticket={"intersection_name": "测试路口"},
    )
    assert len(records) == 1
    assert records[0]["record_id"].startswith("ue_")

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    saved = json.loads(lines[0])
    assert saved["trace_id"] == "tr-001"
    assert saved["experience_type"] == "diagnostic"


def test_experience_persist_dedup_same_content(tmp_path: Path):
    log_path = tmp_path / "user_experience.jsonl"
    service = ExperienceService(log_path)
    payload = {
        "experience_type": "cognitive",
        "content": "东向西早高峰排队溢出",
        "source_span": "东向西早高峰排队溢出",
        "tags": {"inter_id": "x1", "problem_type": "排队溢出"},
    }
    first = service.persist_from_intent(trace_id="t1", user_experiences=[payload])
    # 不同 trace_id、内容一致 → 视为重复，禁止再次落库
    second = service.persist_from_intent(trace_id="t2", user_experiences=[dict(payload)])
    assert len(first) == 1
    assert second == []
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_experience_persist_dedup_across_new_service_instance(tmp_path: Path):
    log_path = tmp_path / "user_experience.jsonl"
    payload = {
        "experience_type": "solution",
        "content": "优先保护下游",
        "source_span": "优先保护下游",
        "tags": {"inter_id": "x1"},
    }
    ExperienceService(log_path).persist_from_intent(trace_id="t1", user_experiences=[payload])
    # 新实例（重启）也应从文件读出既有指纹并去重
    again = ExperienceService(log_path).persist_from_intent(trace_id="t2", user_experiences=[dict(payload)])
    assert again == []
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
