# 回归测试规格 · 全功能点

> 版本：2026-06-28  
> 用途：新增功能 / 优化后回归，保证稳定性、一致性、正确性  
> 配套可视化：[`test-scenario-flowcharts.html`](./test-scenario-flowcharts.html) · [`TEST_SCENARIO_MATRIX.md`](./TEST_SCENARIO_MATRIX.md)

---

## 0. 测试分层

| 层级 | 范围 | 命令 | 频率 |
|------|------|------|------|
| L1 单元 | matcher / NLU / 规则 / 语音映射 | `pytest backend/tests/test_skill_matcher.py` · `npm test voiceStepSync` | 每次 PR |
| L2 集成 | Orchestrator + API + SSE | `pytest backend/tests/` | 每次 PR |
| L3 E2E 冒烟 | 健康 + 流式诊断 | `scripts/e2e-v2.sh` | 部署前 |
| L4 手工/Playwright | 三栏 UI + 地图 + TTS 实播 | 见 §9 | 大版本 |

**优先级**：P0 阻塞发布 · P1 核心回归 · P2 增强覆盖 · P3 边界/体验

---

## 1. 核心差异：初次沉淀 vs 技能复用

这是系统最容易出 bug 的区域。两条路径在**确认轮次、reply 类型、meta、前端步骤**上均有差异。

### 1.1 路径对照总表

| 维度 | 路径 A · 初次诊断（无 Skill） | 路径 B · 初次沉淀 Skill | 路径 C · 技能复用（快路径） |
|------|------------------------------|------------------------|---------------------------|
| **触发** | 首次问路口，库中无 Skill | 路径 A + 用户确认固化 | 同路口第 N 次，match=true |
| **skill_match** | matched=false | matched=false | matched=true, source=skill_fast_path |
| **intersection 步骤** | 三级匹配 exact/variant | 同左 | **跳过解析**，用 Skill inter_id |
| **诊断** | 全量 _diagnose | 全量 _diagnose | 全量 _diagnose + `_filter_skill_rules` |
| **约束注入** | 仅用户 NLU 约束 | 固化时写入 Skill | Skill 有约束且用户无 → **自动注入** nlu.user_suggestion |
| **诊断后第一出口** | **零确认**：溯源后直接 DIAGNOSIS（无落点 generated / 有落点 generated_cross_intersection），state=done | 若首轮带约束 → 直接 DIAGNOSIS + awaiting_create | **始终** awaiting_generate (FOLLOW_UP) ⚠️ |
| **无约束（不固化）** | 直接 done + skipped_no_user_suggestion（主路径无 D1） | — | D1「是」→ **reused_no_persist** |
| **首轮带约束** | 生成后 awaiting_create → D2 | awaiting_create → D2 | D1 补充新约束 → awaiting_create → D2 |
| **D2 确认固化** | skill_created | skill_created | 仅 D1 补充新经验时进入 |
| **前端步骤 7** | 无（未固化） | 经验吸收 + 落盘动画 | 同 B；复用仅「是」时不展示 |
| **语音步骤 7** | 无 | absorption + skillBuild | 同 B 或跳过 |

⚠️ **路径不对称（P0 已测）**：自 2026-06-30 流量溯源重做起，路径 A（普通诊断）**主路径零确认**——溯源完成后直接生成（跨路口协调）治理建议、不再有 D1；无新增约束故不固化（skipped_no_user_suggestion），首轮带约束才进入 D2 固化确认。路径 C（Skill 复用快路径）**仍始终 D1**（受技能固化语义保护，见 RT-REUSE / `.cursor/rules/regression-testing.mdc`）。

快路径**不再**使用 `verified` / `awaiting_update`（已删除 `_finish_fast_path_diagnosis` 死代码，2026-06-28）。

### 1.2 消息序列对照（Happy Path）

#### 路径 A · 初次诊断（无 Skill，零确认）

```
M1: 「路口+时段+方向」（无约束，如 奥体西路×经十路 晚高峰 南北向拥堵）
  → 自动溯源（南北向→南+北进口，逐路口运镜+转向拆分标注）
  → state=done, reply=DIAGNOSIS, suggestion 有值
  → meta.suggestion_action=generated_cross_intersection（无落点时 generated）
  → meta.skill_action=skipped_no_user_suggestion（不固化）
```

#### 路径 B · 初次沉淀（含约束）

```
M1: 「路口+时段+方向+约束」
  → state=awaiting_confirm, reply=DIAGNOSIS, skill_action=awaiting_create
M2: 「确认固化」
  → state=done, reply=skill_created
  → SSE: skill_absorption(6阶段) → skill_build → download_url
```

#### 路径 C · 复用（无新经验）

```
M1: 「路口+时段+方向」（无约束，Skill 已存在）
  → resolution_source=skill_fast_path, skill_reused=true
  → state=awaiting_confirm, reply=FOLLOW_UP, suggestion_action=awaiting_generate
M2: 「是」
  → state=done, skill_action=reused_no_persist, suggestion 有值
  → 无 skill_absorption / skill_build
```

#### 路径 C · 复用（补充新经验）

```
M1: 同 C-无约束
M2: 「是，垂直方向不能溢出」
  → state=awaiting_confirm, skill_action=awaiting_create, suggestion 有值
M3: 「确认固化」
  → skill_created 或 updated
```

---

## 2. 回归测试点目录

