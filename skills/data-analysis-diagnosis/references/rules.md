# 数据分析与诊断规则

## 溢出验证流程

1. 计算目标方向排队比
2. 结合饱和度与绿灯利用率判断放行能力
3. 对下游信控节点输出与目标路口同构的 `metrics` / `by_turn`
4. 通过 `downstream_trace` 完成一跳去向与承接能力判断
5. 通过 `flow_trace` + `arterial_analysis` 完成干线协调分析
6. 区分「本路口放不出去」与「下游接不住」

## 下游信控节点同构分析（剧本第四幕）

- `target_intersection` 与 `downstream_trace.adjacent_intersections[]` 字段对齐
- 必含：`metrics.queue_storage_ratio_max`、`metrics.saturation_rate`、`metrics.green_utilization`、`by_turn`、`remaining_storage_m`
- `downstream_diagnosis` 输出 `release_answer`、`judgment_criteria`、`narrative`
- 核心问题：加绿以后，车有没有地方去？

## 可视化契约（references/流量溯源）

- `map_scenes.downstream_trace_map`：`turn_traces`、`adjacent_intersections`、`trace_direction=downstream`
- `map_scenes.arterial_analysis`：`entry_traces`、干线 HUD 指标
- 字段命名对齐 `frontend/types/map.ts`

## 输出约束

- 本阶段只输出指标与验证结论，不输出成因判断或配时方案
