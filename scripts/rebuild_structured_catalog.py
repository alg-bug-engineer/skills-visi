#!/usr/bin/env python3
"""手动重建 data/structured 旁路沉淀（需求30 方案 A）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.services.case_tag_extractor import CaseTagExtractor  # noqa: E402
from app.services.structured_catalog_service import StructuredCatalogService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild structured knowledge catalogs")
    parser.add_argument("--force", action="store_true", help="忽略源指纹，强制重建")
    args = parser.parse_args()

    settings = get_settings()
    service = StructuredCatalogService(
        output_dir=settings.structured_catalog_abs_path,
        industry_source=settings.case_library_abs_path,
        feedback_source=settings.feedback_log_abs_path,
        experience_source=settings.user_experience_abs_path,
        tag_extractor=CaseTagExtractor(),
    )
    manifest = service.rebuild(force=args.force)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
