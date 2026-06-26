"""YAML-based deterministic rule engine."""

from __future__ import annotations

import logging
from typing import Any

import yaml
from simpleeval import simple_eval

from intersection_agent.config import Settings, get_settings
from intersection_agent.models.domain import DiagnosisResult
from intersection_agent.utils.thresholds_loader import load_thresholds

logger = logging.getLogger(__name__)

OPERATORS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "contains": lambda a, b: b in str(a) if a is not None else False,
}


class RuleEngine:
    """Evaluate traffic rules from YAML configuration."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._rules: list[dict[str, Any]] = []
        self._thresholds: dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load rules and thresholds from YAML files."""
        rules_path = self._settings.rules_dir / "traffic_rules.yaml"
        with open(rules_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        self._rules = config.get("rules", [])
        self._thresholds = load_thresholds()

    def diagnose(self, data: dict[str, Any], problem_type: str) -> DiagnosisResult:
        """Run rules filtered by problem_type and return diagnosis."""
        if data.get("meta", {}).get("missing_dws_coverage"):
            return DiagnosisResult(
                diagnosed=False,
                reason_code="missing_dws_coverage",
                metrics_snapshot=self._snapshot(data),
            )

        matched: list[dict[str, Any]] = []
        for rule in self._rules:
            if rule.get("problem_type") != problem_type:
                continue
            if self._evaluate_rule(rule, data):
                matched.append(rule)

        matched.sort(key=lambda r: r.get("priority", 100))

        if not matched:
            return DiagnosisResult(
                diagnosed=False,
                reason_code="no_rule_matched",
                metrics_snapshot=self._snapshot(data),
            )

        top = matched[0]
        ceiling = top.get("control_ceiling")
        return DiagnosisResult(
            diagnosed=True,
            matched_rules=matched,
            control_ceiling=ceiling,
            metrics_snapshot=self._snapshot(data),
        )

    def diagnose_comprehensive(self, data: dict[str, Any]) -> DiagnosisResult:
        """Evaluate all rules across problem types, sorted by priority."""
        if data.get("meta", {}).get("missing_dws_coverage"):
            return DiagnosisResult(
                diagnosed=False,
                reason_code="missing_dws_coverage",
                metrics_snapshot=self._snapshot(data),
            )

        matched: list[dict[str, Any]] = []
        for rule in self._rules:
            if self._evaluate_rule(rule, data):
                matched.append(rule)

        matched.sort(key=lambda r: r.get("priority", 100))

        if not matched:
            return DiagnosisResult(
                diagnosed=False,
                reason_code="no_rule_matched",
                metrics_snapshot=self._snapshot(data),
            )

        top = matched[0]
        return DiagnosisResult(
            diagnosed=True,
            matched_rules=matched,
            control_ceiling=top.get("control_ceiling"),
            metrics_snapshot=self._snapshot(data),
        )

    def diagnose_focused(
        self,
        categories: list[str],
        data: dict[str, Any],
    ) -> DiagnosisResult:
        """Evaluate rules tagged with focus_category in the given set."""
        if data.get("meta", {}).get("missing_dws_coverage"):
            return DiagnosisResult(
                diagnosed=False,
                reason_code="missing_dws_coverage",
                metrics_snapshot=self._snapshot(data),
            )

        allowed = set(categories)
        matched: list[dict[str, Any]] = []
        for rule in self._rules:
            if rule.get("focus_category") not in allowed:
                continue
            if self._evaluate_rule(rule, data):
                matched.append(rule)

        matched.sort(key=lambda r: r.get("priority", 100))

        if not matched:
            return DiagnosisResult(
                diagnosed=False,
                reason_code="no_rule_matched",
                metrics_snapshot=self._snapshot(data),
            )

        top = matched[0]
        return DiagnosisResult(
            diagnosed=True,
            matched_rules=matched,
            control_ceiling=top.get("control_ceiling"),
            metrics_snapshot=self._snapshot(data),
        )

    def _evaluate_rule(self, rule: dict[str, Any], data: dict[str, Any]) -> bool:
        """Evaluate all conditions for a rule."""
        results = [self._eval_condition(c, data) for c in rule.get("conditions", [])]
        if not results:
            return False
        logic = rule.get("logic", "AND")
        if logic == "OR":
            return any(results)
        return all(results)

    def _eval_condition(self, cond: dict[str, Any], data: dict[str, Any]) -> bool:
        """Evaluate single condition."""
        value = resolve_metric(cond["metric"], data)
        if value is None:
            return False
        op = cond["operator"]
        threshold = cond.get("threshold")
        if threshold is None and cond.get("threshold_ref"):
            threshold = resolve_threshold(cond["threshold_ref"], self._thresholds)
        if threshold is None:
            threshold = cond.get("value")
        fn = OPERATORS.get(op)
        if fn is None:
            return False
        try:
            return bool(fn(value, threshold))
        except TypeError:
            return False

    @staticmethod
    def _snapshot(data: dict[str, Any]) -> dict[str, Any]:
        """Extract key metrics for response."""
        gran = data.get("granularity", {})
        approaches = gran.get("by_approach") or []
        timing = data.get("timing", {})
        corridor = data.get("corridor", {})
        external = data.get("external_evidence", {})
        return {
            "saturation_rate": data.get("traffic_flow", {}).get("saturation_rate"),
            "delay_index": data.get("evaluation", {}).get("delay_index"),
            "green_ratio": data.get("signal_plan", {}).get("green_ratio"),
            "imbalance_index": data.get("evaluation", {}).get("imbalance_index"),
            "level_of_service": data.get("evaluation", {}).get("level_of_service"),
            "turn_saturation_spread": data.get("traffic_flow", {}).get("turn_saturation_spread"),
            "green_deficit_ratio_max": timing.get("green_deficit_ratio_max"),
            "in_corridor": corridor.get("in_corridor"),
            "complaint_total": external.get("complaint_total"),
            "matched_rule_count": None,
        }


def resolve_metric(path: str, data: dict[str, Any]) -> Any:
    """Resolve dotted metric path from nested data dict."""
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def resolve_threshold(ref: str, thresholds: dict[str, Any]) -> Any:
    """Resolve threshold reference like saturation.high."""
    current: Any = thresholds
    for part in ref.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def evaluate_formula(formula: str, data: dict[str, Any]) -> int:
    """Safely evaluate action formula with simpleeval."""
    names = {
        "traffic_flow": data.get("traffic_flow", {}),
        "signal_plan": data.get("signal_plan", {}),
        "evaluation": data.get("evaluation", {}),
    }
    result = simple_eval(formula, names=names, functions={"min": min, "max": max})
    return int(round(float(result)))
