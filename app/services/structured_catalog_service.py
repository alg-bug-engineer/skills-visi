"""Offline structured catalog precipitation (需求30 方案 A).

Reads source libraries (read-only) and writes companion dumps under
``data/structured/``. Frontend and runtime search load these dumps.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.case_tag_extractor import CaseTagExtractor

logger = logging.getLogger(__name__)

INDUSTRY_FILE = "industry_cases.jsonl"
INTERSECTION_FILE = "intersection_cases.jsonl"
EXPERIENCES_FILE = "experiences.jsonl"
MANIFEST_FILE = "manifest.json"


def _file_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "mtime_ns": 0, "size": 0, "sha16": ""}
    data = path.read_bytes()
    return {
        "path": str(path),
        "exists": True,
        "mtime_ns": path.stat().st_mtime_ns,
        "size": len(data),
        "sha16": hashlib.sha256(data).hexdigest()[:16],
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("structured source 第 %d 行解析失败 path=%s: %s", line_no, path, exc)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _experience_seed_tags(record: dict[str, Any], extractor: CaseTagExtractor) -> dict[str, list[str]]:
    """Map experience tags + content keywords into case-tag schema keys."""
    tags = record.get("tags") or {}
    text_parts = [
        record.get("content") or "",
        str(tags.get("problem_type") or ""),
        str(tags.get("strategy_action") or ""),
        str(tags.get("time_period") or ""),
        str(tags.get("cause_keywords") or ""),
        " ".join(str(x) for x in (tags.get("related_poi") or [])),
    ]
    seeded = extractor.extract_from_text(" ".join(text_parts))

    problem = str(tags.get("problem_type") or "")
    if any(k in problem for k in ("溢出", "溢流", "排队")):
        seeded = extractor.merge_tags(seeded, {"problem_type": ["queue_overflow"]})

    period = str(tags.get("time_period") or "")
    period_map = {
        "早高峰": "morning_peak",
        "晚高峰": "evening_peak",
        "平峰": "off_peak",
        "下午": "off_peak",
    }
    for key, value in period_map.items():
        if key in period:
            seeded = extractor.merge_tags(seeded, {"time_period": [value]})

    strategy = str(tags.get("strategy_action") or "")
    strategy_map = {
        "加绿": "phase_resequence",
        "减绿": "phase_resequence",
        "控流": "upstream_control",
        "协调": "green_wave",
        "防止溢出": "spillback_protection",
        "防溢流": "spillback_protection",
    }
    for key, value in strategy_map.items():
        if key in strategy:
            seeded = extractor.merge_tags(seeded, {"strategy_actions": [value]})

    cause = str(tags.get("cause_dimension") or "")
    if cause == "coordination":
        seeded = extractor.merge_tags(seeded, {"scope_type": ["arterial_coordination"]})
    if cause == "event":
        seeded = extractor.merge_tags(seeded, {"weather_event": ["school_event"]})

    return seeded


def _feedback_as_case_text(record: dict[str, Any]) -> str:
    ticket = record.get("diagnosis_ticket") or {}
    tags = record.get("tags") or {}
    plan = record.get("plan_snapshot") or {}
    parts = [
        ticket.get("problem_type") or "",
        ticket.get("intersection_name") or "",
        ticket.get("period") or ticket.get("time_range") or "",
        ticket.get("direction") or "",
        ticket.get("movement") or "",
        tags.get("strategy_applied") or "",
        tags.get("primary_cause") or "",
        record.get("rejection_reason") or "",
        json.dumps(plan, ensure_ascii=False) if plan else "",
    ]
    return " ".join(str(p) for p in parts if p)


class StructuredCatalogService:
    def __init__(
        self,
        *,
        output_dir: Path,
        industry_source: Path,
        feedback_source: Path,
        experience_source: Path,
        tag_extractor: CaseTagExtractor | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.industry_source = industry_source
        self.feedback_source = feedback_source
        self.experience_source = experience_source
        self.tag_extractor = tag_extractor or CaseTagExtractor()

    @property
    def industry_path(self) -> Path:
        return self.output_dir / INDUSTRY_FILE

    @property
    def intersection_path(self) -> Path:
        return self.output_dir / INTERSECTION_FILE

    @property
    def experiences_path(self) -> Path:
        return self.output_dir / EXPERIENCES_FILE

    @property
    def manifest_path(self) -> Path:
        return self.output_dir / MANIFEST_FILE

    def source_fingerprints(self) -> dict[str, Any]:
        return {
            "industry": _file_fingerprint(self.industry_source),
            "feedback": _file_fingerprint(self.feedback_source),
            "experience": _file_fingerprint(self.experience_source),
        }

    def _manifest_matches(self) -> bool:
        if not self.manifest_path.exists():
            return False
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        expected = self.source_fingerprints()
        sources = manifest.get("sources") or {}
        for key in ("industry", "feedback", "experience"):
            left = sources.get(key) or {}
            right = expected.get(key) or {}
            if left.get("sha16") != right.get("sha16") or left.get("size") != right.get("size"):
                return False
        for path in (self.industry_path, self.intersection_path, self.experiences_path):
            if not path.exists():
                return False
        return True

    def build_industry_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, case in enumerate(_read_jsonl(self.industry_source)):
            tag_keys = self.tag_extractor.extract_tags(case)
            meta = case.get("_meta") or {}
            rows.append(
                {
                    "case_id": f"industry_{index}",
                    "category": "textbook",
                    "title": (case.get("案例场景") or "")[:120],
                    "scene": case.get("案例场景") or "",
                    "diagnosis": case.get("交通问题诊断") or "",
                    "solution": case.get("治理方案") or "",
                    "effect": case.get("预期效果") or "",
                    "structured_tags": self.tag_extractor.tags_to_labels(tag_keys),
                    "tag_keys": tag_keys,
                    "source_meta": {
                        "title": meta.get("title"),
                        "account": meta.get("account"),
                        "link": meta.get("link"),
                    },
                    "案例场景": case.get("案例场景"),
                    "交通问题诊断": case.get("交通问题诊断"),
                    "治理方案": case.get("治理方案"),
                    "预期效果": case.get("预期效果"),
                }
            )
        return rows

    def build_intersection_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for record in _read_jsonl(self.feedback_source):
            decision = record.get("decision")
            if decision not in ("accept", "reject"):
                continue
            ticket = record.get("diagnosis_ticket") or {}
            tags = record.get("tags") or {}
            text = _feedback_as_case_text(record)
            tag_keys = self.tag_extractor.extract_from_text(text)
            if ticket.get("problem_type"):
                tag_keys = self.tag_extractor.merge_tags(
                    tag_keys,
                    self.tag_extractor.extract_from_text(str(ticket.get("problem_type"))),
                )
            category = "recommended" if decision == "accept" else "risk"
            rows.append(
                {
                    "case_id": f"{category}_{record.get('trace_id')}_{record.get('plan_id')}",
                    "category": category,
                    "title": tags.get("strategy_applied") or record.get("plan_id"),
                    "trace_id": record.get("trace_id"),
                    "plan_id": record.get("plan_id"),
                    "inter_id": record.get("inter_id") or ticket.get("inter_id"),
                    "intersection_name": ticket.get("intersection_name"),
                    "time_period": ticket.get("period") or ticket.get("time_range"),
                    "recorded_at": record.get("recorded_at"),
                    "lesson": (
                        tags.get("primary_cause")
                        if decision == "accept"
                        else (record.get("rejection_reason") or "历史否决方案")
                    ),
                    "tags": tags,
                    "structured_tags": self.tag_extractor.tags_to_labels(tag_keys),
                    "tag_keys": tag_keys,
                }
            )
        return rows

    def build_experience_rows(self) -> list[dict[str, Any]]:
        from app.services.experience_service import experience_signature

        records = _read_jsonl(self.experience_source)
        records.sort(key=lambda r: str(r.get("recorded_at") or ""), reverse=True)
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for record in records:
            signature = experience_signature(record)
            if signature in seen:
                continue
            seen.add(signature)
            tags = record.get("tags") or {}
            snapshot = record.get("diagnosis_ticket_snapshot") or {}
            tag_keys = _experience_seed_tags(record, self.tag_extractor)
            rows.append(
                {
                    "record_id": record.get("record_id"),
                    "recorded_at": record.get("recorded_at"),
                    "trace_id": record.get("trace_id"),
                    "experience_type": record.get("experience_type"),
                    "content": record.get("content"),
                    "source_span": record.get("source_span"),
                    "tags": tags,
                    "inter_id": tags.get("inter_id") or snapshot.get("inter_id"),
                    "intersection_name": tags.get("intersection_name")
                    or snapshot.get("intersection_name"),
                    "structured_tags": self.tag_extractor.tags_to_labels(tag_keys),
                    "tag_keys": tag_keys,
                }
            )
        return rows

    def rebuild(self, *, force: bool = False) -> dict[str, Any]:
        if not force and self._manifest_matches():
            logger.info(
                "structured catalog 源未变化，跳过重建 dir=%s",
                self.output_dir,
            )
            return self.load_manifest() or {"skipped": True}

        industry = self.build_industry_rows()
        intersection = self.build_intersection_rows()
        experiences = self.build_experience_rows()

        self.output_dir.mkdir(parents=True, exist_ok=True)
        _write_jsonl(self.industry_path, industry)
        _write_jsonl(self.intersection_path, intersection)
        _write_jsonl(self.experiences_path, experiences)

        manifest = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": self.source_fingerprints(),
            "counts": {
                "industry_cases": len(industry),
                "intersection_cases": len(intersection),
                "experiences": len(experiences),
            },
            "files": {
                "industry_cases": INDUSTRY_FILE,
                "intersection_cases": INTERSECTION_FILE,
                "experiences": EXPERIENCES_FILE,
            },
        }
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info(
            "structured catalog 重建完成 industry=%d intersection=%d experiences=%d dir=%s",
            len(industry),
            len(intersection),
            len(experiences),
            self.output_dir,
        )
        return manifest

    def load_manifest(self) -> dict[str, Any] | None:
        if not self.manifest_path.exists():
            return None
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def load_industry_cases(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.industry_path)

    def load_intersection_cases(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.intersection_path)

    def load_experiences(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.experiences_path)

    def load_experiences_grouped(self) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {
            "cognitive": [],
            "diagnostic": [],
            "solution": [],
        }
        for item in self.load_experiences():
            bucket = grouped.get(str(item.get("experience_type")))
            if bucket is not None:
                bucket.append(item)
        return grouped

    def load_catalog(self) -> dict[str, Any]:
        if not self._manifest_matches() and not self.manifest_path.exists():
            self.rebuild(force=True)
        experiences = self.load_experiences_grouped()
        industry = self.load_industry_cases()
        intersection = self.load_intersection_cases()
        return {
            "industry_cases": industry,
            "intersection_cases": intersection,
            "experiences": experiences,
            "meta": self.load_manifest()
            or {
                "counts": {
                    "industry_cases": len(industry),
                    "intersection_cases": len(intersection),
                    "experiences": sum(len(v) for v in experiences.values()),
                }
            },
        }
