"""direction_groups 轴对关注方向归一化。"""

from intersection_agent.utils.direction_groups import (
    normalize_axis_focus_groups,
    primary_groups_from_nlu,
    protected_groups_for_vertical_constraint,
)


def test_normalize_axis_focus_groups_single_pair():
    assert normalize_axis_focus_groups(["东西向", "南北向"]) == ["东西向"]
    assert normalize_axis_focus_groups(["南北向", "东西向"]) == ["南北向"]


def test_primary_groups_from_nlu_collapses_to_one_axis():
    assert primary_groups_from_nlu(["东西向", "南北向"]) == ["东西向"]
    assert primary_groups_from_nlu(["北进口", "南进口"]) == ["南北向"]


def test_protected_groups_excludes_focus():
    protect = protected_groups_for_vertical_constraint(["南北向", "东西向"])
    assert protect == ["东西向"]
