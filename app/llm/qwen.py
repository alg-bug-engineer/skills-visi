from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.config import Settings
from app.data.intersection_matcher import generate_name_variants

logger = logging.getLogger(__name__)


class QwenClient:
    """OpenAI-compatible Qwen API client with mock mode for tests."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_json: bool = True,
        trace_id: str | None = None,
    ) -> dict[str, Any] | str:
        if self.settings.llm_mock:
            return self._mock_response(system_prompt, user_prompt, response_json)

        if not self.settings.qwen_api_key:
            raise RuntimeError("QWEN_API_KEY 未配置，请设置 .env 或启用 LLM_MOCK=true")

        payload: dict[str, Any] = {
            "model": self.settings.qwen_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        if response_json:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.settings.qwen_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.settings.qwen_base_url.rstrip('/')}/chat/completions"

        logger.info(
            "调用 Qwen API model=%s trace_id=%s",
            self.settings.qwen_model,
            trace_id or "-",
        )
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        if response_json:
            return json.loads(content)
        return content

    def _mock_response(
        self,
        system_prompt: str,
        user_prompt: str,
        response_json: bool,
    ) -> dict[str, Any] | str:
        logger.info("LLM mock 模式，跳过真实 API 调用")
        if "意图理解" in system_prompt or "intent" in system_prompt.lower():
            return self._mock_intent(user_prompt)
        if "成因" in system_prompt or "cause" in system_prompt.lower():
            return self._mock_cause_analysis()
        if "策略" in system_prompt:
            return self._mock_strategy()
        if "方案" in system_prompt:
            return self._mock_plan()
        if response_json:
            return {"summary": "mock response", "source": "llm_mock"}
        return "mock response"

    def _mock_intent(self, user_prompt: str) -> dict[str, Any]:
        intersection = "文化西路与舜华路交叉口"
        match = re.search(r"([\u4e00-\u9fff]+路与[\u4e00-\u9fff]+路交叉口)", user_prompt)
        if match:
            intersection = match.group(1)

        time_range = "18:10-18:30"
        time_match = re.search(r"(\d{1,2}[:：]\d{2}).*?(\d{1,2}[:：]\d{2})", user_prompt)
        if time_match:
            time_range = f"{time_match.group(1).replace('：', ':')}-{time_match.group(2).replace('：', ':')}"
        elif "下午" in user_prompt and "3点" in user_prompt:
            time_range = "15:00-16:00"

        direction = "东向西"
        for d in ("东向西", "西向东", "南向北", "北向南"):
            if d in user_prompt:
                direction = d
                break

        problem_type = "排队溢出"
        if "拥堵" in user_prompt and "溢出" not in user_prompt:
            problem_type = "拥堵"

        user_experiences: list[dict[str, Any]] = []
        if re.search(r"(经常|时常).{0,12}(拥堵|排队|溢出)", user_prompt) or "下午" in user_prompt:
            user_experiences.append(
                {
                    "experience_type": "cognitive",
                    "content": f"{intersection}下午经常拥堵",
                    "source_span": user_prompt[:80],
                    "tags": {"problem_type": problem_type, "time_period": "下午时段"},
                }
            )
        if re.search(r"(学校|接送|放学|导致)", user_prompt):
            user_experiences.append(
                {
                    "experience_type": "diagnostic",
                    "content": "附近有学校放学家长接送导致拥堵",
                    "source_span": user_prompt[:120],
                    "tags": {
                        "cause_dimension": "event",
                        "cause_keywords": ["学校", "接送", "放学"],
                        "related_poi": ["学校"],
                    },
                }
            )
        if re.search(r"(应该|建议).{0,8}(加绿|绿灯)", user_prompt):
            user_experiences.append(
                {
                    "experience_type": "solution",
                    "content": "应该增加绿灯时间",
                    "source_span": user_prompt[-40:],
                    "tags": {"strategy_action": "加绿"},
                }
            )

        payload = {
            "object_type": "路口",
            "intersection_name": intersection,
            "intersection_name_candidates": generate_name_variants(intersection.replace("交叉口", "路口")),
            "time_range": time_range,
            "period": "晚高峰" if "18" in time_range else "下午时段",
            "direction": direction,
            "movement": "直行",
            "problem_type": problem_type,
            "constraints": ["优先避免下游继续外溢"] if "外溢" in user_prompt else [],
            "diagnosis_scope": ["目标路口", "上游来车", "下游承接", "干线协调"],
            "governance_goal": "控制溢出扩散，而不是单点清队",
            "user_experiences": user_experiences,
            "source": "llm_mock",
        }
        return payload

    def _mock_cause_analysis(self) -> dict[str, Any]:
        return {
            "primary_cause": "下游承接能力不足",
            "secondary_causes": ["东向西持续高需求", "上游来车集中释放"],
            "optimizable_points": ["绿信比分配存在小幅校正空间"],
            "data_gaps": ["事件干扰、临停占道、视频证据未完全确认"],
            "narrative": "当前问题更接近下游承接不足叠加上游来车冲击的干线传导型问题。",
            "source": "llm_mock",
        }

    def _mock_strategy(self) -> dict[str, Any]:
        return {
            "principles": [
                "防溢流优先",
                "下游保护",
                "上游控流",
                "小步释放",
                "相位差协调",
                "闭环监测",
            ],
            "not_recommended": ["单点激进加绿"],
            "recommended": ["下游保护约束下的小步释放", "上游控流 + 干线协调"],
            "explanation": "下游接不住时不宜单点加绿，应采用干线联控策略。",
            "source": "llm_mock",
        }

    def _mock_plan(self) -> dict[str, Any]:
        return {
            "recommended_plan_id": "arterial_coordination",
            "rationale": "具备下游承接不足+上游来车冲击+目标进口接近溢出的组合特征",
            "source": "llm_mock",
        }
