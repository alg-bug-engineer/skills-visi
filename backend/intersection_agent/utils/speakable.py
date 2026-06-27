"""Normalize text for Qwen-TTS Realtime voice cues."""

from __future__ import annotations

import re

_MAX_CHARS = 280


def speak_decimal(value: float, *, as_percent: bool = False) -> str:
    """Convert a number to Chinese speech-friendly form."""
    if as_percent:
        pct = round(value * 100)
        return f"百分之{pct}"
    rounded = round(value, 2)
    text = f"{rounded:.2f}".rstrip("0").rstrip(".")
    parts = text.split(".")
    whole = _digits_to_zh(parts[0])
    if len(parts) == 1:
        return whole
    frac = "".join(_digit_char(d) for d in parts[1])
    return f"{whole}点{frac}"


def _digit_char(d: str) -> str:
    mapping = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}
    return mapping.get(d, d)


def _digits_to_zh(num: str) -> str:
    if num == "0":
        return "零"
    try:
        n = int(num)
    except ValueError:
        return num
    if n < 10:
        return _digit_char(str(n))
    if n < 100:
        tens, ones = divmod(n, 10)
        if tens == 1:
            head = "十"
        else:
            head = f"{_digit_char(str(tens))}十"
        return head if ones == 0 else f"{head}{_digit_char(str(ones))}"
    return str(n)


def to_speakable(text: str) -> str:
    """Strip UI/markdown noise for TTS."""
    cleaned = text.replace(">", "").replace("·", "，").replace("\n", "，")
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"[【】\[\]()（）]", "", cleaned)
    return cleaned.strip("，。； ")


def truncate_speakable(text: str, limit: int = _MAX_CHARS) -> str:
    """Hard cap for Qwen-TTS input length."""
    body = to_speakable(text)
    if len(body) <= limit:
        return body
    return body[: limit - 1] + "…"
