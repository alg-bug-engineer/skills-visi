"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from intersection_agent import __version__
from intersection_agent.api.middleware import RequestLoggingMiddleware
from intersection_agent.api.routes import router
from intersection_agent.config import get_settings
from intersection_agent.db.postgres import PostgresPool
from intersection_agent.logging_config import setup_logging

_pool = PostgresPool()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — connect/disconnect resources."""
    setup_logging()
    settings = get_settings()
    import logging

    logging.getLogger(__name__).info(
        "app.startup version=%s mock_llm=%s mock_db=%s log_file=%s",
        __version__,
        settings.mock_llm,
        settings.mock_db,
        settings.log_file,
    )
    if not settings.mock_db:
        try:
            await _pool.connect()
        except Exception:
            pass
    yield
    await _pool.close()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title="交通智能体 · 拥堵诊断 API",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api/v1")

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """Return JSON errors instead of empty 500 bodies."""
        import logging

        logging.getLogger(__name__).exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "reply": {"type": "error", "content": f"服务内部错误: {type(exc).__name__}"},
                "detail": str(exc),
            },
        )

    @app.get("/health")
    async def root_health():
        """Root health check (alias)."""
        from intersection_agent.api.routes import health

        return await health()

    return app


app = create_app()


def run() -> None:
    """CLI entrypoint for uvicorn."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "intersection_agent.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
