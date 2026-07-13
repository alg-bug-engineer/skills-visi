# 计划 34 · 点/线典型路口 live 指标绑定与配时护栏一致性修复

> 需求：`needs/34-live指标绑定与配时护栏一致性修复.md`  
> 分支：`20260713111500-34-live指标配时一致性修复`  
> 当前阶段：仅完成分析与开发设计，尚未实施代码

## 一、实施原则

1. 先修确定性数据链，再调整LLM提示或叙事。
2. 目标movement、下游接收movement、激活配时快照贯穿全链路，禁止阶段间重新猜测。
3. 数据缺失或冲突时结构化失败，不使用demo或其他方向MAX兜底。
4. 护栏校验是推荐前置条件，LLM不得覆盖确定性校验结果。
5. 每个修复建立`bugs/`记录，日志携带trace id和关键业务ID。

## 二、预实施审计

实施前读取并对照：

- `bugs/BUG-002-flow-trace-sniff-period-inflation.md`
- `bugs/BUG-003-plan-timing-degenerate-min-green.md`
- `bugs/BUG-006-*`
- `app/metrics/traffic.py`
- `app/trace/topology.py`
- `app/trace/downstream_trace.py`
- `app/trace/downstream_diagnosis.py`
- 方案生成、优化器和guardrail聚合实现
- `references/intersection/`对应阶段实现口径

新增bug记录建议：

- `BUG-007-target-movement-metric-scope.md`
- `BUG-008-signal-plan-snapshot-drift.md`
- `BUG-009-guardrail-result-aggregation.md`
- `BUG-010-downstream-fact-narrative-divergence.md`

## 三、Phase 1 · 建立失败复现测试

### 1.1 目标指标作用域

用本次PG快照或脱敏fixture构造：

- 坤顺×奥体西：北直1.5446、北左1.2365；ticket北左。
- 解放东×奥体中：南左约1.76、南直约1.06；ticket南直。

断言目标`saturation`选择请求movement，而非approach MAX。

### 1.2 库容方向

构造北进口357.21m、东进口195.68m，断言北左只使用北进口库容；不存在北进口库容时返回不可用。

### 1.3 流量比例

复现跨时段聚合导致201.9%/286.39%，断言越界被阻断且不生成叙事。

### 1.4 配时和护栏

- 诊断60s、错误快照164s：断言方案阶段因快照不一致失败。
- `cycle_s=190,max_cycle_s=180`：断言候选失败、不可推荐、顶层未完成。
- 所有候选失败：断言`recommended_plan_id=null`。

## 四、Phase 2 · 修复movement上下文传递

### 2.1 标准化MovementContext

建立确定性结构：

```python
MovementContext(
    inter_id,
    dir8_code,
    turn_dir_no,
    movement_key,
    time_start,
    time_end,
    day_of_week,
)
```

由intent匹配完成后生成，传入诊断、下游追踪、流量追踪、策略、方案，不允许后续模块只根据中文方向再次解析。

### 2.2 指标查询与聚合

- movement查询优先使用`inter_id+dir8_code+turn_dir_no+时间窗`。
- 分离`target_movement_metrics`、`approach_metrics`、`intersection_metrics`。
- 保持当前前端兼容字段，但其值必须来自`target_movement_metrics`；新增`metric_scope`供审计。

### 2.3 库容证据

- 通过目标`dir8_code`关联`direction_spacing`。
- 输出方向、版本、link/spacing来源。
- 加入方向一致性断言和日志。

## 五、Phase 3 · 下游接收movement与统一事实

1. 用`exit_dir8_for_turn`计算出口。
2. 通过出口link真实`t_inter_id`确定直接下游。
3. 计算接收进口`receiving_dir8`及接收转向。
4. 查询下游同窗口指标。
5. 只生成一次`DownstreamCapacityDecision`。
6. `downstream_diagnosis`、cause、strategy、plan scenario、map scene均引用该对象。

补充一致性校验：

- `blocked=false`时禁止使用“接不住/承接不足”场景模板。
- `blocked=true`时禁止推荐持续单点增绿。
- 用户输入中的经验作为约束/假设保留，但数据库事实冲突时必须明确提示，不可覆盖事实。

## 六、Phase 4 · 流量追踪守恒修复

1. 对齐目标诊断时间窗，不允许混入全天或其他period。
2. 明确分母是目标入口到达量或目标转向流量。
3. 同一车辆路径去重，避免多link重复计数。
4. 汇总前校验`0<=share_pct<=100`。
5. 越界输出：

```json
{
  "available": false,
  "reason": "flow_share_out_of_range",
  "raw_share_pct": 286.39
}
```

6. 回归BUG-002，确保单时段与跨时段不会再次膨胀。

## 七、Phase 5 · 激活配时快照统一

### 5.1 SignalPlanSnapshot

诊断阶段解析一次激活方案并形成不可变快照：

- `snapshot_id`
- `inter_id`
- `plan_no`
- `effective_time_window`
- `cycle_s`
- `offset_s`
- 完整stage列表
- 数据源和查询时间

方案优化器只能消费该快照，不得自行选择另一套plan。

### 5.2 基线校验

- `cycle_s`与stage总时长差值应在配置容差内。
- 1s/3s片段必须确认是否为独立阶段；若为拆分片段先规范化再校验最小绿。
- 流量或车道数据缺失的movement不得静默生成饱和度；候选应降级或失败。

