"""阶段展示字段：对齐参考项目 stage_cfg.stage_name / flow_combo / sourceStageAtoms。"""

from app.data.load_intersection_from_pg import (
    _build_signal,
    _resolve_stage_display_name,
    _stage_atoms_from_name,
)


def test_stage_atoms_from_name_splits_cn_delimiters():
    assert _stage_atoms_from_name("北直、南直，东行人") == ["北直", "南直", "东行人"]


def test_resolve_stage_display_name_prefers_stage_cfg():
    cfg = {"stage_name": "东直左、北行人"}
    assert _resolve_stage_display_name(cfg, "东直", "1") == "东直左、北行人"


def test_build_signal_enriches_overlap_slice_stages():
    plan_rows = [
        {
            "plan_no": 18,
            "plan_name": "早高峰",
            "stage_no": 1,
            "stage_seq_no": 1,
            "green_sec": 14,
            "yellow_sec": 3,
            "all_red_sec": 2,
            "min_green_sec": 14,
            "max_green_sec": 60,
        },
        {
            "plan_no": 18,
            "plan_name": "早高峰",
            "stage_no": 8,
            "stage_seq_no": 2,
            "green_sec": 7,
            "yellow_sec": 3,
            "all_red_sec": 2,
            "min_green_sec": 14,
            "max_green_sec": 60,
        },
        {
            "plan_no": 18,
            "plan_name": "早高峰",
            "stage_no": 3,
            "stage_seq_no": 3,
            "green_sec": 52,
            "yellow_sec": 3,
            "all_red_sec": 2,
            "min_green_sec": 32,
            "max_green_sec": 68,
        },
        {
            "plan_no": 18,
            "plan_name": "早高峰",
            "stage_no": 4,
            "stage_seq_no": 4,
            "green_sec": 3,
            "yellow_sec": 3,
            "all_red_sec": 2,
            "min_green_sec": 14,
            "max_green_sec": 60,
        },
    ]
    stage_cfg_rows = [
        {
            "stage_no": 1,
            "stage_name": "东直左、北行人",
            "flow_combo_json": [
                {"f_dir8_no": 2, "flow_type_no": 1, "signal_atom": "东直左"},
                {"f_dir8_no": 0, "flow_type_no": 5, "signal_atom": "北行人"},
            ],
        },
        {
            "stage_no": 8,
            "stage_name": "东直左、北行人、南行人",
            "flow_combo_json": [
                {"f_dir8_no": 2, "flow_type_no": 1, "signal_atom": "东直左"},
                {"f_dir8_no": 0, "flow_type_no": 5, "signal_atom": "北行人"},
                {"f_dir8_no": 4, "flow_type_no": 5, "signal_atom": "南行人"},
            ],
        },
        {
            "stage_no": 3,
            "stage_name": "北直、南直、东行人、西行人",
            "flow_combo_json": [
                {"f_dir8_no": 0, "flow_type_no": 1, "signal_atom": "北直"},
                {"f_dir8_no": 4, "flow_type_no": 1, "signal_atom": "南直"},
                {"f_dir8_no": 2, "flow_type_no": 5, "signal_atom": "东行人"},
                {"f_dir8_no": 6, "flow_type_no": 5, "signal_atom": "西行人"},
            ],
        },
        {
            "stage_no": 4,
            "stage_name": "北直、南直",
            "flow_combo_json": [
                {"f_dir8_no": 0, "flow_type_no": 1, "signal_atom": "北直"},
                {"f_dir8_no": 4, "flow_type_no": 1, "signal_atom": "南直"},
            ],
        },
    ]

    signal = _build_signal(
        plan_rows,
        stage_cfg_rows=stage_cfg_rows,
        active_plan_no="18",
    )
    by_id = {s["phase_stage_id"]: s for s in signal["phase_stage_timing_list"]}

    assert by_id["1"]["phase_stage_name"] == "东直左、北行人"
    assert by_id["8"]["phase_stage_name"] == "东直左、北行人、南行人"
    assert by_id["1"]["phase_stage_name"] != by_id["8"]["phase_stage_name"]

    assert by_id["3"]["phase_stage_name"] == "北直、南直、东行人、西行人"
    assert by_id["4"]["phase_stage_name"] == "北直、南直"
    assert by_id["3"]["phase_stage_name"] != by_id["4"]["phase_stage_name"]

    assert by_id["1"]["source_stage_atoms"] == ["东直左", "北行人"]
    assert by_id["8"]["source_stage_atoms"] == ["东直左", "北行人", "南行人"]
    assert len(by_id["3"]["flow_combo"]) == 4
    assert len(by_id["4"]["flow_combo"]) == 2
