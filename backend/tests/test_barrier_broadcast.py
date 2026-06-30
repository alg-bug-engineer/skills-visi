"""严格栅栏播报：每步产出落库后才 emit 对应结论（直接校验写库与播报时序）。"""

import pytest

from intersection_agent.hooks.execution_emitter import ExecutionEmitter
from intersection_agent.models.domain import DiagnosisResult, NluResult, Session
from intersection_agent.models.skill import SkillRecord
from intersection_agent.models.skill import SkillUpsertResult
from intersection_agent.services.orchestrator import Orchestrator
from intersection_agent.stores.intersection_profile_store import IntersectionProfileStore


class _RecordingStore(IntersectionProfileStore):
    def __init__(self, base_dir, order):
        super().__init__(base_dir=base_dir)
        self._order = order

    def add_cognition(self, *args, **kwargs):
        self._order.append(("store", "cognition"))
        return super().add_cognition(*args, **kwargs)

    def add_diagnosis(self, *args, **kwargs):
        self._order.append(("store", "diagnosis"))
        return super().add_diagnosis(*args, **kwargs)

    def add_solution_ref(self, *args, **kwargs):
        self._order.append(("store", "solution_ref"))
        return super().add_solution_ref(*args, **kwargs)


def _emitter(order):
    async def _cb(payload):
        if payload.get("event") == "step":
            order.append(("emit", payload["step"], payload["status"]))

    return ExecutionEmitter(callback=_cb)


@pytest.mark.asyncio
async def test_cognition_and_diagnosis_emit_after_store(tmp_path):
    order: list = []
    orch = Orchestrator(profile_store=_RecordingStore(tmp_path, order))
    session = Session(inter_id="i1", nlu=NluResult(user_suggestion="绿灯多给点"))
    diagnosis = DiagnosisResult(
        diagnosed=True,
        matched_rules=[{"id": "r1", "conclusion": "过饱和"}],
        metrics_snapshot={"sat": 0.95},
    )
    governance = {
        "primary_diagnosis": {
            "type": "timing_optimizable",
            "headline": "南口过饱和而东口富余",
            "confidence": 0.8,
        }
    }
    await orch._record_problem_experience(session, diagnosis, governance, _emitter(order))

    assert order.index(("store", "cognition")) < order.index(
        ("emit", "experience_cognition", "completed")
    )
    assert order.index(("store", "diagnosis")) < order.index(
        ("emit", "experience_diagnosis", "completed")
    )


@pytest.mark.asyncio
async def test_solution_ref_emit_after_store(tmp_path):
    order: list = []
    orch = Orchestrator(profile_store=_RecordingStore(tmp_path, order))
    session = Session(inter_id="i1", nlu=NluResult(user_suggestion="绿灯多给点"))
    record = SkillRecord(
        skill_id="sk1",
        skill_dir="/tmp/sk1",
        intersection="测试路口",
        inter_id="i1",
        problem_type="congestion",
        time_period_label="晚高峰",
        match_keywords=[],
        data_query_spec={},
        rule_ids=["r1"],
        suggestion_formula="东进口绿灯 +8s",
        created_at="2026-06-29",
    )
    result = SkillUpsertResult(record=record, action="created")
    await orch._record_solution_ref(session, result, _emitter(order))

    assert order.index(("store", "solution_ref")) < order.index(
        ("emit", "experience_solution", "completed")
    )
