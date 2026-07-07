import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACT_PATH = PROJECT_ROOT / "skills" / "intent-understanding" / "scripts" / "extract_user_experiences.py"


def _load_extract_module():
    spec = importlib.util.spec_from_file_location("extract_user_experiences", EXTRACT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


THREE_EXPERIENCE_INPUT = (
    "文化西路与舜华路交叉口下午3点经常拥堵，"
    "这附近有一个小学那时候放学家长接送孩子导致的，"
    "应该增加一点绿灯时间。"
)


def test_extract_three_experience_types_from_llm_payload():
    parsed = {
        "intersection_name": "文化西路与舜华路交叉口",
        "problem_type": "拥堵",
        "user_experiences": [
            {
                "experience_type": "cognitive",
                "content": "文化西路与舜华路交叉口下午3点经常拥堵",
                "source_span": "下午3点经常拥堵",
                "tags": {"problem_type": "拥堵", "time_period": "下午时段"},
            },
            {
                "experience_type": "diagnostic",
                "content": "附近有小学放学家长接送导致",
                "source_span": "小学那时候放学家长接送孩子导致的",
                "tags": {"cause_dimension": "event", "related_poi": ["学校"]},
            },
            {
                "experience_type": "solution",
                "content": "应该增加一点绿灯时间",
                "source_span": "应该增加一点绿灯时间",
                "tags": {"strategy_action": "加绿"},
            },
        ],
    }
    ticket = {"intersection_name": "文化西路与舜华路交叉口", "problem_type": "拥堵"}
    extract_mod = _load_extract_module()
    result = extract_mod.extract_user_experiences(
        parsed=dict(parsed),
        user_input=THREE_EXPERIENCE_INPUT,
        diagnosis_ticket=ticket,
    )
    assert len(result) == 3
    assert {item["experience_type"] for item in result} == {"cognitive", "diagnostic", "solution"}
    assert result[0]["tags"]["time_period"] == "下午时段"
    assert result[1]["tags"]["cause_dimension"] == "event"
    assert result[2]["tags"]["strategy_action"] == "加绿"


def test_extract_cognitive_only_heuristic():
    ticket = {"intersection_name": "测试路口", "problem_type": "拥堵", "time_range": "15:00-16:00"}
    extract_mod = _load_extract_module()
    result = extract_mod.extract_user_experiences(
        parsed={},
        user_input="测试路口下午3点经常拥堵",
        diagnosis_ticket=ticket,
    )
    assert len(result) >= 1
    assert result[0]["experience_type"] == "cognitive"


def test_extract_empty_when_no_experience_signal():
    ticket = {"intersection_name": "测试路口", "problem_type": "排队溢出"}
    extract_mod = _load_extract_module()
    result = extract_mod.extract_user_experiences(
        parsed={},
        user_input="文化西路与舜华路交叉口，18:10-18:30，东向西排队溢出",
        diagnosis_ticket=ticket,
    )
    assert isinstance(result, list)
