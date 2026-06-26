# 场景认知 · 数据字典与表映射

> 检查单逐项定义与检索状态见 [checklist_rules.md](checklist_rules.md)。  
> 表结构详情见 `docs/reference/PG_DATABASE_SCHEMA.md` §7。

## 检索输出结构

`load_intersection_from_pg` 返回：

```json
{
  "ok": true,
  "task": { "scope": {}, "metrics": {}, "signal": {}, "context": {} },
  "raw": { "inter": [], "channelization": [], "...": [] },
  "checklist_queries": [
    {
      "item_id": "inter_basic_info",
      "category": "static",
      "label": "路口交叉道路等级、形态",
      "profile_field": "supply_profile.inter_type, supply_profile.intersection_shape",
      "table": "road6.dim_inter_info + dim_link_info",
      "status": "has_data",
      "row_count": 1,
      "summary": "信号化 · 十字形",
      "data_key": "inter"
    }
  ],
  "errors": []
}
```

前端按 `checklist_queries` 展示检查单进度；`status === has_data` 时可从 `raw[data_key]` 展开原始记录。

## 表 → 画像字段速查

| 类别 | 表 | 主要画像字段 |
| --- | --- | --- |
| 静态 | `road6.dim_inter_info` | `supply_profile.inter_type`, `cross_type`, `intersection_shape`, `leg_count` |
| 静态 | `road6.dwd_tfc_rltn_wide_inter_ft_link` | `supply_profile.approaches`, `channelization` |
| 静态 | `road6.dwd_tfc_rltn_wide_inter_ft_lane` | `supply_profile.lanes` |
| 静态 | `road6.dwd_tfc_rltn_wide_inter_ft_link` + `dim_link_info` | `supply_profile.adjacent_inter_spacing_m`（进口 link 长度）、`road_levels`、`road_grade_combination`、`intersection_importance` |
| 上下文 | `xianchang.ods_amap_aoi_info` | `context.aoi_sources`（面状吸引源） |
| 上下文 | `xianchang.ods_amap_poi_info` | `context.aoi_sources`（医院/学校/商场/园区/停车场出入口等点状吸引源） |
| 控制 | `xianchang.dws_turn_min_green_5min_mm` | `control_profile.min_green_s` |
| 动态 | `xianchang.dws_inter_link_turn_flow_5min_mm` | `demand_profile.movement_volume` |
| 动态 | `xianchang.dws_tfc_inter_turn_flow_correlate_m` | `scenario_report.flowAndDemand.flowTrace` |
| 动态 | `xianchang.dwd_tfc_lane_roadcross_flow_5mi` | `demand_profile.lane_volume` |
| 动态 | `xianchang.dws_turn_saturation_5min_mm` | `traffic_state.movement_saturation` |
| 动态 | `xianchang.dws_inter_evaluation_5min_mm` | `traffic_state.saturation`, `imbalance_index` |
| 动态 | `xianchang.dws_inter_dir_turn_perf_5min_mm` | `traffic_state.queue_m`, `avg_delay_s` |
| 动态 | `xianchang.dws_turn_green_utilization_5min_mm` | `traffic_state.green_utilization` |
| 动态 | `xianchang.dws_lane_capacity_5min_mm` | `supply_profile.movement_capacity` |
| 动态 | `xianchang.dim_lane_saturation_headway` | `scenario_report.capacityAndSupply.saturationFlowRates` |
| 控制 | `xianchang.dwd_ctl_inter_plan_cfg` | `control_profile.current_cycle_s` |
| 控制 | `xianchang.dwd_ctl_inter_plan_stage_timing` | `control_profile.phase_splits` |
| 控制 | `xianchang.dwd_ctl_inter_signal_atom_lane_mapping` | 审计 |
| 控制 | `xianchang.dwd_ctl_inter_schedule_cfg` | `control_profile.time_plan_count` |
| 上下文 | `xianchang.dwd_tfc_complaint_inter_issue` | `context_tags` |
| 上下文 | `xianchang.dwd_tfc_field_survey_inter_issue` | `context_tags` |

## 脚本调用链

1. **`load_intersection_from_pg.py`**：按检查单逐项查询 PG，输出 `checklist_queries` + `raw` + `task`
2. **`calculate_saturation.py` → `build_traffic_context`**：计算内部画像，并组装场景特征总结与六维度 `scenario_report`
3. **`interpret_key_metrics.py`**：从 `raw` 时序提取饱和、排队、绿灯、流量、失衡、设施约束和配时分段等洞察，生成 `metrics_interpretation`
4. **`validate_intersection_input.py`**：校验必填字段与数据质量

```python
pg_result = load_intersection_from_pg(inter_id="...", day_of_week=1, time_hhmm="07:30")
profile = build_traffic_context(pg_result["task"])
```

## 数据覆盖注意

- DWS 汇总约 **473** 路口有完整 KPI；检索前确认目标 `inter_id` 是否在覆盖范围。
- 车道 5 分钟流量表覆盖约 **813** 路口。
- 无 DWS 数据时，对应检查单项为 `no_data`，`quality_tags` 须标记 `missing_dws_coverage`，不得臆造饱和度。
