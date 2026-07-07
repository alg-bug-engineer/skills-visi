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
