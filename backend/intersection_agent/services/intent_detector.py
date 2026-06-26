"""User intent detection for skill confirmation."""

from __future__ import annotations

NEGATIVE_WORDS = ("否", "不是", "不要", "不用", "取消", "算了", "不固化", "不需要", "不对")
CONFIRM_WORDS = {"是", "可以", "确认", "好", "行", "ok", "yes", "好的", "嗯", "对的"}


def detect_confirmation_intent(text: str) -> str | None:
    """Detect confirm/deny intent from short user reply.

    Args:
        text: User message.

    Returns:
        'confirm', 'deny', or None if ambiguous.
    """
    normalized = text.strip().lower()
    if not normalized:
        return None

    # Negative first — avoids "不是" triggering confirm via substring "是"
    for word in NEGATIVE_WORDS:
        if word in text:
            return "deny"

    if normalized in CONFIRM_WORDS:
        return "confirm"

    for word in CONFIRM_WORDS:
        if word == normalized or (word in normalized and len(normalized) <= 8):
            return "confirm"

    return None
