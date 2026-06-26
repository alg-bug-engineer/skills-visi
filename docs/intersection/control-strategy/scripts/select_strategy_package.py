from __future__ import annotations


def select_strategy_package(priority_order: list[str]) -> str:
    if "spillback" in priority_order:
        return "结构性防溢流"
    if "oversaturation" in priority_order:
        return "失衡纠偏"
    if "empty_green" in priority_order:
        return "空放削减"
    return "常态微调"
