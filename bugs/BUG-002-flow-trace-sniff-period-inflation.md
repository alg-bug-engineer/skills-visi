# BUG-002：上游流量溯源流量点虚增（跨时段聚合）

## 基本信息

- **Bug ID**：BUG-002
- **发现日期**：2026-07-07
- **修复日期**：2026-07-07
- **严重程度**：P1
- **状态**：已修复
- **关联需求**：needs/7-流量溯源拓扑可视化.md / needs/9-标准流量溯源拓扑与渠化可视化.md
- **关联分支**：20260707205219-11-治理建议配时协调后端补齐与前端技术债清理

## 问题描述

对照参考可视化 `flow-trace-links-sniff.html`（单时段·晚高峰），项目运行时的上游溯源结果流量点「明显多了许多」。

以「奥体西路与经十路路口 · 西左转 · 来向溯源」为例：

| 口径 | raw_rows | 渲染流量点(rendered) |
|------|----------|----------------------|
| 参考 HTML（晚高峰单时段） | 18 | 2 |
| 项目（修复前，全时段聚合） | 63 | 6+ |
| 项目（修复后，晚高峰） | 18 | 2 |

## 根因

`dws_tfc_inter_turn_flow_correlate_m` 的 `period_type` 有 `EVENING_PEAK` / `MORNING_PEAK` / `OFF_PEAK` 三值。

1. `app/trace/map_scene.py::_correlate_peers` 与 `_best_share_by_inter` **未按 `period_type` 过滤**，把三个时段的 peer 全部聚合，导致溯源 peer（及渲染流量点）约 2~3 倍虚增。
2. `app/data/pg_adapters.py::topology_from_pg_raw` 把 `period_type` **硬编码为 `"EVENING_PEAK"`**，未从 ticket 时段解析，无法驱动按时段过滤。

## 修复方案

1. `map_scene.py` 新增 `resolve_correlate_period()`（中文时段/大写代码 → `EVENING_PEAK|MORNING_PEAK|OFF_PEAK`）与 `_period_match()`。
2. `_correlate_peers` / `_best_share_by_inter` 增加 `period_type` 过滤参数。
3. `build_flow_trace_links_sniff_map_scene` 从 `topology.period_type` 解析时段并过滤；该时段无 `flow_correlate` 行时回退全时段真实数据（避免空场景，绝不合成），并在 `stats.period_type` 标注实际生效时段。
4. `topology_from_pg_raw` 改为 `resolve_correlate_period(ticket.period, ticket.time_range)`，缺省 `EVENING_PEAK`。

## 验证

- 真实 PG 端到端复现：西左转 rendered=2、西直行=19(18+目标)、西右转=20，与参考一致。
- 新增单测：
  - `tests/test_trace_geometry.py::test_flow_trace_links_sniff_scene_filters_by_period`
  - `::test_flow_trace_links_sniff_scene_period_falls_back_when_empty`
  - `::test_topology_resolves_period_from_ticket`
- `pytest tests/ -q` → 106 passed。

## 经验教训

- `flow_correlate` 等 5min/月度聚合表按 `period_type` 分时段，溯源/占比必须限定与诊断一致的单一时段，禁止跨时段聚合。
- 时段（period_type）应由 ticket 真实驱动，禁止硬编码。
