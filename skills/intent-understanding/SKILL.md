---
name: intent-understanding
description: 将用户自然语言描述解析为结构化诊断工单。Use when phase is intent_understanding.
metadata:
  skill_id: intent_understanding
  display_name: 意图理解
  phase: intent_understanding
  version: "0.1.0"
  enabled: true
  handler_class: IntentUnderstandingSkill
  script_files:
    - scripts/build_spatial_objects.py
  reference_files:
    - references/rules.md
    - references/output_schema.md
  resource_files:
    system: resources/prompts/system.txt
  execution_steps:
    - step_id: parse_intent
      title: 解析用户意图
      instruction: 调用 LLM 将自然语言拆解为诊断工单字段。
      script: scripts/build_spatial_objects.py
      function: build_spatial_objects
---

# 意图理解

## 作用

将用户口头描述整理为结构化诊断工单，识别对象、路口、时间、方向、问题类型与治理约束。

## 输出约束

- 必须输出 `diagnosis_ticket` 与 `spatial_objects`
- 不得在此阶段输出指标计算或治理方案
