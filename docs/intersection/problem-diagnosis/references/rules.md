# 路口问题诊断参考规则

> 领域专家经验（静态/动态判别、信控问题识别、优先级、成因归因等）已集中收录于 [`../../common/路口专家经验规则.md`](../../common/路口专家经验规则.md)。本文侧重输出字段、问题码表与脚本约定。

## 目标

问题诊断阶段负责把路口画像中的供给、需求、运行状态、控制参数和外部环境转化为可排序的问题集合。诊断结论必须区分：

- 信控可改善问题：可通过周期、绿信比、相位相序、协调、触发控制等手段改善。
- 工程或秩序治理为主问题：受渠化、出入口、公交停靠、施工占道、违停等约束主导，信控只能缓解。
- 数据不确定问题：关键证据缺失或冲突，需要补采后再下结论。

## 与场景认知结果串联

问题诊断的输入应优先来自路口场景认知阶段保留的内部画像，而不是再次生成场景认知章节。`scenario_report` 主要面向前端展示，诊断侧只把它作为辅助说明；量化判断必须回链到内部画像、检查单检索结果或原始表。

| 诊断用途 | 优先读取字段 | 场景认知来源 |
| --- | --- | --- |
| 静态供给短板 | `supply_profile.channelization`, `supply_profile.lanes`, `supply_profile.static_flags`, `supply_profile.intersection_area_m2`, `supply_profile.adjacent_inter_spacing_m` | `scene_cognition` 的 `load_pg_context` 与 `identify_supply_profile` |
| 供需过载和渠化匹配 | `demand_profile.movement_volume`, `demand_profile.lane_volume`, `demand_profile.lane_utilization_cv`, `supply_profile.movement_capacity` | `identify_demand_profile` 与 `calculate_traffic_state` |
| 运行状态问题 | `traffic_state.saturation`, `traffic_state.queue_m`, `traffic_state.avg_delay_s`, `traffic_state.stop_count`, `traffic_state.spillback_risk`, `traffic_state.imbalance_index`, `traffic_state.green_utilization`, `traffic_state.empty_green_rate` | `calculate_traffic_state` |
| 信控适配问题 | `control_profile.current_cycle_s`, `control_profile.phase_splits`, `control_profile.phase_sequence`, `control_profile.time_plan_count`, `audit.signal_lane_mapping` | `identify_supply_profile` 与控制类 PG 检查项 |
| 外部干扰和特殊需求 | `context_tags`, `context.complaints`, `context.field_survey`, `context.aoi_sources` | `identify_demand_profile` 与上下文检查项 |
| 数据质量 | `quality_tags`, `validation_errors`, `uncertainty`, `evidence_chain` | 场景认知校验与关键指标解读 |

串联规则：

1. 上游 `checklist_queries` 中 `status=has_data` 的项目，可作为诊断证据的来源说明；诊断检查单中的 `profile_checklist_ref` 应指向对应场景认知检查项。
2. `evidence_chain` 中已有的指标解释应被复用到问题证据，不得把展示型总结改写成新的量化事实。
3. 场景认知只输出现状与规律，问题诊断才输出 `issue_code`、`root_cause`、`cause_scores` 和 `control_improvement_ceiling`。
4. 如果只拿到 `scenario_report` 而没有内部画像，静态/动态/信控检查项必须降级：能定性说明的写入 `uncertainty`，需要量化阈值的项标记 `no_data`。

## 诊断报告模板映射

专家报告可参考 `../../common/专家经验调试/交通路口问题诊断与指标解读报告模板.json` 组装。该模板已删除“场景特征速览”章节，章节从静态问题开始：

| 报告章节 | 主要来源 | 运行时字段 |
| --- | --- | --- |
| 第1章 静态问题诊断 | 静态检查单、`check_static_constraints.py`、场景认知供给画像 | `static_constraints`, `checklist_queries`, `issues` |
| 第2章 动态问题诊断 | 动态检查单、运行状态画像、上下文标签 | `traffic_state`, `context_tags`, `issues` |
| 第3章 单点信控问题诊断 | 控制画像、相位渠化映射、协调归属 | `control_profile`, `problem_source`, `control_improvement_ceiling` |
| 第4章 拥堵成因量化评分 | 问题排序和六维归因 | `cause_scores`, `root_causes` |
| 第5章 问题清单与优先级 | 问题集合与优先级排序 | `issues`, `priority_order` |

报告元信息中的 `sceneProfileRef` 只记录上游场景认知结果引用和消费字段，不作为章节输出。

## 输出字段

每个问题必须包含：

