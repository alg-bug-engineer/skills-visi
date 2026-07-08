from app.data import load_intersection_from_pg as pg


def test_adjacent_inter_ids_are_deduplicated():
    rows = [
        {"adjacent_inter_id": "U1"},
        {"adjacent_inter_id": "U1"},
        {"upstream_inter_id": "D1"},
        {"adjacent_inter_id": ""},
        {"inter_id": "target_only"},
    ]

    assert pg._adjacent_inter_ids(rows) == ["U1", "D1"]


def test_adjacent_offsets_from_plan_rows_keep_real_offset_metadata():
    rows = [
        {
            "inter_id": "U1",
            "plan_no": "7",
            "plan_name": "晚高峰",
            "cycle_len_sec": 120,
            "offset_sec": 22,
        },
        {
            "inter_id": "U1",
            "plan_no": "7",
            "cycle_len_sec": 120,
            "offset_sec": 22,
        },
        {
            "inter_id": "D1",
            "plan_no": "8",
            "cycle_len_sec": 100,
            "offset_sec": None,
        },
    ]

    assert pg._adjacent_offsets_from_plan_rows(rows) == {
        "U1": {
            "offset_s": 22.0,
            "cycle_s": 120.0,
            "plan_no": "7",
            "plan_name": "晚高峰",
            "source": "dwd_ctl_inter_plan_cfg.offset_sec",
        }
    }


def test_query_adjacent_offsets_reuses_active_plan_query(monkeypatch):
    calls: list[str] = []

    def fake_active_plan(schema: str, inter_id: str):
        calls.append(f"{schema}:{inter_id}")
        return [
            {
                "inter_id": inter_id,
                "plan_no": "1",
                "cycle_len_sec": 130,
                "offset_sec": 48 if inter_id == "U1" else 66,
            }
        ]

    monkeypatch.setattr(pg, "_query_active_plan", fake_active_plan)

    result = pg._query_adjacent_offsets(
        "flow_schema",
        [{"adjacent_inter_id": "U1"}, {"adjacent_inter_id": "D1"}],
    )

    assert calls == ["flow_schema:U1", "flow_schema:D1"]
    assert result["U1"]["offset_s"] == 48.0
    assert result["D1"]["offset_s"] == 66.0
