---
name: intersection-problem-diagnosis
description: 区分静态短板与动态信控问题，按检查单对失衡、空放、溢流、相位渠化不匹配等问题排序并输出成因评分。Use when phase is problem_diagnosis.
metadata:
  skill_id: intersection_problem_diagnosis
  display_name: 路口问题诊断
  phase: problem_diagnosis
  scenarios: [intersection]
  triggers: [always, pressure_medium, pressure_high, spillback, empty_green]
  tool_names: [diagnose_signal_issues]
  version: "0.2.1"
  enabled: true
  reference_files:
    - ../../common/路口专家经验规则.md
    - ../../common/专家经验调试/路口交通问题诊断方法.md
    - ../../common/专家经验调试/交通路口问题诊断与指标解读报告模板.json
    - ../scene-cognition/references/data_dictionary.md
    - references/rules.md
    - references/checklist_rules.md
    - ../../common/thresholds.yaml
    - ../../common/diagnosis_checklist.yaml
    - ../../common/scene_type_rules.yaml
  script_files:
    - scripts/check_static_constraints.py
    - scripts/diagnosis_static_logic.py
    - scripts/score_intersection_issues.py
    - scripts/run_diagnosis_checklist.py
    - scripts/classify_diagnosis_context.py
    - scripts/summarize_diagnosis.py
    - scripts/validate_diagnosis_output.py
  execution_steps:
    - step_id: consume_scene_cognition_profile
      title: 承接场景认知画像
      instruction: 从上游 scene_cognition 结果读取 supply_profile、demand_profile、traffic_state、control_profile、congestion_profile、context_tags、quality_tags、evidence_chain；不得把 scenario_report.scenarioSummary 重新作为诊断章节输出。缺少字段时先按 data_dictionary 与 checklist_rules 回查可补采数据，仍不可得则写入 uncertainty 与 data_source_gaps。
      output_hint: profile, evidence_chain, data_source_gaps, uncertainty
    - step_id: run_diagnosis_checklist
      title: 检查单逐项诊断
      instruction: 调用 run_diagnosis_checklist 按 references/checklist_rules.md 逐项分析静态/动态/特殊问题，同步更新 checklist_queries 状态与结论；静态扫描与动态评分合并输出，并把命中项证据回链到场景认知 evidence_chain 或 profile_checklist_ref。
      output_hint: checklist_queries, static_constraints, issues, cause_scores, uncertainty
      script: scripts/run_diagnosis_checklist.py
      function: run_diagnosis_checklist
      script_input: profile
    - step_id: classify_problem_source
      title: 问题来源分类
      instruction: 调用 classify_diagnosis_context（scripts/classify_diagnosis_context.py）依据检查单与 scene_type_rules 判定 problem_source；LLM 仅补充 uncertainty，不得覆盖脚本结论。
      output_hint: problem_source, evidence, uncertainty
      script: scripts/classify_diagnosis_context.py
      function: classify_diagnosis_context
      script_input: diagnosis
    - step_id: determine_signal_control_ceiling
      title: 信控优化上限判断
      instruction: 使用 classify_diagnosis_context 输出的 control_improvement_ceiling 与 scene_type_context；静态短板、下游阻塞或外部干扰主导时必须说明非信控治理建议。
      output_hint: control_improvement_ceiling, static_constraints, scene_type_context, uncertainty
    - step_id: summarize_diagnosis
      title: 诊断总结解读
      instruction: 调用 summarize_diagnosis 生成 diagnosis_insights 与规则模板 diagnosis_summary；默认 template，use_llm_narrative=true 时才调用大模型润色。
      output_hint: diagnosis_insights, diagnosis_summary, management_attention
      script: scripts/summarize_diagnosis.py
      function: summarize_diagnosis
      script_input: diagnosis
    - step_id: assemble_diagnosis_output
      title: 诊断输出组装
      instruction: 合并检查单、脚本结果和专家判断，保留确定性问题码、成因评分和证据，不得删除脚本识别出的高风险问题；诊断报告结构参考“交通路口问题诊断与指标解读报告模板.json”，章节从静态问题开始，不再输出场景特征速览；输出必须可被策略阶段直接消费。
      output_hint: checklist_queries, issues, priority_order, root_causes, cause_scores, diagnosis_summary, problem_source, control_improvement_ceiling, static_constraints, data_source_gaps, uncertainty, validation_errors
