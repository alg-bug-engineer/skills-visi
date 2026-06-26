---
name: intersection-scene-cognition
description: 将路口动静态数据组织为场景特征总结和六维度可视化报告，对接 PostgreSQL 检查单形成后续诊断证据链。Use when phase is scene_cognition and scenario is intersection.
metadata:
  skill_id: intersection_scene_cognition
  display_name: 路口场景认知
  phase: scene_cognition
  scenarios: [intersection]
  triggers: [always, intersection_task]
  tool_names: [analyze_traffic_context]
  version: "0.3.0"
  enabled: true
  script_files:
    - scripts/load_intersection_from_pg.py
    - scripts/calculate_saturation.py
    - scripts/traffic_metrics_logic.py
    - scripts/validate_intersection_input.py
    - scripts/interpret_key_metrics.py
  reference_files:
    - ../../common/路口专家经验规则.md
    - references/checklist_rules.md
    - references/dimension_metrics_logic.md
    - references/rules.md
    - references/data_dictionary.md
    - ../../common/thresholds.yaml
    - ../../common/scene_cognition_checklist.yaml
    - ../../common/专家经验调试/交通路口场景认知与指标解读报告模板.json
  execution_steps:
    - step_id: load_pg_context
      title: 加载 PG 路口数据
      instruction: 若 task 缺少 metrics 或 scope.channelization，调用 load_intersection_from_pg 按检查单逐项查询（见 references/checklist_rules.md），同时从 xianchang.ods_amap_aoi_info 与 ods_amap_poi_info 检索路口 800m 范围内主要吸引源及停车场/医院/学校等出入口，标记 checklist_queries 检索状态，合并 task 与 raw。
      output_hint: task, raw, checklist_queries, errors, uncertainty
      script: scripts/load_intersection_from_pg.py
      function: build_task_from_pg
      script_input: task
    - step_id: identify_supply_profile
      title: 识别基础场景
      instruction: 整理路口编号、道路等级组合、几何形态、进出口车道、渠化、相邻上游路口、排队存储空间和周边 AOI；仅补充脚本未覆盖的语义标签，不重复计算指标。
      output_hint: supply_profile, control_profile, evidence, uncertainty
    - step_id: identify_demand_profile
      title: 识别流量需求
      instruction: 整理分进口转向流量、转向占比、三时段时间分布、流量溯源、行人非机动车和需求状态；仅补充 POI/出行目的语义，不输出问题码。
      output_hint: demand_profile, context_tags, evidence, uncertainty
    - step_id: calculate_traffic_state
      title: 计算供给与运行状态
      instruction: 调用确定性脚本计算通行能力、饱和度、排队、延误、停车、绿灯利用率、失衡指数、服务水平、压力等级、拥堵画像和数据质量标签，并同步生成 `scenario_report` 初稿。
      output_hint: scene_type, pressure_level, traffic_state, congestion_profile, metrics_summary, scenario_report, quality_tags, validation_errors
      script: scripts/calculate_saturation.py
      function: build_traffic_context
      script_input: task
    - step_id: assemble_scene_profile
      title: 组装场景报告
      instruction: 合并专家识别和脚本结果，输出 `scenario_report.scenarioSummary` 场景特征总结和六个展示维度；保留供给、需求、运行、控制、拥堵、上下文和质量等内部画像。不得删除脚本识别的数据质量问题，不得加入问题诊断或治理建议。
      output_hint: scene_type, pressure_level, supply_profile, demand_profile, traffic_state, control_profile, congestion_profile, context_tags, quality_tags, scenario_report, evidence, uncertainty, validation_errors
    - step_id: interpret_key_metrics
      title: 解读关键指标
      instruction: 检查单检索与画像计算完成后，调用 interpret_key_metrics 提取 5 分钟时序洞察，刷新场景特征总结中的时间规律，并生成规则模板解读；默认使用 template，仅在 use_llm_narrative=true 时润色 narrative。
      output_hint: metrics_insights, metrics_interpretation, evidence_chain, management_attention
      script: scripts/interpret_key_metrics.py
      function: interpret_key_metrics
      script_input: task
---

# 路口场景认知

## 作用
将路口动静态数据组织成两类结果：

- `scenario_report`：前端可视化展示的标准结果，先输出 `scenarioSummary` 场景特征总结，再输出六个维度分析。
- 内部画像：保留 `supply_profile`、`demand_profile`、`traffic_state`、`control_profile`、`congestion_profile`、`context_tags`、`quality_tags`，供后续诊断回链。

## 专家推理步骤
1. 若输入只有 `inter_id` 或路口名称，先按检查单调用 `load_intersection_from_pg` 拉取静态供给、动态运行、控制画像和环境上下文。
2. 调用 `build_traffic_context` 计算内部画像，并组装 `scenario_report` 初稿。
3. 调用 `interpret_key_metrics` 提取 5 分钟时序洞察，用于刷新拥堵时段、需求时间分布、配时分段和场景特征总结。
4. 最终输出必须与前端展示一致：`scenarioSummary` 在前，六维度分析在后。

## 展示结构
`scenario_report` 只包含一个总结和六个展示维度：

- `scenarioSummary`：场景特征总结，聚合等级定位、形态特征、空间约束、外部荷载、流量规律、转向特征、供需匹配、运行状态、配时特征和时间规律。
- `basicScenario`：维度1，路口基础场景刻画。
- `flowAndDemand`：维度2，流量与需求特征。
- `capacityAndSupply`：维度3，通行能力与供给特征。
- `operationalStatus`：维度4，运行状态特征。
- `signalTimingFeatures`：维度5，现状配时方案特征解析。
- `spatiotemporalPatterns`：维度6，时空特征建模与关联规律。

## 输出约束
- `scenario_report` 结构遵循 `../../common/专家经验调试/交通路口场景认知与指标解读报告模板.json`，字段口径必须与 `SceneProfileView` 的可视化展示一致。
- 本阶段只描述现状特征、指标规律、供需状态、配时结构、时空关联和数据质量；不输出问题诊断、成因判断、治理建议或配时秒数。
- 结论必须来自检查单、脚本计算或任务输入；缺少关键输入时保留空值，写入 `quality_tags`、`validation_errors` 或 `uncertainty`，不得把单时段数据扩写为全天规律。
- 输出必须包含内部画像：`supply_profile`、`demand_profile`、`traffic_state`、`control_profile`、`congestion_profile`、`context_tags` 和 `quality_tags`。
- 指标查询与画像计算完成后，必须输出 `metrics_insights`、`metrics_interpretation`（默认 `source=template`）与 `evidence_chain`。
- 需要确定性计算或校验时，优先调用 `scripts/` 中的脚本能力。
- 检查单逐项检索见 [references/checklist_rules.md](references/checklist_rules.md)；表映射见 [references/data_dictionary.md](references/data_dictionary.md)；详细规则见 [references/rules.md](references/rules.md)。