| 模块 | TC 前缀 | 条数 | § |
|------|---------|------|---|
| 会话与路由 | RT-ROUTE | 8 | §3 |
| 干线扫描 (已废弃) | RT-COR (已废弃) | — | §4 |
| 路口 / NLU | RT-NLU | 14 | §5 |
| 追问 | RT-FU | 10 | §6 |
| 单点诊断流水线 | RT-DIA | 12 | §7 |
| 二次确认 D1/D2 | RT-CONF | 14 | §8 |
| Skill 匹配 | RT-MATCH | 8 | §9 |
| 初次沉淀 | RT-Persist | 10 | §10 |
| 技能复用 | RT-REUSE | 12 | §11 |
| 经验吸收 SSE | RT-ABS | 8 | §12 |
| 前端理解过程 8 步 | RT-UI | 12 | §13 |
| 语音播报与步骤同步 | RT-VOICE | 16 | §14 |
| SSE 协议 | RT-SSE | 8 | §15 |
| 跨路径一致性 | RT-X | 8 | §16 |

---

## 3. RT-ROUTE · 会话与消息路由

| TC-ID | 优先级 | 前置 state | 输入 | 期望 state | 期望处理器 | 现有测试 |
|-------|--------|-----------|------|-----------|-----------|---------|
| RT-ROUTE-01 | P0 | idle | 任意 | 依意图 | handle_message 入口 | — |
| RT-ROUTE-02 | P0 | awaiting_confirm | 「是」 | done/awaiting_confirm | _handle_confirmation | test_api |
| RT-ROUTE-03 | P0 | nlu_incomplete | 补充字段 | processing/awaiting_confirm | _continue_nlu | test_nlu_follow_up |
| RT-ROUTE-04 | P1 | intersection_ambiguous | 选候选 | processing | _handle_candidate_pick | — |
| RT-ROUTE-05 (已废弃) | P1 | awaiting_corridor_pick | 选路口 | nlu_incomplete/processing | _handle_corridor_pick | — (已移除) |
| RT-ROUTE-06 (已废弃) | P1 | corridor_nlu_incomplete | 补时段 | awaiting_corridor_pick | _continue_corridor_scan | — (已移除) |
| RT-ROUTE-07 | P2 | done | 新提问 | processing | 重新进入 pipeline | — |
| RT-ROUTE-08 | P1 | idle | 非法 session | 404 | routes 404 | test_session_not_found |

**一致性断言**：同一 state 下，同步 `/messages` 与 SSE `/messages/stream` 最终 `result.data.state` 一致。

---

## 4. RT-COR · 干线扫描 [已于 06-30 版本移除废弃]

> **说明**：自 06-30 版本重构起，原干线拥堵扫描（`corridor_scan`）与路口选型（`corridor_pick`）相关流程与后端接口已被移除，相关自动化测试已清理。本组测试用例已废弃。

---

## 5. RT-NLU · 路口与自然语言理解

| TC-ID | 优先级 | 场景 | 期望 | 现有测试 |
|-------|--------|------|------|---------|
| RT-NLU-01 | P0 | 完整句（路口+时段+方向） | nlu.status=complete | test_nlu_complete |
| RT-NLU-02 | P0 | 缺方向 | incomplete, follow_up_field=directions | test_nlu_incomplete_missing_directions |
| RT-NLU-03 | P1 | 缺时段 | incomplete | test_nlu_incomplete |
| RT-NLU-04 | P1 | 缺路口 | incomplete | — |
| RT-NLU-05 | P1 | JSON 解析失败 | done, ERROR | — |
| RT-NLU-06 | P1 | 提取 user_suggestion | nlu.user_suggestion 非空 | test_nlu_extracts_user_constraint |
| RT-NLU-07 | P1 | 「垂直方向不能溢出」 | constraint 槽位 | test_nlu_extracts_vertical |
| RT-NLU-08 | P1 | 「绿灯感觉不够」 | **不**写入 user_suggestion | test_green_light_complaint |
| RT-NLU-09 | P2 | 多轮合并重提取 | raw_user_context 含全部 user 消息 | — |
| RT-NLU-10 | P1 | preserved nlu 合并（干线选型后） | 路口/时段不被覆盖 | _merge_preserved_nlu |
| RT-NLU-11 | P1 | 路口精确匹配 | resolution exact | — |
| RT-NLU-12 | P1 | 路口变体匹配 | resolution variant + note | — |
| RT-NLU-13 | P1 | 路口多候选 | intersection_ambiguous | — |
| RT-NLU-14 | P1 | 路口未找到 | done, ERROR + follow_up | test_intersection_not_found |

---

## 6. RT-FU · 追问

| TC-ID | 优先级 | 场景 | reply.type | 现有测试 |
|-------|--------|------|-----------|---------|
| RT-FU-01 | P1 | NLU 缺字段 | follow_up | test_nlu_follow_up |
| RT-FU-02 | P1 | 路口候选 | follow_up + candidates | — |
| RT-FU-03 | P1 | 路口未找到引导 | error/follow_up | test_intersection_not_found |
| RT-FU-04 (已废弃) | P1 | 干线 NLU 缺字段 | follow_up, intent=corridor_scan | — (已移除) |
| RT-FU-05 (已废弃) | P2 | 干线选型失败 | follow_up, intent=corridor_pick | — (已移除) |
| RT-FU-06 | P1 | D1 意图模糊 | follow_up, awaiting_generate | — |
| RT-FU-07 | P1 | D2 意图模糊 | follow_up, for_skill_confirm | test_intent_detector |
| RT-FU-08 | P2 | 问候语 | 自然 follow_up | test_greeting |
| RT-FU-09 | P2 | 单字段优先级 | 路口>时段>方向 | 文档/代码 |
| RT-FU-10 | P1 | 前端 panelMode | conversation 非 analysis | 手工 |

---

## 7. RT-DIA · 单点诊断流水线

