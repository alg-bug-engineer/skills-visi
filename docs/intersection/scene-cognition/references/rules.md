# 路口场景认知规则

> 本文只规定场景认知阶段的输出结构、边界和加载约定。六维度字段口径见 [dimension_metrics_logic.md](dimension_metrics_logic.md)，检查单与表映射见 [checklist_rules.md](checklist_rules.md) / [data_dictionary.md](data_dictionary.md)。

## 目标

路口场景认知把静态供给、动态运行、信号控制、环境上下文和数据质量组织成两类结果：

- 面向展示的 `scenario_report`：先展示 `scenarioSummary` 场景特征总结，再展示六个维度分析。
- 面向诊断的内部画像：保留供给、需求、运行、控制、拥堵、上下文、质量与证据链字段。

本阶段只做事实抽取、指标计算、质量标记和场景标签，不做问题归因、主因判断、治理建议或配时生成。

## 必要输出

- `scenario_report`：标准展示结果。
- `scene_type`、`pressure_level`：场景类型与压力等级。
- `supply_profile`、`demand_profile`、`traffic_state`、`control_profile`、`congestion_profile`：内部画像。
- `context_tags`、`quality_tags`、`uncertainty`、`validation_errors`：上下文、数据质量与不确定性。
- `metrics_insights`、`metrics_interpretation`、`evidence`、`evidence_chain`：时序洞察、自然语言解读和诊断回链证据。

## 展示结构

`scenario_report` 字段必须与前端 `SceneProfileView` 的展示一致：

- `scenarioSummary`：场景特征总结，回答“是什么样的路口、呈现什么运行规律”。来源是六维度结果和 `metrics_insights`，不是独立诊断章节。
- `basicScenario`：维度1，路口基础场景刻画，包括节点属性、空间协同、周边吸引源。
- `flowAndDemand`：维度2，流量与需求特征，包括转向流量、转向占比、时间分布、流量溯源、慢行流量。
- `capacityAndSupply`：维度3，通行能力与供给特征，包括饱和流率、转向能力、总能力与需求匹配。
- `operationalStatus`：维度4，运行状态特征，包括转向运行指标、失衡指数和服务水平。
- `signalTimingFeatures`：维度5，现状配时方案特征解析，包括时间段与周期、相位相序、配时特征概述。
- `spatiotemporalPatterns`：维度6，时空特征建模与关联规律，包括拥堵时段、最大排队、上下游关联、吸引源和事件影响。

若当前输入只有单一时段聚合指标，只填充对应时段，其余时段保持空值，并在 `quality_tags` 或 `uncertainty` 说明证据不足；不得把单时段事实扩写为全天规律。

## 指标口径

阈值以 `skillpacks/intersection/common/thresholds.yaml` 为唯一真源；场景认知与诊断共用但语义不同：

- `saturation.high`：场景认知高饱和时段窗口。
- `saturation.oversaturation`：场景认知过饱和峰值标注；诊断阶段触发过饱和问题。
- `green.low_utilization_cognition`：场景认知低绿灯利用时段。
- `green.low_utilization_diagnosis`：诊断阶段空放/低利用触发条件之一。

- `saturation = volume / capacity`，无能力值时不臆造饱和度，应标记缺少 `metrics.capacity`。
- `queue_storage_ratio = queue_m / storage_m`，用于判断排队是否接近进口道存储空间。
- `pressure_level` 取饱和度、延误、排队、溢流、冲突风险中的最大压力。
- `green_utilization` 与 `empty_green_rate` 同时存在时都保留；二者冲突时写入 `quality_tags`。
- `movement_saturation` 仅在分流向流量和分流向能力同时存在时计算。

## 数据质量与边界

以下情况必须写入 `quality_tags`，并同步进入 `validation_errors` 或 `uncertainty`：

- 缺少 `scope.level`、`metrics.volume`、`metrics.capacity`、`metrics.avg_delay_s`、信号配时或 DWS 时序等关键字段。
- `capacity <= 0` 但存在流量。
- 检测器在线率低于 0.9。
- 数据延迟超过 120 秒。
- 灯态、相位或配时字段缺失，导致无法建立控制画像。
- 指标明显冲突，例如饱和度很低但延误和排队都很高。

## 关键指标解读

检查单检索与 `build_traffic_context` 完成后，必须调用 `scripts/interpret_key_metrics.py`：

- `metrics_insights` 提取路口/进口饱和时段、排队延误、绿灯利用、需求形态、失衡与服务水平、设施约束和配时分段。
- `metrics_interpretation` 基于 `metrics_insights` 如实描述观测窗口；无模型凭证时回退规则模板（`source=template`）。
- 解读完成后可刷新 `scenario_report.scenarioSummary.portrait.时间规律`，但不得覆盖确定性脚本已计算的基础指标。
- 缺少 DWS 时序时，说明无法推断时段分布，并指向 `inter_evaluation` / `turn_saturation` 等补采表。

## 检查单逐项检索

场景认知必须按 [checklist_rules.md](checklist_rules.md) **逐项查询** PostgreSQL，并在 `checklist_queries` 中标记每项检索状态：

- `has_data`：有数据，可展开 `raw[data_key]` 查看原始记录
- `no_data`：已查询但无记录，写入 `quality_tags` 与 `validation_errors`
- `error` / `skipped`：表不可用或前置条件缺失

检索顺序：静态供给 → 动态运行 → 控制画像 → 环境上下文。不得跳过检查单直接臆造画像字段。

## PostgreSQL 数据加载

- 仅有 `inter_id` 或路口名称时，优先调用 `scripts/load_intersection_from_pg.py` 拉取数据，再调用 `build_traffic_context`。
- 周边交通发生源/吸引源来自 `xianchang.ods_amap_aoi_info` 与 `xianchang.ods_amap_poi_info`，以路口中心 800m 半径检索，写入 `context.aoi_sources` 和 `scenario_report.basicScenario.attractionSources`。
- 检查单定义见 [checklist_rules.md](checklist_rules.md)；表映射见 [data_dictionary.md](data_dictionary.md)。
- 目标路口无 DWS 覆盖时，必须在 `quality_tags` 标记 `missing_dws_coverage`，并在 `uncertainty` 说明可用表与补采建议。
