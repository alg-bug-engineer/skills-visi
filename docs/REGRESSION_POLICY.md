# 回归测试约束（项目强制）

> 版本：2026-06-28  
> 状态：**强制** — 所有新增功能与改动必须遵守

---

## 1. 原则

1. **改动必测**：任何影响用户路径、API 响应、SSE 事件、Skill 匹配/复用/沉淀、前端理解过程或语音同步的代码变更，必须附带或更新回归测试。
2. **规格为准**：测试点以 [`REGRESSION_TEST_SPEC.md`](./REGRESSION_TEST_SPEC.md) 为权威清单；新增场景须先补充 TC-ID 再实现。
3. **路径一致**：同步 API（`/messages`）与 SSE（`/messages/stream`）对同一输入的 `state` / `reply.type` / 关键 `meta` 必须一致。
4. **Skill 双路径**：**初次沉淀**与**技能复用（快路径）**行为差异见 REGRESSION_TEST_SPEC §1；改动 `orchestrator` 或 `skill_matcher` 必须跑 P0 快路径套件。
5. **禁止死代码**：不可达分支须删除或恢复调用；不得保留「文档说有、代码从未执行」的路径。

---

## 2. 合并前必跑（P0）

```bash
bash scripts/regression.sh
```

等价于：

```bash
cd backend && pytest tests/ -q
cd frontend-v2 && npm test -- --run
```

### P0 子集（Skill / 确认相关改动时额外必跑）

```bash
cd backend && pytest \
  tests/test_skill_fast_path.py \
  tests/test_skill_matcher.py \
  tests/test_api.py \
  -q
```

---

## 3. 改动 → 必跑 TC 组

| 改动模块 | 必跑 |
|---------|------|
| `orchestrator.py` | RT-ROUTE, RT-CONF, RT-REUSE, RT-X |
| `skill_matcher.py` / `skill_service.py` | RT-MATCH, RT-Persist, RT-REUSE |
| `nlu_service.py` / `follow_up_service.py` | RT-NLU, RT-FU |
| `corridor_*` | RT-COR |
| `App.vue` / `usePresentation` / 理解过程 | RT-UI |
| `voice_narration.json` / `voiceStepSync` | RT-VOICE |
| `execution_emitter` / SSE | RT-SSE, RT-DIA |

完整映射见 REGRESSION_TEST_SPEC §19。

---

## 4. 新增功能流程

1. 在 `REGRESSION_TEST_SPEC.md` 增加 TC-ID（前缀 + 期望断言）。
2. 实现 pytest / vitest 用例，函数 docstring 或 `@pytest.mark` 标注 TC-ID。
3. 若涉及 Skill 路径，更新 §1 对照表（如有新分支）。
4. 本地 `bash scripts/regression.sh` 全绿后再提 PR。

---

## 5. Skill 路径约定（当前实现）

| 路径 | 诊断后 | D1「是」无补充 | 有 user_suggestion |
|------|--------|---------------|-------------------|
| 初次（无 Skill） | awaiting_generate | skipped_no_user_suggestion | 首轮可跳过 D1 → awaiting_create |
| 初次沉淀 | 首轮带约束 → awaiting_create | — | 固化 → skill_created |
| **复用快路径** | **始终 awaiting_generate** | **reused_no_persist** | D1 补充新约束 → awaiting_create |

快路径**不**使用 `verified` / `awaiting_update`（已移除死代码 `_finish_fast_path_diagnosis`）。

---

## 6. 相关文档

- [REGRESSION_TEST_SPEC.md](./REGRESSION_TEST_SPEC.md) — 全量测试点
- [TEST_SCENARIO_MATRIX.md](./TEST_SCENARIO_MATRIX.md) — TC 速查
- [test-scenario-flowcharts.html](./test-scenario-flowcharts.html) — 流程图
- [技能沉淀与匹配逻辑开发计划.md](./技能沉淀与匹配逻辑开发计划.md) — 产品设计
