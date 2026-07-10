import importlib.util
from pathlib import Path


def _load_contrast_module():
    path = Path(__file__).resolve().parents[1] / "skills/strategy-generation/scripts/build_experience_contrast.py"
    spec = importlib.util.spec_from_file_location("build_experience_contrast", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_experience_contrast_from_pipeline_outputs():
    mod = _load_contrast_module()
    cause = {
        "cause_analysis": {"primary_cause": "下游承接不足导致排队外溢"},
        "cause_scores": {"scores": {"downstream": 0.8, "demand": 0.3}},
        "user_experience_refs": [
            {"record_id": "ue_1", "experience_type": "diagnostic", "content": "需分析下游拓扑"}
        ],
        "case_cards": {"cards": [{"case_id": "A", "title": "相似案例"}]},
    }
    strategy = {
        "strategy_package": "incremental_release",
        "package_scores": {"incremental_release": 0.45, "downstream_protection": 0.2},
        "strategy": {"hard_constraints": ["护栏1", "护栏2"]},
    }
    diagnosis = {
        "downstream_diagnosis": {"release_answer": "不宜单点加绿"},
    }
    result = mod.build_experience_contrast(cause=cause, diagnosis=diagnosis, strategy=strategy, ticket={})
    assert result["available"] is True
    assert len(result["items"]) >= 2
    dims = {item["dimension"] for item in result["items"]}
    assert "策略选择" in dims
    assert "成因判断" in dims
    strategy_item = next(i for i in result["items"] if i["dimension"] == "策略选择")
    assert strategy_item["with_experience"]["refs"]
