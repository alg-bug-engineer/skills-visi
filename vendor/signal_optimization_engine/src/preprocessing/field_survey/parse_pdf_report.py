"""解析交通组织调研 PDF：问题明细、矩阵、建议与图片。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from preprocessing.complaint.inter_match import normalize_location_name
from preprocessing.field_survey.taxonomy import (
    ISSUE_TYPES,
    issue_category_for_type,
    section_names,
    validate_issue_type,
)

try:
    import fitz  # PyMuPDF
except ImportError as exc:  # pragma: no cover
    raise ImportError("请安装 pymupdf: pip install pymupdf") from exc

_PAGE_FOOTER_RE = re.compile(r"^--\s*\d+\s+of\s+\d+\s*--$")
_PAGE_NUM_RE = re.compile(r"^\d+$")
_SECTION_HDR_RE = re.compile(r"^(\d+)\s+(工业南路|新泺大街|解放路|经十路|旅游路|奥体西路|奥体中路)$")
_INTER_HDR_RE = re.compile(
    r"^(\d+\.\d+)\s+(.+?)(?:路口)?(?:（(.+?)）)?$"
)
_CASE_INTER_RE = re.compile(r"^(\d+)、(.+?)路口$")
_ISSUE_HDR_RE = re.compile(r"^问题\s*(\d+)[：:]\s*(.+)$")
_REC_INLINE_RE = re.compile(r"^建议(.+)$")
_CAPTION_RE = re.compile(r"^图\s*(.+)$")
_HORIZON_RE = re.compile(r"^[一二三四五六七八九十]+、\s*(近期|远期)[：:]?\s*$")
_REC_ITEM_RE = re.compile(r"^(\d+)[、.．]\s*(.+)$")
_MATRIX_ROW_RE = re.compile(r"^(\d+\.\d+)\s+(.+)$")
_SKIP_LINES = frozenset(
    {
        "通行秩序与管控类问题",
        "交通空间与渠化设计类问题",
        "交通管控配套设施类问题",
        "序号",
        "路口名称",
        "大类",
        "编号",
        "细分问题",
        "问题核心属性",
        "本次调研问题规模",
        "二、具体路口问题",
    }
)


@dataclass
class _ParseState:
    section_no: str = ""
    section_name: str = ""
    inter_seq: str = ""
    inter_name_raw: str = ""
    inter_alias: str = ""
    current_issue_seq: int = 0
    current_issue_type: str = ""
    current_issue_key: str = ""
    in_case_study: bool = False
    case_inter_name: str = ""
    in_recommendation_block: bool = False
    current_horizon: str = ""
    rec_seq: int = 0


def make_issue_key(
    report_batch: str,
    section_no: str,
    inter_seq: str,
    issue_seq: int,
    issue_type: str,
) -> str:
    raw = f"{report_batch}|{section_no}|{inter_seq}|{issue_seq}|{issue_type}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def make_matrix_key(report_batch: str, inter_seq: str) -> str:
    raw = f"{report_batch}|{inter_seq}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def make_rec_key(report_batch: str, inter_name_raw: str, horizon: str, rec_seq: int) -> str:
    raw = f"{report_batch}|{inter_name_raw}|{horizon}|{rec_seq}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def make_image_key(report_batch: str, local_path: str) -> str:
    raw = f"{report_batch}|{local_path}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def inter_name_slug(name: str) -> str:
    norm = normalize_location_name(name)
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", norm.lower())
    slug = slug.strip("_")
    return slug[:64] or "unknown"


def _clean_line(line: str) -> str:
    text = (line or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _is_noise_line(line: str) -> bool:
    if not line:
        return True
    if _PAGE_FOOTER_RE.match(line):
        return True
    if _PAGE_NUM_RE.match(line) and len(line) <= 3:
        return True
    if line in _SKIP_LINES:
        return True
    if line.startswith("大类") or line.startswith("一、") and "总结" in line:
        return True
    return False


def _normalize_inter_name(name: str, alias: str = "") -> str:
    text = (name or "").strip()
    if text and not text.endswith("路口"):
        text = f"{text}路口"
    return text


def _extract_pages_text(pdf_path: Path) -> list[tuple[int, list[str]]]:
    doc = fitz.open(str(pdf_path))
    pages: list[tuple[int, list[str]]] = []
    try:
        for page_idx in range(len(doc)):
            page_no = page_idx + 1
            text = doc[page_idx].get_text("text")
            lines = [_clean_line(ln) for ln in text.splitlines()]
            lines = [ln for ln in lines if not _is_noise_line(ln)]
            pages.append((page_no, lines))
    finally:
        doc.close()
    return pages


_MATRIX_SECTION_RE = re.compile(r"^[一二三四五六七八九十]+、(.+)$")
_MATRIX_SEQ_RE = re.compile(r"^(\d+\.\d+)$")


def _parse_matrix_rows(pages: list[tuple[int, list[str]]], *, report_batch: str, source_file: str) -> list[dict[str, Any]]:
    """PDF 表格按单元格逐行导出：序号、路口名、✅ 各占一行。"""
    rows: list[dict[str, Any]] = []
    section_name = ""
    matrix_lines: list[str] = []

    for page_no, lines in pages:
        if 11 <= page_no <= 13:
            matrix_lines.extend(lines)

    i = 0
    while i < len(matrix_lines):
        line = matrix_lines[i]

        m_sec = _MATRIX_SECTION_RE.match(line)
        if m_sec:
            section_name = m_sec.group(1).strip()
            i += 1
            continue

        m_seq = _MATRIX_SEQ_RE.match(line)
        if not m_seq:
            i += 1
            continue

        inter_seq = m_seq.group(1)
        i += 1
        name_parts: list[str] = []
        while i < len(matrix_lines):
            nxt = matrix_lines[i]
            if _MATRIX_SEQ_RE.match(nxt) or _MATRIX_SECTION_RE.match(nxt):
                break
            if nxt == "✅":
                break
            if nxt in _SKIP_LINES or nxt in ISSUE_TYPES:
                i += 1
                continue
            if "管控类问题" in nxt or nxt in {"序号", "路口名称", "不足", "问题"}:
                i += 1
                continue
            name_parts.append(nxt)
            i += 1

        check_count = 0
        while i < len(matrix_lines) and matrix_lines[i] == "✅":
            check_count += 1
            i += 1

        name_part = re.sub(r"\s+", "", "".join(name_parts))
        name_part = name_part.replace("-", "与").replace("（", "(").replace("）", ")")
        if "(" in name_part and ")" in name_part:
            # 保留括号别名但统一为中文括号
            name_part = name_part.replace("(", "（").replace(")", "）")
        if name_part and not name_part.endswith("路口"):
            name_part = f"{name_part}路口"

        flag_json = {t: False for t in ISSUE_TYPES}
        for idx in range(min(check_count, len(ISSUE_TYPES))):
            flag_json[ISSUE_TYPES[idx]] = True

        if not name_part:
            continue

        issue_type_cnt = sum(1 for v in flag_json.values() if v)
        rows.append(
            {
                "matrix_key": make_matrix_key(report_batch, inter_seq),
                "report_batch": report_batch,
                "inter_seq": inter_seq,
                "inter_name_raw": name_part,
                "section_name": section_name,
                "flag_json": flag_json,
                "issue_type_cnt": issue_type_cnt,
                "source_file": source_file,
            }
        )
    return rows


def _parse_text_content(
    pages: list[tuple[int, list[str]]],
    *,
    report_batch: str,
    source_file: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    issues: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    warnings: list[str] = []

    state = _ParseState()
    pending_desc: list[str] = []
    pending_rec: list[str] = []
    detail_started = False

    def flush_issue(*, page_no: int) -> None:
        nonlocal pending_desc, pending_rec
        if not state.current_issue_type or state.current_issue_seq <= 0:
            pending_desc = []
            pending_rec = []
            return

        inter_name = state.inter_name_raw or state.case_inter_name
        if not inter_name:
            pending_desc = []
            pending_rec = []
            return

        issue_type = validate_issue_type(state.current_issue_type)
        if issue_type is None:
            warnings.append(f"未知问题类型 p{page_no}: {state.current_issue_type}")
            pending_desc = []
            pending_rec = []
            return

        issue_key = make_issue_key(
            report_batch,
            state.section_no or "0",
            state.inter_seq or "0",
            state.current_issue_seq,
            issue_type,
        )
        desc_text = "".join(pending_desc).strip()
        rec_text = "".join(pending_rec).strip()
        if desc_text.startswith("建议"):
            if not rec_text:
                rec_text = desc_text
            desc_text = ""
        if not desc_text and not rec_text:
            pending_desc = []
            pending_rec = []
            return

        issues.append(
            {
                "issue_key": issue_key,
                "report_batch": report_batch,
                "section_no": state.section_no or None,
                "section_name": state.section_name or None,
                "inter_seq": state.inter_seq or None,
                "inter_name_raw": inter_name,
                "inter_alias": state.inter_alias or None,
                "issue_seq": state.current_issue_seq,
                "issue_category": issue_category_for_type(issue_type),
                "issue_type": issue_type,
                "issue_desc": desc_text or None,
                "recommendation_text": rec_text or None,
                "source_page_start": page_no,
                "source_page_end": page_no,
                "source_file": source_file,
            }
        )
        state.current_issue_key = issue_key
        pending_desc = []
        pending_rec = []

    def flush_rec_item(*, page_no: int) -> None:
        nonlocal pending_rec
        if not state.in_recommendation_block or not state.current_horizon:
            return
        text = "".join(pending_rec).strip()
        if not text:
            return
        inter_name = state.case_inter_name or state.inter_name_raw
        if not inter_name:
            pending_rec = []
            return
        recommendations.append(
            {
                "rec_key": make_rec_key(report_batch, inter_name, state.current_horizon, state.rec_seq),
                "report_batch": report_batch,
                "inter_name_raw": inter_name,
                "horizon": state.current_horizon,
                "rec_seq": state.rec_seq,
                "rec_text": text,
                "issue_key": state.current_issue_key or None,
                "source_file": source_file,
            }
        )
        pending_rec = []

    for page_no, lines in pages:
        if page_no >= 14 or (page_no >= 3 and page_no <= 10):
            if page_no >= 14:
                detail_started = True
            i = 0
            while i < len(lines):
                line = lines[i]

                if line == "改造建议：":
                    flush_issue(page_no=page_no)
                    state.in_recommendation_block = True
                    state.current_horizon = ""
                    state.rec_seq = 0
                    i += 1
                    continue

                hm = _HORIZON_RE.match(line)
                if hm:
                    flush_rec_item(page_no=page_no)
                    state.current_horizon = hm.group(1)
                    state.rec_seq = 0
                    i += 1
                    continue

                if state.in_recommendation_block and state.current_horizon:
                    rm = _REC_ITEM_RE.match(line)
                    if rm:
                        flush_rec_item(page_no=page_no)
                        state.rec_seq = int(rm.group(1))
                        pending_rec = [rm.group(2).strip()]
                        i += 1
                        while i < len(lines):
                            nxt = lines[i]
                            if (
                                _REC_ITEM_RE.match(nxt)
                                or _HORIZON_RE.match(nxt)
                                or _ISSUE_HDR_RE.match(nxt)
                                or _CASE_INTER_RE.match(nxt)
                                or _INTER_HDR_RE.match(nxt)
                                or _SECTION_HDR_RE.match(nxt)
                                or nxt == "改造建议："
                            ):
                                break
                            pending_rec.append(nxt)
                            i += 1
                        flush_rec_item(page_no=page_no)
                        continue

                cm = _CASE_INTER_RE.match(line)
                if cm and page_no <= 10:
                    flush_issue(page_no=page_no)
                    state.in_case_study = True
                    state.in_recommendation_block = False
                    state.case_inter_name = _normalize_inter_name(cm.group(2))
                    state.inter_name_raw = state.case_inter_name
                    state.section_no = "0"
                    state.inter_seq = cm.group(1)
                    i += 1
                    continue

                sm = _SECTION_HDR_RE.match(line)
                if sm and detail_started:
                    flush_issue(page_no=page_no)
                    state.in_case_study = False
                    state.in_recommendation_block = False
                    state.section_no = sm.group(1)
                    state.section_name = sm.group(2)
                    state.inter_seq = ""
                    state.inter_name_raw = ""
                    state.inter_alias = ""
                    i += 1
                    continue

                im = _INTER_HDR_RE.match(line)
                if im and (detail_started or page_no <= 10):
                    flush_issue(page_no=page_no)
                    state.in_recommendation_block = False
                    state.inter_seq = im.group(1)
                    name_body = im.group(2).strip()
                    alias = (im.group(3) or "").strip()
                    if alias and alias in name_body:
                        alias = ""
                    if not name_body.endswith("路口"):
                        name_body = f"{name_body}路口"
                    state.inter_name_raw = name_body
                    state.inter_alias = alias
                    state.case_inter_name = ""
                    i += 1
                    continue

                ism = _ISSUE_HDR_RE.match(line)
                if ism:
                    flush_issue(page_no=page_no)
                    state.current_issue_seq = int(ism.group(1))
                    state.current_issue_type = ism.group(2).strip()
                    pending_desc = []
                    pending_rec = []
                    i += 1
                    continue

                if _CAPTION_RE.match(line):
                    i += 1
                    continue

                rm = _REC_INLINE_RE.match(line)
                if rm and state.current_issue_seq > 0:
                    pending_rec.append(rm.group(1).strip())
                    i += 1
                    continue

                if state.current_issue_seq > 0 and not state.in_recommendation_block:
                    if line.startswith("改造建议"):
                        i += 1
                        continue
                    if re.match(r"^[东西南北]口", line) and "交通流量" in line:
                        i += 1
                        continue
                    pending_desc.append(line)
                i += 1

            flush_issue(page_no=page_no)
            flush_rec_item(page_no=page_no)

    # 更新 source_page_end
    issue_by_key = {row["issue_key"]: row for row in issues}
    for row in issues:
        key = row["issue_key"]
        same = [
            r
            for r in issues
            if r["inter_name_raw"] == row["inter_name_raw"] and r["issue_seq"] == row["issue_seq"]
        ]
        if same:
            row["source_page_end"] = max(r["source_page_start"] for r in same)

    return issues, recommendations, warnings


def _extract_images(
    pdf_path: Path,
    *,
    report_batch: str,
    output_dir: Path,
    issues: list[dict[str, Any]],
    source_file: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    page_to_inter: dict[int, str] = {}
    page_to_issue: dict[int, str] = {}
    for issue in issues:
        start = int(issue.get("source_page_start") or 0)
        end = int(issue.get("source_page_end") or start)
        for p in range(start, end + 1):
            page_to_inter[p] = issue["inter_name_raw"]
            page_to_issue[p] = issue["issue_key"]

    image_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    doc = fitz.open(str(pdf_path))
    try:
        for page_idx in range(len(doc)):
            page_no = page_idx + 1
            page = doc[page_idx]
            inter_name = page_to_inter.get(page_no, "")
            default_issue_key = page_to_issue.get(page_no)
            image_list = page.get_images(full=True)
            if not image_list:
                continue

            slug = inter_name_slug(inter_name) if inter_name else "unassigned"
            inter_dir = images_dir / slug
            inter_dir.mkdir(parents=True, exist_ok=True)

            for seq, img_info in enumerate(image_list, start=1):
                xref = img_info[0]
                try:
                    extracted = doc.extract_image(xref)
                except Exception as exc:
                    warnings.append(f"图片提取失败 p{page_no} xref={xref}: {exc}")
                    continue

                ext = extracted.get("ext") or "png"
                filename = f"p{page_no:03d}_{seq:03d}.{ext}"
                rel_path = f"data/field_survey/{report_batch}/images/{slug}/{filename}"
                abs_path = output_dir / "images" / slug / filename
                abs_path.write_bytes(extracted["image"])

                width = extracted.get("width")
                height = extracted.get("height")
                file_size = len(extracted["image"])
                issue_key = default_issue_key
                match_status = "linked" if issue_key else "orphan"

                image_rows.append(
                    {
                        "image_key": make_image_key(report_batch, rel_path),
                        "report_batch": report_batch,
                        "issue_key": issue_key,
                        "inter_name_raw": inter_name or None,
                        "page_no": page_no,
                        "image_seq": seq,
                        "caption_text": None,
                        "local_path": rel_path,
                        "local_url": f"/static/field_survey/{report_batch}/images/{slug}/{filename}",
                        "minio_bucket": None,
                        "minio_object_key": None,
                        "image_url": None,
                        "width": width,
                        "height": height,
                        "file_size": file_size,
                        "match_status": match_status,
                        "source_file": source_file,
                    }
                )
    finally:
        doc.close()

    return image_rows, warnings


def parse_pdf_report(
    pdf_path: Path,
    *,
    report_batch: str = "jinan_20260609",
    output_dir: Path | None = None,
) -> dict[str, Any]:
    pdf_path = pdf_path.resolve()
    source_file = str(pdf_path)
    if output_dir is None:
        output_dir = Path("data") / "field_survey" / report_batch
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    pages = _extract_pages_text(pdf_path)
    issues, recommendations, text_warnings = _parse_text_content(
        pages, report_batch=report_batch, source_file=source_file
    )
    matrix_rows = _parse_matrix_rows(pages, report_batch=report_batch, source_file=source_file)
    images, image_warnings = _extract_images(
        pdf_path,
        report_batch=report_batch,
        output_dir=output_dir,
        issues=issues,
        source_file=source_file,
    )

    warnings = text_warnings + image_warnings
    inter_names_detail = {i["inter_name_raw"] for i in issues if i.get("inter_seq")}
    inter_names_matrix = {m["inter_name_raw"] for m in matrix_rows}
    orphan_images = sum(1 for img in images if img.get("match_status") == "orphan")

    manifest = {
        "report_batch": report_batch,
        "source_file": source_file,
        "issue_count": len(issues),
        "recommendation_count": len(recommendations),
        "matrix_count": len(matrix_rows),
        "image_count": len(images),
        "orphan_image_count": orphan_images,
        "detail_intersection_count": len(inter_names_detail),
        "matrix_intersection_count": len(inter_names_matrix),
        "warning_count": len(warnings),
        "warnings": warnings[:50],
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    debug_path = output_dir / "parse_debug.json"
    debug_path.write_text(
        json.dumps(
            {
                "issues": issues,
                "recommendations": recommendations,
                "matrix": matrix_rows,
                "images": [{k: v for k, v in img.items() if k != "file_size"} for img in images],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "issues": issues,
        "recommendations": recommendations,
        "matrix": matrix_rows,
        "images": images,
        "manifest": manifest,
        "warnings": warnings,
        "output_dir": str(output_dir),
    }
