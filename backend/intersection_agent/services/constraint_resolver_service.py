"""Resolve natural-language user constraints into quantitative guardrails."""

from __future__ import annotations

import re
from typing import Any

from intersection_agent.utils.direction_groups import (
    primary_groups_from_nlu,
    protected_groups_for_vertical_constraint,
)
from intersection_agent.utils.thresholds_loader import load_thresholds, threshold_value


class ConstraintResolverService:
    """Translate user_suggestion into measurable constraints."""

    def resolve(
        self,
        user_suggestion: str | None,
        *,
        nlu_directions: list[str],
        problem_evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Return structured constraints or None when no suggestion."""
        text = (user_suggestion or "").strip()
        if not text:
            return None

        thresholds = load_thresholds()
        primary_groups = primary_groups_from_nlu(nlu_directions)
        by_direction = (problem_evidence or {}).get("by_direction") or []
        dir_map = {item["group"]: item for item in by_direction}

        intent = self._detect_intent(text)
        protected_groups = self._protected_groups(text, primary_groups, intent)
        constraints: list[dict[str, Any]] = []
        narratives: list[str] = []

        spillback_high = threshold_value("spillback", "risk_high", default=0.80)
        storage_high = threshold_value("queue", "queue_storage_ratio_high", default=0.80)
        spillback_margin = threshold_value("constraint", "spillback_margin", default=0.05)
        queue_margin = threshold_value("constraint", "queue_growth_margin", default=0.10)
        sat_margin = threshold_value("constraint", "saturation_margin", default=0.10)

        for group in protected_groups:
            metrics = dir_map.get(group, {})
            storage = _float(metrics.get("queue_storage_ratio"))
            spillback = _float(metrics.get("queue_storage_ratio"))  # proxy
            queue_m = _float(metrics.get("avg_queue_m"))
            saturation = _float(metrics.get("saturation"))

            if intent in ("no_spillback", "no_worsen", "protect"):
                baseline = spillback if spillback is not None else storage
                if baseline is not None:
                    cap = min(baseline + spillback_margin, spillback_high)
                    constraints.append(
                        {
                            "metric": "spillback_risk",
                            "scope": group,
                            "operator": "<=",
                            "value": round(cap, 3),
                            "baseline": round(baseline, 3),
                            "threshold_ref": "spillback.risk_high",
                        }
                    )
                    narratives.append(
                        f"{group}溢流风险不超过 {cap:.2f}（当前约 {baseline:.2f}，上限 {spillback_high:.2f}）"
                    )

            if intent in ("no_queue_growth", "no_worsen", "protect") and queue_m is not None:
                cap_q = round(queue_m * (1 + queue_margin), 1)
                constraints.append(
                    {
                        "metric": "avg_queue_m",
                        "scope": group,
                        "operator": "<=",
                        "value": cap_q,
                        "baseline": queue_m,
                        "threshold_ref": "queue.long_queue_m",
                    }
                )
                narratives.append(
                    f"{group}平均排队不超过 {cap_q}m（当前约 {queue_m}m）"
                )

            if intent == "saturation_cap" and saturation is not None:
                cap_s = round(min(saturation + sat_margin, 1.0), 3)
                constraints.append(
                    {
                        "metric": "saturation",
                        "scope": group,
                        "operator": "<=",
                        "value": cap_s,
                        "baseline": saturation,
                        "threshold_ref": "saturation.high",
                    }
                )
                narratives.append(f"{group}饱和度不超过 {cap_s:.2f}（当前约 {saturation:.2f}）")

        max_delta = self._extract_max_delta(text)
        if max_delta is not None:
            constraints.append(
                {
                    "metric": "delta_seconds",
                    "scope": "global",
                    "operator": "<=",
                    "value": max_delta,
                    "baseline": None,
                    "threshold_ref": None,
                }
            )
            narratives.append(f"绿灯调整幅度不超过 {max_delta} 秒")

        narrative = (
            f"已将「{text}」量化为：" + "；".join(narratives)
            if narratives
            else f"已记录用户约束「{text}」，将优先在建议文案中体现"
        )

        return {
            "raw_text": text,
            "intent": intent,
            "primary_directions": primary_groups,
            "protected_directions": protected_groups,
            "constraints": constraints,
            "narrative": narrative,
        }

    @staticmethod
    def apply_to_delta(
        delta_seconds: int,
        constraints: dict[str, Any] | None,
        *,
        problem_evidence: dict[str, Any] | None = None,
    ) -> tuple[int, str | None]:
        """Conservatively clip delta_seconds based on quantitative constraints."""
        if not constraints:
            return delta_seconds, None

        clipped = delta_seconds
        notes: list[str] = []
        by_direction = {
            item["group"]: item for item in (problem_evidence or {}).get("by_direction") or []
        }

        for item in constraints.get("constraints") or []:
            metric = item.get("metric")
            if metric == "delta_seconds":
                cap = int(item.get("value") or delta_seconds)
                if clipped > cap:
                    clipped = cap
                    notes.append(f"按用户约束将调整幅度限制为 {cap} 秒")
                continue

            if metric not in ("spillback_risk", "avg_queue_m", "saturation"):
                continue

            scope = str(item.get("scope") or "")
            baseline = _float(item.get("baseline"))
            cap_value = _float(item.get("value"))
            current = by_direction.get(scope, {})

            if metric == "spillback_risk" and baseline is not None:
                if baseline >= float(item.get("value") or 1) * 0.95:
                    reduction = max(1, int(delta_seconds * 0.3))
                    if clipped > reduction:
                        clipped = max(1, clipped - reduction)
                        notes.append(
                            f"{scope}已接近溢流阈值，保守缩减绿灯增幅至 {clipped} 秒"
                        )
            elif metric == "avg_queue_m" and baseline is not None:
                if baseline >= 80:
                    reduction = max(1, int(delta_seconds * 0.25))
                    if clipped > reduction:
                        clipped = max(1, clipped - reduction)
                        notes.append(
                            f"保护{scope}排队，将调整幅度收敛至 {clipped} 秒"
                        )
            elif metric == "saturation" and baseline is not None and cap_value is not None:
                if baseline >= cap_value * 0.9:
                    clipped = min(clipped, max(1, int(delta_seconds * 0.5)))
                    notes.append(f"{scope}饱和度偏高，建议谨慎调整")

        note = "；".join(notes) if notes else None
        return clipped, note

    @staticmethod
    def _detect_intent(text: str) -> str:
        lowered = text.lower()
        if any(token in text for token in ("溢出", "外溢", "溢流")):
            return "no_spillback"
        if any(token in text for token in ("排队加剧", "排队增加", "排队变长", "不能加剧")):
            return "no_queue_growth"
        if any(token in text for token in ("不影响", "保障", "优先")):
            return "saturation_cap"
        if "垂直" in text:
            return "no_spillback"
        if any(token in text for token in ("不能", "不要", "避免")):
            return "no_worsen"
        return "protect"

    @staticmethod
    def _protected_groups(
        text: str,
        primary_groups: list[str],
        intent: str,
    ) -> list[str]:
        if "垂直" in text or intent in ("no_spillback", "no_queue_growth", "no_worsen"):
            return protected_groups_for_vertical_constraint(primary_groups)
        explicit = re.findall(r"(东西向|南北向|东南向|西南向|东北向|西北向)", text)
        if explicit:
            return list(dict.fromkeys(explicit))
        return protected_groups_for_vertical_constraint(primary_groups)

    @staticmethod
    def _extract_max_delta(text: str) -> int | None:
        patterns = (
            r"(?:不超过|不能(?:超过|超)|不可超过|至多|最多)\s*(\d+)\s*秒",
            r"(\d+)\s*秒(?:以内|之内|内)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return int(match.group(1))
        return None


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
