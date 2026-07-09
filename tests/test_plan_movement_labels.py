"""需求 20·R1：方案证据 movement/供需强度 标签中文化，杜绝 d2_t2 机器码。"""

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    path = PROJECT_ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_OPT = _load("rspo", "skills/plan-generation/scripts/run_single_point_optimizer.py")


def test_movement_evidence_fills_chinese_label_when_missing():
    item = {"dir8No": 4, "turnDirNo": 2, "turnFlowTotal": 800}
    result = _OPT._normalize_movement_evidence(item)
    assert result["label"] == "南进口直行"
    # movementKey 保留机读键，但 label 必须是人可读中文，前端优先展示 label
    assert result["movementKey"] == "d4_t2"


def test_movement_evidence_prefers_existing_cn_label():
    item = {"dir8No": 2, "turnDirNo": 1, "label": "东-左转"}
    result = _OPT._normalize_movement_evidence(item)
    assert result["label"] == "东-左转"


def test_machine_key_label_is_replaced_with_chinese():
    item = {"dir8No": 6, "turnDirNo": 2, "label": "d6_t2"}
    result = _OPT._normalize_movement_evidence(item)
    assert result["label"] == "西进口直行"


def test_direction_intensity_list_labels_are_chinese():
    meta = {
        "direction_intensity_list": [
            {"dir8No": 0, "turnDirNo": 2, "intensity": 0.9, "historyVirtualFlowVph": 80},
            {"dir8No": 2, "turnDirNo": 2, "intensity": 0.8, "movementKey": "d2_t2"},
        ]
    }
    out = _OPT._build_optimization_meta(meta)
    labels = [row["label"] for row in out["direction_intensity_list"]]
    assert labels == ["北进口直行", "东进口直行"]
    assert "historyVirtualFlowVph" not in out["direction_intensity_list"][0]
    assert "has_virtual_flow" not in out["data_quality"]
    assert "virtual_flow_movements" not in out["data_quality"]
