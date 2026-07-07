# 剧本字段 → API 路径对照表

供前端对接使用。所有路径基于 `POST /api/v1/agent/run` 的公开响应（经 `build_public_run_response` 整形），除非注明为独立 API。

## 通用约定

### 请求

```http
POST /api/v1/agent/run
Content-Type: application/json

{
  "user_input": "文化西路与舜华路交叉口，六点十分到六点半，东向西排队溢出到上游，优先避免下游继续外溢。",
  "trace_id": "可选，便于日志追踪",
  "task": {
    "metrics": {},
    "topology": {},
    "signal": {},
    "diagnosis_ticket": {}
  }
}
```

- `task` 可选。生产环境无 `PG_DSN` 时，须注入 `metrics` + `topology`（及方案阶段的 `signal`），否则对应 Skill 返回 `available: false`。
- 测试/演示可设 `ALLOW_DEMO_FALLBACK=true` 使用 `tests/fixtures/` 样例数据。

### 响应顶层结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `trace_id` | string | 全链路追踪 ID |
| `completed` | boolean | 流水线是否全部成功 |
| `diagnosis_ticket` | object | 第一幕诊断工单（与 `phases.intent.diagnosis_ticket` 相同） |
| `phases.intent` | object | 第一～二幕 |
| `phases.diagnosis` | object | 第三～五幕 |
| `phases.cause` | object | 第六幕 |
| `phases.strategy` | object | 第七幕 |
| `phases.plan` | object | 第八幕（完整） |
| `plan` | object | 第八幕精简子集 |
| `phase_results[]` | array | 各 Skill 执行 success / duration_ms / errors |

### 第九幕（独立 API）

```http
POST /api/v1/agent/plan/decision

{
  "trace_id": "...",
  "plan_id": "arterial_coordination",
  "decision": "accept | reject",
  "rejection_reason": "可选",
  "plan_snapshot": {},
  "diagnosis_ticket": {},
  "artifacts_summary": {}
}
```

---

## 第一幕：诊断工单

**屏幕**：左侧结构化诊断工单。

| 剧本字段 | API 路径 | 类型 | 备注 |
|----------|----------|------|------|
| 对象 | `diagnosis_ticket.object_type` | string | 如「路口」 |
| 路口 | `diagnosis_ticket.intersection_name` | string | |
| 路口 ID | `diagnosis_ticket.inter_id` | string | PG 匹配或显式注入 |
| 坐标 | `diagnosis_ticket.lng` / `lat` | number | |
| 时间 | `diagnosis_ticket.time_range` | string | 如「18:10—18:30」 |
| 时段 | `diagnosis_ticket.period` | string | 如「晚高峰」 |
| 方向 | `diagnosis_ticket.direction` | string | 如「东向西」 |
| 转向 | `diagnosis_ticket.movement` | string | 如「直行」 |
| 问题类型 | `diagnosis_ticket.problem_type` | string | 如「排队溢出」 |
| 约束 | `diagnosis_ticket.constraints` | string[] | 如「优先避免下游继续外溢」 |
| 诊断范围 | `diagnosis_ticket.diagnosis_scope` | string | |
| 治理目标 | `diagnosis_ticket.governance_goal` | string | |
| 匹配置信度 | `diagnosis_ticket.match_confidence` | number | 0–1 |
| 匹配方法 | `diagnosis_ticket.match_method` | string | explicit / fuzzy / reversed_order |
| 候选路口 | `diagnosis_ticket.match_candidates` | array | |
| 用户经验（需求3） | `phases.intent.user_experiences[]` | array | `experience_type`: cognitive / diagnostic / solution |

---

## 第二幕：落到真实路网

**屏幕**：地图缩放、上下游高亮、右侧识别步骤。

| 剧本字段 | API 路径 | 类型 | 备注 |
|----------|----------|------|------|
| 目标路口 | `phases.intent.spatial_scene.target` | object | `inter_id`, `inter_name`, `lng`, `lat` |
| 目标方向/转向 | `phases.intent.spatial_scene.target.direction` / `movement` | string | |
| 识别步骤（5 步） | `phases.intent.spatial_scene.recognition_steps[]` | array | `step`, `label`, `status` |
| 上游节点 | `phases.intent.spatial_scene.upstream_nodes[]` | array | 需 topology |
| 下游节点 | `phases.intent.spatial_scene.downstream_nodes[]` | array | |
| 高亮路径 | `phases.intent.spatial_scene.highlight_path` | array | 坐标点列 |
| 场景可用 | `phases.intent.spatial_scene.available` | boolean | 无拓扑时为 false |
| 文本空间对象（兼容） | `phases.intent.spatial_objects` | object | 上游/下游文字描述 |

