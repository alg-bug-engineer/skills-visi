# 方案生成规则

## 输入

- `inter_id` / 诊断工单中的路口标识
- `task.signal`：现状周期、`phase_stage_timing_list`、各阶段最小/最大绿
- `task.constraints.max_cycle_s`：周期上限
- `target_periods`：来自诊断工单时段

## 优化口径

轻量确定性调整：在现状配时基础上按策略包小步调整目标相位绿信比，从低利用率相位借绿；后续可切换至原工程 SLSQP 优化器。

## 护栏

- 周期不得超过 `constraints.max_cycle_s`
- 阶段绿灯不得小于 `minGreenTime`，不得大于 `maxGreenTime`
- 必须提供 `rollback_condition`
- 未通过 `validate_plan_guardrails` 的方案标记为 `rejected`，不得作为推荐方案

## 候选方案

1. 下游保护方案
2. 目标路口小步释放方案
3. 干线联控方案

## 推荐原则

选择最符合问题结构、通过护栏且风险最可控的方案，而非最激进方案。
