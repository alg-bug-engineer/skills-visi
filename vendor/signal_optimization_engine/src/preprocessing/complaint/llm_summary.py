"""核心问题描述：优先 LLM，失败则规则摘要。"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request


def summarize_core_problem(
    *,
    inter_name: str,
    complaint_type: str,
    source_texts: list[str],
    complaint_count: int,
) -> str:
    merged = "\n".join(t.strip() for t in source_texts if t and t.strip())
    if not merged:
        return f"{inter_name}反映{complaint_type}相关诉求约{complaint_count}件。"
    llm = _summarize_via_llm(inter_name, complaint_type, merged, complaint_count)
    if llm:
        return llm[:512]
    return _summarize_fallback(inter_name, complaint_type, merged, complaint_count)


def _summarize_via_llm(
    inter_name: str,
    complaint_type: str,
    merged: str,
    complaint_count: int,
) -> str | None:
    api_base = (os.getenv("LLM_API_BASE") or "").rstrip("/")
    api_key = os.getenv("LLM_API_KEY") or ""
    if not api_base or not api_key:
        return None
    prompt = (
        f"路口：{inter_name}\n"
        f"投诉类型：{complaint_type}\n"
        f"投诉条数：{complaint_count}\n"
        f"原始描述：{merged[:1200]}\n\n"
        "请用1-2句话提炼该路口在此投诉类型下的核心问题，聚焦信号配时/相位/车道等可优化点，"
        "不超过120字，不要列举件数，直接输出结论。"
    )
    payload = {
        "model": os.getenv("LLM_MODEL", "qwen-plus"),
        "messages": [
            {"role": "system", "content": "你是交通信号优化专家，输出简洁中文。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 200,
    }
    req = urllib.request.Request(
        f"{api_base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"].strip()
        content = re.sub(r"\s+", " ", content)
        return content or None
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError):
        return None


def _summarize_fallback(
    inter_name: str,
    complaint_type: str,
    merged: str,
    complaint_count: int,
) -> str:
    snippet = merged.replace("；", "，").replace(";", "，")
    snippet = re.sub(r"（约\s*\d+\s*件）", "", snippet)
    snippet = re.sub(r"\s+", "", snippet)
    if len(snippet) > 160:
        snippet = snippet[:160].rstrip("，。；") + "…"
    return f"{inter_name}主要反映{complaint_type}：{snippet}"
