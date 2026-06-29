"""扫描快照存储（v1：JSON 文件；PG 表留待后续）。

一次扫描 = 一个 ``ScanRun``，落 ``{snapshot_dir}/{run_id}.json``。
地图只读这些快照，秒级响应。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ScanRun:
    """一次区域扫描的完整快照。"""

    run_id: str
    created_at: str
    region: str
    version_id: str
    periods: list[str]
    intersection_total: int
    covered: int
    records: list[dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def new_run_id() -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S")


def _ensure_dir(snapshot_dir: str) -> Path:
    path = Path(snapshot_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_run(run: ScanRun, snapshot_dir: str) -> str:
    """写快照 JSON，返回文件路径。"""
    path = _ensure_dir(snapshot_dir) / f"{run.run_id}.json"
    path.write_text(
        json.dumps(asdict(run), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(path)


def load_run(run_id: str, snapshot_dir: str) -> ScanRun:
    """按 run_id 读回快照。"""
    path = Path(snapshot_dir) / f"{run_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return ScanRun(**data)


def list_runs(snapshot_dir: str) -> list[dict[str, Any]]:
    """列出全部快照摘要，按 created_at 倒序。"""
    path = Path(snapshot_dir)
    if not path.exists():
        return []
    runs: list[dict[str, Any]] = []
    for fp in path.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        runs.append(
            {
                "run_id": data.get("run_id"),
                "created_at": data.get("created_at"),
                "region": data.get("region"),
                "periods": data.get("periods"),
                "intersection_total": data.get("intersection_total"),
                "covered": data.get("covered"),
            }
        )
    runs.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return runs
