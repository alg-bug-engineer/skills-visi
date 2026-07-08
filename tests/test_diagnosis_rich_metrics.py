"""需求13-步骤4：诊断响应透传逐进口/逐转向富指标与配时画像。

验证 analyze_overflow 在有 pg_raw + task.metrics + signal 时透传富指标，
且在 mock/无 pg_raw 场景下富字段安全降级（空列表/None），不破坏原有标量指标。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = REPO_ROOT / "data" / "aoti_jingshi_backend_data.json"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_analyze_overflow():
    script = (
        REPO_ROOT
        / "skills"
        / "data-analysis-diagnosis"
        / "scripts"
        / "analyze_overflow.py"
    )
    spec = importlib.util.spec_from_file_location("analyze_overflow", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.analyze_overflow


@pytest.fixture
def snapshot() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


@pytest.fixture
def rich_ticket() -> dict:
    return {
        "intersection_name": "奥体西路与经十路路口",
        "direction": "北向南",
        "movement": "直行",
    }


def test_rich_metrics_passthrough_from_snapshot(snapshot, rich_ticket):
    from app.data.pg_adapters import metrics_for_diagnosis

    analyze_overflow = _load_analyze_overflow()
    task = snapshot["task"]
    raw = snapshot["raw"]
    metrics_input = metrics_for_diagnosis(task["metrics"], rich_ticket)

    output = analyze_overflow(
        metrics_input,
        rich_ticket,
        topology=None,
        pg_raw=raw,
        signal=task["signal"],
        scope=task["scope"],
        task_metrics=task["metrics"],
    )
    metrics = output["metrics"]

    # by_approach：逐进口饱和度
    assert isinstance(metrics["by_approach"], list) and metrics["by_approach"]
    for approach in metrics["by_approach"]:
        assert approach["approach"]
        assert "saturation" in approach
        assert "delay_index" in approach
        assert "los" in approach

    # by_movement：逐转向饱和度 + 绿灯利用率 + 等级分类
    assert isinstance(metrics["by_movement"], list) and metrics["by_movement"]
    for movement in metrics["by_movement"]:
        assert movement["movement"]
        assert "saturation" in movement
        assert "green_utilization" in movement
        assert "level" in movement
    # 存在过饱和转向（快照最大饱和度 1.90）
    oversaturated = [m for m in metrics["by_movement"] if m["level"] == "过饱和"]
    assert oversaturated, "应存在过饱和转向"
    assert all(m["saturation"] >= 1.0 for m in oversaturated)

    # 方向失衡指数透传
    assert metrics["imbalance_index"] is not None
    assert metrics["imbalance_index"] == pytest.approx(task["metrics"]["imbalance_index"])

    # 交叉口级 LOS 仍在
    assert metrics["los"]

    # 计数
    assert metrics["approach_count"] is not None
    assert metrics["lane_count"] is not None

    # 配时画像
    timing = output["timing_profile"]
    assert timing["cycle_s"] == pytest.approx(task["signal"]["current_cycle_s"])
    assert timing["time_plan_count"] == task["signal"]["time_plan_count"]
    assert timing["plan_name"] == task["signal"]["plan_name"]


def test_rich_metrics_graceful_without_pg_raw():
    analyze_overflow = _load_analyze_overflow()
    metrics_input = json.loads(
        (FIXTURES / "overflow_metrics.json").read_text(encoding="utf-8")
    )
    ticket = {
        "intersection_name": "文化西路与舜华路交叉口",
        "direction": "东向西",
        "movement": "直行",
    }

    output = analyze_overflow(
        metrics_input,
        ticket,
        topology=None,
        pg_raw={},
        signal={},
        scope={},
        task_metrics={},
    )
    metrics = output["metrics"]

    # 富字段存在但为空/None（安全降级）
    assert metrics["by_approach"] == []
    assert metrics["by_movement"] == []
    assert metrics["imbalance_index"] is None
    assert metrics["approach_count"] is None
    assert metrics["lane_count"] is None
    assert output["timing_profile"]["cycle_s"] is None
    assert output["timing_profile"]["time_plan_count"] is None

    # 原有标量指标不受影响
    assert metrics["queue_length_m"] == metrics_input["queue_length_m"]
    assert metrics["storage_length_m"] == metrics_input["storage_length_m"]
    assert metrics["green_utilization"] == metrics_input["green_utilization"]
    assert metrics["saturation"] is not None
    assert metrics["los"]


@pytest.mark.asyncio
async def test_handler_threads_rich_metrics(snapshot, rich_ticket):
    from app.config import Settings
    from app.data.pg_adapters import metrics_for_diagnosis, topology_from_pg_raw
    from app.runtime.registry import get_registry
    from app.runtime.skill_types import SkillContext

    task = snapshot["task"]
    raw = snapshot["raw"]
    inter = raw.get("inter") or {}
    if isinstance(inter, list):
        inter = inter[0] if inter else {}
    metrics_input = metrics_for_diagnosis(task["metrics"], rich_ticket)
    topology = topology_from_pg_raw({**raw, "metrics": task["metrics"]}, rich_ticket, inter)

    skill = get_registry().get("data_analysis_diagnosis")
    context = SkillContext(
        trace_id="rich-metrics-test",
        user_input="test",
        task={
            "diagnosis_ticket": rich_ticket,
            "metrics": {**task["metrics"], **metrics_input},
            "topology": topology,
            "pg_raw": raw,
            "signal": task["signal"],
            "scope": task["scope"],
        },
    )
    result = await skill.run(context, settings=Settings(allow_demo_fallback=False))

    assert result.success is True
    out_metrics = result.output["metrics"]
    assert out_metrics["by_movement"], "handler 应透传 by_movement"
    assert out_metrics["by_approach"], "handler 应透传 by_approach"
    assert result.output["timing_profile"]["cycle_s"] == pytest.approx(
        task["signal"]["current_cycle_s"]
    )