- `issue_code`：稳定问题码，同时保留 `code` 作为兼容字段。
- `name`：中文问题名。
- `severity`：`high`、`medium`、`low`。
- `score`：0 到 1 的排序分。
- `confidence`：0 到 1 的诊断置信度。
- `evidence`：指标证据数组，至少包含 `metric`、`value`、`threshold`、`source`。
- `root_cause`：主因判断。
- `control_leverage`：`high`、`medium`、`low`、`none`。
- `non_signal_suggestion`：非信控治理建议，若无则为空字符串。

阶段级输出必须包含：

- `issues`
- `priority_order`
- `root_causes`
- `uncertainty`
- `validation_errors`
- `problem_source`
- `control_improvement_ceiling`
- `cause_scores`：供给/需求/控制/秩序/事件/数据质量六维主因贡献（0–1 归一）
- `static_constraints`：静态短板扫描结果
- `data_source_gaps`：无法从场景认知画像、检查单或已知 PG 表定位来源的数据缺口清单

`data_source_gaps` 每条建议包含：

- `field`：缺失字段或指标。
- `used_for`：影响的诊断项或报告字段。
- `expected_source`：已知候选来源；未知时写 `unknown`。
- `fallback`：当前降级处理，如 `no_data`、`uncertainty` 或人工补采。

## 问题码与触发条件

阈值数字以 `skillpacks/intersection/common/thresholds.yaml` 为唯一真源；下表只列触发线索与阈值键。

| 问题码 | 问题 | 典型触发条件 | 信控改善空间 |
| --- | --- | --- | --- |
| `phase_sequence_conflict` | 相位相序或冲突风险 | `conflict.risk_high`、直左/机非/人车冲突标签 | 中到高，需安全校验 |
| `spillback` | 排队溢出或锁死风险 | `spillback.risk_high`、`queue.queue_storage_ratio_high` | 高，优先防锁死 |
| `service_imbalance` | 进口/流向/相位服务失衡 | `imbalance.diagnosis`、`imbalance.movement_saturation_gap`、连续 15 分钟超阈值 | 高 |
| `empty_green` | 绿灯损失或空放 | `green.low_utilization_diagnosis`、连续 15 分钟低于阈值 | 高 |
| `lane_mismatch` | 车道利用率低或渠化不匹配 | `static.lane_utilization_cv`、关键转向排队长但相邻车道空闲、导向与流量不匹配、进口能力比 < `organization.approach_capacity_ratio_low`、流向 V/C > `organization.movement_vc_ratio_high` | 低到中，常需渠化治理 |
| `manual_intervention` | 人工干预频繁 | `manual_intervention_count >= 3` 或人工接管标签 | 中 |
| `plan_granularity` | 配时方案精细度不足 | 时段方案数少、特殊日/学校/医院/活动未覆盖、时段内指标波动大 | 中 |
| `green_wave_break` | 上下游协调问题 | `green_wave_pass_rate`、`offset_deviation_s`、相邻路口排队传导 | 中到高 |
| `external_disturbance` | 外部干扰主导 | 违停、公交停靠、单位/小区出入口、强吸引点、施工占道、事故等事件标签 | 低，信控只做缓解 |
| `public_complaint` | 投诉或专项保障诉求 | `complaints` 非空或 `special_requests` 非空 | 中，需人工审核 |
| `phase_channel_mismatch` | 相位相序与渠化不匹配 | 专用车道无对应相位、静态扫描命中 | 低，常需渠化 |
| `cycle_timing_issue` | 周期过长/过短 | `cycle.max_s` 或 `cycle.min_s` | 中 |
| `downstream_blockage` | 下游阻塞/出口干扰 | 溢流 + 施工/事故/出入口标签 | 中 |
| `pedestrian_protection_gap` | 行人非机动车保护不足 | 学校/医院 POI、投诉 | 中 |
| `stable` | 运行基本稳定 | 无明显问题触发 | 低 |

## 优先级

排序应先看安全和扩散风险，再看效率和体验：

1. 相位冲突、人车/机非冲突等安全问题。
2. 溢流、锁死、下游阻塞。
3. 需求压力感知、关键进口持续排队。
4. 服务失衡、低效率、空放。
5. 车道渠化不匹配、人工干预、方案精细度。
6. 外部干扰、投诉体验和专项保障诉求。


## 不确定性

出现以下情况时必须写入 `uncertainty` 或 `validation_errors`：

