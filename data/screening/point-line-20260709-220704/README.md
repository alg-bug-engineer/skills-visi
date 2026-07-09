# 点/线优化路口全库筛选结果

生成时间：2026-07-09T22:07:35.117399

## 文件说明

| 文件 | 说明 |
|------|------|
| `intermediate_01_direction_spacing.*` | 进口道相邻间距（SQL 口径） |
| `intermediate_02_exit_downstream.*` | 出口 link → 下游信控路口拓扑 |
| `intermediate_03_turn_overflow_evening_peak.json` | 转向级晚高峰溢流比 max/mean |
| `intermediate_04_turn_overflow_all_day.json` | 转向级全天溢流比 |
| `intermediate_05_turn_saturation_evening_peak.json` | 转向级晚高峰饱和度/绿灯利用率 |
| `full_pair_screening_results.*` | **全量** 目标-下游走廊配对及分型 |
| `type1_candidates.*` | Type1 点优化（含 WEAK） |
| `type2_candidates.*` | Type2 线优化（含 WEAK） |
| `type1_strong_candidates.json` | 严格 Type1（溢流≥0.8 或饱和≥0.9 且下游有空间） |
| `type2_strong_candidates.json` | 严格 Type2 |
| `screening_summary.json` | 汇总统计 |

详细方法论见 `docs/点线优化路口筛选分析.md`。

## 本次扫描统计

- 走廊配对总数：1378
- 严格 Type1：73
- 严格 Type2：20
- 下游缺 DWD：31
