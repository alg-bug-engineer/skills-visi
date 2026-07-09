"""交通组织调研报告问题分类与路口别名。"""

from __future__ import annotations

import re

ISSUE_CATEGORIES: dict[str, str] = {
    "秩序": "通行秩序与管控类问题",
    "空间": "交通空间与渠化设计类问题",
    "配套": "交通管控配套设施类问题",
}

ISSUE_TYPES: tuple[str, ...] = (
    "非机动车管控不足",
    "路内乱停车",
    "机非混行",
    "机动车或非机动车冲突",
    "渠化不合理",
    "车道功能不合理",
    "出入口开口问题",
    "慢行空间被占用或其环境不良",
    "信号配时不合理",
    "标志、标线不清",
)

ISSUE_TYPE_TO_CATEGORY: dict[str, str] = {
    "非机动车管控不足": "秩序",
    "路内乱停车": "秩序",
    "机非混行": "秩序",
    "机动车或非机动车冲突": "秩序",
    "渠化不合理": "空间",
    "车道功能不合理": "空间",
    "出入口开口问题": "空间",
    "慢行空间被占用或其环境不良": "空间",
    "信号配时不合理": "配套",
    "标志、标线不清": "配套",
}

_SECTION_NAMES: tuple[str, ...] = (
    "工业南路",
    "新泺大街",
    "解放路",
    "经十路",
    "旅游路",
    "奥体西路",
    "奥体中路",
)

# 报告别名 → 匹配用 canonical 名称片段（仅用于括号内别名或整段替换）
INTER_NAME_ALIASES: dict[str, str] = {
    "茂岭二号路": "海右路",
    "茂岭山三号路": "山左路",
    "规划路": "华龙路会展路",
}

_ISSUE_TYPE_SET = frozenset(ISSUE_TYPES)

# 报告个别表述与标准 10 类不完全一致时的映射
ISSUE_TYPE_ALIASES: dict[str, str] = {
    "非机动车过街等待区不足": "慢行空间被占用或其环境不良",
    "标志标线不清": "标志、标线不清",
}


def validate_issue_type(value: str) -> str | None:
    text = (value or "").strip()
    if text in _ISSUE_TYPE_SET:
        return text
    if text in ISSUE_TYPE_ALIASES:
        return ISSUE_TYPE_ALIASES[text]
    for alias, canonical in ISSUE_TYPE_ALIASES.items():
        if alias in text:
            return canonical
    for issue_type in ISSUE_TYPES:
        if issue_type in text or text in issue_type:
            return issue_type
    return None


def issue_category_for_type(issue_type: str) -> str:
    return ISSUE_TYPE_TO_CATEGORY.get(issue_type, "秩序")


def normalize_inter_name_for_match(name: str) -> str:
    """展开已知道路别名片段，供路网匹配前预处理。"""
    text = (name or "").strip()
    for alias, canonical in INTER_NAME_ALIASES.items():
        if alias in text:
            text = text.replace(alias, canonical)
    return text


def match_name_candidates(inter_name_raw: str, inter_alias: str | None = None) -> list[str]:
    """生成多个路口名候选，提高括号别名与 PG 标准名匹配率。"""
    raw = (inter_name_raw or "").strip()
    alias = (inter_alias or "").strip()
    candidates: list[str] = []

    def _add(name: str) -> None:
        name = (name or "").strip()
        if not name:
            return
        if not name.endswith("路口"):
            name = f"{name}路口"
        normalized = normalize_inter_name_for_match(name)
        for item in (name, normalized):
            if item and item not in candidates:
                candidates.append(item)

    _add(raw)
    base = re.sub(r"（[^）]+）", "", raw).strip()
    if base and base != raw:
        _add(base)

    if alias:
        m = re.match(r"^(.+?)与(.+?)路口", base.replace("与", "与"))
        if m:
            _add(f"{alias}与{m.group(2)}路口")
            _add(f"{m.group(1)}与{alias}路口")

    for alias_key, canonical in INTER_NAME_ALIASES.items():
        if alias_key in raw or alias_key in base or alias_key in alias:
            _add(raw.replace(alias_key, canonical))
            _add(base.replace(alias_key, canonical))

    return candidates


def section_names() -> tuple[str, ...]:
    return _SECTION_NAMES
