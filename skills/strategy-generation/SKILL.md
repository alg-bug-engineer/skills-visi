---
name: strategy-generation
description: 从单点加绿升级为干线联控的治理策略原则。Use when phase is strategy_generation.
metadata:
  skill_id: strategy_generation
  display_name: 策略生成
  phase: strategy_generation
  version: "0.1.0"
  enabled: true
  handler_class: StrategyGenerationSkill
  script_files:
    - scripts/select_package.py
  reference_files:
    - references/rules.md
    - references/strategy_packages.md
  resource_files:
    system: resources/prompts/system.txt
  execution_steps:
    - step_id: select_package
      title: 选择策略包
      script: scripts/select_package.py
      function: select_strategy_package
    - step_id: summarize_strategy
      title: 生成策略原则
      instruction: 由 LLM 输出治理原则，不输出具体秒数。
---

# 策略生成

## 作用

将成因结论转换为可审签的治理策略原则，明确推荐与不推荐策略及案例依据。

## 输出约束

- 不输出具体配时秒数
- 必须说明为何不推荐单点激进加绿（当下游接不住时）
