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
