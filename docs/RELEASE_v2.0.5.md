# Release v2.0.5 · 地图渠化融合 · 语音演示 · 呈现同步

> 日期：2026-06-28  
> 范围：frontend-v2 演示体验 + 后端 narration 增强 + 运行时网络修复  
> 前置版本：v2.0.4（语音步骤同步 + 饱和度口径）

---

## 1. 概述

本版本聚焦 **v2 工作台演示链路**：地图与真实渠化融合、语音旁白精简、理解过程/吸收面板/TTS 三流同步、以及开发环境代理误伤后端 HTTP 的修复。

---

## 2. 新功能

### 2.1 地图 · 渠化融合视图（R2）

- 认知阶段起高德底图**始终可见**，3D 渠化透明叠加（非纯黑全屏独占）。
- 渠化模式下地图 `setCenter` 居中，`pan` 偏移为 **0**，避免右栏补偿导致左侧黑条。
- 详见 [`地图语音暂停交互增强开发计划.md`](./地图语音暂停交互增强开发计划.md) §4.2。

### 2.2 标注分层（渠化层承载语义）

| 层 | 职责 |
|----|------|
| AMap 底图 | 道路 tile；干线扫描阶段保留地理 pin/polyline |
| 3D 渠化 | 路臂几何、排队、方向角色高亮、`applyArmSceneLabels` 路臂标注 |
| 渠化 DOM | 阶段 HUD、证据卡、图例、metric strip |

- 进入渠化后（`channelizationLocked`）**禁止**在 AMap 上绘制 Marker/Polyline。
- 转换：`utils/channelArmLabels.buildArmLabelsFromScene` → `channelizationLayer.applyArmSceneLabels`。
- 阶段 HUD 迁入 `ChannelizationStageOverlay` 顶栏。

### 2.3 语音旁白增强

- **轴路名播报**：`map_presentation_service` 输出 `axis_roads` / `speakable`；`buildCognitionVoiceCue`。
- **分向/饱和度/失衡**：`enqueueSceneVoice` 接入 `voiceCueExtractors` 模板。
- **干线/配时/外部等 narration**：`buildNarrationPhaseVoiceCue` + `voiceTextSummarize` **只播关键点**（约 42 字），面板仍展示全文。
- 固定引导语精简：[`frontend-v2/src/config/voice_narration.json`](../frontend-v2/src/config/voice_narration.json)。

### 2.4 演示暂停（空格）

- `usePresentationPause`：在 `AnalysisQueue` 任务边界 pause/resume，不中断 SSE。
- 空格切换暂停；toast「已暂停 · 按空格继续」。

### 2.5 呈现同步栅栏

- `usePresentationBarrier.whenSettled()`：步骤切换前同时等待  
  **理解过程打字** + **TTS 播完** + **吸收面板无 running 行**。
- 规范：[`PRESENTATION_SYNC_BARRIER.md`](./PRESENTATION_SYNC_BARRIER.md)（**后续开发必读**）。

### 2.6 方向角色与图例

- 关注/保护方向：`applyDirectionRoleHighlight`（橙/绿）+ 图例块联动。
- `ChannelizationLegend` 按 phase 揭示排队/失衡说明。

---

## 3. Bug 修复

| 问题 | 原因 | 修复 |
|------|------|------|
| `ImportError: socksio` / 服务内部错误 | shell `all_proxy=socks5` 被 httpx 继承 | `network_env.disable_shell_proxy_env()` 于 `main.py` 启动清除；`QwenClient` `trust_env=False` |
| 左侧通屏黑条 | 底图 `panToVisualCenter(-120)` + 融合视图空白区 | 渠化态 offset=0 + `setCenter`；标注不再依赖底图 pan |
| 标注在底图 HTML Marker 上，视觉杂乱 | 双轨：AMap + 3D 同时标注 | 渠化态清空 AMap overlay，标注迁 3D 路臂 |
| 地图完全不可见 | 误用 `map-hidden` 隐藏 canvas | 恢复 `.map-blended` 底图可见 |
| 干线 phase 无语音 | `enqueueSceneVoice` 未覆盖 corridor | `enqueueNarrationPhaseVoice` + 摘要 |
| 语音朗读面板全文过长 | narration 全文入 TTS 队列 | `summarizeNarrationForVoice` 按 phase 提取要点 |
| 语音未完理解已跳步 | 仅 `whenProcessIdle` | `whenPresentationSettled` 三流栅栏 |

---

## 4. 后端变更摘要

- `map_presentation_service.py`：`axis_roads_summary`、`speakable` narration、方向角色 meta。
- `network_env.py`：清除继承的 proxy 环境变量（**非** git/终端代理配置）。
- 单测：`test_network_env.py`、`test_map_presentation.py` 扩展。

---

## 5. 前端变更摘要（关键文件）

| 路径 | 说明 |
|------|------|
| `App.vue` | 旁白接线、呈现栅栏、暂停、narration 语音 |
| `MapStage.vue` | 融合底图、渠化态禁 AMap 标注、居中 |
| `ChannelizationCanvas3D.vue` | 路臂 scene labels |
| `channelizationLayer.js` | `applyArmSceneLabels` |
| `usePresentationBarrier.ts` | 三流同步 |
| `useVoiceNarration.ts` | `whenIdle()` |
| `voiceTextSummarize.ts` | TTS 摘要 |
| `channelArmLabels.ts` | marker → 路臂标签 |

---

## 6. 文档索引（v2.0 起沉淀）

| 文档 | 用途 |
|------|------|
| [PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md) | 根仓库权威索引 |
| [PRESENTATION_SYNC_BARRIER.md](./PRESENTATION_SYNC_BARRIER.md) | 呈现同步栅栏（强制） |
| [地图语音暂停交互增强开发计划.md](./地图语音暂停交互增强开发计划.md) | R1–R4 设计与验收 |
| [DEV_CONSTRAINTS.md](./DEV_CONSTRAINTS.md) | 开发环境约束（含终端代理） |
| [REGRESSION_POLICY.md](./REGRESSION_POLICY.md) | 合并前回归 |
| `frontend-v2/docs/PROGRESS.md` | 前端版本进度 |
| `backend/docs/CHANGELOG.md` | 后端变更日志 |

---

## 7. 验证

```bash
bash scripts/regression.sh
```

新增/扩展单测：`voiceTextSummarize`、`channelArmLabels`、`usePresentationBarrier`、`test_network_env` 等。

---

## 8. 开发环境说明

- **终端代理**（git push / npm / pip）：见 [DEV_CONSTRAINTS.md](./DEV_CONSTRAINTS.md) 与 `.cursor/rules/network-proxy.mdc`。
- **应用运行时**不使用代理；勿将 proxy 写入 `backend/.env`。
