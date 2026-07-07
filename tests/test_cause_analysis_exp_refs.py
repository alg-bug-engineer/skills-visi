import json
from pathlib import Path

import pytest

from app.config import PROJECT_ROOT, Settings
from app.llm.qwen import QwenClient
from app.runtime.skill_loader import load_skill_from_dir
from app.runtime.skill_types import SkillContext
from app.services.experience_library import ExperienceLibraryService


@pytest.mark.asyncio
async def test_cause_analysis_includes_user_experience_refs(tmp_path: Path):
    lib_path = tmp_path / "user_experience.jsonl"
    sample = {
        "record_id": "ue_diag",
        "trace_id": "tr-x",
        "experience_type": "diagnostic",
        "content": "附近有学校下午接送导致拥堵",
        "tags": {
            "intersection_name": "文化西路与舜华路交叉口",
            "cause_dimension": "event",
            "cause_keywords": ["学校", "接送"],
        },
    }
    lib_path.write_text(json.dumps(sample, ensure_ascii=False) + "\n", encoding="utf-8")

    cause_skill = load_skill_from_dir(PROJECT_ROOT / "skills" / "cause-analysis")
    context = SkillContext(
        trace_id="cause-exp-001",
        user_input="test",
        task={
            "diagnosis_ticket": {
                "intersection_name": "文化西路与舜华路交叉口",
                "problem_type": "排队溢出",
            }
        },
    )
    context.artifacts["data_analysis_diagnosis"] = {
        "metrics": {"saturation": 0.9},
        "overflow_verification": {"risk_level": "high"},
    }

    result = await cause_skill.run(
        context,
        llm=QwenClient(Settings(llm_mock=True)),
        experience_library=ExperienceLibraryService(lib_path),
    )
    assert result.success is True
    assert len(result.output["user_experience_refs"]) >= 1