## 八、Phase 6 · 护栏与状态机修复

### 6.1 候选护栏

建立纯函数校验并返回逐条结果：

```text
min_green_pass
max_green_pass
max_cycle_pass
yellow_all_red_pass
pedestrian_clearance_pass
snapshot_consistency_pass
data_completeness_pass
```

`guardrail_pass=all(results)`，不得由LLM或候选模板提供。

### 6.2 推荐聚合

- 先过滤失败候选，再评分。
- 推荐对象必须在通过集合中。
- `all_guardrails_passed`按产品语义明确为“所有候选均通过”或“至少一个可推荐候选通过”；建议拆为：
  - `has_feasible_candidate`
  - `all_candidates_passed`
- 保留旧字段时给出唯一映射并增加契约测试。

### 6.3 流水线状态

定义状态表：

| problem_confirmed | healthy | feasible plan | completed |
|---|---|---|---|
| true | false | true | true |
| true | false | false | false，附无可行解 |
| false | true | 不生成 | true，健康结束 |
| false | false | 不生成 | false，诊断状态冲突 |

## 九、Phase 7 · 文案与契约同步

- 候选`scenario/rationale/risk`使用结构化事实插值，不允许固定写“下游接不住”。
- 更新`docs/剧本字段-API对照.md`中movement scope、配时快照、护栏和不可用状态。
- 前端只呈现后端事实，不增加纠错或数据合成逻辑。

## 十、测试计划

### 单元测试

- `test_target_movement_metric_binding.py`
- `test_direction_spacing_binding.py`
- `test_flow_share_conservation.py`
- `test_downstream_decision_consistency.py`
- `test_signal_plan_snapshot.py`
- `test_plan_guardrail_aggregation.py`
- `test_pipeline_completion_state.py`

### 集成测试

1. 点案例：北左→礼耕，验证movement、下游slack、小步释放和≤90s可行性。
2. 线案例：南直→坤顺×奥体中，验证下游blocked、上游溯源、干线推荐和≤180s护栏。
3. 无可行周期：必须返回结构化失败而不是伪通过。
4. 下游缺数：必须`UNKNOWN`，不得自动视作slack。

### 回归命令

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_target_movement_metric_binding.py -q
PYTHONPATH=. .venv/bin/python -m pytest tests/test_direction_spacing_binding.py -q
PYTHONPATH=. .venv/bin/python -m pytest tests/test_flow_share_conservation.py -q
PYTHONPATH=. .venv/bin/python -m pytest tests/test_downstream_decision_consistency.py -q
PYTHONPATH=. .venv/bin/python -m pytest tests/test_signal_plan_snapshot.py -q
PYTHONPATH=. .venv/bin/python -m pytest tests/test_plan_guardrail_aggregation.py -q
PYTHONPATH=. .venv/bin/python -m pytest tests/test_pipeline_completion_state.py -q
```

随后运行相关既有测试和完整后端测试集。

## 十一、live重采与验收

### 点案例

```bash
PYTHONPATH=. .venv/bin/python scripts/capture_typical_point_line_fixtures.py --live --case case_a
```

要求：严格证据校验，不使用`--relax-evidence`；目标为北左、下游礼耕、无比例越界、现状周期一致、候选≤90s或明确无可行解。

### 线案例

```bash
PYTHONPATH=. .venv/bin/python scripts/capture_typical_point_line_fixtures.py --live --case case_b
```

使用南进口直行准确 query（manifest `case_b`）调用真实链路；不得复用旧「北直」Case D 或已剔除的浆水泉 Case。要求目标南直、下游坤顺×奥体中、候选≤180s。

### 结果审计

- 保存完整public response与步骤日志到`logs/`，文件名带trace id。
- 生成新旧字段对比报告。
- 人工核对上下游空间关系、movement和配时stage。
- 通过后才更新典型案例文档和manifest。

## 十二、实施顺序与完成条件

| 阶段 | 内容 | 完成条件 |
|---|---|---|
| 1 | 失败复现 | 现有两个trace问题均有红测 |
| 2 | movement/库容 | 点、线目标指标均绑定正确 |
| 3 | 下游事实 | 诊断、策略、方案无反转文案 |
| 4 | 流量守恒 | 比例不越界，BUG-002回归通过 |
| 5 | 配时快照 | 诊断与方案基线一致 |
| 6 | 护栏/状态机 | 190>180必失败，无矛盾状态 |
| 7 | 契约/文案 | 文档、API、前端类型同步 |
| 8 | live重采 | 两例严格校验达到需求验收标准 |

## 十三、风险与回滚

| 风险 | 缓解与回滚 |
|---|---|
| movement严格绑定后部分历史案例变为缺数 | 返回结构化不可用；禁止回退进口MAX |
| 统一激活方案后方案数量下降 | 保留旧快照解析日志；不回退到跨方案拼接 |
| 严格护栏导致无推荐方案增多 | 正确呈现“约束下无可行解”；不得放宽护栏掩盖问题 |
| API字段变化影响前端 | 新字段先增量兼容，契约测试通过后再清理旧字段 |
| live受模型波动影响 | 核心判定全部确定性化；至少连续2次live结论一致后验收 |

回滚仅允许撤销本需求代码改动并恢复上一稳定版本；不得恢复已确认的错误MAX兜底、比例越界输出或护栏伪通过逻辑。
