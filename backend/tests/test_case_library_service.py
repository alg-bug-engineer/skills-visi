import inspect

from intersection_agent.services.case_library_service import CaseLibraryService


def test_parses_all_scenarios():
    svc = CaseLibraryService()
    scenarios = svc._load()
    ids = {s["scenario_id"] for s in scenarios}
    assert len(scenarios) == 19
    assert {"arterial_green_wave", "school_zone", "short_spacing_coordinated"} <= ids
    # 每个场景至少解析出一个典型问题
    assert all(s["problems"] for s in scenarios)


def test_matches_school_zone_scenario():
    svc = CaseLibraryService()
    matches = svc.match(
        problem_types=["congestion"], scene_text="路口旁边有小学，上下学高峰排队", k=1
    )
    assert matches and matches[0]["scenario_id"] == "school_zone"


def test_matches_short_spacing_and_block_has_measures():
    svc = CaseLibraryService()
    matches = svc.match(
        problem_types=["spillback"],
        scene_text="两个相邻路口相距很短，排队回溢到上游",
        k=1,
    )
    assert matches[0]["scenario_id"] == "short_spacing_coordinated"
    block = svc.format_experience_block(matches)
    assert "治理方案" in block and "关键措施" in block


def test_fallback_to_general_when_no_scene_hit():
    svc = CaseLibraryService()
    matches = svc.match(problem_types=["congestion"], scene_text="", k=1)
    assert matches  # 回退一般路口/首个场景


def test_list_all_returns_full_structure():
    svc = CaseLibraryService()
    scenarios = svc.list_all()
    assert len(scenarios) == 19
    sample = next(s for s in scenarios if s["scenario_id"] == "arterial_green_wave")
    assert sample["case_count"] >= 1
    assert sample["scenario_name"]
    assert sample["problems"], "场景应解析出典型问题"
    prob = sample["problems"][0]
    assert "occurrence" in prob
    assert isinstance(prob.get("symptoms"), list)
    assert prob["solutions"], "问题应解析出治理方案"
    sol = prob["solutions"][0]
    assert "frequency" in sol
    assert isinstance(sol.get("measures"), list)
    reps = sol.get("representative_cases")
    assert isinstance(reps, list) and reps, "方案应解析出代表案例"
    rep = reps[0]
    assert rep["id"] and rep["title"] and rep["snippet"]


def test_list_all_not_truncated():
    """list_all 不应像 match 那样裁剪到前 2 个方案。"""
    svc = CaseLibraryService()
    scenarios = svc.list_all()
    sample = next(s for s in scenarios if s["scenario_id"] == "arterial_green_wave")
    parking = next((p for p in sample["problems"] if "停车" in p["problem"]), None)
    assert parking is not None
    assert len(parking["solutions"]) >= 3


def test_no_vector_dependency():
    import intersection_agent.services.case_library_service as m

    src = inspect.getsource(m)
    assert "faiss" not in src and "embedding" not in src.lower()
