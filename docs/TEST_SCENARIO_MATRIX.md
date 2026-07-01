# 自动化测试场景矩阵 · 全功能路径

> 版本：2026-06-28  
> 用途：E2E / 集成测试用例设计、Skill 快路径回归  
> 流程图可视化：[`test-scenario-flowcharts.html`](./test-scenario-flowcharts.html)  
> **完整回归规格（130+ 测试点）**：[`REGRESSION_TEST_SPEC.md`](./REGRESSION_TEST_SPEC.md)

---

## 1. 消息入口路由（handle_message）

每条用户消息按 **当前 session.state** 优先路由，与意图无关：

| 优先级 | 当前 state | 处理器 | 下一可能 state |
|--------|-----------|--------|----------------|
| 1 | `awaiting_confirm` | `_handle_confirmation` | `done` / `awaiting_confirm` / follow_up |
| 2 | `intersection_ambiguous` | `_handle_candidate_pick` | `processing` → `_diagnose` |
| 3 | `awaiting_corridor_pick` | `_handle_corridor_pick` | `nlu_incomplete` / `processing` |
| 4 | `corridor_nlu_incomplete` | `_continue_corridor_scan` | `corridor_nlu_incomplete` / `awaiting_corridor_pick` / `done` |
| 5 | `nlu_incomplete` | `_continue_nlu` → `_run_pipeline` | 同 NLU 流程 |
| 6 | `idle` / `done` | 意图分类 → 干线或单点 | 见下文 |

**idle/done 首轮分支：**

| 条件 | 下一 state | 流程 |
|------|-----------|------|
| 意图 = `corridor_scan` | `corridor_scanning` | `_run_corridor_pipeline` |
| 意图 = `intersection_diagnosis` | `processing` | `_run_pipeline` |

---

## 2. Skill 匹配决策树（match_skill）

前置：`inter_id` 已由 `resolve_with_context` 预解析。

```
candidates = skills WHERE inter_id ∧ problem_type ∧ time_period.label
├─ candidates 为空 → no_skill, matched=false
└─ 遍历 candidates（created_at 降序）
    ├─ directions 不兼容 → continue（试下一个）
    ├─ user_constraint 与 skill_constraint 不兼容 → constraint_mismatch, matched=false 【立即返回】
    ├─ match_keywords 不匹配 → continue
    └─ 全部通过 → matched=true, reason=matched
遍历结束仍无命中：
├─ nlu.directions 非空 → direction_mismatch
└─ 否则 → no_skill
```

### 约束兼容表（自动化断言）

| TC-ID | 用户 user_suggestion | Skill user_constraints | matched | reason |
|-------|---------------------|------------------------|---------|--------|
| SM-01 | 无 | 无 | ✅ | matched |
| SM-02 | 无 | 「绿灯应更长」 | ✅ | matched（诊断时注入历史约束） |
| SM-03 | 「绿灯应更长」 | 「绿灯应更长」 | ✅ | matched |
| SM-04 | 「绿灯不超过10秒」 | 「绿灯应更长」 | ❌ | constraint_mismatch |
| SM-05 | 「垂直方向不能溢出」 | 无 | ❌ | constraint_mismatch |
| SM-06 | 「东西向」方向 | Skill directions=南北向 | ❌ | direction_mismatch |
| SM-07 | 无匹配 keywords | Skill 有 match_keywords | ❌ | no_skill（跳过该 skill） |

---

## 3. _diagnose 出口决策树（诊断成立后）

```
diagnosis.diagnosed && matched_rules 非空？
├─ NO → state=done, reply=TEXT, reason_code
└─ YES
    ├─ skill_reuse_mode=true 【快路径】
    │   ├─ 注入：skill 有约束且 nlu 无 user_suggestion → 写入 nlu.user_suggestion
    │   ├─ _filter_skill_rules(diagnosis, skill.rule_ids)
    │   └─ 【始终】state=awaiting_confirm
    │       pending_suggestion_action=generate
    │       reply=FOLLOW_UP（非 DIAGNOSIS）
    │       meta: skill_reused=true, suggestion_action=awaiting_generate
    │
    ├─ nlu.user_suggestion 非空 【普通路径·首轮带约束】
    │   └─ 直接 _generate_suggestion_content
    │       → _await_skill_create_confirmation
    │       state=awaiting_confirm, skill_action=awaiting_create
    │       reply=DIAGNOSIS（含建议正文）
    │
    └─ 无 user_suggestion 【普通路径·标准】
        └─ state=awaiting_confirm
            pending_suggestion_action=generate
            reply=FOLLOW_UP
            meta: suggestion_action=awaiting_generate
```

### ⚠️ 已知不对称（快路径疑似 bug 区）

