"""单点优化器 vendor 集成：仓库内置 vendor 副本即可加载。"""

from app.optimization.bootstrap import _ensure_engine_path, engine_available, get_optimize_intersection


def test_vendored_signal_optimization_engine_is_available():
    path = _ensure_engine_path()
    assert path is not None
    assert (path / "optimization" / "intersection_optimizer.py").exists()
    assert engine_available() is True
    assert get_optimize_intersection().__name__ == "optimize_intersection"
