"""Qwen LLM client via DashScope OpenAI-compatible API."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from intersection_agent.config import Settings, get_settings
from intersection_agent.logging.helpers import log_event, safe_preview

logger = logging.getLogger(__name__)


def _dashscope_error_message(response: httpx.Response) -> str | None:
    """Extract user-facing message from DashScope error body."""
    try:
        body = response.json()
    except json.JSONDecodeError:
        return None
    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict):
        return None
    code = str(err.get("code") or err.get("type") or "")
    message = str(err.get("message") or "").strip()
    if code == "Arrearage":
        return "百炼账户欠费或停服，请登录阿里云控制台充值后再试。"
    if message:
        return f"百炼 API 错误 ({code or response.status_code}): {message}"
    return None


class QwenClient:
    """Async client for Qwen chat completions."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        """Send chat completion and return assistant text.

        Args:
            system: System prompt.
            user: User message.
            temperature: Sampling temperature.
            json_mode: Use DashScope JSON Object mode (requires "JSON" in messages).

        Returns:
            Assistant message content.

        Raises:
            RuntimeError: If API call fails or mock is disabled without key.
        """
        if self._settings.mock_llm:
            log_event(logger, logging.DEBUG, "llm.mock", json_mode=json_mode)
            return self._mock_response(system, user)

        if not self._settings.dashscope_api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is not configured")

        if json_mode and "json" not in (system + user).lower():
            system = f"{system}\n请严格以 JSON 格式输出。"

        log_event(
            logger,
            logging.INFO,
            "llm.request",
            model=self._settings.qwen_model,
            json_mode=json_mode,
            user_preview=safe_preview(user, 200),
        )

        url = f"{self._settings.dashscope_base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": self._settings.qwen_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        payload["enable_thinking"] = False
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self._settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }

        client_kwargs: dict[str, Any] = {
            "timeout": self._settings.llm_timeout_s,
            "trust_env": False,
        }
        if self._settings.llm_http_proxy:
            client_kwargs["proxy"] = self._settings.llm_http_proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
            except httpx.ConnectError as exc:
                hint = ""
                if not self._settings.llm_http_proxy:
                    hint = "（若本机 Clash TUN 劫持 DNS，可在 .env 设置 LLM_HTTP_PROXY=http://127.0.0.1:7897）"
                raise RuntimeError(f"无法连接百炼 API{hint}") from exc
            if response.status_code >= 400:
                api_message = _dashscope_error_message(response)
                log_event(
                    logger,
                    logging.ERROR,
                    "llm.error",
                    status=response.status_code,
                    body=safe_preview(response.text, 400),
                )
                if api_message:
                    raise RuntimeError(api_message)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        log_event(
            logger,
            logging.INFO,
            "llm.response",
            json_mode=json_mode,
            output_len=len(content),
            total_tokens=usage.get("total_tokens"),
            preview=safe_preview(content, 300),
        )
        return content.strip()

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        max_retries: int = 2,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Chat with JSON mode and parse response; retry with repair on failure."""
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                text = await self.chat(
                    system=system,
                    user=user,
                    json_mode=True,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return self._extract_json(text)
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning("NLU JSON parse failed attempt=%d: %s", attempt + 1, exc)
                if attempt < max_retries:
                    user = (
                        f"{user}\n\n上次输出无法解析，请仅返回符合字段规范的 JSON 对象，"
                        "不要 markdown 代码块。"
                    )
        if last_error:
            raise last_error
        raise ValueError("Failed to obtain JSON from model")

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Extract JSON object from model output."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
        raise ValueError(f"Failed to parse JSON from LLM output: {text[:200]}")

    def _mock_response(self, system: str, user: str) -> str:
        """Deterministic mock for offline tests."""
        if "首轮意图分类器" in system:
            return self._mock_intent_classifier_json(user)

        if "交通经验抽取器" in system:
            return self._mock_experience_extract(user)

        if "只输出 JSON" in system or "必须严格使用以下字段名" in system:
            if "干线拥堵扫描" in system or '"corridor"' in system:
                return self._mock_corridor_scan_json(user)
            result: dict[str, Any] = {
                "intersection": None,
                "time_period": None,
                "problem_types": self._mock_problem_types(user),
                "directions": [],
                "user_suggestion": None,
            }
            if "奥体" in user or "经十" in user:
                result["intersection"] = "奥体西路与经十路交叉口"
            if "低饱和" in user:
                result["intersection"] = "低饱和测试路口交叉口"
            if "四点" in user or "16" in user or "晚高峰" in user or "下午" in user:
                result["time_period"] = {
                    "start": "16:00",
                    "end": "18:00",
                    "label": "晚高峰",
                }
            if "早高峰" in user or "早上" in user or "七点" in user:
                result["time_period"] = {
                    "start": "07:00",
                    "end": "09:00",
                    "label": "早高峰",
                }
            if (
                "平峰" in user
                or "十点" in user
                or "十一点" in user
                or "上午十" in user
            ):
                result["time_period"] = {
                    "start": "10:00",
                    "end": "11:00",
                    "label": "平峰",
                }
            explicit_suggestion_tokens = (
                "绿灯延长",
                "绿灯应",
                "绿灯应该",
                "应该绿灯",
                "不超过",
                "建议",
                "优先",
                "考虑",
                "不能",
                "避免",
                "溢出",
            )
            if any(token in user for token in explicit_suggestion_tokens):
                if "垂直方向不能溢出" in user:
                    result["user_suggestion"] = "要考虑垂直方向不能溢出"
                elif "不超过" in user and "秒" in user:
                    result["user_suggestion"] = "绿灯不超过10秒"
                else:
                    result["user_suggestion"] = "绿灯延长"
            if "南北" in user:
                result["directions"] = ["南北向"]
            if "东西" in user and "东西路" not in user:
                result["directions"] = ["东西向"]
            if "只有路口" in user:
                result["intersection"] = "测试路口A与测试路B交叉口"
                result["time_period"] = None
            if "缺少时段" in user:
                result["intersection"] = "奥体西路与经十路交叉口"
                result["time_period"] = None
            return json.dumps(result, ensure_ascii=False)

        if "路口名称变体" in system or "规范化" in system:
            return json.dumps(
                {
                    "variants": [
                        "奥体西路与经十路交叉口",
                        "经十路与奥体西路交叉口",
                    ]
                },
                ensure_ascii=False,
            )

        if (
            "治理建议" in system
            or "诊断结果" in system
            or "治理建议" in user
            or "诊断结果" in user
        ):
            if "用户约束或建议：" in user and "无" not in user.split("用户约束或建议：", 1)[1][:4]:
                constraint = user.split("用户约束或建议：", 1)[1].splitlines()[0].strip()
                return (
                    "根据运行数据，建议适当增加主方向绿灯时长，"
                    f"同时重点考虑{constraint}，避免造成次要方向排队外溢。"
                )
            return "根据运行数据，建议适当增加主方向绿灯时长，缓解晚高峰排队。"

        if "引导" in system or "追问" in system or "交通智能体" in system:
            return self._mock_follow_up(user)

        if "经验吸收追踪日志" in system or "experience_points" in user:
            from intersection_agent.skills.absorption_narrative_service import (
                mock_narrative_from_facts,
            )

            facts = json.loads(user)
            return json.dumps(mock_narrative_from_facts(facts), ensure_ascii=False)

        return "好的。"

    @staticmethod
    def _mock_problem_types(user: str) -> list[str]:
        """Keyword-based four-class classification for offline NLU tests."""
        ptypes: list[str] = []
        if "堵" in user or "拥堵" in user:
            ptypes.append("congestion")
        if "溢出" in user:
            ptypes.append("spillback")
        if "空放" in user:
            ptypes.append("empty_green")
        if "冲突" in user or "相位" in user or "相序" in user:
            ptypes.append("conflict")
        return ptypes or ["congestion"]

    @staticmethod
    def _mock_experience_extract(user: str) -> str:
        """关键词 mock：定性反馈 → 结构化经验条目。"""
        polarity = "none"
        if "绿灯" in user and any(t in user for t in ("多", "增", "延长", "再给", "更长")):
            polarity = "increase_green"
        elif "绿灯" in user and any(t in user for t in ("太长", "缩短", "减少", "少给", "压缩")):
            polarity = "decrease_green"
        elif any(t in user for t in ("均衡", "分配", "让给", "协调")):
            polarity = "rebalance"
        dimension = "signal_timing" if "绿灯" in user else "control"
        return json.dumps(
            {
                "dimension": dimension,
                "polarity": polarity,
                "target_turn": None,
                "raw": user,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _mock_intent_classifier_json(user: str) -> str:
        from intersection_agent.services.intent_router import route_intent_by_rules

        intent = route_intent_by_rules(user)
        return json.dumps(
            {
                "intent": intent,
                "confidence": "high",
                "reason": "mock 与规则一致",
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _mock_corridor_scan_json(user: str) -> str:
        result: dict[str, Any] = {
            "corridor": None,
            "time_period": None,
            "problem_type": "congestion",
        }
        if "奥体" in user:
            result["corridor"] = "奥体西路"
        if "晚高峰" in user or "四点" in user or "下午" in user:
            result["time_period"] = {
                "start": "16:00",
                "end": "18:00",
                "label": "晚高峰",
            }
        if "早高峰" in user or "早上" in user or "七点" in user:
            result["time_period"] = {
                "start": "07:00",
                "end": "09:00",
                "label": "早高峰",
            }
        if ("最拥堵" in user or "最堵" in user) and "晚高峰" not in user and "早高峰" not in user:
            if "奥体" in user:
                result["corridor"] = "奥体西路"
            result["time_period"] = None
        return json.dumps(result, ensure_ascii=False)

    @staticmethod
    def _mock_follow_up(user: str) -> str:
        """Context-aware mock follow-up for offline tests."""
        if "【对话历史】" in user:
            history = user.split("【对话历史】")[1].split("【")[0].strip()
        else:
            history = user
        greeting = history.strip() in ("你好", "您好", "hi", "hello", "嗨")
        if greeting or (len(history) < 8 and "路口" not in history):
            return (
                "您好！我是交通智能体，专门做路口拥堵诊断。"
                "请先告诉我具体是哪个路口，以及拥堵一般在什么时段出现。"
            )
        if "本轮需引导补充】intersection" in user:
            return "好的，请先告诉我具体是哪个路口？"
        if "本轮需引导补充】time_period" in user:
            return "了解。这个路口一般在什么时段拥堵比较明显，比如晚高峰或下午四五点？"
        if "本轮需引导补充】directions" in user:
            return "拥堵主要集中在哪个方向？例如东西向或南北向。"
        if "干线扫描" in user or "本轮需补充】time_period" in user:
            return "请问您关心哪个时段？早高峰、晚高峰还是平峰？"
        if "候选路口" in user or "系统候选" in user:
            return "这几个路口里，您说的是哪一个？直接回复完整路口名即可。"
        if "未找到" in user or "暂无运行数据" in user:
            return "抱歉，系统里暂时没有这个路口的数据，麻烦您再核对一下路口名称。"
        if "Skill" in user or "固化" in user:
            return "如果您认可这份诊断，回复「是」即可固化；不需要的话回复「否」。"
        return "请再补充一些信息，方便我继续分析。"
