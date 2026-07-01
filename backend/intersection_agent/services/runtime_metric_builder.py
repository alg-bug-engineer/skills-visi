"""Build diagnosis-driven runtime metric rows for the frontend panel."""

from __future__ import annotations

from typing import Any

from intersection_agent.models.domain import NluResult
from intersection_agent.services.dimension_pack_service import DimensionPackService
from intersection_agent.utils.problem_type_narrative import (
    infer_mixed_turn_approaches,
    resolve_primary_problem_type,
    user_mentions,
)
from intersection_agent.utils.thresholds_loader import threshold_value

APPROACH_DIRS = ("东", "南", "西", "北")
EMPHASIS_ORDER = ("primary", "secondary", "background")
LOW_UTIL_DEFAULT = 0.60


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sat_tone(sat: float) -> str:
    if sat >= 0.95:
        return "过饱和"
    high = threshold_value("saturation", "high", default=0.80)
    if sat >= high:
        return "偏高"
    if sat >= 0.65:
        return "可控"
    return "偏低"


def _sat_severity(sat: float) -> str:
    high = threshold_value("saturation", "high", default=0.80)
    if sat >= high:
        return "high"
    if sat >= 0.65:
        return "medium"
    return "low"


def _row(
    key: str,
    label: str,
    value: str,
    emphasis: str,
    *,
    severity: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "key": key,
        "id": f"{key}-{label}",
        "label": label,
        "value": value,
        "emphasis": emphasis,
    }
    if severity:
        item["severity"] = severity
    return item


