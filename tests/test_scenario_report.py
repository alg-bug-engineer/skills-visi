from app.trace.scenario_report import build_scenario_report, checklist_data_gaps


def test_build_scenario_report_with_checklist():
    checklist = [
        {"item_id": "turn_flow", "label": "转向流量", "status": "has_data", "summary": "流量正常"},
        {"item_id": "complaint_records", "label": "投诉记录", "status": "no_data", "summary": "无数据"},
    ]
    report = build_scenario_report(
        checklist,
        {"queue_ratio": 0.92, "saturation": 0.88},
        ticket={"direction": "东向西", "movement": "直行"},
    )
    assert report["available"] is True
    assert len(report["issues"]) == 2
    assert report["summary"]["has_data"] == 1
    gaps = checklist_data_gaps(report)
    assert any("投诉记录" in gap for gap in gaps)


def test_scenario_report_unavailable_without_checklist():
    report = build_scenario_report(None, {})
    assert report["available"] is False
