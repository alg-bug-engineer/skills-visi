# Release v3.0.1 · 吸收/固化空格暂停 · 叙事分栏 · 饱和度小数 · LLM 调用收敛

> 日期：2026-06-29  
> Git 标签：`v3.0.1`  
> 前置版本：v3.0（渠化 AMap、领导演示叙事、TTS 鉴权）  
> 回归：`bash scripts/regression.sh` → backend **141** passed · frontend vitest **105** passed

---

## 1. 概述

v3.0.1 在 v3.0 演示基线上补齐 **经验吸收与技能固化的空格暂停**、**流式打字机与呈现栅栏修复**、**叙事卡左右分栏**、**饱和度全链路小数口径**，并收敛 Qwen LLM 调用（统一禁用 thinking 模式）。

---

## 2. 经验吸收 / 技能固化空格暂停（RT-PAUSE-ABS）

### 2.1 交付

| 项 | 说明 |
|----|------|
| 阶段边界 pause gate | `skill_absorption` / `skill_build` 在 `stage_done` / `file_done` 后入队暂停 |
| 流式即时 apply | `thought_delta` / `file_delta` 等 SSE 到达即呈现，不进 AnalysisQueue |
| 暂停缓冲回放 | `presentationPause.paused` 时缓冲事件，恢复后 `requestAnimationFrame` 逐帧回放 |
| 空格键激活 | 吸收进行中 / 固化 running / 队列运行 / 已暂停均可触发 |

### 2.2 关键模块

| 模块 | 职责 |
|------|------|
| `skillPresentationDispatch.ts` | 流式/边界分类 + pause gate 策略 |
| `App.vue` | `dispatchSkillAbsorptionEvent` / `dispatchSkillBuildEvent` |
| `regressionSkillFlow.ts` | `isSkillPresentationActive` 空格键条件 |
| `usePresentationBarrier.ts` | 固化 `whenProcessAndVoiceSettled` |

### 2.3 踩坑与修复

- **栅栏死锁**：禁止在 `stage_start` / `start` 上全量 `whenPresentationSettled`；gate 仅 `stage_done`
- **队列堆积**：流式 delta 同步 apply，避免整段刷字
- **固化 gate 误等吸收**：交错落盘时固化 gate 不再等待吸收 `running` 行

详见 [`plans/2026-06-28-经验吸收技能固化空格暂停与呈现修复-复盘.md`](plans/2026-06-28-经验吸收技能固化空格暂停与呈现修复-复盘.md)。

---

## 3. 叙事卡布局（左右分栏）

- 左侧：**路口态势**（认知、运行数据、渠化摘要）
- 右侧：**问题验证** + **治理建议**（默认展开问题验证，取消自动折叠）
- 技能终端写入展开时：`hideLeftPanel` 隐藏左侧叙事卡，避免与 `SkillBuildDrawer` 叠层冲突
- `data_fetch` running 时提前展示理解过程步骤 3

---

## 4. 饱和度口径

| 层级 | 变更 |
|------|------|
| 后端 | 移除 `cap_saturation`；`data_fetcher` / `intersection_cognition_service` / `problem_evidence_service` 保留原始饱和度 |
| 地图 | `map_presentation_service._fmt_sat()` 小数两位（如 `0.92`） |
| 前端 | 图例、marker、TTS 摘要统一小数格式 |
| 语音 | `traffic` / `granularity` / `saturation` phase 摘要精简 |

---

## 5. LLM 调用收敛

- `QwenClient.chat` / `chat_json`：移除 `enable_thinking` 参数，**始终** `enable_thinking=False`
- 原因：JSON Mode 与 thinking 模式不兼容；意图分类等结构化输出场景无需思考链
- `IntentClassifierService` 调用侧同步简化

---

## 6. 文档与回归

| 文档 | 内容 |
|------|------|
| [`PRESENTATION_SYNC_BARRIER.md`](PRESENTATION_SYNC_BARRIER.md) | §7 吸收/固化栅栏约束 |
| [`REGRESSION_TEST_SPEC.md`](REGRESSION_TEST_SPEC.md) | RT-PAUSE-ABS 用例 |
| [`backend/docs/CHANGELOG.md`](../backend/docs/CHANGELOG.md) | 变更记录 |
| [`frontend-v2/docs/PROGRESS.md`](../frontend-v2/docs/PROGRESS.md) | 前端进度 |

新增单测：`skillPresentationDispatch.spec.ts` · `regressionSkillFlow` RT-PAUSE-ABS 扩展。

---

## 7. 验证

```bash
bash scripts/regression.sh          # 141 + 105
bash scripts/dev-v2.sh              # 8011 + 5568
cd backend && DEMO_MODE=1 python scripts/run_demo_rehearsal.py
```

演示验收要点：

1. 诊断阶段空格暂停 → 吸收阶段同样可暂停/继续  
2. 吸收/固化打字机逐字呈现，无整段堆积  
3. 叙事卡左态势 / 右验证+建议分栏；固化终端时左栏隐藏  
4. 地图 marker 饱和度显示 `0.92` 而非 `92%`

---

## 8. 后续待办（继承 v3.0）

- [ ] Playwright E2E：渠化标注时序、叙事卡折叠、TTS 步骤对齐
- [ ] 治理建议段「↩ 源自民警约束」二次点亮
- [ ] 真实浏览器像素级走查（需高德 key 域名白名单）
