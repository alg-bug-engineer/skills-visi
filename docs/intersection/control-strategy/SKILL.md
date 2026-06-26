---
name: intersection-control-strategy
description: 基于诊断结论生成可机读策略指令，不直接输出配时秒数。
metadata:
  skill_id: intersection_control_strategy
  display_name: 路口控制策略
  phase: control_strategy
  scenarios: [intersection]
  triggers: [oversaturation, excess_delay, spillback, green_wave_break, strategy_ready]
  tool_names: [recommend_control_strategy]
  version: "0.1.0"
  enabled: true
  reference_files: [references/rules.md]
  script_files:
    - scripts/validate_strategy_instruction.py
    - scripts/select_strategy_package.py
---

# 路口控制策略

## 作用
基于诊断结论生成可机读策略指令，不直接输出配时秒数。

## 渐进式加载条件
- 阶段：`control_strategy`
- 场景：`intersection`
- 触发：`oversaturation`, `excess_delay`, `spillback`, `green_wave_break`, `strategy_ready`

## 专家推理步骤
1. 按安全底线、防溢流防锁死、基本公平、效率、体验建立目标优先级。
2. 优先选择最小充分策略包，避免把局部问题升级为过度控制。
3. 输出 object_scope、problem_set、target_priority、strategy_package、hard_constraints、trigger_exit_rules、fallback_plan 和 explanation。
4. 高风险策略必须设置人工确认、触发退出规则、滞回和渐进恢复。

## 输出约束
- 结论必须给出证据指标、适用边界和不确定性。
- 需要确定性计算或校验时，优先调用 `scripts/` 中的脚本能力。
- 详细规则见 [references/rules.md](references/rules.md)。
