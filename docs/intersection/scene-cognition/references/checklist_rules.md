# 场景认知 · 检查单检索规则

> **机器可读真源**：`skillpacks/intersection/common/scene_cognition_checklist.yaml`  
> 依据 `docs/算法设计文档/交通智能体问题检查单-0614.docx` §1.1 与 `docs/reference/PG_DATABASE_SCHEMA.md` §7。  
> 加载脚本 **`load_intersection_from_pg.py`** 按本检查单**逐项查询** PostgreSQL，并在 `checklist_queries` 中标记检索状态。

## 检索状态约定

| 状态 | 含义 |
| --- | --- |
| `has_data` | 查询成功且返回 ≥1 条有效记录 |
| `no_data` | 查询成功但目标路口/时间片无记录 |
| `error` | SQL 异常或表不可用 |
| `skipped` | 前置条件不满足（如未解析出 inter_id） |

每项输出字段：

- `item_id`：检查单唯一标识
- `category`：`static` / `dynamic` / `control` / `context`
- `label`：检查单描述（中文）
- `profile_field`：写入画像的字段路径
- `table`：推荐 PostgreSQL 表
- `status` / `row_count` / `summary` / `data_key`（对应 `raw` 中的键，供前端展开查看）

## 1. 静态供给检查单

| item_id | 检查单描述 | 画像字段 | 推荐表 | data_key |
| --- | --- | --- | --- | --- |
| `inter_basic_info` | 路口交叉道路等级、形态 | `supply_profile.inter_type`, `cross_type`, `intersection_shape`; `scenario_report.basicScenario.nodeAttributes` | `road6.dim_inter_info` + `dim_link_info` | `inter` |
| `channelization` | 进口/出口/渠化 | `supply_profile.approaches`, `exits`, `channelization`; `scenario_report.basicScenario.nodeAttributes.inboundLanes/outboundLanes/turnLaneConfig` | `road6.dwd_tfc_rltn_wide_inter_ft_link` | `channelization` |
| `lane_detail` | 车道明细 | `supply_profile.lanes`; `scenario_report.basicScenario.nodeAttributes.turnLaneConfig` | `road6.dwd_tfc_rltn_wide_inter_ft_lane` | `lane_detail` |
| `adjacent_spacing` | 相邻路口间距、进口道路等级 | `supply_profile.adjacent_inter_spacing_m`, `road_levels`, `road_grade_combination`; `scenario_report.basicScenario.spatialCoordination` | `road6.dwd_tfc_rltn_wide_inter_ft_link` + `dim_link_info` | `adjacent_spacing` |
| `aoi_sources` | 周边交通发生源/吸引源 | `context.aoi_sources`; `scenario_report.basicScenario.attractionSources`、`spatiotemporalPatterns.attractionImpact` | `xianchang.ods_amap_aoi_info` + `xianchang.ods_amap_poi_info` | `aoi_sources` |
| `min_green_cfg` | 各方向最小绿 | `control_profile.min_green_s`; `scenario_report.signalTimingFeatures.minGreens` | `xianchang.dws_turn_min_green_5min_mm` | `min_green` |

## 2. 动态运行检查单