| TC-ID | 优先级 | 场景 | 期望 | 现有测试 |
|-------|--------|------|------|---------|
| RT-DIA-01 | P0 | 诊断成立 | matched_rules 非空 | test_full_flow |
| RT-DIA-02 | P0 | 规则未命中 | reason_code=no_rule_matched | test_rule_engine |
| RT-DIA-03 | P0 | DWS 缺失 | missing_dws_coverage | — |
| RT-DIA-04 | P1 | problem_evidence SSE | chronic/dow/by_direction | test_sse |
| RT-DIA-05 | P1 | flow_timing_governance | 四类问题标签 | test_flow_timing_governance |
| RT-DIA-06 | P1 | 约束量化 | quantitative_constraints | test_constraint |
| RT-DIA-07 | P1 | 7 日 data_window | meta.data_window.type=rolling_7d | test_api |
| RT-DIA-08 | P2 | DEMO_MODE | meta.demo_mode=true | demo_config |
| RT-DIA-09 | P1 | 确认文案不含治理动作 | _diagnosis_only_conclusion | test_problem_confirm_message |
| RT-DIA-10 | P1 | delta 约束裁剪 | clip_note in narrative | test_saturation_cap |
| RT-DIA-11 | P2 | 配时画像 | timing_profile in payload | — |
| RT-DIA-12 | P2 | 干线上下文 | corridor_context | — |
| RT-DIA-13 | P0 | 转向饱和度最高优先 | headline 饱和度取 by_turn AVG 转向的最大值，非全局 MAX | test_saturation_granularity.py |
| RT-DIA-14 | P0 | 车道级饱和度降级 | 转向级数据缺失时回退到 by_lane 的 lane_saturation | test_saturation_granularity.py |
| RT-DIA-15 | P1 | 路口级饱和度降级 | 转向级和车道级均缺失时回退到路口级 | test_saturation_granularity.py |
| RT-DIA-16 | P0 | 证据指标对齐转向级 | problem_evidence 饱和度计算对齐 granularity.by_turn | test_problem_evidence_saturation.py |
| RT-DIA-17 | P1 | 流量 payload 自动覆盖 | apply_canonical_saturation_to_payload 覆盖 stale traffic_flow | test_saturation_granularity.py |

**SSE 步骤顺序（P1）**：

```
orchestrator.start → nlu → skill_match → intersection → intersection_cognition
→ data_fetch → [flow_trace highlight_flow_sources] → problem_evidence → rule_engine → [suggestion] → complete
```

---

## 7b. RT-FLOW · 流量溯源接入问题诊断（2026-06-29）

> 设计/计划：[`plans/2026-06-29-流量溯源接入问题诊断-开发计划.md`](plans/2026-06-29-流量溯源接入问题诊断-开发计划.md)
> 数据源：`xianchang.dws_tfc_inter_turn_flow_correlate_m`（月度·转向级·UPSTREAM）。
> 关键语义：`flow_share_ratio`＝途经率（多跳叠加，可 >100%），**非来车占比**。一跳＝同上游方位 coverage 最大者。
> 触发：分向饱和度 ≥ `flow_trace.trigger_saturation`(0.90) 的问题转向；演示路口 `011wwe28ctu00001`（奥体西路×经十路）。

| TC-ID | 优先级 | 场景 | 期望 | 现有测试 |
|-------|--------|------|------|---------|
| RT-FLOW-01 | P0 | by_turn 带方位编码 | by_turn 行含 dir8_code/turn_dir_no | test_data_fetcher::test_by_turn_keeps_dir8_and_turn_codes |
| RT-FLOW-02 | P0 | 一跳锁定 | 同方位多跳取最大 coverage | test_flow_trace_service::test_one_hop_lock_keeps_max_per_bearing |
| RT-FLOW-03 | P0 | 来源结构判定 | single/multi/local 分类正确 | test_flow_trace_service::test_classify_* |
| RT-FLOW-04 | P1 | 未达饱和阈值不触发 | available=false, reason=not_triggered | test_flow_trace_service::test_service_not_triggered* |
| RT-FLOW-05 | P1 | MOCK_DB 可产出 | available=true（演示兜底） | test_flow_trace_service::test_service_mock_db_builds_trace |
| RT-FLOW-06 | P1 | 思考过程 beat | diagnosis_story 含 flow_trace phase | test_problem_evidence_verdict::test_diagnosis_story_includes_flow_trace_beat |
| RT-FLOW-07 | P0 | 能力瓶颈→上游协调 | action_type=upstream_coordination，文案带路口名/「辆/100」 | test_governance_action_plan::test_upstream_coordination_* |
| RT-FLOW-08 | P1 | timing 可优化也补充上游维度 | flow_trace_supplement 非空，辆/100 口径 | test_governance_action_plan::test_flow_trace_supplement_* |
| RT-FLOW-09 | P1 | 地图动作 | highlight_flow_sources 含 entry_traces+沿路 path | test_map_presentation::test_flow_sources_action_* |
| RT-FLOW-10 | P1 | 地图左下摘要 | FlowTraceMapSummary 渲染 100 辆口径 narrative | FlowTraceMapSummary.spec.ts / flowTraceCopy.spec.ts |
| RT-FLOW-11 | P1 | 语音同步 | 问题诊断步命中溯源播 flowTrace 旁白 | voiceStepSync.spec.ts |
| RT-FLOW-12 | P1 | 主诊断富余阈值 | turn_balance 含 spare 绿利用 &lt;0.60 | test_flow_timing_governance::test_primary_timing_optimizable |
| RT-FLOW-13 | P1 | 进口道溯源 | build_entry_traces 100 辆归一化 | test_flow_trace_service::test_build_entry_traces_* |
| RT-FLOW-14 | P1 | 思考 beat 口径 | _flow_trace_beat_text 用 entry_traces narrative | test_problem_evidence_verdict::test_flow_trace_beat_* |

