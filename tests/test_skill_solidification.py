import copy
import json
from pathlib import Path

import pytest

from app.services.skill_solidification_service import (
    BUILD_STAGE_DEFS,
    SkillSolidificationService,
    compute_skill_id,
    derive_context,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "frontend"
    / "src"
    / "mock"
    / "run_1_fixture.json"
)


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def real_inputs() -> dict:
    fixture = _load_fixture()
    return {
        "diagnosis_ticket": fixture["diagnosis_ticket"],
        "strategy": fixture["phases"]["strategy"],
        "plan_snapshot": fixture["plan"],
    }


@pytest.fixture
def service(tmp_path) -> SkillSolidificationService:
    return SkillSolidificationService(tmp_path / "skills")


def _solidify(service: SkillSolidificationService, inputs: dict) -> dict:
    return service.solidify(
        trace_id="trace-1",
        plan_id="plan-1",
        diagnosis_ticket=inputs.get("diagnosis_ticket"),
        strategy=inputs.get("strategy"),
        plan_snapshot=inputs.get("plan_snapshot"),
    )


def test_solidify_writes_real_skill_package(service, real_inputs, tmp_path):
    result = _solidify(service, real_inputs)

    assert result["action"] == "created"
    assert result["skill_id"] == "skill-011wwe289qc00001-evening_rush_hour"
    assert result["download_url"] == (
        "/api/v1/agent/skills/skill-011wwe289qc00001-evening_rush_hour/download"
    )
    assert result["intersection"] == "经十路与转山西路路口"
    assert result["inter_id"] == "011wwe289qc00001"

    skill_dir = tmp_path / "skills" / result["skill_id"]
    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "经十路与转山西路路口" in skill_md
    assert "queue_spillback" in skill_md

    meta = json.loads((skill_dir / "skill.meta.json").read_text(encoding="utf-8"))
    assert meta["skill_id"] == result["skill_id"]
    assert meta["tags"]["match"]["inter_id"] == "011wwe289qc00001"
    assert meta["content_signature"].startswith("sha256:")

    assert (skill_dir / "scripts" / "fetch_traffic_data.sql").exists()
    assert (skill_dir / "reference.md").exists()


def test_result_structure_matches_contract(service, real_inputs):
    result = _solidify(service, real_inputs)

    absorption = result["absorption"]
    assert absorption["action"] == "CREATE"
    assert len(absorption["stages"]) == 6
    assert [s["key"] for s in absorption["stages"]] == [
        "recap",
        "decompose",
        "retrieve",
        "compare",
        "value",
        "blueprint",
    ]
    assert "value_snapshot" in absorption
    assert absorption["value_snapshot"]["what"]["bullets"]
    assert absorption["value_snapshot"]["why_rows"]

    build = result["build"]
    assert len(build["stages"]) == len(BUILD_STAGE_DEFS) == 7
    assert build["stages"][-1]["progress"] == 100
    progresses = [s["progress"] for s in build["stages"]]
    assert progresses == sorted(progresses)

    file_names = {f["name"] for f in build["files"]}
    assert file_names == {
        "SKILL.md",
        "reference.md",
        "fetch_traffic_data.sql",
        "skill.meta.json",
    }


def test_files_list_matches_on_disk(service, real_inputs, tmp_path):
    result = _solidify(service, real_inputs)
    skill_dir = tmp_path / "skills" / result["skill_id"]
    for entry in result["build"]["files"]:
        on_disk = (skill_dir / entry["path"]).read_text(encoding="utf-8")
        assert on_disk == entry["content"]


def test_upsert_unchanged_and_updated(service, real_inputs, tmp_path):
    first = _solidify(service, real_inputs)
    assert first["action"] == "created"

    second = _solidify(service, real_inputs)
    assert second["action"] == "unchanged"

    # 同键目录只有一个
    skills_root = tmp_path / "skills"
    dirs = [p for p in skills_root.iterdir() if p.is_dir()]
    assert len(dirs) == 1

    changed = copy.deepcopy(real_inputs)
    changed["plan_snapshot"]["recommended"]["expected_effect"] = "改写后的预期效果"
    third = _solidify(service, changed)
    assert third["action"] == "updated"
    dirs_after = [p for p in skills_root.iterdir() if p.is_dir()]
    assert len(dirs_after) == 1


def test_unchanged_keeps_created_at(service, real_inputs, tmp_path):
    first = _solidify(service, real_inputs)
    meta_path = tmp_path / "skills" / first["skill_id"] / "skill.meta.json"
    created_first = json.loads(meta_path.read_text(encoding="utf-8"))["created_at"]
    _solidify(service, real_inputs)
    created_second = json.loads(meta_path.read_text(encoding="utf-8"))["created_at"]
    assert created_first == created_second


def test_signature_is_deterministic(tmp_path, real_inputs):
    svc_a = SkillSolidificationService(tmp_path / "a")
    svc_b = SkillSolidificationService(tmp_path / "b")
    res_a = _solidify(svc_a, real_inputs)
    res_b = _solidify(svc_b, real_inputs)
    meta_a = json.loads((tmp_path / "a" / res_a["skill_id"] / "skill.meta.json").read_text("utf-8"))
    meta_b = json.loads((tmp_path / "b" / res_b["skill_id"] / "skill.meta.json").read_text("utf-8"))
    assert meta_a["content_signature"] == meta_b["content_signature"]


def test_degradation_missing_everything(service):
    result = service.solidify(
        trace_id="t",
        plan_id="p",
        diagnosis_ticket=None,
        strategy=None,
        plan_snapshot=None,
    )
    assert result["action"] == "created"
    assert result["skill_id"] == "skill-unknown-all"
    assert result["inter_id"] is None
    assert result["intersection"] is None
    assert len(result["absorption"]["stages"]) == 6
    assert len(result["build"]["files"]) == 4


def test_degradation_missing_strategy_and_plan(service, real_inputs):
    result = service.solidify(
        trace_id="t",
        plan_id="p",
        diagnosis_ticket=real_inputs["diagnosis_ticket"],
        strategy=None,
        plan_snapshot=None,
    )
    assert result["action"] == "created"
    assert result["inter_id"] == "011wwe289qc00001"


def test_derive_context_slug_fallback_to_inter_id():
    ctx = derive_context(diagnosis_ticket={"intersection_name": "经十路口", "inter_id": "abc123"})
    assert compute_skill_id(ctx) == "skill-abc123-all"
