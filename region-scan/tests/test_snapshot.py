"""Task 4.1 — 扫描快照存储。"""

from region_scan.snapshot import ScanRun, list_runs, load_run, save_run


def _run() -> ScanRun:
    return ScanRun(
        run_id="20260629-120000",
        created_at="2026-06-29T12:00:00",
        region="全域",
        version_id="20260501",
        periods=["早高峰", "白平峰", "晚高峰"],
        intersection_total=2,
        covered=2,
        records=[
            {"inter_id": "A1", "period": "早高峰", "problem_band": "配时可解", "pilot_score": 42.0},
            {"inter_id": "A1", "period": "晚高峰", "problem_band": "工程可解", "pilot_score": None},
        ],
    )


def test_save_and_load_roundtrip(tmp_path):
    run = _run()
    path = save_run(run, str(tmp_path))
    assert path.endswith(".json")

    loaded = load_run("20260629-120000", str(tmp_path))
    assert loaded == run
    assert loaded.records[0]["problem_band"] == "配时可解"


def test_list_runs(tmp_path):
    save_run(_run(), str(tmp_path))
    runs = list_runs(str(tmp_path))
    assert len(runs) == 1
    assert runs[0]["run_id"] == "20260629-120000"
    assert runs[0]["covered"] == 2
    assert runs[0]["periods"] == ["早高峰", "白平峰", "晚高峰"]