**口径红线**：文案禁用「贡献」「占比」，统一「途经/来自」；展示「近月同时段规律」。

## 7c. RT-TRACE · 单链路发光溯源重构（2026-06-30）

> 设计/计划：[`plans/2026-06-30-单链路发光溯源重构计划.md`](plans/2026-06-30-单链路发光溯源重构计划.md)
> 目标：流量溯源收口为「单一进口/转向一条链路（≤5 跳）」，地图以发光干线 + 流动粒子 + 节点脉冲 + 极简标签呈现，去除红色遮罩 / 虚线框 / 多方向同画 / 密集指标卡。

| TC-ID | 优先级 | 场景 | 期望 | 现有测试 |
|-------|--------|------|------|---------|
| RT-TRACE-01 | P0 | 用户明示进口/转向 | `_run_upstream_trace` 只溯该方向（approaches 仅该进口） | test_orchestrator_upstream_phase::test_user_direction_takes_priority |
| RT-TRACE-02 | P0 | 用户未指定方向 | 默认只聚焦诊断命中的首个（最饱和）问题进口一条链 | test_orchestrator_upstream_phase::test_no_user_direction_defaults_to_top_saturated |
| RT-TRACE-03 | P1 | 上游链路截断 | 节点/边/帧限制在 ≤5 跳 | upstreamStoryboard.spec.ts |
| RT-TRACE-04 | P1 | 粒子插值/采样 | interpolatePath/sampleAlongPath 端点夹紧、计数正确、时长夹紧 | traceParticles.spec.ts |
| RT-TRACE-05 | P1 | 左侧理解过程 | 「进口/转向 → 上游N」编号链路，无治理结论 | upstreamProcessText.spec.ts |
| RT-TRACE-06 | P1 | 画面去旧视觉 | 溯源期间无 .us-card/.us-dot/.us-ripple/.us-chip、无红色遮罩/虚线框 | scripts/verify-upstream-trace.mjs（截图验收） |
| RT-TRACE-07 | P0 | 拓扑一跳 | 西左转 @ 奥体西路×经十路：地图标签含「转山西路」（link 邻接，非 correlate 东侧误跳） | `test_upstream_topology.py` + verify `topo-hop-west-left` |
| RT-TRACE-08 | P0 | 禁飞线 | storyboard `edge.path` 来自 `dim_link_info.geom`；前端 `resolveEdgePath` 无两点 fallback；E2E 无 `.us-flyline` | `test_upstream_storyboard.py` + verify `geom-path-not-flyline` |
| RT-TRACE-09 | P1 | 粒子（软） | headless 下 `.us-particle` 可缺失，不作为阻断；实机以发光干线为准 | verify `has-particles`（非 gate） |

---

## 8. RT-CONF · 二次确认

### 8.0 主路径零确认（2026-06-30 流量溯源重做）

普通诊断路径（无 Skill 复用）不再有 D1 治理建议确认：溯源完成后自动生成建议。
仅当首轮带用户约束时进入 D2 固化确认；Skill 复用快路径仍走 §8.1 的 D1。

| TC-ID | 优先级 | 输入 | state | reply | meta | 现有测试 |
|---|---|---|---|---|---|---|
| RT-CONF-AUTO-01 | P0 | 路口+时段+南北向（无约束，过饱和触发溯源） | done | DIAGNOSIS | suggestion_action=generated_cross_intersection, skill_action=skipped_no_user_suggestion | test_first_diagnosis_auto_generates_cross_intersection |
| RT-CONF-AUTO-02 | P0 | 同上 | done | DIAGNOSIS | suggestion 有值, problem_evidence 齐备 | test_first_diagnosis_auto_generates_without_confirm |
| RT-CONF-AUTO-03 | P1 | 「…拥堵，绿灯感觉不够」（未给明确约束，user_suggestion=None） | done | DIAGNOSIS | skipped_no_user_suggestion | test_green_light_complaint_without_explicit_advice_auto_generates |
| RT-CONF-AUTO-04 | P1 | 纯诊断（无约束） | done | DIAGNOSIS | suggestion 有值, 不固化 | test_plain_diagnosis_generates_suggestion_without_skill |
| RT-CONF-AUTO-05 | P0 | 首轮即带约束 | awaiting_confirm | DIAGNOSIS | generated_with_user_suggestion → awaiting_create | test_diagnosis_with_constraint_generates_suggestion_then_awaits_skill_confirm |
| RT-MONITOR-01 | P0 | 低饱和路口+时段（basically_matched，无规则命中） | done | DIAGNOSIS | suggestion.rule_id=monitoring_feedback, skill_action=skipped_no_user_suggestion, 叙事卡+返回主页 | test_healthy_intersection_monitoring_feedback |

> RT-CONF-D1-01/02/03（旧普通路径 D1）已被本节取代（普通路径不再产出 awaiting_generate）；
> D1 语义现仅适用于 Skill 复用快路径（RT-CONF-D1-04~07）。

### 8.1 D1 · 治理建议生成（仅 Skill 复用快路径）

