"""Direction group helpers shared by cognition, evidence, and constraints."""

from __future__ import annotations

DIR4_TO_GROUP: dict[str, str] = {
    "东": "东西向",
    "西": "东西向",
    "南": "南北向",
    "北": "南北向",
    "东南": "东南向",
    "西南": "西南向",
    "东北": "东北向",
    "西北": "西北向",
}

GROUP_ORDER = ("东西向", "南北向", "东南向", "西南向", "东北向", "西北向")

PERPENDICULAR_GROUP: dict[str, str] = {
    "东西向": "南北向",
    "南北向": "东西向",
    "东南向": "西北向",
    "西北向": "东南向",
    "东北向": "西南向",
    "西南向": "东北向",
}

DOW_LABELS: dict[int, str] = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "周日",
}


def normalize_dir_label(label: str) -> str:
    """北进口 → 北"""
    text = str(label or "").replace("进口", "").replace("出口", "").strip()
    for key in ("东北", "东南", "西北", "西南", "东", "西", "南", "北"):
        if key in text:
            return key
    return text or str(label or "")


def direction_to_group(label: str) -> str:
    """Map dir4 label or group name to canonical direction group."""
    text = str(label or "").strip()
    if text in GROUP_ORDER:
        return text
    key = normalize_dir_label(text)
    return DIR4_TO_GROUP.get(key, text or "其他")


def perpendicular_group(group: str) -> str | None:
    """Return perpendicular direction group for axis pairs."""
    canonical = direction_to_group(group)
    return PERPENDICULAR_GROUP.get(canonical)


def primary_groups_from_nlu(directions: list[str]) -> list[str]:
    """Normalize NLU direction hints to direction groups."""
    groups: list[str] = []
    for item in directions:
        group = direction_to_group(item)
        if group and group not in groups:
            groups.append(group)
    return groups


def protected_groups_for_vertical_constraint(primary_groups: list[str]) -> list[str]:
    """垂直方向 → 与主方向正交的方向组。"""
    protected: list[str] = []
    for group in primary_groups:
        perp = perpendicular_group(group)
        if perp and perp not in protected:
            protected.append(perp)
    if not protected and "南北向" in primary_groups:
        protected.append("东西向")
    elif not protected and "东西向" in primary_groups:
        protected.append("南北向")
    elif not protected:
        protected.append("东西向")
    return protected
