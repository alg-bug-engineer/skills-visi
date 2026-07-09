"""Load project-level .env into os.environ."""

from __future__ import annotations

from pathlib import Path


def load_project_env() -> None:
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        return

    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")
