from intersection_agent.stores.intersection_profile_store import IntersectionProfileStore


def test_append_and_load_roundtrip(tmp_path):
    store = IntersectionProfileStore(base_dir=tmp_path)
    store.add_cognition(
        "inter_1", text="下午四点常堵", status="verified", source="data", evidence={"sat": 0.95}
    )
    prof = store.load("inter_1")
    assert prof.cognition[0].status == "verified"


def test_data_doubt_status_kept(tmp_path):
    store = IntersectionProfileStore(base_dir=tmp_path)
    store.add_cognition(
        "inter_1", text="人说堵但数据不显著", status="data_doubt", source="user", evidence={}
    )
    assert store.load("inter_1").cognition[0].status == "data_doubt"


def test_diagnosis_and_solution_ref(tmp_path):
    store = IntersectionProfileStore(base_dir=tmp_path)
    store.add_diagnosis("i1", cause="旁边小学放学", dimension="event", source="user", confidence=0.8)
    store.add_solution_ref("i1", skill_id="sk1", qualitative="绿灯多给点", quantified="东进口 +8s")
    prof = store.load("i1")
    assert prof.diagnosis[0].dimension == "event"
    assert prof.solution_ref[0].quantified == "东进口 +8s"


def test_add_cognition_returns_outcome(tmp_path):
    store = IntersectionProfileStore(base_dir=tmp_path)
    _, o1 = store.add_cognition("i1", text="早高峰空放", status="data_doubt", source="user")
    assert o1 == "inserted"
    _, o2 = store.add_cognition("i1", text="早高峰空放", status="data_doubt", source="user")
    assert o2 == "exists"
    _, o3 = store.add_cognition(
        "i1", text="早高峰空放", status="verified", source="data", evidence={"sat": 0.9}
    )
    assert o3 == "updated"


def test_add_diagnosis_returns_outcome(tmp_path):
    store = IntersectionProfileStore(base_dir=tmp_path)
    _, o1 = store.add_diagnosis("i1", cause="放学", dimension="event", source="user", confidence=0.0)
    assert o1 == "inserted"
    _, o2 = store.add_diagnosis("i1", cause="放学", dimension="event", source="user", confidence=0.0)
    assert o2 == "exists"
    _, o3 = store.add_diagnosis("i1", cause="放学", dimension="event", source="data", confidence=0.7)
    assert o3 == "updated"


def test_add_solution_ref_returns_outcome(tmp_path):
    store = IntersectionProfileStore(base_dir=tmp_path)
    _, o1 = store.add_solution_ref("i1", skill_id="sk1", quantified="东进口 +8s")
    assert o1 == "inserted"
    _, o2 = store.add_solution_ref("i1", skill_id="sk1", quantified="东进口 +8s")
    assert o2 in ("exists", "updated")


def test_missing_profile_returns_empty(tmp_path):
    store = IntersectionProfileStore(base_dir=tmp_path)
    prof = store.load("never_seen")
    assert prof.cognition == [] and prof.diagnosis == [] and prof.solution_ref == []