| item_id | 检查单描述 | 画像字段 | 推荐表 | data_key |
| --- | --- | --- | --- | --- |
| `turn_flow` | 转向流量 | `demand_profile.movement_volume`; `scenario_report.flowAndDemand.turnFlows`、`turnProportions` | `xianchang.dws_inter_link_turn_flow_5min_mm` | `turn_flow` |
| `flow_correlate` | 转向流量溯源 | `scenario_report.flowAndDemand.flowTrace` | `xianchang.dws_tfc_inter_turn_flow_correlate_m` | `flow_correlate` |
| `lane_flow` | 车道流量 | `demand_profile.lane_volume`; `scenario_report.flowAndDemand.demandCharacteristics` 辅助口径 | `xianchang.dwd_tfc_lane_roadcross_flow_5mi` | `lane_flow` |
| `turn_saturation` | 转向/相位饱和度 | `traffic_state.movement_saturation`; `scenario_report.operationalStatus.saturations` | `xianchang.dws_turn_saturation_5min_mm` | `turn_saturation` |
| `inter_evaluation` | 路口综合评价 | `traffic_state.saturation`, `imbalance_index`, `los`; `scenario_report.capacityAndSupply.totalCapacity`、`operationalStatus.imbalanceAndService`、`spatiotemporalPatterns.congestionTimeProfile` | `xianchang.dws_inter_evaluation_5min_mm` | `evaluation` |
| `turn_perf` | 排队/延误/停车/溢流 | `traffic_state.queue_m`, `avg_delay_s`, `stop_count`; `scenario_report.operationalStatus.queues/delaysAndStops/overflows` | `xianchang.dws_inter_dir_turn_perf_5min_mm` | `turn_perf` |
| `green_utilization` | 绿灯利用率/空放 | `traffic_state.green_utilization`, `empty_green_rate`; `scenario_report.operationalStatus.greenUtilization` | `xianchang.dws_turn_green_utilization_5min_mm` | `green_utilization` |
| `lane_capacity` | 车道通行能力 | `supply_profile.movement_capacity`; `scenario_report.capacityAndSupply.turnCapacities/totalCapacity` | `xianchang.dws_lane_capacity_5min_mm` | `lane_capacity` |
| `lane_saturation_headway` | 车道级饱和流率 | `scenario_report.capacityAndSupply.saturationFlowRates` | `xianchang.dim_lane_saturation_headway` | `lane_saturation_headway` |

## 3. 控制画像检查单

| item_id | 检查单描述 | 画像字段 | 推荐表 | data_key |
| --- | --- | --- | --- | --- |
| `plan_cfg` | 当前方案/周期 | `control_profile.current_cycle_s`, `plan_no`; `scenario_report.signalTimingFeatures.cycle` | `xianchang.dwd_ctl_inter_plan_cfg` | `plan` |
| `stage_timing` | 阶段绿信比 | `control_profile.phase_splits`; `scenario_report.signalTimingFeatures.phaseSequence/greenRatios` | `xianchang.dwd_ctl_inter_plan_stage_timing` | `plan` |
| `signal_lane_mapping` | 信号原子↔车道 | 审计字段 | `xianchang.dwd_ctl_inter_signal_atom_lane_mapping` | `signal_lane_mapping` |
| `schedule_cfg` | 时段方案数 | `control_profile.time_plan_count`; `scenario_report.signalTimingFeatures.timeSegments` | `xianchang.dwd_ctl_inter_schedule_cfg` | `schedule_cfg` |

## 4. 环境与上下文检查单

| item_id | 检查单描述 | 画像字段 | 推荐表 | data_key |
| --- | --- | --- | --- | --- |
| `aoi_sources` | 周边交通发生源/吸引源 | `context.aoi_sources`; `scenario_report.basicScenario.attractionSources`、`spatiotemporalPatterns.attractionImpact` | `xianchang.ods_amap_aoi_info` + `xianchang.ods_amap_poi_info` | `aoi_sources` |
| `complaint_records` | 投诉台账 | `context_tags`; `scenario_report.basicScenario.attractionSources`、`spatiotemporalPatterns.attractionImpact` | `xianchang.dwd_tfc_complaint_inter_issue` | `complaints` |
| `field_survey` | 现场调研 | `context_tags`; `scenario_report.spatiotemporalPatterns.incidentImpacts` | `xianchang.dwd_tfc_field_survey_inter_issue` | `field_survey` |

## 5. 时间片与过滤约定

- **动态 DWS 表**：仅按 `day_of_week`（1=周一 … 7=周日）过滤，**不限定** `step_index`，拉取该星期全天 5 分钟时序后再聚合。
- **车道流量 DWD 表** `dwd_tfc_lane_roadcross_flow_5mi`：按 `dt`（由 `day_of_week` 映射到样本日期）过滤，不限定 `step_index`。
- xianchang 表：`is_deleted = 0`
- road6 维表：`version_id = (SELECT version_id FROM road6.dim_data_version WHERE is_enable = 1)`
- 画像聚合：转向流量/绿灯利用率等取**全天均值**，饱和度/排队等取**峰值**，最小绿按 `link_id + turn_dir_no` 去重。

