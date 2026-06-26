---
name: intersection-evaluation-feedback
description: 评估路口方案效果、执行稳定性和问题改善，并沉淀闭环样本。
metadata:
  skill_id: intersection_evaluation_feedback
  display_name: 路口评价反馈
  phase: evaluation_feedback
  scenarios: [intersection]
  triggers: [plan_ready, evaluation_window, needs_iteration]
  tool_names: [evaluate_signal_plan]
  version: "0.1.0"
  enabled: true
  reference_files: [references/rules.md]
  script_files:
    - scripts/compare_kpis.py
    - scripts/decide_iteration.py
---

# 路口评价反馈

## 作用
评估路口方案效果、执行稳定性和问题改善，并沉淀闭环样本。

## 渐进式加载条件
- 阶段：`evaluation_feedback`
- 场景：`intersection`
- 触发：`plan_ready`, `evaluation_window`, `needs_iteration`

## 专家推理步骤
1. 按同口径比较优化前后延误、排队、停车、绿灯利用率、溢流风险和执行一致率。
2. 评价未达标时，说明应回流到认知、诊断、策略还是方案生成环节。
3. 输出 learning_notes，用于沉淀场景-问题-策略-方案-效果-评分-审核样本。
4. 多轮无效或风险恶化时触发人工复核和回滚建议。

## 输出约束
- 结论必须给出证据指标、适用边界和不确定性。
- 需要确定性计算或校验时，优先调用 `scripts/` 中的脚本能力。
- 详细规则见 [references/rules.md](references/rules.md)。