**识别步骤文案对照**（`recognition_steps[].label`）：

1. 路口匹配完成  
2. 进口方向识别完成  
3. 转向关系识别完成  
4. 上下游拓扑识别完成  
5. 干线路径识别完成  

---

## 第三幕：溢出验证

**屏幕**：排队比、饱和度、绿灯利用率、时序趋势；中央判定文案。

| 剧本字段 | API 路径 | 类型 | 备注 |
|----------|----------|------|------|
| 排队长度 | `phases.diagnosis.metrics.queue_length_m` | number | |
| 进口道蓄车长度 | `phases.diagnosis.metrics.storage_length_m` | number | |
| 排队比 | `phases.diagnosis.metrics.queue_ratio` | number | ≥0.8 预警，≥1.0 溢出 |
| 饱和度 | `phases.diagnosis.metrics.saturation` | number | |
| 绿灯利用率 | `phases.diagnosis.metrics.green_utilization` | number | |
| 停车次数 | `phases.diagnosis.metrics.stop_count` | number | |
| 平均延误 | `phases.diagnosis.metrics.avg_delay_s` | number | |
| 连续时间片趋势 | `phases.diagnosis.metrics.time_series_trend` | string | |
| 溢出判定 | `phases.diagnosis.overflow_verification` | object | `verified`, `risk_level`, `message` |
| 问题成立 | `phases.diagnosis.problem_confirmed` | boolean | |
| 目标路口 | `phases.diagnosis.target_intersection` | object | |
| 数据来源 | `phases.diagnosis.data_source` | string | pg / task_injection / mock |
| 地图场景 | `phases.diagnosis.map_scenes` | object | 下游/干线地图 payload |

**中央判定文案**：`phases.diagnosis.overflow_verification.message`

---

## 第四幕：本路口放不出去 vs 下游接不住

**屏幕**：两分支判断、判据列表、倾向结论。

| 剧本字段 | API 路径 | 类型 | 备注 |
|----------|----------|------|------|
| 核心问答 | `phases.diagnosis.downstream_diagnosis.release_answer` | string | 「本路口放不出去」/「下游接不住」 |
| 场景编码 | `phases.diagnosis.downstream_diagnosis.scenario` | string | 如 `high_demand_downstream_blocked` |
| 叙事说明 | `phases.diagnosis.downstream_diagnosis.narrative` | string | |
| 判据列表 | `phases.diagnosis.downstream_diagnosis.judgment_criteria` | string[] | |
| 能否简单加绿 | `phases.diagnosis.downstream_diagnosis.can_simple_add_green` | boolean | |
| 专家问题 | `phases.diagnosis.downstream_diagnosis.expert_question` | string | |
| 瓶颈类型 | `phases.diagnosis.bottleneck_analysis.bottleneck_type` | string | |
| 下游指标 | `phases.diagnosis.downstream_metrics` | object | 含下游 `queue_ratio` 等 |
| 下游溯源 | `phases.diagnosis.downstream_trace` | object | 相邻路口、治理建议 |

---

## 第五幕：干线协调

**屏幕**：干线视图、上游控流判断、相位差匹配。

| 剧本字段 | API 路径 | 类型 | 备注 |
|----------|----------|------|------|
| 上游到达流量 | `phases.diagnosis.arterial_analysis.upstream_arrival_flow_vph` | number | |
| 上游放行强度 | `phases.diagnosis.arterial_analysis.upstream_release_intensity_vph` | number | |
| 目标进口剩余空间 | `phases.diagnosis.arterial_analysis.target_remaining_storage_m` | number | |
| 下游剩余承接空间 | `phases.diagnosis.arterial_analysis.downstream_remaining_capacity` | string | |
| 相位差匹配 | `phases.diagnosis.arterial_analysis.phase_offset_match` | string | |
| 是否上游控流 | `phases.diagnosis.arterial_analysis.need_upstream_metering` | boolean | |
| 是否下游先消散 | `phases.diagnosis.arterial_analysis.need_downstream_dissipation_first` | boolean | |
| 干线摘要 | `phases.diagnosis.arterial_analysis.summary` | string | |
| 来车溯源 | `phases.diagnosis.flow_trace.entry_traces[]` | array | |
| 干线地图 | `phases.diagnosis.map_scenes.arterial_analysis` | object | |

