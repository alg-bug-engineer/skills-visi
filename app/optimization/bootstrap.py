"""Bootstrap signal_optimization_engine on sys.path."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from app.config import PROJECT_ROOT, get_settings


@lru_cache(maxsize=1)
def _ensure_engine_path() -> Path | None:
    settings = get_settings()
    candidates: list[Path] = []
    if settings.signal_opt_engine_src:
        candidates.append(Path(settings.signal_opt_engine_src))
    default = PROJECT_ROOT.parent / "古特代码仓库" / "signal_optimization_engine" / "src"
    candidates.append(default)

    for path in candidates:
        resolved = path.resolve()
        if (resolved / "optimization" / "intersection_optimizer.py").exists():
            src = str(resolved)
            if src not in sys.path:
                sys.path.insert(0, src)
            return resolved
    return None


def engine_available() -> bool:
    return _ensure_engine_path() is not None


@lru_cache(maxsize=1)
def get_optimize_intersection() -> Callable[[dict[str, Any]], dict[str, Any]]:
    if not _ensure_engine_path():
        raise RuntimeError(
            "未找到 signal_optimization_engine，请设置 SIGNAL_OPT_ENGINE_SRC 指向其 src 目录"
        )
    from optimization.intersection_optimizer import optimize_intersection

    return optimize_intersection
