"""道路 line 实体生成。"""

__all__ = ["run_build"]


def __getattr__(name: str):
    if name == "run_build":
        from preprocessing.line.dim_line_info import run_build
        return run_build
    raise AttributeError(name)