- 缺少流量、能力、延误、排队、相位、车道利用率等关键字段。
- 指标互相冲突，例如饱和度很低但排队和延误长期很高。
- 问题由外部事件主导，但事件持续性、空间范围或责任边界不清。
- 相位冲突、机非冲突、人车冲突只有文本标签，没有轨迹或冲突点证据。
- 模板字段要求的诊断数据无法从场景认知内部画像、检查单或已知 PG 表映射时，同时写入 `data_source_gaps`。

## 数据来源缺口记录

以下模板字段目前没有稳定的单一来源，若任务输入、现场调研或后续数据表未提供，不应臆造：

| 模板字段 | 诊断用途 | 当前已知候选来源 | 缺口处理 |
| --- | --- | --- | --- |
| `staticDiagnosis.roadSegment[].issueType` 中公交站点设置 | 判断公交站点对通行影响 | 场景认知 §1.3 `context.aoi_sources`（公交站类型）、现场调研 | 无 §1.3 检索结果时记 `data_source_gaps` |
| `staticDiagnosis.roadSegment[].issueType` 中单位出入口密集 | 判断出入口扰动 | 场景认知 §1.3 POI 出入口、路段出入口 GIS、现场调研 | 无 POI 出入口记录时记 `data_source_gaps` |
| `staticDiagnosis.roadSegment[].issueType` 中非机动车专用道/斑马线数量 | 慢行设施短板 | 现场调研、道路设施 GIS、视频识别 | 无设施数据时只能写不确定性 |
| `supply_profile.driveway_spacing_m`、`road_class` | 判定出入口距交叉口是否过近 | 出入口 GIS、道路等级、现场调研 | 无距离或道路等级时仅保留出入口干扰标签 |
| `supply_profile.channelization[].width_m` | 判定右转或混行车道宽度不足 | 渠化台账、道路设施 GIS、现场测量 | 无宽度数据时只输出慢行冲突不确定性 |
| `conflictSafety.conflicts[].frequency` | 机非人冲突强度 | 视频轨迹、冲突识别、现场调研 | 只有文本标签时不得填写频次 |
| `conflictSafety.slowTrafficFacilities` | 慢行等待与保护 | 现场调研、设施 GIS | 缺安全岛/等待区字段时标记 `no_data` |
| `areaClearance.startupLoss.value` | 启动损失与清空效率 | 相位放行轨迹、排队启动观测、绿灯利用率辅助 | 无观测数据时不从周期直接推断 |
| `dynamicDiagnosis.supplyDemand.busLaneUtilization` | 公交专用道利用率 | 公交 GPS/刷卡/站点客流、车道级流量 | 当前 PG 字典未给出稳定公交专用道利用表 |
| `dynamicDiagnosis.supplyDemand.attractionQueueSpill[].spillLength` | 强吸引点出入口排队溢出 | 视频、现场调研、停车场/出入口排队数据 | 只有 AOI 时只能标记潜在诱因 |
| `orderManagement.illegalParking[].impactDegree` | 违停造成能力下降 | 违停事件、视频识别、现场调研 | 无占道时长和车道占用比例时不估算百分比 |
| `badDrivingBehavior[].frequency` | 加塞/违规变道频次 | 视频事件识别、现场调研 | 无事件检测时不填频次 |
| `incident[].emergencyResponse` | 应急处置效果 | 事件处置系统、警情/施工/活动台账 | 无处置记录时写未知 |

## 按场景类型分化规则

`scene_type` 由 `skillpacks/intersection/common/scene_type_rules.yaml` 解析，诊断阶段由 `classify_diagnosis_context.py` 应用：

| scene_type | 诊断侧重 | 默认信控上限 |
| --- | --- | --- |
| 单点配时优化 | 失衡、空放、过饱和 | high |
| 干线协调优化 | 绿波断裂、溢流传导 | medium |
| 区域拥堵治理 | 过饱和、下游阻塞 | low |
| 应急优先 | 溢流、外部干扰 | medium |

- 干线协调场景应提升 `green_wave_break` 排序权重，降低单点 `plan_granularity` 优先级。
- 区域治理场景静态短板 ≥2 且无高杠杆动态问题时，`control_improvement_ceiling` 应为 `low` 或 `none`。
- 应急场景 `problem_source` 优先判为 `external_disturbance`，不得将设施问题伪装成配时问题。

## 检查单与脚本

- 专家静态判定：`scripts/diagnosis_static_logic.py`（相位渠化 §1 规则 A–D、渠化流量 §2 规则 A–D、漏斗 §3 规则 A–B）
- 静态问题扫描：`scripts/check_static_constraints.py`
- 动态问题评分与成因量化：`scripts/score_intersection_issues.py` → `cause_scores`
- 完整检查单映射见 [checklist_rules.md](checklist_rules.md)

