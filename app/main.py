from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.logging_setup import setup_logging
from app.services.case_tag_extractor import CaseTagExtractor
from app.services.structured_catalog_service import StructuredCatalogService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    try:
        catalog = StructuredCatalogService(
            output_dir=settings.structured_catalog_abs_path,
            industry_source=settings.case_library_abs_path,
            feedback_source=settings.feedback_log_abs_path,
            experience_source=settings.user_experience_abs_path,
            tag_extractor=CaseTagExtractor(),
        )
        manifest = catalog.rebuild(force=False)
        logger.info(
            "启动前结构化沉淀完成 skipped=%s counts=%s",
            manifest.get("skipped"),
            (manifest.get("counts") if isinstance(manifest, dict) else None),
        )
    except Exception as exc:  # pragma: no cover - 启动降级，不阻断服务
        logger.exception("启动前结构化沉淀失败，继续启动: %s", exc)
    yield


app = FastAPI(
    title="交通智能体 API",
    description="基于 Qwen 与 Skills 的交通排队溢出诊断后端",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
