"""Task 5.1 — 扫描 API（TestClient + 预置快照）。"""

import pytest
from fastapi.testclient import TestClient

from region_scan.api import create_app
from region_scan.snapshot import ScanRun, save_run


def _rec(inter_id, period, band, pilot, sat):
    return {
        "inter_id": inter_id,
        "inter_name": f"路口{inter_id}",
        "lon": 117.0,
        "lat": 36.6,
        "period": period,
        "metrics": {"saturation_max": sat, "unbalance_index": 0.3, "green_utilization": 0.5},
        "top_issues": ["失衡"] if band != "无明显问题" else [],
        "severity": "medium",
        "control_improvement_ceiling": "high" if band == "配时可解" else "low",
        "governance_summary": "g",
        "governance_actions": [],
        "has_data": True,
        "data_quality_tags": [],
        "problem_band": band,
        "pilot_score": pilot,
    }


@pytest.fixture()
def client(tmp_path):
    run = ScanRun(
        run_id="R1",
        created_at="2026-06-29T12:00:00",
        region="全域",
        version_id="20260501",
        periods=["早高峰", "晚高峰"],
        intersection_total=3,
        covered=3,
        records=[
            _rec("A", "早高峰", "配时可解", 80.0, 0.75),
            _rec("B", "早高峰", "配时可解", 40.0, 0.70),
            _rec("C", "早高峰", "工程可解", None, 1.2),
            _rec("A", "晚高峰", "无明显问题", None, 0.4),
        ],
    )
    save_run(run, str(tmp_path))
    return TestClient(create_app(snapshot_dir=str(tmp_path)))


def test_list_runs(client):
    r = client.get("/api/scan/runs")
    assert r.status_code == 200
    assert r.json()[0]["run_id"] == "R1"


def test_get_run_filters_by_band(client):
    r = client.get("/api/scan/runs/R1", params={"band": "配时可解"})
    assert r.status_code == 200
    recs = r.json()["records"]
    assert recs and all(x["problem_band"] == "配时可解" for x in recs)


def test_get_run_filters_by_period(client):
    r = client.get("/api/scan/runs/R1", params={"period": "晚高峰"})
    recs = r.json()["records"]
    assert all(x["period"] == "晚高峰" for x in recs)


def test_pilots_sorted_desc(client):
    r = client.get("/api/scan/runs/R1/pilots")
    assert r.status_code == 200
    pilots = r.json()["pilots"]
    scores = [p["pilot_score"] for p in pilots]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 80.0
    assert all(p["problem_band"] == "配时可解" for p in pilots)


def test_intersection_detail(client):
    r = client.get("/api/scan/intersections/A", params={"run_id": "R1", "period": "早高峰"})
    assert r.status_code == 200
    body = r.json()
    assert body["inter_id"] == "A"
    assert body["period"] == "早高峰"


def test_unknown_run_404(client):
    assert client.get("/api/scan/runs/NOPE").status_code == 404


def test_post_triggers_scan(client, tmp_path):
    captured = {}

    async def fake_runner(pool, settings, **kw):
        captured["ran"] = True
        from region_scan.snapshot import ScanRun as SR

        return SR("R2", "now", "全域", "v", ["早高峰"], 0, 0, [])

    app = create_app(snapshot_dir=str(tmp_path), scan_runner=fake_runner)
    c = TestClient(app)
    r = c.post("/api/scan/runs", json={"periods": ["早高峰"]})
    assert r.status_code == 202
    assert r.json()["status"] == "accepted"
    assert captured.get("ran")