### 相邻路口间距计算

- 数据源：`dwd_tfc_rltn_wide_inter_ft_link`（`link_role = entrance`）JOIN `dim_link_info.length_m`
- 每个进口 link 的长度 = 上游路口（`f_inter_id`）到本路口的沿路距离
- `adjacent_inter_spacing_m` = 各进口 link 长度的 **最小值**
- 明细写入 `supply_profile.adjacent_inter_spacing_detail`
- 同一查询读取 `dim_link_info.road_level`，按编码归一到 `road_levels`、`road_grade_combination` 和 `intersection_importance`

### 周边 AOI / POI 检索

- 面状吸引源：`xianchang.ods_amap_aoi_info`（回退 `gaode.ods_aoi_info`）
- 点状出入口：`xianchang.ods_amap_poi_info`，重点筛选医院、学校、商场、园区及停车场出入口
- 空间范围：以 `road6.dim_inter_info.geom_center` 为中心，检索 **800m** 半径内记录
- 输出字段：类型、名称、方位/距离、影响时段、影响方式、出入口角色（POI）；写入 `context.aoi_sources`，并映射到报告 `1.3 周边交通发生源/吸引源`
- 类型归并：学校、医院、商圈、港区/园区、公交站、停车场、查验口/收费站、其他
- POI 筛选口径：
  - 医院：`医疗保健服务` 中的综合/专科/诊所
  - 学校：`科教文化服务` 且 `category_l2=学校`
  - 商场：`购物服务` 且 `category_l2=商场`
  - 园区：名称/分类/类型路径含「产业园/工业园/物流园/科技园/园区」
  - 停车场出入口：`category_l3` 为停车场出入口/入口/出口，或名称含入口/出口

### 道路等级与路口形态

- `road_level` 编码：`41000` 高速公路、`42000` 国道、`43000` 城市快速路、`44000` 城市主干道、`45000` 城市次干道、`47000` 城市普通道路、`51000` 省道、`52000` 县道、`53000` 乡道、`54000` 县乡村内部道路、`49` 小路。
- 路口形态由 `dim_inter_info.inter_type` / `inter_proto` 与进口方向数量共同归一，写入 `supply_profile.intersection_shape` 和 `leg_count`。
- 复杂形态（环岛、畸形、多路、斜交、行人过街）同步写入 `static_flags`，供诊断阶段识别供给约束与冲突背景。

## 6. 检索顺序与画像组装

脚本按 **静态 → 动态 → 控制 → 上下文** 顺序逐项查询；每完成一项即写入 `checklist_queries`。全部检索完成后：

1. **`_aggregate_metrics`**：合并动态指标到 `task.metrics`
2. **`_build_scope` / `_build_signal` / `_build_context`**：组装画像字段
3. **`build_traffic_context`**（`calculate_saturation.py`）：计算内部画像、压力等级、质量标签，并生成六维度 `scenario_report` 初稿
4. **`interpret_key_metrics`**：从 `raw` 时序提取饱和时段、需求时间分布与配时分段，生成 `metrics_insights` / `metrics_interpretation`，再刷新 `scenario_report.scenarioSummary` 中的时间规律描述

缺少 DWS 动态数据时，`inter_evaluation` / `turn_flow` 等为 `no_data`，必须在 `quality_tags` 标记 `missing_dws_coverage`，且 `metrics_interpretation` 应说明无法推断时段。

## 7. 调用示例

```python
result = load_intersection_from_pg(
    inter_id="011wwe0rvxj00001",
    day_of_week=1,
    time_hhmm="07:30",
)
for item in result["checklist_queries"]:
    print(item["item_id"], item["status"], item["row_count"])
    if item["status"] == "has_data":
        print(result["raw"][item["data_key"]])
```