---

## 第六幕：成因判断 + 相似案例

**屏幕**：主因/次因/诱因、案例 A/B 卡片。

| 剧本字段 | API 路径 | 类型 | 备注 |
|----------|----------|------|------|
| 主因 | `phases.cause.cause_analysis.primary_cause` | string | LLM |
| 次因 | `phases.cause.cause_analysis.secondary_causes` | string[] | |
| 可优化点 | `phases.cause.cause_analysis.optimizable_points` | string[] | |
| 数据不足 | `phases.cause.cause_analysis.data_gaps` | string[] | |
| 约束（复述） | `diagnosis_ticket.constraints` | string[] | 成因块内不重复 |
| 成因排序 | `phases.cause.cause_ranking` | array | `dimension`, `label`, `score` |
| 确定性评分 | `phases.cause.cause_scores` | object | 六维 0–1 |
| 匹配案例数 | `phases.cause.case_cards.matched_count` | number | |
| 高度相似数 | `phases.cause.case_cards.high_similarity_count` | number | |
| 案例卡片 | `phases.cause.case_cards.cards[]` | array | `title`, `similarity`, `action`, `outcome`, `lesson` |
| 用户诊断经验 | `phases.cause.user_experience_refs[]` | array | 需求 3 |
| 证据摘要 | `phases.cause.evidence_summary` | object | |
| 需干线协调 | `phases.cause.arterial_coordination_needed` | boolean | |

---

## 第七幕：治理策略

**屏幕**：策略摘要、控制范围地图、案例经验引用。

| 剧本字段 | API 路径 | 类型 | 备注 |
|----------|----------|------|------|
| 策略原则 | `phases.strategy.strategy.principles` | string[] | 防溢流优先、下游保护等 |
| 推荐策略 | `phases.strategy.strategy.recommended` | string[] | |
| 硬约束 | `phases.strategy.strategy.hard_constraints` | string[] | |
| 触发/退出规则 | `phases.strategy.strategy.trigger_exit_rules` | object | |
| 不推荐策略 | `phases.strategy.strategy.not_recommended` | string[] | |
| 策略包 | `phases.strategy.strategy_package` | string | downstream_protection / incremental_release / arterial_coordination |
| 优化器契约 | `phases.strategy.strategy_instruction` | object | 供方案生成使用 |
| 控制范围地图 | `phases.strategy.control_scope_map` | object | 上游控流点、目标路口、下游保护节点 |
| 案例引用 | `phases.strategy.case_references` | object | `failure_lesson`, `success_lesson`, `matched_count` |
| 包评分 | `phases.strategy.package_scores` | object | |

---

## 第三幕补充：场景检查单

| 剧本字段 | API 路径 | 类型 | 备注 |
|----------|----------|------|------|
| 场景报告 | `phases.diagnosis.scenario_report` | object | 需 PG/checklist |
| 检查项 | `phases.diagnosis.scenario_report.issues[]` | array | `item_id`, `label`, `status`, `summary` |

---

## 第八幕：可执行方案

**屏幕**：三候选方案、推荐结论、护栏与回滚。

### 精简块 `plan`（推荐列表页使用）

| 剧本字段 | API 路径 | 类型 | 备注 |
|----------|----------|------|------|
| 候选方案列表 | `plan.candidates[]` | array | 见下表 |
| 推荐方案 | `plan.recommended` | object | 与某一 candidate 同构 |
| 推荐理由 | `plan.recommendation.rationale` | string | |
| 推荐 plan_id | `plan.recommendation.recommended_plan_id` | string | |
| 回滚条件 | `plan.rollback_conditions` | string[] | |
| 配时来源 | `plan.signal_source` | string | pg / task_injection / mock |
| 优化引擎 | `plan.optimizer_engine` | string | |
| 全部过护栏 | `plan.all_guardrails_passed` | boolean | |

### 完整块 `phases.plan`

| 剧本字段 | API 路径 | 类型 | 备注 |
|----------|----------|------|------|
| 推荐 plan_id | `phases.plan.recommendation.recommended_plan_id` | string | |
| 推荐理由 | `phases.plan.recommendation.rationale` | string | |
| 用户方案经验 | `phases.plan.user_solution_refs[]` | array | |
| 已接受方案溯源 | `phases.plan.accepted_plan_refs[]` | array | `trace_id`, `plan_id` |
| 否决规避 | `phases.plan.rejected_plan_avoidance[]` | array | |

### 每个候选 `candidates[]` / `plan.recommended`