| 场景 | 普通路径 | 快路径 | 是否一致 |
|------|---------|--------|---------|
| 首轮带 user_suggestion | 跳过 D1，直接出建议 + D2 | 仍走 D1（awaiting_generate） | ❌ 不一致 |
| 诊断一致无需更新 | N/A | `_finish_fast_path_diagnosis` → verified | ❌ **死代码，不可达** |
| 诊断有差异需更新 | N/A | `_finish_fast_path_diagnosis` → awaiting_update | ❌ **死代码，不可达** |

---

## 4. D1 治理建议确认（_handle_suggestion_confirmation）

触发：`state=awaiting_confirm` 且 `pending_suggestion_action=generate`

```
extract_user_suggestion_text(content)
├─ 有 suggestion_text → intent=confirm
└─ 无 → detect_confirmation_intent(content)

intent=deny → done, suggestion_action=declined

intent≠confirm → FOLLOW_UP 澄清

intent=confirm:
├─ 有 suggestion_text → 写入 nlu.user_suggestion + ConstraintResolver
├─ _generate_suggestion_content
└─ 分支（注意 skill_reuse_mode 在入口已被置 false，靠 suggestion_text 区分）:
    【此前是快路径】通过 suggestion_text 判断：
    ├─ 进入时 skill_reuse_mode=true（在 generate 前读取）
    │   ├─ 有 suggestion_text → awaiting_create（D2）
    │   └─ 无 suggestion_text → done, reused_no_persist, suggestion 已生成
    └─ 普通路径
        ├─ 有 suggestion_text → awaiting_create（D2）
        └─ 无 suggestion_text → done, skipped_no_user_suggestion
```

### D1 测试用例

| TC-ID | 前置 | 用户回复 | state | meta.skill_action | suggestion |
|-------|------|---------|-------|-------------------|------------|
| D1-01 | 普通·无约束 | 「否」 | done | — | null |
| D1-02 | 普通·无约束 | 「是」 | done | skipped_no_user_suggestion | 有 |
| D1-03 | 普通·无约束 | 「是，垂直方向不能溢出」 | awaiting_confirm | awaiting_create | 有 |
| D1-04 | 快路径·无约束 | 「是」 | done | reused_no_persist | 有 |
| D1-05 | 快路径·无约束 | 「是，垂直方向不能溢出」 | awaiting_confirm | awaiting_create | 有 |
| D1-06 | 任意 | 模糊文本 | awaiting_confirm | awaiting_generate | — |

---

## 5. D2 Skill 固化确认（_handle_confirmation · 非 generate）

触发：`state=awaiting_confirm` 且 `pending_skill_action=create|update`

| TC-ID | pending_skill_action | 用户回复 | state | reply.type | meta.skill_action |
|-------|---------------------|---------|-------|------------|-------------------|
| D2-01 | create | 「是」/「确认固化」 | done | skill_created | created |
| D2-02 | create | 「否」 | done | text | declined_create |
| D2-03 | create | 模糊 | awaiting_confirm | follow_up | awaiting_create |
| D2-04 | update | 「是」 | done | skill_updated | updated |
| D2-05 | update | 「否」 | done | text | declined_update |
| D2-06 | create | 「是」且 upsert=unchanged | done | text | unchanged |

> **TC D2-04/05**：`pending_skill_action=update` 仅由 `_finish_fast_path_diagnosis` 设置，**当前代码不可达**。

---

## 6. 完整端到端场景目录

### A. 单点诊断 · 标准路径

| TC-ID | 消息序列 | 关键断言 |
|-------|---------|---------|
| A-01 | 完整一句（无约束） | awaiting_confirm, awaiting_generate, suggestion=null |
| A-02 | A-01 + 「是」 | done, skipped_no_user_suggestion |
| A-03 | 完整一句（含约束） | awaiting_confirm, awaiting_create, suggestion 有 |
| A-04 | A-03 + 「确认固化」 | done, skill_created |
| A-05 | 分轮 NLU（缺时段→补） | nlu_incomplete → awaiting_confirm |
| A-06 | 分轮 NLU（缺方向→补） | 同上 |
| A-07 | 路口 ambiguous → 选择 | intersection_ambiguous → processing |
| A-08 | 路口 not_found | done, error |
| A-09 | 诊断不成立 | done, reason_code=no_rule_matched |
| A-10 | DWS 缺失 | done, missing_dws_coverage |

### B. 干线扫描路径

