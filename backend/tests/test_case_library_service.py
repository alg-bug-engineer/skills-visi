import inspect
from pathlib import Path

from intersection_agent.services.case_library_service import CaseLibraryService

_QA_PATH = Path(__file__).resolve().parents[2] / "docs" / "knowledge_qa.jsonl"


def test_match_by_problem_type_and_shape():
    svc = CaseLibraryService(path=_QA_PATH)
    hits = svc.match(problem_types=["spillback"], shape_tags=["短间距"], k=3)
    assert hits and "溢出" in (hits[0]["交通问题诊断"] + hits[0]["案例场景"])
    assert len(hits) <= 3


def test_default_path_resolves():
    svc = CaseLibraryService()
    hits = svc.match(problem_types=["congestion"], shape_tags=[], k=2)
    assert len(hits) <= 2


def test_no_vector_dependency():
    import intersection_agent.services.case_library_service as m

    src = inspect.getsource(m)
    assert "faiss" not in src and "embedding" not in src.lower()
