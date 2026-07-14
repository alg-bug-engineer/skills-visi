---
name: data-analysis-diagnosis
description: 验证溢出是否成立，计算排队比、饱和度、绿灯利用率等核心指标。Use when phase is data_analysis_diagnosis.
metadata:
  skill_id: data_analysis_diagnosis
  display_name: 数据分析与诊断
  phase: data_analysis_diagnosis
  version: "0.1.0"
  enabled: true
  handler_class: DataAnalysisDiagnosisSkill
  script_files:
    - scripts/analyze_overflow.py
  reference_files:
    - references/rules.md
    - references/thresholds.md
  resource_files: {}
  execution_steps:
    - step_id: verify_overflow
      title: 溢出验证
      instruction: 计算排队比并结合饱和度、绿灯利用率验证溢出问题是否成立。
      script: scripts/analyze_overflow.py
      function: analyze_overflow
---

# 数据分析与诊断

## 作用

借鉴路口场景认知与流量溯源可视化契约，对目标路口、直接下游信控节点、上游来车进行同构指标分析。

## 核心指标

- 排队比 = 排队长度 / 进口道蓄车长度
- 排队比 ≥ 0.8：溢出预警；≥ 1.0：明确溢出风险
- 目标路口与下游信控节点输出同构 `metrics` / `by_turn`
- `downstream_trace`：目标进口左转/直行/右转的一跳去向、占比、承接能力（对齐 FlowTraceMap）；治理护栏仍以票据选中转向为准
- `flow_trace`：上游来源路径、entry_traces、governance_hints
- `arterial_analysis`：上游到达/放行、剩余空间、控流建议
- `downstream_diagnosis`：下游信控节点同构对比与放行判断
- `map_scenes`：前端地图可视化载荷
