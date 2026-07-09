"""解析 docx 年报与 HTML 地图数据源。"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

_TITLE_RE = re.compile(r"^(\d+)、(.+?)\s+(.+?)\s+（共计\s*(\d+)\s*件）$")
_ISSUE_RE = re.compile(r"([一二三四五六七八九十]+)是([^（；]+?)（约\s*(\d+)\s*件）")


def make_location_key(district_name: str, location_text: str, stat_period: str) -> str:
    raw = f"{district_name.strip()}|{location_text.strip()}|{stat_period.strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def parse_docx_report(path: Path, *, stat_period: str = "2025") -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    text = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    entries: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        match = _TITLE_RE.match(lines[i])
        if not match:
            i += 1
            continue
        seq, district, location, count = match.groups()
        body: list[str] = []
        i += 1
        while i < len(lines) and not _TITLE_RE.match(lines[i]) and not lines[i].startswith("三、"):
            body.append(lines[i])
            i += 1
        summary = "".join(body)
        issue_items = []
        for im in _ISSUE_RE.finditer(summary):
            issue_items.append(
                {
                    "seq_cn": im.group(1),
                    "topic_raw": im.group(2).strip(),
                    "count": int(im.group(3)),
                    "text": im.group(2).strip(),
                }
            )
        district_name = district.strip()
        location_text = location.strip()
        entries.append(
            {
                "location_key": make_location_key(district_name, location_text, stat_period),
                "stat_period": stat_period,
                "report_seq": int(seq),
                "district_name": district_name,
                "location_text": location_text,
                "complaint_count": int(count),
                "summary_text": summary,
                "issue_items_json": issue_items,
                "source_file": str(path),
            }
        )
    return entries


def parse_html_geocode(path: Path, *, stat_period: str = "2025") -> list[dict[str, Any]]:
    content = path.read_text(encoding="utf-8")
    match = re.search(r"const points = (\[.*?\]);", content, re.S)
    if not match:
        raise ValueError(f"未在 HTML 中找到 points 数组: {path}")
    points = json.loads(match.group(1))
    rows: list[dict[str, Any]] = []
    for point in points:
        district_name = str(point.get("district") or "").strip()
        location_text = str(point.get("location") or "").strip()
        rows.append(
            {
                "location_key": make_location_key(district_name, location_text, stat_period),
                "stat_period": stat_period,
                "location_text": location_text,
                "district_name": district_name,
                "complaint_count": int(point.get("count") or 0),
                "summary_text": str(point.get("summary") or ""),
                "geocode_name": str(point.get("matched_name") or ""),
                "geocode_method": str(point.get("match_method") or ""),
                "lon": float(point["lon"]) if point.get("lon") is not None else None,
                "lat": float(point["lat"]) if point.get("lat") is not None else None,
                "coord_srs": "gcj02",
                "source_file": str(path),
            }
        )
    return rows
