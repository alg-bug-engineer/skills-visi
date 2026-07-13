# BUG-004 PG 路径下游承接指标恒为 0/无（拓扑未加载相邻路口指标）

- 状态：已修复
- 发现分支：`20260708170725-20-方案与协调呈现优化及下游指标修复`
- 关联需求/计划：需求 20（R6）/ `archive/plans/20-方案与协调呈现优化及下游指标修复.md`

## 现象

`analysis/典型输入案例.md` Case 3 目标路口「解放东路与奥体中路路口」(`011wwe294k300001`)，
下游「奥体中路与经十路路口」(`011wwe291ey00001`) 在案例中标注为极饱和（饱和度 >1.05、排队反传，
数据完整）。但系统实际呈现的下游承接判别中，该下游的排队、饱和度指标为 `0` 或「无」，
与案例宣称的 PG 数据完整不一致。

## 根因

`app/data/pg_adapters.py::topology_from_pg_raw` 基于 `trace_geometry` + `flow_correlate` 构建
`downstream_nodes` 时，**只写入几何与占比字段**（`inter_id/inter_name/lng/lat/share_pct/path/
receiving_dir8/receiving_label`），**从未加载相邻（下游）路口自身的运行指标**。

下游 profile 由 `app/trace/intersection_profile.py::build_intersection_profile(node)` 计算，
其 `queue_length_m / storage_length_m / volume_vph / capacity_vph` 在缺省时取 0，导致
`calculate_saturation`、`calculate_queue_ratio` 恒为 0（或 None），最终「下游承接判别」显示
饱和度/排队为 0。

对比：fixture 路径 `tests/fixtures/overflow_topology.json` 的下游节点**自带**
`queue_length_m/volume_vph/...`，故 mock 演示正常——仅 **PG 真实路径漏加载下游指标**。
此外 `build_intersection_profile` 在无指标时用缺省 0 伪造，违反 `docs/rule.md` 14/16（禁止静默造数）。

## 修复

1. `app/data/pg_adapters.py` 新增 `enrich_downstream_metrics(topology, *, load_pg_metrics)`：
   按每个下游节点承接进口方向 `receiving_dir8`（经 `_direction_for_dir8` 反查方向字符串）加载其
   真实 PG 聚合指标，绑定 `queue_length_m/storage_length_m/volume_vph/capacity_vph/saturation/
   green_utilization/...` 到节点，并置 `metrics_available=true`、`metrics_source=pg_adjacent`。
2. PG 加载路径接线：`app/services/intersection_load_service.py`（前端 `/intersection/load`）与
   `app/data/load_pg_bundle.py`（诊断 bundle）在构建拓扑后调用 enrich，`load_pg_metrics` 复用
   `load_intersection_from_pg(相邻 inter_id, 同 day/step)` 取其 `task.metrics`。
3. `build_intersection_profile` 尊重 `metrics_available=false`：饱和度/排队/LOS/剩余空间返回 `None`
   并透出 `metrics_reason`，`overflow_verification` 走「无法验证」分支，**不再伪造 0**。
   取不到 PG 指标时置 `metrics_available=false` + `metrics_reason`（降级为「暂无数据」而非错误 0）。

## 验证

- 新增单测 `tests/test_downstream_metrics_enrichment.py`(3)：
  真实指标注入后下游饱和度/排队 >0、`downstream_blocked=true`；缺失时 `metrics_available=false`、
  饱和度/排队为 `None`、`overflow_verification.risk_level=unknown`（不伪造 0）。
- 后端全量 `.venv/bin/python -m pytest tests/ -q` → **145 passed**；前端 `npm test` → **102 passed**、`npm run build` 通过。
- 线上须配置 `PG_DSN` 后以 Case 3 端到端复核下游真实饱和度呈现（本地无 PG，逻辑已单测覆盖）。
