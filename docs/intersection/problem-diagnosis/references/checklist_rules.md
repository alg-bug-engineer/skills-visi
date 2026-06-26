# 问题诊断 · 检查单规则与问题码映射

> **机器可读真源**：`skillpacks/intersection/common/diagnosis_checklist.yaml`  
> **统一阈值**：`skillpacks/intersection/common/thresholds.yaml`  
> 依据 `docs/算法设计文档/交通智能体问题检查单-0614.docx` §1.2 与 `docs/reference/PG_DATABASE_SCHEMA.md` §7。  
> 诊断脚本 **`run_diagnosis_checklist.py`** 按本检查单**逐项分析**场景画像，并在 `checklist_queries` 中同步标记检查状态与结论。

## 检索状态约定

| 状态 | 含义 |
| --- | --- |
| `passed` | 检查完成，未触发问题 |
| `triggered` | 检查完成，命中问题/风险 |
| `no_data` | 画像缺少关键字段，无法判定 |
| `error` | 检查脚本异常 |
| `skipped` | 前置条件不满足 |
| `pending` / `loading` | 前端流式进度占位 |

每项输出字段：

- `item_id`：检查单唯一标识
- `category`：`static` / `dynamic` / `special` / `summary`
- `label`：检查单描述（中文）
- `profile_field`：依据的画像字段路径
- `issue_codes`：关联问题码（命中时）
- `status` / `triggered` / `summary` / `evidence`

## 1. 静态问题检查单

| item_id | 检查单描述 | 问题码 | 触发线索 |
| --- | --- | --- | --- |
| `phase_channel_mismatch` | 相位相序与渠化是否匹配 | `phase_channel_mismatch` | 规则 A–D：阶段冲突、专用道保护、专用道无对应放行（见 `路口交通问题诊断方法.md` §1） |
| `lane_flow_mismatch` | 渠化设计与车流量是否匹配 | `lane_mismatch` | 分进口结构/运行规则 A–D（见 §2） |
| `funnel_effect` | 进出口是否存在漏斗效应 | `lane_mismatch` | 对向直行漏斗 A、进出口方向数 B（见 §3）；无车道明细时回退 `static_flags`/`funnel_details` |
| `adjacent_spacing` | 相邻路口间距过短 | `green_wave_break` | `static.adjacent_spacing_m` |
| `road_segment_interference` | 公交站点、单位出入口、强吸引点是否干扰路口运行 | `external_disturbance`、`downstream_blockage` | 场景认知 §1.3 `context.aoi_sources`：公交站、POI 出入口、学校/医院/商圈等强吸引源；补充 `driveway_spacing_m` 过近 |
| `slow_traffic_facilities` | 非机动车、行人过街、右转空间等慢行设施是否不足 | `pedestrian_protection_gap`、`phase_sequence_conflict` | 缺少非机动车道、斑马线过多、等待区不足、右转车道宽度不足 |

> 以下静态项因当前数据链路无法稳定获取，已从检查单与脚本中移除：转向车道长度、机非人冲突/等待区与清空、路口面积、公交线路集聚/靠站形态、路内停车或临停占道。

静态检查由 **`check_static_constraints.py`** 提供底层扫描，`run_diagnosis_checklist.py` 逐项输出结论。

## 2. 动态问题检查单

| item_id | 检查单描述 | 问题码 | 量化阈值 |
| --- | --- | --- | --- |
| `demand_pressure_perception` | 高饱和持续是否提示需求压力 | — | `saturation.high` + 连续 `demand.high_saturation_duration_h`（inter_evaluation 时序） |
| `spillback` | 排队溢出/锁死 | `spillback` | `spillback.risk_high`、`queue.queue_storage_ratio_high` |
| `downstream_blockage` | 出口停车/下游阻塞 | `downstream_blockage` | 溢流 + 施工/事故/出入口标签 |
| `service_imbalance` | 服务失衡 | `service_imbalance` | `imbalance.diagnosis` |
| `empty_green` | 空放/绿灯损失 | `empty_green` | `green.low_utilization_diagnosis` |
| `cycle_timing` | 周期过长/过短 | `cycle_timing_issue` | `cycle.max_s` 或 `cycle.min_s` |
| `plan_granularity` | 配时方案精细度不足 | `plan_granularity` | `plan.min_time_plans`、特殊日未覆盖 |

> 以下动态项因当前数据链路无法稳定获取，已从检查单与脚本中移除：需求超过通行能力（过饱和）、延误/停车偏高。

动态评分与排序由 **`score_intersection_issues.py`** 完成；检查单逐项给出命中状态与证据摘要。

## 3. 特殊需求与反馈

| item_id | 检查单描述 | 问题码 | 触发线索 |
| --- | --- | --- | --- |
| `special_demand` | 学校/医院/公交/货运/应急/施工 | `pedestrian_protection_gap`、`external_disturbance` | POI 标签、context_tags |
| `attractor_demand_pressure` | 强吸引点到达量是否超过路口承载能力 | `external_disturbance` | 强吸引点标签、`attractor.arrival_capacity_ratio_year1/2/3` |
| `public_complaint` | 投诉或现场调研 | `public_complaint` | complaints / field_survey 非空 |

## 4. 拥堵成因评分（cause_scores）

| item_id | 检查单描述 | 输出 |
| --- | --- | --- |
| `cause_scores` | 供给/需求/控制/秩序/事件/数据质量六维主因 | `cause_scores` 归一化 0–1 |

由 **`score_intersection_issues.py` → `_compute_cause_scores`** 计算；最后一项检查单汇总主因贡献。

## 5. 检查顺序与输出组装

脚本按 **静态 → 动态 → 特殊 → 成因汇总** 顺序逐项检查；每完成一项即写入 `checklist_queries`。全部完成后：

1. **`diagnose_signal_issues`**：合并问题列表、`priority_order`、`cause_scores`
2. **`summarize_diagnosis`**：生成 `diagnosis_insights` 与 `diagnosis_summary` 自然语言解读
3. **大模型组总结**（API 层）：依据检查单结论与问题排序生成最终 narrative

缺少关键画像字段时，对应项标记 `no_data`，并在 `uncertainty` 中说明降级原因。

## 6. 诊断优先级（检查单对齐）

1. 安全：相位冲突、慢行保护不足
2. 扩散：溢流、锁死、下游阻塞
3. 供需：需求压力感知、强吸引点到达压力
4. 效率：失衡、空放、周期不合理
5. 结构：渠化不匹配、路段侧干扰、慢行设施不足、方案精细度
6. 体验：投诉、专项保障

## 7. 信控优化上限判定

| 条件 | `control_improvement_ceiling` |
| --- | --- |
| 结构性短板 ≥ 2 项且无动态高杠杆问题 | `low` |
| 公交站点、出入口、强吸引点等路段侧干扰主导 | `none` 或 `low` |
| 慢行设施不足或右转空间受限主导 | `low`，安全校核优先 |
| 动态失衡/空放/周期问题为主 | `high` |
| 外部干扰或秩序问题主导 | `none` 或 `low` |
| 数据关键字段缺失 | 降级并输出 `uncertainty` |

## 8. 调用示例

```python
from run_diagnosis_checklist import iter_diagnosis_checklist, run_diagnosis_checklist

for event in iter_diagnosis_checklist(profile):
    if event["type"] == "checklist_item":
        item = event["item"]
        print(item["item_id"], item["status"], item["summary"])
    elif event["type"] == "complete":
        diagnosis = event["diagnosis"]
        print(diagnosis["cause_scores"])
```
