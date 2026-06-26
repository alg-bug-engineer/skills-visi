---
name: intersection-plan-generation
description: 把策略指令转换为周期、绿信比、相位相序和下发护栏等方案草案。
metadata:
  skill_id: intersection_plan_generation
  display_name: 路口方案生成
  phase: plan_generation
  scenarios: [intersection]
  triggers: [strategy_ready, plan_ready]
  tool_names: [generate_timing_plan, generate_single_point_optimization_plan]
  version: "0.1.0"
  enabled: true
  reference_files: [references/rules.md]
  script_files:
    - scripts/calculate_phase_splits.py
    - scripts/generate_single_point_optimization.py
    - scripts/validate_plan_guardrails.py
---

# 路口方案生成

## 作用
把策略指令转换为周期、绿信比、相位相序和下发护栏等方案草案。

## 渐进式加载条件
- 阶段：`plan_generation`
- 场景：`intersection`
- 触发：`strategy_ready`, `plan_ready`

## 专家推理步骤
1. 先校验策略指令、最小绿、最大周期、清空时间、行人过街和设备能力边界。
2. 方案参数必须服务于策略目标；具备 `phasePlanOfTimeList` 或 `phaseStageInfoList` 时，由 `scripts/generate_single_point_optimization.py` 融合场景认知、诊断和策略后调用单点优化引擎生成周期与绿信比。
3. 输出计划编号、周期、相位绿信比、偏移策略、下发模式、回滚条件和参数说明。
4. 如数据不足，生成需要人工补充的方案草案，而不是直接下发建议。

## 输出约束
- 结论必须给出证据指标、适用边界和不确定性。
- 需要确定性计算或校验时，优先调用 `scripts/` 中的脚本能力。
- 详细规则见 [references/rules.md](references/rules.md)。
