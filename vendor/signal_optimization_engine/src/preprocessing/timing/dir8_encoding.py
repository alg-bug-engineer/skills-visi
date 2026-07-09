"""8 方位方向编码（统一 0 基：北=0 .. 西北=7）。

工程内 dir8_no / dir8No / f_dir8_no / dir8Code（渠化 API）均使用同一套 0 基编码。
"""

from __future__ import annotations

from typing import Any

DIR8_NO_MIN = 0
DIR8_NO_MAX = 7

DIR8_LABELS: dict[int, str] = {
    0: "北",
    1: "东北",
    2: "东",
    3: "东南",
    4: "南",
    5: "西南",
    6: "西",
    7: "西北",
}

DIR8_NO_TO_CN = {value: key for key, value in DIR8_LABELS.items()}

DIR_CN_TO_DIR8_NO: dict[str, int] = dict(DIR8_NO_TO_CN)

DIR4_LABELS: dict[int, str] = {0: "北", 1: "东", 2: "南", 3: "西"}


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def is_valid_dir8_no(value: int | None) -> bool:
    return value is not None and DIR8_NO_MIN <= value <= DIR8_NO_MAX


def dir4_code_from_dir8_no(dir8_no: int | None) -> int | None:
    if not is_valid_dir8_no(dir8_no):
        return None
    return dir8_no // 2


def dir8_label(dir8_no: int | None) -> str:
    if dir8_no is None:
        return ""
    return DIR8_LABELS.get(dir8_no, str(dir8_no))


_DIR8_CN_BY_LENGTH = tuple(sorted(DIR_CN_TO_DIR8_NO, key=len, reverse=True))


def dir8_no_from_cn_text(text: Any) -> int | None:
    """从中文方向前缀（signal_atom / f_dir8_name）解析 0 基 dir8_no。"""
    raw = str(text or "").strip()
    if not raw:
        return None
    for name in _DIR8_CN_BY_LENGTH:
        if raw.startswith(name):
            return DIR_CN_TO_DIR8_NO[name]
    return None


def dir8_no_from_flow_combo_item(item: dict[str, Any]) -> int | None:
    """从 flow_combo 单条记录解析 0 基 dir8_no。

    优先 f_dir8_name / signal_atom（与 stage_name 同源），最后才回退 f_dir8_no，
    避免存量库把 dir4 或错误迁移值写进 f_dir8_no 字段。
    """
    if not isinstance(item, dict):
        return None
    name = str(item.get("f_dir8_name") or item.get("f_dir8Name") or "").strip()
    if name in DIR_CN_TO_DIR8_NO:
        return DIR_CN_TO_DIR8_NO[name]
    atom = str(item.get("signal_atom") or item.get("signalAtom") or "").strip()
    from_atom = dir8_no_from_cn_text(atom)
    if from_atom is not None:
        return from_atom
    return normalize_dir8_no(item.get("f_dir8_no"))


def repair_flow_combo_item(item: dict[str, Any]) -> bool:
    """按中文方向名修正 flow_combo 条目的 f_dir8_no / f_dir8_name。有变更返回 True。"""
    resolved = dir8_no_from_flow_combo_item(item)
    if resolved is None:
        return False
    old = _to_int(item.get("f_dir8_no"))
    label = dir8_label(resolved)
    changed = old != resolved or str(item.get("f_dir8_name") or "") != label
    if not changed:
        return False
    item["f_dir8_no"] = resolved
    if label:
        item["f_dir8_name"] = label
    return True


def normalize_dir8_no(value: Any, *, allow_legacy_one_based: bool = False) -> int | None:
    """归一化为 0 基 dir8_no。

    默认按工程内 0 基口径解析。
    ``allow_legacy_one_based=True`` 兼容尚未回退的 1 基存量（1..8 → 0..7）。
    """
    raw = _to_int(value)
    if raw is None:
        return None
    if is_valid_dir8_no(raw):
        return raw
    if allow_legacy_one_based and 1 <= raw <= 8:
        bumped = raw - 1
        return bumped if is_valid_dir8_no(bumped) else None
    return None