<!-- BEGIN AUTO-GENERATED: expert-compiler -->

## 专家经验编译产物

> 本节由 `tools/expert_compiler/compile_expert_experience.py` 依据 `common/路口专家经验规则.md` 生成。人工修改应回写专家源稿后重新编译。

### EXP-DIAG-002 动态供需失衡

- 类型：checklist_item, issue_code
- 现象：高峰小时流量接近或超过通行能力，节假日、开学日或强吸引点导致需求激增。
- 判别依据：饱和度, 交通量, 连续周期不清空, 主流向占比, 特殊时段或特殊吸引点标签。
- 适用边界：动态流量和能力证据可用。
- 不要误判为：静态渠化短板或外部事件主导。
- 运行时意图：由 `demand_pressure_perception`、`attractor_demand_pressure`、`cycle_timing` 等检查项覆盖，触发过饱和、需求失衡或特殊需求相关问题，并在成因维度中体现需求贡献。
- 目标产物：thresholds, rules_md, checklist_rules_md

### EXP-DIAG-003 交通秩序与外部事件干扰

- 类型：checklist_item, issue_code, scene_type_rule
- 现象：违停、双排停车、网约车和快递临停、公交停靠、施工、事故、恶劣天气、大型活动或临时管制会导致通行能力突降或需求突变。
- 判别依据：投诉台账, 现场调研, 施工事件, 事故标签, 公交站点, 出入口干扰, 天气或活动信息。
- 适用边界：外部扰动有上下文证据支撑。
- 不要误判为：单纯信控参数不适配。
- 运行时意图：优先判定为秩序或事件主导，降低信控优化上限，输出协同治理或应急策略建议。
- 目标产物：diagnosis_checklist, scene_type_rules, rules_md, checklist_rules_md

### EXP-DIAG-004 路口服务失衡

- 类型：checklist_item, threshold, issue_code
- 现象：各进口、流向或相位饱和度差异过大，部分方向持续排队或高饱和，其他方向空闲。
- 判别依据：失衡指数, 转向车流饱和度极差, 连续 15 分钟超阈值窗口, 车道利用率离散, 关键相位排队不清空。
- 适用边界：分进口、分流向或分相位运行数据可用。
- 不要误判为：下游阻塞或静态渠化短板单独主导。
- 运行时意图：由 `service_imbalance`、`lane_flow_mismatch` 等检查项覆盖，触发服务失衡问题，提升控制参数不适配成因贡献。
- 目标产物：thresholds, rules_md, checklist_rules_md

### EXP-DIAG-006 绿灯损失或空放

- 类型：checklist_item, threshold, issue_code
- 现象：某相位绿灯期间无车或少车通过，平峰或夜间沿用高峰方案，造成无效等待。
- 判别依据：空放率, 绿灯利用率, 启动损失, 时段方案数, 到达流量。
- 适用边界：绿灯利用率或相位放行观测可用。
- 不要误判为：因检测器缺测造成的假空放。
- 运行时意图：由 `empty_green`、`plan_granularity` 等检查项覆盖，触发空放或方案精细度问题，并保留数据质量不确定性。
- 目标产物：thresholds, rules_md, checklist_rules_md

### EXP-DIAG-007 相位相序与慢行保护

- 类型：checklist_item, issue_code, narrative_rule
- 现象：高冲突流向同相放行、左转专用车道无保护相位、全红清空与实际冲突不匹配、学校医院商圈慢行需求高。
- 判别依据：相位相序, 信号原子与车道映射, 冲突标签, 行人非机动车需求, 投诉或现场调研。
- 适用边界：冲突风险或慢行需求证据可用。
- 不要误判为：单纯效率问题；涉及安全时安全优先。
- 运行时意图：触发相位冲突或慢行保护不足问题，并提高安全类问题优先级。
- 目标产物：diagnosis_checklist, rules_md, script_draft, checklist_rules_md

### EXP-DIAG-009 诊断优先级

- 类型：narrative_rule, scene_type_rule
- 现象：多个问题同时出现时，需要先处理安全和扩散风险，再处理效率和体验。
- 判别依据：冲突风险, 溢流锁死, 下游阻塞, 过饱和, 服务失衡, 长排队, 空放, 方案精细度, 投诉和专项保障。
- 适用边界：诊断阶段已形成多个候选问题。
- 不要误判为：按单个分值机械排序。
- 运行时意图：优先级排序遵循安全、扩散、供需、效率、结构、体验的顺序。
- 目标产物：rules_md, scene_type_rules

<!-- END AUTO-GENERATED: expert-compiler -->