class RuntimeMetricBuilder:
    """Assemble runtime panel items from payload + problem-type profile."""

    def __init__(self, dimension_packs: DimensionPackService | None = None) -> None:
        self._packs = dimension_packs or DimensionPackService()

    def build(
        self,
        data: dict[str, Any],
        problem_types: list[str],
        *,
        diagnosis: dict[str, Any] | None = None,
        user_context: str = "",
        nlu: NluResult | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
        profile = self._packs.runtime_profile(problem_types or ["congestion"])
        emphasis_by_key = self._emphasis_map(profile)
        items: list[dict[str, Any]] = []
        seen_labels: set[str] = set()

        def push(item: dict[str, Any]) -> None:
            key = str(item.get("key") or "")
            if key and key not in emphasis_by_key:
                return
            label = str(item.get("label") or "")
            if not label or label in seen_labels:
                return
            seen_labels.add(label)
            item["emphasis"] = emphasis_by_key.get(key, item.get("emphasis", "secondary"))
            items.append(item)

        for key in self._ordered_keys(profile):
            emphasis = emphasis_by_key.get(key)
            if not emphasis:
                continue
            for item in self._extract(key, data, diagnosis=diagnosis, emphasis=emphasis):
                push(item)

        primary = resolve_primary_problem_type(problem_types)
        has_primary = any(i.get("emphasis") == "primary" for i in items)
        synth = self._synthesize_hints(
            primary,
            data,
            diagnosis=diagnosis,
            user_context=user_context,
            nlu=nlu,
            emphasis_by_key=emphasis_by_key,
        )
        filled_keys = {str(i.get("key") or "") for i in items}
        if primary in ("conflict", "empty_green", "spillback"):
            for item in synth:
                key = str(item.get("key") or "")
                label = str(item.get("label") or "")
                if key in filled_keys and not (
                    primary == "empty_green" and key == "green_split" and label == "绿信比"
                ):
                    continue
                push(item)
                if key:
                    filled_keys.add(key)
        elif not has_primary:
            for item in synth:
                push(item)

        items = self._apply_background_cap(items, primary)

        items.sort(
            key=lambda row: (
                EMPHASIS_ORDER.index(str(row.get("emphasis") or "secondary"))
                if str(row.get("emphasis") or "secondary") in EMPHASIS_ORDER
                else 99,
                self._ordered_keys(profile).index(str(row.get("key") or ""))
                if str(row.get("key") or "") in self._ordered_keys(profile)
                else 999,
            )
        )
        return items, profile

    @staticmethod
    def _apply_background_cap(items: list[dict[str, Any]], primary: str) -> list[dict[str, Any]]:
        """主问题明确时弱化背景指标（饱和/延误等）。"""
        primaries = [i for i in items if i.get("emphasis") == "primary"]
        secondaries = [i for i in items if i.get("emphasis") == "secondary"]
        backgrounds = [i for i in items if i.get("emphasis") == "background"]
        if primary == "conflict" and primaries:
            backgrounds = []
        elif primary == "empty_green" and primaries:
            backgrounds = backgrounds[:1]
        elif primary == "spillback" and primaries:
            backgrounds = backgrounds[:1]
        elif primaries:
            backgrounds = backgrounds[:2]
        return primaries + secondaries + backgrounds

    def _synthesize_hints(
        self,
        primary: str,
        data: dict[str, Any],
        *,
        diagnosis: dict[str, Any] | None,
        user_context: str,
        nlu: NluResult | None,
        emphasis_by_key: dict[str, str],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cognition = data.get("cognition") or {}
        timing = (data.get("problem_evidence") or {}).get("timing_profile") or data.get(
            "timing_profile"
        ) or {}

        if primary == "conflict":
            emphasis = emphasis_by_key.get("channel_match", "primary")
            mixed = infer_mixed_turn_approaches(cognition)
            if mixed or user_mentions(user_context, "混行", "左转和直行", "左转与直行"):
                dirs = "、".join(mixed) if mixed else "东进口"
                rows.append(
                    _row(
                        "channel_match",
                        "渠化匹配",
                        f"{dirs}左转与直行混行，车道功能与放行需对齐",
                        emphasis,
                        severity="high",
                    )
                )
            if user_mentions(user_context, "机非", "非机动车", "行人"):
                rows.append(
                    _row(
                        "nonmotor_conflict",
                        "机非冲突",
                        "机非冲突风险突出，慢行保护需复核",
                        emphasis_by_key.get("nonmotor_conflict", "primary"),
                        severity="high",
                    )
                )
            fit = timing.get("flow_green_fit") or {}
            if user_mentions(user_context, "相位", "放行", "相序") or fit.get("verdict") == "mismatch":
                rows.append(
                    _row(
                        "phase_sequence",
                        "相位相序",
                        str(fit.get("narrative") or "相位放行与流量结构不够顺畅")[:48],
                        emphasis_by_key.get("phase_sequence", "primary"),
                        severity="medium",
                    )
                )
            if user_mentions(user_context, "冲突") and not any(
                r.get("key") == "conflict_type" for r in rows
            ):
                rows.append(
                    _row(
                        "conflict_type",
                        "冲突类型",
                        "转向/相位冲突与渠化结构相关",
                        emphasis_by_key.get("conflict_type", "primary"),
                        severity="high",
                    )
                )
            arms = cognition.get("arms") or []
            if arms and not any(r.get("key") == "lane_function" for r in rows):
                lane_count = sum(len(a.get("lanes") or []) or int(a.get("lane_num") or 0) for a in arms)
                rows.append(
                    _row(
                        "arm_structure",
                        "进口结构",
                        f"{len(arms)} 进口 · {lane_count} 车道",
                        emphasis_by_key.get("arm_structure", "secondary"),
                    )
                )

        elif primary == "empty_green":
            evaluation = data.get("evaluation") or {}
            gu = _float(evaluation.get("green_utilization"))
            if gu is not None:
                rows.append(
                    _row(
                        "green_utilization",
                        "绿灯利用率",
                        f"{gu:.2f}",
                        emphasis_by_key.get("green_utilization", "primary"),
                        severity="low" if gu < 0.55 else "medium",
                    )
                )
            empty_rate = _float(evaluation.get("empty_green_rate"))
            if empty_rate is not None:
                rows.append(
                    _row(
                        "empty_green_rate",
                        "空放率",
                        f"{empty_rate:.2f}",
                        emphasis_by_key.get("empty_green_rate", "primary"),
                        severity="high" if empty_rate >= 0.2 else "medium",
                    )
                )
            if user_mentions(user_context, "没车", "无车", "空放", "绿灯经常"):
                spare = next((d for d in (nlu.directions if nlu else []) if "西" in d), "西进口")
                busy = next((d for d in (nlu.directions if nlu else []) if "东" in d), "东进口")
                rows.append(
                    _row(
                        "green_split",
                        "绿信比",
                        f"{spare}常无车放行，{busy}排队较长",
                        emphasis_by_key.get("green_split", "primary"),
                        severity="medium",
                    )
                )

        elif primary == "spillback":
            evidence = data.get("problem_evidence") or {}
            metrics = evidence.get("metrics") or {}
            if user_mentions(user_context, "溢出", "外溢", "蔓延", "顶到", "排到上游"):
                rows.append(
                    _row(
                        "spillback_risk",
                        "溢流风险",
                        "用户描述排队外溢，需复核下游阻塞与储车空间",
                        emphasis_by_key.get("spillback_risk", "primary"),
                        severity="high",
                    )
                )
            q = _float(metrics.get("max_queue_m"))
            if q is not None:
                rows.append(
                    _row(
                        "max_queue_m",
                        "最大排队",
                        f"{q:.0f} m",
                        emphasis_by_key.get("max_queue_m", "primary"),
                        severity="high",
                    )
                )
            ratio = _float(metrics.get("queue_storage_ratio_max"))
            if ratio is not None:
                rows.append(
                    _row(
                        "queue_storage_ratio",
                        "排队存储比",
                        f"{ratio:.2f}",
                        emphasis_by_key.get("queue_storage_ratio", "primary"),
                        severity="high" if ratio >= 0.8 else "medium",
                    )
                )

        return rows

    @staticmethod
    def _emphasis_map(profile: dict[str, list[str]]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for bucket in EMPHASIS_ORDER:
            for key in profile.get(bucket, []):
                mapping.setdefault(key, bucket)
        return mapping

    @staticmethod
    def _ordered_keys(profile: dict[str, list[str]]) -> list[str]:
        keys: list[str] = []
        for bucket in EMPHASIS_ORDER:
            for key in profile.get(bucket, []):
                if key not in keys:
                    keys.append(key)
        return keys

    def _extract(
        self,
        key: str,
        data: dict[str, Any],
        *,
        diagnosis: dict[str, Any] | None,
        emphasis: str,
    ) -> list[dict[str, Any]]:
        cognition = data.get("cognition") or {}
        evaluation = data.get("evaluation") or {}
        traffic = data.get("traffic_flow") or {}
        evidence = data.get("problem_evidence") or {}
        metrics = evidence.get("metrics") or {}
        timing = evidence.get("timing_profile") or data.get("timing_profile") or {}
        gran = data.get("granularity") or {}
        governance = data.get("flow_timing_governance") or {}
        corridor = evidence.get("corridor_context") or data.get("corridor_context") or {}
        external = evidence.get("external_evidence") or data.get("external_evidence") or {}
        matched_rules = (diagnosis or {}).get("matched_rules") or data.get("matched_rules") or []

        if key == "approach_saturation":
            rows: list[dict[str, Any]] = []
            arms = cognition.get("metrics_by_arm") or []
            for d in APPROACH_DIRS:
                arm = next(
                    (a for a in arms if str(a.get("dir4_label") or "").startswith(d)),
                    None,
                )
                sat = _float(arm.get("saturation")) if arm else None
                if sat is None:
                    continue
                rows.append(
                    _row(
                        key,
                        f"{d}进口饱和度",
                        f"{sat:.2f} · {_sat_tone(sat)}",
                        emphasis,
                        severity=_sat_severity(sat),
                    )
                )
            return rows

        if key == "delay_index":
            delay = _float(metrics.get("delay_index")) or _float(evaluation.get("delay_index"))
            if delay is None:
                return []
            sev = "high" if delay >= threshold_value("delay", "high_delay_index", default=2.0) else "medium"
            return [_row(key, "延误指数", f"{delay:.2f}", emphasis, severity=sev)]

        if key == "avg_queue_m":
            q = _float(metrics.get("avg_queue_m"))
            if q is None:
                return []
            return [_row(key, "平均排队", f"{q:.0f} m", emphasis, severity="medium")]

        if key == "max_queue_m":
            q = _float(metrics.get("max_queue_m"))
            if q is None:
                return []
            long_q = threshold_value("queue", "long_queue_m", default=100)
            sev = "high" if q >= long_q else "medium"
            return [_row(key, "最大排队", f"{q:.0f} m", emphasis, severity=sev)]

        if key == "chronic":
            chronic = evidence.get("chronic") or {}
            if not chronic.get("is_chronic"):
                return []
            days = chronic.get("congested_days")
            window = chronic.get("window_days") or 7
            if days is None:
                return []
            return [
                _row(
                    key,
                    "常发拥堵",
                    f"近 {window} 天有 {days} 天偏堵",
                    emphasis,
                    severity="high",
                )
            ]

        if key == "turn_saturation":
            rows = []
            turns = gran.get("by_turn") or evidence.get("by_turn") or []
            tb = (governance.get("primary_diagnosis") or {}).get("turn_balance") or {}
            over = tb.get("over") or {}
            if over.get("label") and over.get("turn_saturation") is not None:
                sat = float(over["turn_saturation"])
                rows.append(
                    _row(
                        key,
                        f"{over['label']}饱和度",
                        f"{sat:.2f} · {_sat_tone(sat)}",
                        emphasis,
                        severity=_sat_severity(sat),
                    )
                )
            for turn in turns:
                label = str(turn.get("label") or "")
                sat = _float(turn.get("turn_saturation"))
                if not label or sat is None:
                    continue
                if rows and rows[0]["label"] == f"{label}饱和度":
                    continue
                rows.append(
                    _row(
                        key,
                        f"{label}饱和度",
                        f"{sat:.2f} · {_sat_tone(sat)}",
                        emphasis,
                        severity=_sat_severity(sat),
                    )
                )
                if len(rows) >= 2:
                    break
            return rows[:2]

        if key == "imbalance_index":
            imb = _float(metrics.get("imbalance_index")) or _float(evaluation.get("imbalance_index"))
            if imb is None:
                return []
            high = imb >= threshold_value("imbalance", "diagnosis", default=0.30)
            return [
                _row(
                    key,
                    "方向失衡",
                    f"{imb:.2f} · {'各进口差异大' if high else '较均衡'}",
                    emphasis,
                    severity="medium" if high else "low",
                )
            ]

        if key == "green_utilization":
            gu = _float(evaluation.get("green_utilization")) or _float(metrics.get("green_utilization"))
            if gu is None:
                return []
            low = threshold_value("green", "low_utilization_diagnosis", default=0.50)
            sev = "low" if gu < low else "medium"
            return [_row(key, "绿灯利用率", f"{gu:.2f}", emphasis, severity=sev)]

        if key == "empty_green_rate":
            rate = _float(evaluation.get("empty_green_rate")) or _float(metrics.get("empty_green_rate"))
            if rate is None:
                gu = _float(evaluation.get("green_utilization"))
                if gu is not None:
                    rate = max(0.0, 1.0 - gu)
            if rate is None:
                return []
            high = rate >= threshold_value("green", "empty_green_rate", default=0.20)
            return [
                _row(
                    key,
                    "空放率",
                    f"{rate:.2f} · {'偏高' if high else '可控'}",
                    emphasis,
                    severity="high" if high else "medium",
                )
            ]

        if key == "low_util_turn":
            rows = []
            low_util = threshold_value("green", "low_utilization_diagnosis", default=0.50)
            turns = gran.get("by_turn") or evidence.get("by_turn") or []
            tb = (governance.get("primary_diagnosis") or {}).get("turn_balance") or {}
            spare = tb.get("spare") or {}
            if spare.get("label") and spare.get("green_utilization") is not None:
                gu = float(spare["green_utilization"])
                if gu < low_util:
                    rows.append(
                        _row(
                            key,
                            f"{spare['label']}绿灯利用",
                            f"{gu:.2f} · 偏低",
                            emphasis,
                            severity="low",
                        )
                    )
            for turn in turns:
                label = str(turn.get("label") or "")
                gu = _float(turn.get("green_utilization"))
                if not label or gu is None or gu >= low_util:
                    continue
                if any(r["label"] == f"{label}绿灯利用" for r in rows):
                    continue
                rows.append(
                    _row(
                        key,
                        f"{label}绿灯利用",
                        f"{gu:.2f} · 偏低",
                        emphasis,
                        severity="low",
                    )
                )
                if len(rows) >= 2:
                    break
            return rows

        if key == "green_split":
            fit = timing.get("flow_green_fit") or {}
            narrative = str(fit.get("narrative") or "").strip()
            if narrative:
                return [_row(key, "绿信比匹配", narrative[:48], emphasis)]
            deficit = timing.get("deficit_turns") or []
            if deficit:
                first = deficit[0]
                label = str(first.get("label") or "关键转向")
                ratio = _float(first.get("deficit_ratio"))
                if ratio is not None:
                    return [_row(key, "绿信比", f"{label} 绿灯偏紧 {ratio:.0%}", emphasis)]
            return []

        if key == "ring_diagram":
            ring = timing.get("ring_diagram") or {}
            if ring.get("available"):
                return [_row(key, "配时环图", "已加载相位环结构", emphasis)]
            return []

        if key == "cycle_len":
            cycle = _float(timing.get("cycle_length"))
            if cycle is None:
                return []
            return [_row(key, "周期", f"{cycle:.0f} s", emphasis)]

        if key == "spare_turn":
            spare = (governance.get("primary_diagnosis") or {}).get("turn_balance", {}).get("spare") or {}
            label = str(spare.get("label") or "").strip()
            if not label:
                return []
            return [_row(key, "可让绿方向", label, emphasis, severity="low")]

        if key == "queue_storage_ratio":
            ratio = _float(metrics.get("queue_storage_ratio_max"))
            if ratio is None:
                return []
            high = ratio >= threshold_value("queue", "queue_storage_ratio_high", default=0.80)
            return [
                _row(
                    key,
                    "排队存储比",
                    f"{ratio:.2f} · {'接近上限' if high else '尚可'}",
                    emphasis,
                    severity="high" if high else "medium",
                )
            ]

        if key == "spillback_risk":
            risk = _float(metrics.get("spillback_risk_max"))
            if risk is None:
                return []
            high = risk >= threshold_value("spillback", "risk_high", default=0.80)
            return [
                _row(
                    key,
                    "溢流风险",
                    f"{risk:.2f} · {'偏高' if high else '可控'}",
                    emphasis,
                    severity="high" if high else "medium",
                )
            ]

        if key == "corridor_context":
            if corridor.get("in_corridor") or corridor.get("corridor_name"):
                name = str(corridor.get("corridor_name") or "协调走廊")
                return [_row(key, "走廊关联", f"位于 {name}", emphasis)]
            nodes = corridor.get("corridor_nodes") or []
            if nodes:
                return [_row(key, "上下游关联", f"关联 {len(nodes)} 个协调节点", emphasis)]
            return []

        if key == "corridor_node":
            nodes = corridor.get("corridor_nodes") or []
            current = next((n for n in nodes if n.get("is_current")), None)
            if not nodes:
                return []
            if current:
                seq = current.get("seq")
                return [_row(key, "走廊节点", f"当前为第 {seq} 个节点" if seq else "位于协调走廊", emphasis)]
            return [_row(key, "走廊节点", f"共 {len(nodes)} 个节点", emphasis)]

        if key == "channel_match":
            for rule in matched_rules:
                if rule.get("focus_category") == "channelization" or rule.get("problem_type") == "channelization":
                    conclusion = str(rule.get("conclusion") or rule.get("name") or "").strip()
                    if conclusion:
                        return [_row(key, "渠化匹配", conclusion[:40], emphasis, severity="high")]
            if data.get("channelization", {}).get("has_mixed_left"):
                return [_row(key, "渠化匹配", "左转混行与专用道不匹配", emphasis, severity="high")]
            return []

        if key == "phase_sequence":
            narrative = str(timing.get("narrative") or "").strip()
            if "相序" in narrative or "冲突" in narrative:
                return [_row(key, "相位相序", narrative[:40], emphasis, severity="high")]
            fit = timing.get("flow_green_fit") or {}
            if fit.get("verdict") == "mismatch":
                return [_row(key, "相位相序", "流量与放行结构不匹配", emphasis, severity="medium")]
            return []

        if key == "conflict_type":
            for rule in matched_rules:
                rid = str(rule.get("id") or "")
                if "conflict" in rid or rule.get("focus_category") == "channelization":
                    return [_row(key, "冲突类型", str(rule.get("name") or "相位/渠化冲突"), emphasis, severity="high")]
            return []

        if key == "nonmotor_conflict":
            ch = data.get("channelization") or {}
            if ch.get("has_mixed_left") or ch.get("has_nonmotor_conflict"):
                return [_row(key, "机非混行", "进口存在机非混行风险", emphasis, severity="high")]
            return []

        if key == "lane_function":
            arms = cognition.get("arms") or []
            bits: list[str] = []
            for arm in arms[:4]:
                lanes = arm.get("lanes") or []
                if not lanes:
                    continue
                dir_l = str(arm.get("dir4_label") or "")[:1]
                turn_types = {str(l.get("turn_type") or l.get("lane_turn") or "") for l in lanes}
                turn_types.discard("")
                if dir_l and turn_types:
                    bits.append(f"{dir_l}向{'/'.join(sorted(turn_types)[:2])}")
            if bits:
                return [_row(key, "车道功能", "；".join(bits[:3]), emphasis)]
            return []

        if key == "arm_structure":
            arms = cognition.get("arms") or []
            lane_count = sum(len(a.get("lanes") or []) or int(a.get("lane_num") or 0) for a in arms)
            if not arms:
                return []
            return [_row(key, "进口结构", f"{len(arms)} 进口 · {lane_count} 车道", emphasis)]

        if key == "complaint":
            total = external.get("complaint_total")
            complaints = external.get("complaints") or []
            if total and int(total) > 0:
                return [_row(key, "现场/投诉", f"关联投诉 {int(total)} 件", emphasis, severity="medium")]
            if complaints:
                first = complaints[0]
                ctype = str(first.get("type") or "投诉")
                count = int(first.get("count") or 1)
                return [_row(key, "现场/投诉", f"{ctype} {count} 件", emphasis, severity="medium")]
            return []

        return []
