from intersection_agent.services.dimension_pack_service import DimensionPackService


def test_single_type_resolves_focus_categories():
    svc = DimensionPackService()
    cats = svc.focus_categories(["spillback"])
    assert "spillback" in cats
    # base 维度恒在
    assert "saturation" in cats  # base 含基础指标类目


def test_multiple_types_union_no_dup():
    svc = DimensionPackService()
    cats = svc.focus_categories(["congestion", "empty_green"])
    assert "empty_green" in cats and "imbalance" in cats
    assert len(cats) == len(set(cats))


def test_presentation_dimensions_gate_ring_to_empty_green():
    svc = DimensionPackService()
    # 拥堵：不含配时方案/环图维度
    congestion = svc.presentation_dimensions(["congestion"])
    assert "ring" not in congestion and "timing_plan" not in congestion
    assert "queue" in congestion and "flow" in congestion  # base + 拥堵
    # 空放：配时方案/环图维度出现
    empty = svc.presentation_dimensions(["empty_green"])
    assert "ring" in empty and "timing_plan" in empty


def test_presentation_dimensions_union_dedup():
    svc = DimensionPackService()
    dims = svc.presentation_dimensions(["congestion", "spillback"])
    assert "queue" in dims  # 两类共有，去重
    assert len(dims) == len(set(dims))


def test_unknown_type_falls_back_to_base():
    svc = DimensionPackService()
    cats = svc.focus_categories(["__nope__"])
    assert cats  # 至少返回 base


def test_no_deepagent_dependency():
    """硬约束守护：backend 运行时代码禁止 import deepagent 包(traffic_signal_agent)。"""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "intersection_agent"
    offenders = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        if "import traffic_signal_agent" in text or "from traffic_signal_agent" in text:
            offenders.append(str(p))
    assert not offenders, f"禁止依赖 deepagent: {offenders}"
