from intersection_agent.utils.problem_type_infer import infer_problem_types_from_text, merge_problem_types


def test_infer_empty_green_from_natural_phrase():
    text = "西进口绿灯经常没车也放行，东进口却排队很长"
    types = infer_problem_types_from_text(text)
    assert "empty_green" in types
    assert "congestion" in types


def test_merge_supplements_llm_default():
    merged = merge_problem_types(["congestion"], "西进口绿灯经常没车也放行，东进口却排队很长")
    assert "empty_green" in merged
    assert "congestion" in merged


def test_merge_spillback_keyword():
    merged = merge_problem_types(["congestion"], "排队溢出到上游")
    assert "spillback" in merged