| TC-ID | 优先级 | 前置 | 用户回复 | state | meta | 现有测试 |
|-------|--------|------|---------|-------|------|---------|
| RT-CONF-D1-01 | P0 | 普通·无约束 | 「否」 | done | suggestion_action=declined | test_deny_suggestion |
| RT-CONF-D1-02 | P0 | 普通·无约束 | 「是」 | done | skipped_no_user_suggestion | test_plain_confirmation |
| RT-CONF-D1-03 | P0 | 普通·无约束 | 「是,+约束」 | awaiting_confirm | awaiting_create | test_confirmation_with_constraint |
| RT-CONF-D1-04 | P0 | 快路径 | 「是」 | done | **reused_no_persist** | test_fast_path_reuses |
| RT-CONF-D1-05 | P0 | 快路径 | 「是,+新约束」 | awaiting_confirm | awaiting_create | test_fast_path_supplement |
| RT-CONF-D1-06 | P1 | 快路径 | 「否」 | done | declined | — |
| RT-CONF-D1-07 | P1 | 任意 | 模糊 | awaiting_confirm | awaiting_generate | — |
| RT-CONF-D1-08 | P1 | D1 | extract 优先于 intent | 带约束文本即 confirm | — | orchestrator 逻辑 |

### 8.2 D2 · Skill 固化

| TC-ID | 优先级 | 前置 | 用户回复 | reply.type | meta.skill_action | 现有测试 |
|-------|--------|------|---------|-----------|-------------------|---------|
| RT-CONF-D2-01 | P0 | awaiting_create | 「确认」 | skill_created | created | test_full_flow |
| RT-CONF-D2-02 | P0 | awaiting_create | 「否」 | text | declined_create | test_declined_skill_create |
| RT-CONF-D2-03 | P1 | awaiting_create | 模糊 | follow_up | awaiting_create | — |
| RT-CONF-D2-04 | P1 | 重复 upsert | 「确认」 | text | unchanged | test_upsert_unchanged |

---

## 9. RT-MATCH · Skill 匹配逻辑

| TC-ID | 优先级 | 条件 | matched | reason | 现有测试 |
|-------|--------|------|---------|--------|---------|
| RT-MATCH-01 | P0 | inter+period+type 相同，无约束 | ✅ | matched | test_match_without_user_constraints |
| RT-MATCH-02 | P0 | 用户无约束，Skill 有约束 | ✅ | matched | test_match_without_user_constraints |
| RT-MATCH-03 | P0 | 约束相同 | ✅ | matched | test_match_with_same_constraints |
| RT-MATCH-04 | P0 | 约束冲突 | ❌ | constraint_mismatch | test_constraint_mismatch |
| RT-MATCH-05 | P0 | 用户新约束，Skill 无 | ❌ | constraint_mismatch | test_new_constraint_on_skill |
| RT-MATCH-06 | P1 | 方向不匹配 | ❌ | direction_mismatch | test_direction_mismatch |
| RT-MATCH-07 | P2 | match_keywords  gate | ❌ | no_skill | — |
| RT-MATCH-08 | P1 | 多 Skill 取最新 | created_at 降序 | — | 代码逻辑 |

**constraint_mismatch 后行为（P0）**：
- SSE skill_match: matched=false, reuse_notice 含说明
- resolution_source **≠** skill_fast_path
- 走完整 intersection 解析 + 普通诊断

---

## 10. RT-Persist · 初次技能沉淀

| TC-ID | 优先级 | 场景 | 断言 | 现有测试 |
|-------|--------|------|------|---------|
| RT-Persist-01 | P0 | 固化后目录结构 | SKILL.md + skill.meta.json + scripts | test_upsert_writes |
| RT-Persist-02 | P0 | tags 三层 | match/content/meta | test_build_skill_tags |
| RT-Persist-03 | P0 | tags.directions 写入 | meta.json | 技能沉淀计划 |
| RT-Persist-04 | P1 | user_constraints 持久化 | 与 nlu.user_suggestion 一致 | test_constraint_persisted |
| RT-Persist-05 | P1 | rule_ids + formula | content 层 | test_skill_package |
| RT-Persist-06 | P1 | quantitative_constraints | 写入 Skill | test_constraint |
| RT-Persist-07 | P1 | GET /skills 列表 | 含新 skill_id | test_list_skills |
| RT-Persist-08 | P2 | GET /skills/{id}/download | ZIP 可下载 | — |
| RT-Persist-09 | P1 | 无 user_suggestion 不触发 D2 | skipped_no_user_suggestion | test_plain_confirmation |
| RT-Persist-10 | P1 | 首轮带约束直接 D2 | awaiting_create 无 D1 | test_full_flow |

---

## 11. RT-REUSE · 技能复用（快路径）

| TC-ID | 优先级 | 场景 | 关键断言 | 现有测试 |
|-------|--------|------|---------|---------|
| RT-REUSE-01 | P0 | 二次同路口无约束 | skill_fast_path, skill_reused=true | test_fast_path_reuses |
| RT-REUSE-02 | P0 | 确认「是」无补充 | reused_no_persist, suggestion 有 | test_fast_path_reuses |
| RT-REUSE-03 | P0 | 确认带新约束 | awaiting_create | test_fast_path_supplement |
| RT-REUSE-04 | P0 | 约束冲突 | ≠ skill_fast_path | test_constraint_mismatch |
| RT-REUSE-05 | P1 | SSE skill_match matched=true | reuse_notice, tags | — |
| RT-REUSE-06 | P1 | 快路径拒绝 D1 | suggestion_action=declined | test_fast_path_deny_suggestion |
| RT-REUSE-07 | P1 | 注入历史约束 | nlu.user_suggestion 来自 Skill | test_fast_path_injects_historical_constraint |
| RT-REUSE-08 | P0 | 首轮带约束（与 Skill 同） | 仍 awaiting_generate | test_fast_path_with_same_constraint_still_awaits_d1 |
| RT-REUSE-11 | P1 | 复用后不固化无步骤 7 | 无 skill_absorption SSE | regressionSkillFlow.spec |
| RT-REUSE-12 | P1 | 复用+补充后固化 | skill_created/updated | test_fast_path_supplement |
| RT-REUSE-13 | P1 | 快路径命中递增 hit_count | leaderboard hit_count≥1 | test_fast_path_records_hit |

