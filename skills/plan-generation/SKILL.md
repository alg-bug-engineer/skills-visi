---
name: plan-generation
description: 将策略转为可执行配时方案草案。Use when phase is plan_generation.
metadata:
  skill_id: plan_generation
  display_name: 方案生成
  phase: plan_generation
  version: "0.1.0"
  enabled: true
  handler_class: PlanGenerationSkill
  script_files:
    - scripts/build_candidates.py
  reference_files:
    - references/rules.md
    - references/rollback_conditions.md
  resource_files:
    system: resources/prompts/system.txt
  execution_steps:
    - step_id: build_candidates
      title: 生成候选方案
      script: scripts/build_candidates.py
      function: build_plan_candidates
    - step_id: recommend_plan
      title: 推荐方案
      instruction: 结合策略与 LLM 输出推荐结论与回滚条件。
---

# 方案生成

## 作用

将策略转换为多个可执行配时方案草案，给出推荐方案、风险边界与回滚条件。

## 输出约束

- 方案必须包含周期、绿灯、上游控流、相位差等可执行参数
- 必须给出回滚条件
