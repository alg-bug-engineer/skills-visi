# BUG-009：周期护栏可被引擎上限旁路 / 缺约束静默通过

- **状态**：已修复
- **发现日期**：2026-07-13
- **关联需求**：`needs/34-live指标绑定与配时护栏一致性修复.md`（E7）

## 现象

线案例候选 `cycle_s=190`，策略硬约束 180，但 `guardrail_pass=true` 且 `completed=true`。

## 根因

1. `validate_plan_guardrails` 在 `engine_max >= cycle` 时忽略产品 `max_cycle_s`。
2. `max_cycle_s` 缺失时周期检查直接跳过。
3. 策略 `quantitative_constraints.max_cycle_s` 未并入方案护栏约束。

## 修复

- 删除 engine_max 旁路；缺 `max_cycle_s` 视为护栏失败。
- 方案生成合并策略定量上限（取更严值）。
- 无可行候选时 `recommended_plan_id=null` 且 skill `success=false`。