### 11.2 RT-SkillBoard · 技能排行榜

| TC-ID | 优先级 | 场景 | 关键断言 | 现有测试 |
|-------|--------|------|---------|---------|
| RT-SkillBoard-01 | P1 | GET /skills/leaderboard 空库 | `[]` | test_leaderboard_empty |
| RT-SkillBoard-02 | P1 | 固化后排行榜含 tags | hit_count=0, download_url | test_leaderboard_after_persist |
| RT-SkillBoard-03 | P1 | record_hit 递增 | meta.hit_count +1 | test_record_hit_increments |
| RT-SkillBoard-04 | P1 | upsert 保留 hit_count | 仍为 1 | test_upsert_preserves_hit_count |

---

### 11.1 复用 vs 初次 · 一致性检查清单（RT-X 引用）

每次改动 orchestrator / skill_matcher / App.vue 后必跑：

- [ ] RT-REUSE-01~04（快路径核心四件套）
- [ ] RT-Persist-10 + RT-REUSE-08（带约束不对称）
- [ ] RT-CONF-D1-02 vs RT-CONF-D1-04（skipped vs reused）
- [ ] RT-MATCH-04（冲突降级普通路径）

---

## 12. RT-ABS · 经验吸收与落盘 SSE

| TC-ID | 优先级 | 场景 | SSE 断言 | 现有测试 |
|-------|--------|------|---------|---------|
| RT-ABS-01 | P0 | 固化触发顺序 | absorption 全部 stage 在 build 之前 | test_message_stream_skill_absorption |
| RT-ABS-02 | P1 | 6 阶段顺序 | recap→decompose→retrieve→compare→value→blueprint | test_absorption_sse_stage_order |
| RT-ABS-03 | P1 | skill_build | drawer_open→file_chunk→done | test_execution_emitter |
| RT-ABS-04 | P2 | unchanged 缩短 | progress 100, action=unchanged | — |
| RT-ABS-05 | P1 | 前端 ExperienceAbsorptionPanel | active on start | useExperienceAbsorption.spec |
| RT-ABS-06 | P1 | SkillBuildDrawer L3 交错 | interleaved=true | — |
| RT-ABS-07 | P2 | download_url | skill_build_done 含 url | — |
| RT-ABS-08 | P2 | 文案无营销腔 | absorption_renderer | test_absorption_renderer |

---

## 13. RT-UI · 前端理解过程 8 步

| 步骤 | index | SSE 触发 | 证据揭示 | TC-ID |
|------|-------|---------|---------|-------|
| 理解描述 | 0 | nlu complete → beginAnalysisFlow | — | RT-UI-01 |
| 锁定路口 | 1 | intersection / skill_match notice | 摘要+查看详情 | RT-UI-02 |
| 路口结构 | 2 | cognition + narration links | link 明细折叠 | RT-UI-03 |
| 运行数据 | 3 | data_fetch + map narration | step_summary；MetricStrip 错峰 | RT-UI-04 |
| 问题印证 | 4 | problem_evidence | InsightStack 同步揭示 | RT-UI-05 |
| 原因诊断 | 5 | rule_engine + flow_timing | 配时环/绿波 auto 延后 | RT-UI-06 |
| 治理建议 | 6 | suggestion / confirm_bubble | — | RT-UI-07 |
| 经验固化 | 7 | skill_absorption + skill_build | 仅路径 B/C 有 D2 | RT-UI-08 |

| TC-ID | 优先级 | 场景 | 断言 | 现有测试 |
|-------|--------|------|------|---------|
| RT-UI-01 | P1 | NLU complete 才 beginAnalysisFlow | panelMode=analysis | — |
| RT-UI-02 | P1 | skill_match 经验命中 | summary 含历史约束；detail 含 Skill 明细 | presentationCopy.spec |
| RT-UI-03 | P1 | AnalysisQueue STEP_PAUSE_MS=2200 | 不抢跑 | constants |
| RT-UI-04 | P0 | 证据 buffer 延迟揭示 | patchEvidence vs reveal | card-timing-sync-plan |
| RT-UI-05 | P1 | 追问模式 | panelMode=conversation | — |
| RT-UI-06 | P1 | 干线侧栏 | CorridorScanSidebar visible | — |
| RT-UI-07 | P1 | reused_no_persist 无步骤 7 | 步骤 7 不出现 | **缺失** |
| RT-UI-08 | P1 | initSession 重置 | 清空证据/地图/voice | App.vue |
| RT-UI-09 | P2 | 渠化全屏 hideInputDock | 输入隐藏 | — |
| RT-UI-10 | P2 | prepareNewAnalysisRun | analysisRunKey++ | — |
| RT-UI-11 | P1 | onStepStart 仅首次 | 同 step append 不重复 | useUnderstandingProcess.spec |
| RT-UI-12 | P2 | 饱和度小数展示 | formatSaturation 0.92 | evidencePresentation.spec |
| RT-UI-13 | P1 | 呈现时序 gates | usePresentationSequence.spec | usePresentationSequence.spec |
| RT-UI-14 | P1 | 暂停 toast | 「分析暂停 · 空格继续」 | WorkbenchLayout |
| RT-UI-15 | P1 | 隐藏进口级饱和度 | 转向级数据存在时，叙事卡过滤掉进口级饱和度行 | narrativeStack.spec |
| RT-UI-16 | P1 | 进口道标签优先转向最大值 | 转向数据存在时，Arm 标签采用转向最大饱和度 | channelArmLabels.spec |

