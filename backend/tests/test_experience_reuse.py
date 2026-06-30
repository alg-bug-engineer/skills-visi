import pytest

from intersection_agent.models.domain import Session
from intersection_agent.services.experience_reuse_service import ExperienceReuseService
from intersection_agent.services.orchestrator import Orchestrator
from intersection_agent.stores.intersection_profile_store import IntersectionProfileStore


def _seed(tmp_path) -> IntersectionProfileStore:
    store = IntersectionProfileStore(base_dir=tmp_path)
    store.add_cognition("i1", text="下午四点常堵", status="verified", source="data", evidence={})
    store.add_diagnosis(
        "i1", cause="旁边小学放学", dimension="event", source="user", confidence=0.8
    )
    store.add_solution_ref("i1", skill_id="sk1", qualitative="绿灯多给点", quantified="东进口 +8s")
    return store


def test_reuse_injects_by_step(tmp_path):
    svc = ExperienceReuseService(_seed(tmp_path))
    ctx = svc.for_step("i1", step="attribution")
    assert ctx.diagnosis_priors  # 注入了诊断经验
    assert ctx.reuse_badges  # 含「复用了 i1 的某条诊断经验」高亮标记


def test_identify_step_returns_cognition_only(tmp_path):
    svc = ExperienceReuseService(_seed(tmp_path))
    ctx = svc.for_step("i1", step="identify")
    assert ctx.cognition_priors
    assert not ctx.diagnosis_priors


def test_solution_step_returns_solution_refs(tmp_path):
    svc = ExperienceReuseService(_seed(tmp_path))
    ctx = svc.for_step("i1", step="solution")
    assert ctx.solution_refs
    assert ctx.reuse_badges


def test_empty_when_no_profile(tmp_path):
    svc = ExperienceReuseService(IntersectionProfileStore(base_dir=tmp_path))
    ctx = svc.for_step("never", step="attribution")
    assert not ctx.reuse_badges
    assert not ctx.diagnosis_priors


@pytest.mark.asyncio
async def test_second_run_surfaces_reused_experience(tmp_path):
    store = IntersectionProfileStore(base_dir=tmp_path)
    orch = Orchestrator(profile_store=store)

    s1 = Session()
    await orch.handle_message(
        s1, "奥体西路与经十路交叉口，下午四点南北向经常拥堵，绿灯应更长"
    )

    s2 = Session()
    resp = await orch.handle_message(
        s2, "奥体西路与经十路交叉口，下午四点南北向经常拥堵"
    )
    assert resp["meta"].get("reused_experience")  # 第二次复用第一次沉淀的经验
