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


# --- API layer (TestClient) ---


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from app.api.routes import get_skill_solidification_service
    from app.main import app

    service = SkillSolidificationService(tmp_path / "skills")
    app.dependency_overrides[get_skill_solidification_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_skill_solidification_service, None)


def _post_solidify(client, real_inputs):
    return client.post(
        "/api/v1/agent/skill/solidify",
        json={
            "trace_id": "trace-1",
            "plan_id": "plan-1",
            "diagnosis_ticket": real_inputs["diagnosis_ticket"],
            "strategy": real_inputs["strategy"],
            "plan_snapshot": real_inputs["plan_snapshot"],
        },
    )


def test_api_solidify_returns_structure(client, real_inputs):
    response = _post_solidify(client, real_inputs)
    assert response.status_code == 200
    data = response.json()
    for key in ("action", "skill_id", "skill_dir", "download_url", "tags", "absorption", "build"):
        assert key in data
    assert data["action"] == "created"


def test_api_list_includes_new_skill(client, real_inputs):
    _post_solidify(client, real_inputs)
    response = client.get("/api/v1/agent/skills/solidified")
    assert response.status_code == 200
    skills = response.json()["skills"]
    assert any(s["skill_id"] == "skill-011wwe289qc00001-evening_rush_hour" for s in skills)


def test_api_download_returns_zip(client, real_inputs):
    result = _post_solidify(client, real_inputs).json()
    response = client.get(f"/api/v1/agent/skills/{result['skill_id']}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.content[:2] == b"PK"


def test_api_download_rejects_traversal(client):
    response = client.get("/api/v1/agent/skills/..%2Fetc/download")
    assert response.status_code in (404, 422)


def test_api_download_missing_skill_404(client):
    response = client.get("/api/v1/agent/skills/skill-nope-all/download")
    assert response.status_code == 404


def test_existing_pipeline_skills_endpoint_not_regressed(client):
    response = client.get("/api/v1/agent/skills")
    assert response.status_code == 200
    assert len(response.json()["skills"]) == 5