---

## 13b. RT-PAUSE-ABS · 经验吸收 / 固化暂停与流式呈现（2026-06-28）

| TC-ID | 优先级 | 场景 | 断言 | 现有测试 |
|-------|--------|------|------|---------|
| RT-PAUSE-ABS-01 | P0 | 流式事件分类 | `thought_delta`/`file_delta` 为 stream | skillPresentationDispatch.spec |
| RT-PAUSE-ABS-02 | P0 | pause gate 边界 | 仅 `stage_done`/`file_done` 入队 gate | skillPresentationDispatch.spec |
| RT-PAUSE-ABS-03 | P1 | 演示进行中判定 | `isSkillPresentationActive` | regressionSkillFlow.spec |
| RT-PAUSE-ABS-04 | P1 | 固化 gate 不等吸收 | `whenProcessAndVoiceSettled` | usePresentationBarrier.spec |
| RT-PAUSE-ABS-05 | P2 | 手工 | 吸收 trace 逐字 + 空格阶段暂停 | 彩排 |

详见 [2026-06-28-经验吸收技能固化空格暂停与呈现修复-复盘.md](./plans/2026-06-28-经验吸收技能固化空格暂停与呈现修复-复盘.md)

---

## 14. RT-PRES · 汇报向呈现（2026-06-28）

| TC-ID | 优先级 | 场景 | 断言 | 现有测试 |
|-------|--------|------|------|---------|
| RT-PRES-SUMMARY | P1 | narration SSE | step_summary ≤40 字 + focus_step_index | test_map_presentation.py |
| RT-PRES-SEQ | P1 | MetricStrip 错峰 | direction 步不揭示 strip | usePresentationSequence.spec |
| RT-PRES-COPY | P1 | Skill 复用文案 | formatSkillReuseLines | presentationCopy.spec |

---

## 15. RT-VOICE · 语音播报与理解过程同步

### 14.1 步骤 ↔ 文案映射（必须与 voice_narration.json 一致）

| stepIndex | 理解过程标签 | configKey | 触发时机 | TC-ID |
|-----------|-------------|-----------|---------|-------|
| 0 | 理解描述 | guide.understand | onStepStart(0) | RT-VOICE-01 |
| 1 | 锁定路口 | templates.intersection | onStepStart(1)，**需 intersectionName** | RT-VOICE-02 |
| 2 | 路口结构 | guide.cognition | onStepStart(2) | RT-VOICE-03 |
| 3 | 运行数据 | guide.dataFetch | onStepStart(3) | RT-VOICE-04 |
| 4 | 问题印证 | guide.evidenceIntro | onStepStart(4) | RT-VOICE-05 |
| 5 | 原因诊断 | guide.ruleIntro | onStepStart(5) | RT-VOICE-06 |
| 6 | 治理建议 | guide.suggestionConfirm | onStepStart(6) | RT-VOICE-07 |
| 7 | 经验固化 | **无 guide**（null） | 见 absorption/build | RT-VOICE-08 |

| TC-ID | 优先级 | 场景 | 断言 | 现有测试 |
|-------|--------|------|------|---------|
| RT-VOICE-01 | P1 | PROCESS_STEP_VOICE_MAP 完整 | 每 index 有 guide | voiceStepSync.spec |
| RT-VOICE-02 | P1 | 步骤 1 无路口名不播 | resolve 返回 null | voiceStepSync.spec |
| RT-VOICE-03 | P1 | rememberIntersectionName 触发步骤 1 | 匹配后立即播 | App.vue |
| RT-VOICE-04 | P1 | 同 step 不重复播 | voiceSentForStep Set | App.vue + spec |
| RT-VOICE-05 | P1 | 新分析 run 清空 | voiceSentForStep.clear | prepareNewAnalysisRun |
| RT-VOICE-06 | P1 | 关闭开关不 enqueue | enabled=false | useVoiceNarration |
| RT-VOICE-07 | P2 | interrupt 新 run | sessionEpoch++ | useVoiceNarration |
| RT-VOICE-08 | P1 | 步骤 7 无 processStepVoice | resolve(SKILL)=null | voiceStepSync.spec |
| RT-VOICE-09 | P1 | absorptionStart | skill_absorption_start | App.vue |
| RT-VOICE-10 | P1 | 6 阶段 stage 文案 | ABSORPTION_STAGE_VOICE | voice_narration.json |
| RT-VOICE-11 | P1 | absorptionDone | skill_absorption_done | App.vue |
| RT-VOICE-12 | P1 | skillBuildStart/Done | skill_build events | App.vue |
| RT-VOICE-13 | P2 | TTS PCM 流 | POST /tts/synthesize/stream | test_tts_stream |
| RT-VOICE-14 | P2 | TTS 关闭不影响诊断 | 后端无 TTS 依赖 | 架构约束 |
| RT-VOICE-15 | P2 | 模板播报 saturation/ruleHit | templates.* | — |
| RT-VOICE-16 | P1 | **复用路径无步骤 7 语音** | 无 absorption 事件则不播 | **缺失** |

### 14.2 语音同步时序（回归时手工听感或 mock 断言）

```
nlu complete
  → enqueueProcess(0) → onStepStart(0) → 播 guide.understand
intersection 完成 / rememberIntersectionName
  → onStepStart(1) → 播 templates.intersection(name)
… 步骤 2~6 同理，各仅一次 …
确认固化
  → skill_absorption_start → 播 absorptionStart
  → stage_start × 6 → 播 absorption[stage]
  → skill_absorption_done → 播 absorptionDone
  → skill_build_start → 播 skillBuildStart
  → skill_build_done → 播 skillBuildDone
```