| 剧本字段 | API 路径 | 类型 | 备注 |
|----------|----------|------|------|
| 方案 ID | `plan_id` | string | downstream_protection / incremental_release / arterial_coordination |
| 方案名称 | `name` | string | |
| 状态 | `status` | string | valid / rejected / needs_review |
| 适用场景 | `scenario` | string | |
| 周期 | `timing.cycle_s` | number | |
| 相位配时 | `timing.phase_stage_timing_list[]` | array | 见下行 |
| 单相位绿灯 | `phase_stage_timing_list[].green_time_s` | number | |
| 黄灯 | `phase_stage_timing_list[].yellow_time_s` | number | |
| 全红 | `phase_stage_timing_list[].all_red_time_s` | number | |
| 最小/最大绿 | `min_green_time_s` / `max_green_time_s` | number | |
| 上游控流 | `upstream_control` | object | `enabled`, `control_points[]` |
| 相位差 | `phase_offset_sec` | number | |
| 行人约束 | `pedestrian_constraints` | object | `satisfied`, `violations` |
| 下游风险 | `downstream_risk` | object | `level`, `reasons` |
| 预期效果 | `expected_effect` | string | |
| 风险提示 | `risk` | string | |
| 回滚条件 | `rollback_condition` | string | |
| 案例依据 | `case_basis` | object | `matched_cases`, `lesson` |
| 执行顺序 | `execution_order` | string[] | |
| 护栏通过 | `guardrail_pass` | boolean | |
| 校验错误 | `validation_errors` | string[] | |
| 否决风险警告 | `risk_warning` | string | 可选 |

**三方案与剧本对应**：

| plan_id | 剧本名称 |
|---------|----------|
| `downstream_protection` | 下游保护方案 |
| `incremental_release` | 目标路口小步释放方案 |
| `arterial_coordination` | 干线联控方案 |

---

## 第九幕：反馈沉淀

**屏幕**：接受/拒绝、意见填写、案例沉淀字段。

| 剧本字段 | API / 存储 | 状态 | 备注 |
|----------|------------|------|------|
| 接受方案 | `POST /agent/plan/decision` `decision=accept` | ✅ | 写入 `data/plan_feedback.jsonl` |
| 拒绝方案 | `decision=reject` + `rejection_reason` | ✅ | |
| 修改后再生成 | `POST /agent/plan/regenerate` | ✅ | 从 `restart_from` 起重跑 |
| 近期案例列表 | `GET /agent/cases` | ✅ | textbook / recommended / risk |
| 执行效果回填 | — | ❌ | 无 evaluation-feedback |
| 专家评价 | — | ❌ | |
| 推荐/风险案例标记 | `plan_feedback.retrieval` | ✅ | `as_recommended_case` / `as_risk_case` |
| 拓扑指纹 | `plan_feedback.fingerprint` | ✅ | |
| 用户经验入库 | `data/user_experience.jsonl` | ✅ | 第一幕 NLU 自动写入 |

---

## 执行状态栏（底部任务栏）

| 剧本元素 | API 路径 | 说明 |
|----------|----------|------|
| 当前阶段 | `phase_results[].phase` | intent / diagnosis / cause / strategy / plan |
| 本段是否完成 | `completed` | 本次请求执行段 |
| 全流水线完成 | `pipeline_complete` | 五段均已产出 artifact |
| 是否成功 | `phase_results[].success` | |
| 耗时 | `phase_results[].duration_ms` | |
| 错误 | `phase_results[].errors` | 失败时展示 |

流水线在某一 Skill 失败时 `completed=false`，后续 Skill 不执行。

---

## 路口加载与分步执行

```http
POST /api/v1/intersection/load
POST /api/v1/intersection/load/stream
POST /api/v1/agent/run        # 支持 skill_ids、stop_after
POST /api/v1/agent/plan/regenerate
GET  /api/v1/agent/cases
```

详见 `docs/前端集成指南.md`。

---

## 健康检查与配置

```http
GET /api/v1/health
```

| 字段 | 说明 |
|------|------|
| `llm_mock` | 是否使用 LLM mock |
| `model` | 当前 Qwen 模型 |

生产部署建议：`.env` 中 `ALLOW_DEMO_FALLBACK=false`、`LLM_MOCK=false`，并配置 `PG_DSN`。

---

## 相关文档

- 叙事原文：`docs/剧本.md`
- 项目进度：`docs/项目进度.md`
- 开发约束：`docs/rule.md`
