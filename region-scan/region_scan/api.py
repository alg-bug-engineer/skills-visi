"""扫描 API —— 只读快照 + 触发后台扫描。

地图前端消费这些端点；读路径全部从快照 JSON 取，秒级响应。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from region_scan.config import get_scan_settings
from region_scan.snapshot import list_runs, load_run, save_run

ScanRunner = Callable[..., Awaitable[Any]]


class ScanRequest(BaseModel):
    periods: list[str] | None = None
    region: str = "全域"
    concurrency: int | None = None


def _load_or_404(run_id: str, snapshot_dir: str):
    try:
        return load_run(run_id, snapshot_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")


def create_app(
    snapshot_dir: str | None = None,
    scan_runner: ScanRunner | None = None,
) -> FastAPI:
    settings = get_scan_settings()
    snap_dir = snapshot_dir or settings.snapshot_dir

    app = FastAPI(title="区域路口扫描 API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/scan/runs")
    def get_runs() -> list[dict[str, Any]]:
        return list_runs(snap_dir)

    @app.get("/api/scan/runs/{run_id}")
    def get_run(
        run_id: str,
        period: str | None = Query(None),
        band: str | None = Query(None),
        metric: str | None = Query(None),
    ) -> dict[str, Any]:
        run = _load_or_404(run_id, snap_dir)
        records = run.records
        if period:
            records = [r for r in records if r.get("period") == period]
        if band:
            records = [r for r in records if r.get("problem_band") == band]
        if metric:
            for r in records:
                r["color_value"] = (r.get("metrics") or {}).get(metric)
        return {
            "run_id": run.run_id,
            "created_at": run.created_at,
            "region": run.region,
            "periods": run.periods,
            "intersection_total": run.intersection_total,
            "covered": run.covered,
            "metric": metric,
            "records": records,
        }

    @app.get("/api/scan/runs/{run_id}/pilots")
    def get_pilots(
        run_id: str,
        period: str | None = Query(None),
    ) -> dict[str, Any]:
        run = _load_or_404(run_id, snap_dir)
        pilots = [
            r
            for r in run.records
            if r.get("problem_band") == "配时可解" and r.get("pilot_score") is not None
        ]
        if period:
            pilots = [r for r in pilots if r.get("period") == period]
        pilots.sort(key=lambda r: float(r.get("pilot_score") or 0), reverse=True)
        return {"run_id": run.run_id, "count": len(pilots), "pilots": pilots}

    @app.get("/api/scan/intersections/{inter_id}")
    def get_intersection(
        inter_id: str,
        run_id: str = Query(...),
        period: str | None = Query(None),
    ) -> dict[str, Any]:
        run = _load_or_404(run_id, snap_dir)
        matches = [r for r in run.records if r.get("inter_id") == inter_id]
        if period:
            matches = [r for r in matches if r.get("period") == period]
        if not matches:
            raise HTTPException(status_code=404, detail="intersection not found in run")
        if period:
            return matches[0]
        return {"inter_id": inter_id, "run_id": run_id, "records": matches}

    @app.post("/api/scan/runs", status_code=202)
    async def trigger_scan(req: ScanRequest, background: BackgroundTasks) -> dict[str, Any]:
        runner = scan_runner
        if runner is None:
            from region_scan.scan_engine import run_region_scan

            async def runner(pool, settings, **kw):  # type: ignore[misc]
                return await run_region_scan(pool, settings, **kw)

        async def _job() -> None:
            from intersection_agent.db.postgres import PostgresPool

            pool = PostgresPool(settings.base)
            run = await runner(
                pool,
                settings,
                periods=req.periods,
                concurrency=req.concurrency,
                region=req.region,
            )
            await pool.close()
            save_run(run, snap_dir)

        background.add_task(_job)
        return {"status": "accepted", "region": req.region, "periods": req.periods}

    return app


app = create_app()
