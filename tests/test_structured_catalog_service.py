import json
from pathlib import Path

from app.services.structured_catalog_service import StructuredCatalogService
from app.services.case_tag_extractor import CaseTagExtractor


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_rebuild_writes_three_dumps_and_manifest(tmp_path: Path):
    industry = tmp_path / "knowledge_qa.jsonl"
    feedback = tmp_path / "plan_feedback.jsonl"
    experience = tmp_path / "user_experience.jsonl"
    out = tmp_path / "structured"

    _write_jsonl(
        industry,
        [
            {
                "案例场景": "晚高峰干线绿波协调，两路口相距150m排队溢出",
                "交通问题诊断": "短间距下游承接不足",
                "治理方案": "统一公共周期与绿波相位差",
                "预期效果": "拥堵指数下降",
            }
        ],
    )
    _write_jsonl(
        feedback,
        [
            {
                "decision": "accept",
                "trace_id": "t1",
                "plan_id": "plan_a",
                "inter_id": "int_1",
                "recorded_at": "2026-07-11T10:00:00Z",
                "diagnosis_ticket": {
                    "inter_id": "int_1",
                    "intersection_name": "测试路口",
                    "problem_type": "排队溢出",
                    "period": "晚高峰",
                },
                "tags": {"strategy_applied": "干线联控", "primary_cause": "下游受阻"},
            }
        ],
    )
    _write_jsonl(
        experience,
        [
            {
                "record_id": "ue1",
                "experience_type": "cognitive",
                "content": "晚高峰排队溢出",
                "recorded_at": "2026-07-11T09:00:00Z",
                "tags": {
                    "problem_type": "排队溢出",
                    "time_period": "晚高峰",
                    "intersection_name": "测试路口",
                    "inter_id": "int_1",
                },
            }
        ],
    )

    service = StructuredCatalogService(
        output_dir=out,
        industry_source=industry,
        feedback_source=feedback,
        experience_source=experience,
        tag_extractor=CaseTagExtractor(),
    )
    manifest = service.rebuild(force=True)
    assert manifest["counts"]["industry_cases"] == 1
    assert manifest["counts"]["intersection_cases"] == 1
    assert manifest["counts"]["experiences"] == 1
    assert (out / "industry_cases.jsonl").exists()
    assert (out / "intersection_cases.jsonl").exists()
    assert (out / "experiences.jsonl").exists()

    industry_row = service.load_industry_cases()[0]
    assert industry_row["structured_tags"]
    assert "tag_keys" in industry_row

    catalog = service.load_catalog()
    assert len(catalog["industry_cases"]) == 1
    assert catalog["experiences"]["cognitive"]
    assert catalog["intersection_cases"][0]["category"] == "recommended"


def test_rebuild_skips_when_sources_unchanged(tmp_path: Path):
    industry = tmp_path / "knowledge_qa.jsonl"
    feedback = tmp_path / "plan_feedback.jsonl"
    experience = tmp_path / "user_experience.jsonl"
    out = tmp_path / "structured"
    _write_jsonl(industry, [{"案例场景": "溢出", "交通问题诊断": "排队溢出", "治理方案": "协调", "预期效果": "改善"}])
    _write_jsonl(feedback, [])
    _write_jsonl(experience, [])

    service = StructuredCatalogService(
        output_dir=out,
        industry_source=industry,
        feedback_source=feedback,
        experience_source=experience,
    )
    first = service.rebuild(force=True)
    second = service.rebuild(force=False)
    assert first.get("generated_at")
    assert second.get("skipped") is True or second.get("generated_at") == first.get("generated_at")