| TC-ID | 消息序列 | 关键断言 |
|-------|---------|---------|
| B-01 | 「奥体西最堵」→ 缺时段 | corridor_nlu_incomplete |
| B-02 | 「奥体西晚高峰哪些堵」 | awaiting_corridor_pick, corridor_scan |
| B-03 | B-02 + 选型失败 | follow_up, intent=corridor_pick |
| B-04 | B-02 + 选路口（缺方向） | nlu_incomplete, missing=directions |
| B-05 | B-02 + 选路口 + 补方向 | processing → 进入 A 系列 |
| B-06 | 干线多候选 | follow_up, line_candidates |

### C. Skill 快路径 · 完整矩阵

**前置**：同路口已固化 Skill（test_fast_path 流程）

| TC-ID | 第 N 次提问内容 | 匹配 | 第 1 轮 state | 确认后 |
|-------|----------------|------|--------------|--------|
| C-01 | 同路口同时段同方向，无约束 | ✅ fast_path | awaiting_confirm, skill_reused | +「是」→ reused_no_persist |
| C-02 | 同 C-01 +「否」 | ✅ | awaiting_confirm | done, declined |
| C-03 | 同 C-01 +「是，新约束」 | ✅ | awaiting_confirm | awaiting_create |
| C-04 | 约束与历史冲突 | ❌ | 非 fast_path | 普通 A 系列 |
| C-05 | 方向不匹配 | ❌ | 非 fast_path | 普通 A 系列 |
| C-06 | 首轮即带与历史相同约束 | ✅ | **awaiting_generate**（非直接建议） | 见 C-01/C-03 |
| C-07 | Skill 有约束、用户无 | ✅ | awaiting_generate | +「是」→ 建议含历史约束 |

### D. Skill 固化 · 经验吸收 SSE

| TC-ID | 条件 | SSE 事件 |
|-------|------|---------|
| D-01 | 确认固化 create | skill_absorption 6 阶段 + skill_build |
| D-02 | 重复 upsert 相同快照 | action=unchanged |
| D-03 | 规则变化后 upsert | action=updated |
| D-04 | 带 emitter 可视化 | drawer_open → file_chunk → done |

### E. 不可达 / 死代码路径（需修复或删测）

| 路径 | 代码位置 | 状态 |
|------|---------|------|
| skill_action=verified | `_finish_fast_path_diagnosis` L1482 | **从未被调用** |
| skill_action=awaiting_update | `_finish_fast_path_diagnosis` L1512 | **从未被调用** |
| SSE skill_verify 事件 | 同上 L1489 | **从未被调用** |

---

## 7. 推荐测试实现优先级

### P0 — Skill 快路径回归（用户关注）

```python
# 已有：test_skill_fast_path.py
test_fast_path_reuses_skill_with_suggestion_confirmation  # C-01, C-04
test_constraint_mismatch_skips_fast_path                  # C-04
test_fast_path_supplement_triggers_skill_confirm          # C-03

# 建议新增：
test_fast_path_first_message_with_same_constraint_still_awaits_d1  # C-06 不对称
test_fast_path_injects_skill_constraint_on_confirm_yes           # C-07
test_finish_fast_path_diagnosis_is_dead_code                     # 文档化/待修复
```

### P1 — 二次确认全分支

- D1-01 ~ D1-06
- D2-01 ~ D2-03（create 路径）
- test_deny_suggestion_confirmation（已有 D1-01 部分）

### P2 — 干线 + NLU 追问

- test_corridor_scan_flow.py 已有 B-01~B-05 部分
- test_nlu_follow_up / test_follow_up.py

### P3 — SSE 步骤顺序断言

- orchestrator.start → nlu → skill_match → … → complete
- 快路径时 intersection step source=skill_fast_path

---

## 8. 每条路径的 meta 断言速查

| meta 字段 | 取值场景 |
|-----------|---------|
| `resolution_source` | `skill_fast_path` / `exact` / `variant` / `corridor_pick` |
| `skill_reused` | 快路径诊断完成后为 true |
| `suggestion_action` | `awaiting_generate` / `generated` / `declined` / `generated_with_user_suggestion` |
| `skill_action` | `awaiting_create` / `created` / `updated` / `unchanged` / `reused_no_persist` / `skipped_no_user_suggestion` / `declined_*` / `verified`（不可达） |
| `skill_match_reason` | 快路径命中时为 `matched` |
| `matched_skill` | skill_id 或 null |

---

## 9. 文件索引

| 流程定义 | 路径 |
|---------|------|
| 状态机入口 | `backend/intersection_agent/services/orchestrator.py` |
| Skill 匹配 | `backend/intersection_agent/services/skill_matcher.py` |
| 快路径集成测 | `backend/tests/test_skill_fast_path.py` |
| 匹配单测 | `backend/tests/test_skill_matcher.py` |
| 产品设计 | `docs/plans/技能沉淀与匹配逻辑开发计划.md` |
