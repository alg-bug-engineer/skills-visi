"""治理建议溯源依据派生测试。"""

from intersection_agent.services.suggestion_context import derive_suggestion_references


def test_derive_industry_references_from_case_matches():
    case_matches = [
        {
            "scenario_id": "school_zone",
            "scenario_name": "学校周边交通组织",
            "description": "学校周边上下学高峰...",
            "problems": [{"problem": "上下学拥堵"}],
        }
    ]
    refs = derive_suggestion_references(case_matches, [], inter_id=None)
    assert any(r.type == "industry" and r.id == "industry:school_zone" for r in refs)
    ind = next(r for r in refs if r.type == "industry")
    assert ind.scenario_id == "school_zone"
    assert ind.title and ind.summary


def test_derive_intersection_reference_when_reused():
    refs = derive_suggestion_references(
        [], ["复用了 inter_001 的认知经验：早高峰空放"], inter_id="inter_001"
    )
    assert any(
        r.type == "intersection" and r.id == "intersection:inter_001" for r in refs
    )


def test_derive_dedup_and_cap():
    case_matches = [
        {"scenario_id": "s1", "scenario_name": "A", "description": "", "problems": []},
        {"scenario_id": "s1", "scenario_name": "A", "description": "", "problems": []},
    ]
    refs = derive_suggestion_references(case_matches, [], inter_id=None)
    ids = [r.id for r in refs]
    assert ids.count("industry:s1") == 1


def test_derive_empty():
    assert derive_suggestion_references([], [], inter_id=None) == []
