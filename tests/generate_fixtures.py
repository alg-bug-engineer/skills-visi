from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1] / "skills"
OUT = Path(__file__).resolve().parent / "fixtures"


def _load(name: str, script: str):
    spec = importlib.util.spec_from_file_location(name, SKILLS / script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = _load("dm", "data-analysis-diagnosis/scripts/demo_metrics.py").DEMO_METRICS
    ticket = {"intersection_name": "文化西路与舜华路交叉口", "direction": "东向西", "movement": "直行"}
    topology = _load("dt", "data-analysis-diagnosis/scripts/demo_topology.py").build_demo_topology(ticket)
    (OUT / "overflow_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "overflow_topology.json").write_text(json.dumps(topology, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
