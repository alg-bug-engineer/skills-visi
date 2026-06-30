"""专家经验库（expert_knowledge.md）场景匹配，作为大模型案例治理经验输入。

按「场景 → 典型问题 → 治理方案」结构解析，按问题类型 + 路口场景文本做关键词匹配，
返回最相关场景的典型问题与专家治理方案（关键措施/适用条件/注意事项），供方案生成参考。
纯关键词/文本匹配，不引入任何向量库依赖。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from intersection_agent.config import get_settings

# 场景 ID → 场景关键词（用于把当前路口认知文本映射到专家场景）
_SCENE_KEYWORDS: dict[str, list[str]] = {
    "arterial_green_wave": ["干线", "绿波", "主干道", "协调", "带宽"],
    "commercial_district": ["商圈", "商业", "购物", "核心区", "综合体"],
    "mixed_traffic_conflict": ["机非", "非机动车", "行人", "混行", "电动车"],
    "short_spacing_coordinated": ["短间距", "相邻", "间距", "回溢", "相距"],
    "irregular_geometry": ["畸形", "异形", "几何", "错位", "Y型", "T型", "五岔"],
    "school_zone": ["学校", "小学", "中学", "上下学", "学生", "校门"],
    "interchange_confluence": ["立交", "合流", "匝道", "桥下", "互通"],
    "construction_impacted": ["施工", "占道", "改造", "围挡", "工地"],
    "freight_corridor": ["货运", "货车", "物流", "港口", "重载"],
    "tide_flow_management": ["潮汐", "可变方向", "钟摆", "向心"],
    "scenic_area": ["景区", "旅游", "集散", "景点", "游客"],
    "variable_lane": ["可变导向", "可变车道", "导向车道", "潮汐车道"],
    "general_intersection": ["一般路口", "单点", "普通路口"],
    "standardization_upgrade": ["标准化", "标志标线", "系统升级", "联网联控"],
    "large_event_support": ["大型活动", "赛事", "临时保障", "演唱会", "活动"],
    "bridge_ramp_integration": ["桥路衔接", "桥头", "上桥", "下桥"],
    "historical_urban_core": ["老城", "历史", "密路网", "古城", "窄路"],
    "holiday_peak_management": ["节假日", "刚性出行", "假期", "返程"],
    "micro_circulation_school": ["微循环", "校园微循环", "单向组织"],
}

# 问题类型 → 典型问题/治理方案文本关键词（用于在场景内挑选相关典型问题）
_PROBLEM_TYPE_KEYWORDS: dict[str, list[str]] = {
    "spillback": ["溢出", "回溢", "积压", "锁死", "外溢", "清空"],
    "congestion": ["拥堵", "排队", "停车", "延误", "饱和", "通行能力"],
    "empty_green": ["空放", "绿灯利用", "绿损", "放空", "绿信比"],
    "conflict": ["冲突", "相位", "相序", "左转", "机非", "干扰"],
}


def _default_path() -> Path:
    settings = get_settings()
    path = Path(settings.case_library_path)
    if path.is_absolute():
        return path
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / path


class CaseLibraryService:
    """解析专家经验库并按场景/问题类型匹配治理经验。"""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else _default_path()
        self._scenarios: list[dict[str, Any]] | None = None

    # ---- 解析 ----
    def _load(self) -> list[dict[str, Any]]:
        if self._scenarios is not None:
            return self._scenarios
        scenarios: list[dict[str, Any]] = []
        if self._path.exists():
            text = self._path.read_text(encoding="utf-8")
            scenarios = self._parse(text)
        self._scenarios = scenarios
        return scenarios

    @staticmethod
    def _parse(text: str) -> list[dict[str, Any]]:
        scenarios: list[dict[str, Any]] = []
        # 以 "## " 分块，仅保留含场景 ID 的块
        blocks = re.split(r"(?m)^## ", text)
        for block in blocks:
            if "**场景 ID**" not in block:
                continue
            lines = block.splitlines()
            name = lines[0].strip()
            id_match = re.search(r"场景 ID\*\*:\s*`([^`]+)`", block)
            scenario_id = id_match.group(1) if id_match else name
            desc_match = re.search(r"(?m)^([^#\n*\-|].*适用于.*)$", block)
            description = desc_match.group(1).strip() if desc_match else ""

            scenario = {
                "scenario_id": scenario_id,
                "scenario_name": name,
                "description": description,
                "problems": [],
            }

            # 典型问题分块
            prob_blocks = re.split(r"(?m)^### 典型问题:\s*", block)[1:]
            for pblock in prob_blocks:
                plines = pblock.splitlines()
                problem_name = plines[0].strip()
                problem = {
                    "problem": problem_name,
                    "occurrence": CaseLibraryService._collect_int(pblock, "出现频次"),
                    "symptoms": CaseLibraryService._collect_sublist(pblock, "典型表现"),
                    "solutions": [],
                }
                sol_blocks = re.split(r"(?m)^#### 治理方案:\s*", pblock)[1:]
                for sblock in sol_blocks:
                    slines = sblock.splitlines()
                    sol_name = slines[0].strip()
                    measures = CaseLibraryService._collect_sublist(sblock, "关键措施")
                    applicability = CaseLibraryService._collect_inline(sblock, "适用条件")
                    caution = CaseLibraryService._collect_inline(sblock, "注意事项")
                    problem["solutions"].append(
                        {
                            "name": sol_name,
                            "frequency": CaseLibraryService._collect_int(sblock, "频次"),
                            "measures": measures,
                            "applicability": applicability,
                            "caution": caution,
                            "representative_cases": CaseLibraryService._collect_cases(
                                sblock
                            ),
                        }
                    )
                scenario["problems"].append(problem)
            scenario["case_count"] = CaseLibraryService._scene_case_count(block)
            scenarios.append(scenario)
        return scenarios

    @staticmethod
    def _collect_sublist(block: str, label: str) -> list[str]:
        """收集 "- <label>:" 之后的缩进子项。"""
        lines = block.splitlines()
        out: list[str] = []
        capture = False
        for line in lines:
            if re.match(rf"^- {label}:\s*$", line.strip()) or re.match(
                rf"^- {label}:\s*$", line
            ):
                capture = True
                continue
            if capture:
                m = re.match(r"^\s+- (.+)$", line)
                if m:
                    out.append(m.group(1).strip())
                elif line.strip().startswith("- "):
                    break
        return out

    @staticmethod
    def _collect_inline(block: str, label: str) -> str:
        m = re.search(rf"(?m)^- {label}:\s*(.+)$", block)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _collect_int(block: str, label: str) -> int:
        m = re.search(rf"(?m)^- {label}:\s*(\d+)\s*$", block)
        return int(m.group(1)) if m else 0

    @staticmethod
    def _scene_case_count(block: str) -> int:
        """场景头部的 **案例数**: N。"""
        m = re.search(r"\*\*案例数\*\*:\s*(\d+)", block)
        return int(m.group(1)) if m else 0

    @staticmethod
    def _collect_cases(block: str) -> list[dict[str, str]]:
        """收集 "- 代表案例:" 之后的 "- [#N] 标题: 摘要..." 子项。"""
        lines = block.splitlines()
        out: list[dict[str, str]] = []
        capture = False
        for line in lines:
            if re.match(r"^- 代表案例:\s*$", line.strip()):
                capture = True
                continue
            if capture:
                m = re.match(r"^\s+- \[#(\d+)\]\s*(.+)$", line)
                if m:
                    case_id, rest = m.group(1), m.group(2).strip()
                    title, _, snippet = rest.partition(": ")
                    out.append(
                        {
                            "id": case_id,
                            "title": title.strip(),
                            "snippet": snippet.strip() or title.strip(),
                        }
                    )
                elif line.strip().startswith("- "):
                    break
        return out

    # ---- 浏览 ----
    def list_all(self) -> list[dict[str, Any]]:
        """返回全部场景的完整结构（不裁剪），供案例库行业案例浏览。"""
        return [
            {
                "scenario_id": sc["scenario_id"],
                "scenario_name": sc["scenario_name"],
                "description": sc.get("description", ""),
                "case_count": sc.get("case_count", 0),
                "problems": sc["problems"],
            }
            for sc in self._load()
        ]

    # ---- 匹配 ----
    def match(
        self,
        problem_types: list[str],
        scene_text: str = "",
        shape_tags: list[str] | None = None,
        k: int = 1,
    ) -> list[dict[str, Any]]:
        """按场景关键词命中度排序取 Top-K 场景，并在场景内挑选与问题类型相关的典型问题。"""
        scenarios = self._load()
        if not scenarios:
            return []
        query = scene_text + " ".join(shape_tags or [])

        scored: list[tuple[int, dict[str, Any]]] = []
        for sc in scenarios:
            keywords = _SCENE_KEYWORDS.get(sc["scenario_id"], [])
            hits = sum(1 for kw in keywords if kw in query)
            scored.append((hits, sc))

        scored.sort(key=lambda item: item[0], reverse=True)
        top = [sc for score, sc in scored if score > 0][:k]
        if not top:
            # 无场景命中 → 回退一般路口
            top = [
                sc for sc in scenarios if sc["scenario_id"] == "general_intersection"
            ][:k] or [scenarios[0]]

        pt_keywords: list[str] = []
        for pt in problem_types:
            pt_keywords.extend(_PROBLEM_TYPE_KEYWORDS.get(pt, []))

        results: list[dict[str, Any]] = []
        for sc in top:
            problems = self._pick_problems(sc, pt_keywords)
            results.append(
                {
                    "scenario_id": sc["scenario_id"],
                    "scenario_name": sc["scenario_name"],
                    "description": sc["description"],
                    "problems": problems,
                }
            )
        return results

    @staticmethod
    def _pick_problems(
        scenario: dict[str, Any], pt_keywords: list[str], limit: int = 2
    ) -> list[dict[str, Any]]:
        problems = scenario["problems"]
        if not problems:
            return []
        scored: list[tuple[int, dict[str, Any]]] = []
        for p in problems:
            text = p["problem"] + "".join(
                s["name"] + s.get("applicability", "") for s in p["solutions"]
            )
            hits = sum(1 for kw in pt_keywords if kw in text)
            scored.append((hits, p))
        scored.sort(key=lambda item: item[0], reverse=True)
        picked = [p for score, p in scored if score > 0][:limit]
        if not picked:
            picked = problems[:limit]
        # 每个问题只保留前 2 个治理方案，控制 prompt 体积
        return [
            {
                "problem": p["problem"],
                "solutions": p["solutions"][:2],
            }
            for p in picked
        ]

    # ---- 输出 ----
    @staticmethod
    def format_experience_block(matches: list[dict[str, Any]]) -> str:
        """把匹配到的专家经验格式化为供大模型参考的文本块。"""
        if not matches:
            return "无同类场景经验。"
        parts: list[str] = []
        for m in matches:
            parts.append(f"【场景】{m['scenario_name']}")
            for p in m["problems"]:
                parts.append(f"  · 典型问题：{p['problem']}")
                for s in p["solutions"]:
                    measures = "、".join(s.get("measures") or []) or s["name"]
                    line = f"    - 治理方案：{s['name']}（关键措施：{measures}）"
                    if s.get("applicability"):
                        line += f"；适用条件：{s['applicability']}"
                    if s.get("caution"):
                        line += f"；注意事项：{s['caution']}"
                    parts.append(line)
        return "\n".join(parts)
