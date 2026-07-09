"""解析人工调查 HTML 地图中的 pointData。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from preprocessing.manual_survey.taxonomy import (
    split_problem_types,
    validate_problem_type,
    validate_time_period,
)

logger = logging.getLogger(__name__)

_POINT_DATA_RE = re.compile(r"const pointData = (\[.*?\]);", re.DOTALL)


def make_record_key(
    survey_point_id: str,
    time_period: str,
    problem_primary: str,
    problem_desc: str,
) -> str:
    raw = f"{survey_point_id.strip()}|{time_period.strip()}|{problem_primary.strip()}|{problem_desc.strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def parse_html_manual_survey(
    path: Path,
    *,
    survey_batch: str = "jinan_2025",
) -> tuple[list[dict[str, Any]], list[str]]:
    """解析 HTML，返回 ODS 行列表与校验警告。"""
    content = path.read_text(encoding="utf-8")
    match = _POINT_DATA_RE.search(content)
    if not match:
        raise ValueError(f"未在 HTML 中找到 pointData 数组: {path}")

    points = json.loads(match.group(1))
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    for idx, point in enumerate(points):
        survey_point_id = str(point.get("id") or "").strip()
        inter_name_raw = str(point.get("name") or "").strip()
        time_period = str(point.get("time") or "").strip()
        problem_primary = str(point.get("problem") or "").strip()
        problem_full_text = str(point.get("full_problem") or problem_primary).strip()
        problem_desc = str(point.get("desc") or "").strip()
        lon = point.get("lng")
        lat = point.get("lat")
        display_color = str(point.get("color") or "").strip() or None

        if not survey_point_id or not inter_name_raw:
            warnings.append(f"行 {idx}: 缺少 id 或 name，已跳过")
            continue
        if validate_time_period(time_period) is None:
            warnings.append(f"行 {idx} ({survey_point_id}): 未知时段 '{time_period}'")
        if validate_problem_type(problem_primary) is None:
            warnings.append(f"行 {idx} ({survey_point_id}): 未知主问题 '{problem_primary}'")
        for pt in split_problem_types(problem_full_text):
            if validate_problem_type(pt) is None:
                warnings.append(f"行 {idx} ({survey_point_id}): 未知完整问题类型 '{pt}'")
        if lon is None or lat is None:
            warnings.append(f"行 {idx} ({survey_point_id}): 缺少坐标")
            continue

        rows.append(
            {
                "record_key": make_record_key(
                    survey_point_id, time_period, problem_primary, problem_desc
                ),
                "survey_batch": survey_batch,
                "survey_point_id": survey_point_id,
                "inter_name_raw": inter_name_raw,
                "time_period": time_period,
                "problem_primary": problem_primary,
                "problem_full_text": problem_full_text,
                "problem_desc": problem_desc[:512],
                "lon": float(lon),
                "lat": float(lat),
                "coord_srs": "gcj02",
                "display_color": display_color,
                "source_file": str(path),
            }
        )

    for msg in warnings:
        logger.warning(msg)

    return rows, warnings