**禁止**：步骤 index 与语音 configKey 错位；步骤 7 理解过程面板与 absorption 语音不同步。

---

## 15. RT-SSE · 协议与事件

| TC-ID | 优先级 | 场景 | 断言 | 现有测试 |
|-------|--------|------|------|---------|
| RT-SSE-01 | P0 | Content-Type | text/event-stream | test_message_stream |
| RT-SSE-02 | P0 | 事件类型齐全 | step/result/error/done | test_sse |
| RT-SSE-03 | P1 | 快路径 skill_match 数据 | matched, tags, reuse_notice | — |
| RT-SSE-04 | P1 | problem_evidence step | data 含 chronic/dow | test_sse |
| RT-SSE-05 | P1 | map_action 序列 | fly_to/highlight/narration | — |
| RT-SSE-06 | P1 | confirm_bubble | action_type generate/create | — |
| RT-SSE-07 | P2 | done 终止 | 流结束 | test_sse |
| RT-SSE-08 | P2 | error 事件 | 异常不挂死 | — |

---

## 16. RT-X · 跨路径一致性（发布前必跑）

| TC-ID | 优先级 | 检查项 | 期望 |
|-------|--------|--------|------|
| RT-X-01 | P0 | 同输入 sync vs stream | state/reply/meta 一致 |
| RT-X-02 | P0 | 快路径 vs 普通诊断数据 | 同一 inter_id 诊断结论同规则集（filter 后） |
| RT-X-03 | P0 | reused_no_persist ≠ skipped | meta.skill_action 字段不同 |
| RT-X-04 | P1 | 带约束：普通跳过 D1，快路径不跳过 | 文档化差异或修复后统一 |
| RT-X-05 | P1 | constraint_mismatch 后 meta | skill_reused=false |
| RT-X-06 | P1 | 固化后再问：必走 fast_path 或 no_skill | 不应 middle state |
| RT-X-07 | P2 | DEMO_MODE 与非 DEMO 同结构 | 仅 data 锚定不同 |
| RT-X-08 | P1 | initSession 后可再问 | state 回 idle |

---

## 17. 覆盖率与缺口

### 17.1 已有 pytest / vitest（119 + 24 项）

| 模块 | 文件 | 覆盖 TC |
|------|------|---------|
| 快路径 | test_skill_fast_path.py | RT-REUSE-01~04 |
| 匹配 | test_skill_matcher.py | RT-MATCH-01~06 |
| 确认 | test_api.py | RT-CONF-D1/D2 大部分 |
| 干线 (已废弃) | — | — |
| SSE | test_sse.py | RT-SSE-01~04, RT-ABS-01 |
| 语音映射 | voiceStepSync.spec.ts | RT-VOICE-01~02, 08 |
| 步骤触发 | useUnderstandingProcess.spec.ts | RT-UI-11 |

### 17.2 P0 缺口补齐记录（2026-06-28）

| TC-ID | 测试文件 |
|-------|---------|
| RT-REUSE-07 | test_fast_path_injects_historical_constraint_on_confirm_yes |
| RT-REUSE-08 | test_fast_path_with_same_constraint_still_awaits_d1 |
| RT-UI-07 / RT-VOICE-16 | regressionSkillFlow.spec.ts |
| RT-CONF-D2-02 | test_declined_skill_create |
| RT-REUSE-06 | test_fast_path_deny_suggestion_declines |



---

## 18. CI 回归命令

```bash
# L1+L2 后端全量
cd backend && pytest tests/ -q

# 前端单元
cd frontend-v2 && npm test

# P0 快路径 + 确认 + 匹配 子集
cd backend && pytest tests/test_skill_fast_path.py tests/test_skill_matcher.py \
  tests/test_api.py::test_plain_confirmation_generates_suggestion_without_skill \
  tests/test_api.py::test_confirmation_with_constraint_generates_suggestion_then_awaits_skill_confirm \
  -q

# L3 冒烟
./scripts/e2e-v2.sh
```

---

## 19. 变更影响矩阵（新增功能时用）

| 改动模块 | 必跑 TC 组 |
|---------|-----------|
| orchestrator.py | RT-ROUTE, RT-CONF, RT-REUSE, RT-X |
| skill_matcher.py | RT-MATCH, RT-REUSE, RT-X-05 |
| skill_service / package_builder | RT-Persist, RT-ABS |
| nlu_service | RT-NLU, RT-FU |
| corridor_* (已废弃) | — |
| App.vue / usePresentation | RT-UI, RT-VOICE |
| voice_narration.json | RT-VOICE 全组 |
| execution_emitter | RT-SSE, RT-DIA |
| follow_up_service | RT-FU |

---

## 20. 文档索引

| 文档 | 内容 |
|------|------|
| [技能沉淀与匹配逻辑开发计划.md](./plans/技能沉淀与匹配逻辑开发计划.md) | 匹配规则、meta 约定、流程改造 |
| [TEST_SCENARIO_MATRIX.md](./TEST_SCENARIO_MATRIX.md) | TC-ID 与状态机 |
| [test-scenario-flowcharts.html](./test-scenario-flowcharts.html) | 可视化流程 |
| [frontend-v2/docs/ARCHITECTURE.md](../frontend-v2/docs/ARCHITECTURE.md) | 三栏与证据时序 |
| [backend/docs/API.md](../backend/docs/API.md) | API 与 meta 字段 |