---

# 路口问题诊断

## 作用
区分静态短板与动态信控问题，对失衡、空放、溢流、相位渠化不匹配等问题排序，并输出供给/需求/控制/秩序/事件/数据质量六维成因评分。

## 上游衔接
问题诊断必须承接路口场景认知阶段输出的内部画像，而不是重新生成“场景特征速览”章节：

- `supply_profile`：供给、渠化、进出口车道、相邻路口间距、路口面积、静态短板标签。
- `demand_profile`：分进口转向流量、车道流量、转向占比、车道利用离散。
- `traffic_state`：饱和度、排队、延误、停车、溢流、失衡、绿灯利用率、空放、绿波或下游阻塞线索。
- `control_profile`：现状周期、相位、绿信比、时段方案、信号原子与车道映射。
- `congestion_profile`、`context_tags`、`quality_tags`、`evidence_chain`：用于判断空间传导、外部干扰、数据质量和证据回链。

若上游只提供 `scenario_report` 展示结构，应优先使用同次场景认知保留的内部画像；缺少内部画像时，只能从 `scenario_report` 抽取定性辅助信息，量化诊断项必须标记 `no_data` 或补采。

## 渐进式加载条件
- 阶段：`problem_diagnosis`
- 场景：`intersection`
- 触发：`pressure_medium`, `pressure_high`, `spillback`, `empty_green`

## 专家推理步骤
1. 承接场景认知内部画像和 `evidence_chain`，确认各检查项所需字段是否可用；不可用字段写入 `data_source_gaps`。
2. 调用 `run_diagnosis_checklist` 按检查单逐项分析静态短板、动态信控与特殊需求，同步更新 `checklist_queries`。
3. 静态项：相位渠化匹配（规则 A–D）、渠化与流量匹配（规则 A–D）、漏斗效应（规则 A–B）、相邻间距、出入口/强吸引点路段侧干扰、慢行设施与右转空间不足。
4. 动态项：需求压力感知、溢流、下游阻塞、失衡、空放、周期、方案精细度。
5. 调用 `diagnose_signal_issues` 合并问题排序与 `cause_scores`（供给/需求/控制/秩序/事件/数据质量）。
6. 调用 `summarize_diagnosis` 生成结构化洞察与自然语言解读，再交由大模型组综合总结。
7. 静态短板、外部干扰或秩序治理主导时必须输出信控优化上限，不把设施问题伪装成配时问题。

## 输出约束
- 结论必须给出证据指标、适用边界和不确定性。
- 每个问题必须包含 `issue_code`、`severity`、`confidence`、`evidence`、`root_cause`、`control_leverage`。
- 阶段输出必须包含 `checklist_queries`、`cause_scores`（六维主因贡献）和 `static_constraints`。
- 检查单完成后必须输出 `diagnosis_insights` 与 `diagnosis_summary`；总结应依据检查单命中项与问题排序如实描述，数据不足时说明无法判定项。
- 面向专家报告时参考 `../../common/专家经验调试/交通路口问题诊断与指标解读报告模板.json`；报告章节从“静态问题诊断”开始，不再包含“场景特征速览”。
- 数据不知道从哪里获取或无法由场景认知画像回链时，必须输出 `data_source_gaps`，列明字段、用途、可能来源和当前阻塞原因。
- `priority_order` 必须只包含 `issues` 中出现的问题码，并保持与问题排序一致。
- 检查单映射见 [references/checklist_rules.md](references/checklist_rules.md)；详细规则见 [references/rules.md](references/rules.md)。
