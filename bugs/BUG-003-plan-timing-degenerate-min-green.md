# BUG-003 方案配时塌缩为最小绿占位（优化器输入缺失真实需求）

- 状态：已修复
- 发现分支：`20260707215155-12-方案生成配时优化对齐参考项目`
- 关联需求/计划：`needs/12` / `plans/12`

## 现象

路口「经十路与转山西路路口」晚高峰，PG 现状配时真实可用（cycle 130，绿 60/12/49，最小绿 35/12/35），
但三个候选方案配时全部塌缩为 `cycle=42`、三阶段各 `14s`、`split=0.333`、`phase_saturation=None`、无优化元数据。
对比参考项目 `traffic_signal_deepagent` 的可信配时，当前项目相当于"无有效配时结果"。

## 根因

方案配时链路把真实需求丢失，`signal_optimization_engine` 只能塌缩到默认机动车最小绿 14s：

1. `app/optimization/request_builder.py::_build_phase_plan` 用占位流量 `turnFlowTotal ... or 500`、车道 `or 2`，
   且每阶段仅生成单个 `phaseDirInfoDTOList`（多转向合并阶段只取其一）；真实 `raw.turn_flow`/`turn_saturation` 从未绑定。
2. 请求只发送 `minGreenTime/greenTime`，而引擎 `_stage_min_green_s` 只认 `greenBounds.minGreenS` / `min_green_s` /
   `currentTiming.greenSec`，三者皆未发送 → 回落默认最小绿 14s，历史绿稳定性下限（>30s 取 60%）也因缺 `currentTiming` 未触发。
3. 优化输出未回填逐相位饱和度与 `meta`（强度/solver）。
4. 退化结果未被识别，占位配时被当作成功方案返回（违反 `docs/rule.md` 14/16）。
5. `plan.recommended_plan_id` 顶层缺失，前端取不到推荐方案。

## 修复

1. 新增 `app/data/turn_flow_binding.py::bind_turn_flows_to_signal`，在 `_assemble_task_from_raw` 把真实
   逐转向流量（时段均值 vph）、饱和度、车道绑定到 `signal.phase_stage_timing_list[].phaseDirInfoDTOList`，
   多转向阶段展开；绑不到真实流量的转向标注 `flow_available=false`，`signal.flow_binding` 记录降级原因。
2. 重写 `request_builder._build_phase_plan`：下发 `currentTiming`（现状绿）+ `greenBounds`（真实最小/最大绿）+
   `min_green_s`，去掉占位流量/写死车道，多转向展开；无法定位方向的转向不下发。
3. `run_single_point_optimizer` 回填每阶段 `phase_saturation` 与顶层 `timing.meta`（solver/max_phase_saturation/
   total_turn_flow_vph/direction_intensity_list）。
4. 退化护栏 `_degradation_reason`：绑定失败 / `total_turn_flow_vph<=0` / 无逐相位饱和度 → 判退化，
   `build_candidates` 回退真实现状配时调整（`adjust_phase_timing`）并透传 `optimizer_degraded_reason`，
   不以塌缩占位冒充优化结果。
5. `handler` + `response_builder` 补齐顶层 `recommended_plan_id`。

## 验证

- 真实 PG 端到端（经十路与转山西路路口，晚高峰）：`flow_binding.ok=true`、`total_flow_vph=7044`，
  优化输出 `cycle≈98~108`、绿灯 `36/12/35`~`38/20/35`（均≥真实最小绿）、逐相位饱和度 0.75~0.87、
  `solver=scipy_slsqp_document_model`，无退化。
- 重采 `frontend/src/mock/run_1_fixture.json`：配时不再 14/14/14，带饱和度与 meta，`recommended_plan_id=downstream_protection`。
- 单测：`tests/test_turn_flow_binding.py`(5)、`tests/test_request_builder.py`(4)、`tests/test_plan_optimizer_degradation.py`(6)；
  后端全量 `120 passed`，前端 `63 passed` + build 通过。
