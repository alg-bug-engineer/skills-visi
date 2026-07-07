import logging
import uuid
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import PROJECT_ROOT

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_var.get()
        return True


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def set_trace_id(trace_id: str | None = None) -> str:
    value = trace_id or new_trace_id()
    trace_id_var.set(value)
    return value


def get_trace_id() -> str:
    return trace_id_var.get()


def setup_logging(level: str = "INFO") -> None:
    log_format = "%(asctime)s | %(levelname)s | trace_id=%(trace_id)s | %(name)s | %(message)s"
    formatter = logging.Formatter(log_format)
    trace_filter = TraceIdFilter()

    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(trace_filter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        LOG_DIR / "agent.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(trace_filter)
    root.addHandler(file_handler)
