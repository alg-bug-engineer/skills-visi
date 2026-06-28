# Release v3.0 · 渠化 AMap 迁移 · 领导演示叙事 · TTS 鉴权修复

> 日期：2026-06-28  
> Git 标签：`v3.0`  
> 前置版本：v2.0.5（地图渠化融合、呈现栅栏、语音摘要）  
> 回归：`bash scripts/regression.sh` → backend **141** passed · frontend vitest **99** passed

---

## 1. 概述

v3.0 是 **演示向大版本**：将渠化从 THREE.js/D3 全量迁移至高德 AMap 矢量覆盖物并下沉主图下钻；重构领导汇报叙事为左上角生长卡栈 + 镜头连贯；修复 TTS Realtime workspace 鉴权导致无声；收敛 UI 布局避免重复 HUD 与图例遮挡。

合并分支：`feat/channelization-amap-migration`、`feature/tts`（均已合入 `main`，0 未合并提交）。

---

## 2. 渠化 AMap 迁移（feat/channelization-amap-migration）

### 2.1 新增模块

| 模块 | 说明 |
|------|------|
| `lib/channelizationGeometry.ts` | 渠化几何纯函数（19 单测） |
| `lib/channelizationAmap.ts` | AMap 渲染器 + 四套阶段标注（11 单测） |
| `lib/channelizationPhase.ts` | 阶段→标注调度器，三池语义（7 单测） |
| `lib/channelizationController.ts` | 渠化层生命周期（4 单测） |

### 2.2 主图整合

- 渠化下沉 `MapStage` 主图，`zoomend` 分级下钻（L0 路网 / L1 轮廓 / L2 全渠化+标注）。
- `ChannelizationStageOverlay` 去 3D 画布，保留 header/HUD/图例/证据/建议/迷你窗 HUD 浮层。
- 移除 THREE/D3 旧实现与 `three`/`d3` 依赖，包体显著缩减。

### 2.3 计划与偏差

详见 [`plans/2026-06-28-渠化AMap迁移与主图下钻.md`](plans/2026-06-28-渠化AMap迁移与主图下钻.md) §执行结果。

- 迷你窗 D3/SVG 组件为死代码，已删除；AMap 主图下钻覆盖其职能。
- 转角贝塞尔圆弧（`buildCorners`）在 v3.0 补丁中移除：控制点以路口中心为锚，弧线向内部弯曲横穿人行横道，影响清晰度。

---

## 3. 领导演示叙事重构

### 3.1 右上角 → 左上角生长卡栈

- `IntersectionNarrativeStack` 移至 **左上角**，单列时间线：认知头 → 运行数据逐项 ✓ → 问题验证（自动折叠）→ 治理建议。
- 图例 `ChannelizationLegend` 移至 **右下角**；迷你窗靠右排布，避免遮挡叙事卡。
- 渠化舞台在叙事卡激活时 `suppressStageHud`，避免顶部身份/HUD 与信息卡重复。

### 3.2 镜头连贯

- 单调 zoom 下钻，`userInteracted` 保留视角，只前进不回跳。
- 8 步理解过程与语音、地图动作三线对齐（见复盘 §2）。

### 3.3 文档

| 文档 | 内容 |
|------|------|
| [领导演示叙事-需求理解](plans/2026-06-28-领导演示叙事与地图呈现重构-需求理解.md) | 需求与约束 C1–C3 |
| [领导演示叙事-开发方案](plans/2026-06-28-领导演示叙事与地图呈现重构-开发方案.md) | 技术方案 |
| [领导演示叙事-UI交互](plans/2026-06-28-领导演示叙事与地图呈现重构-UI交互.md) | 交互规格 |
| [叙事卡栈重构-设计](plans/2026-06-28-叙事卡栈重构-设计.md) | 卡栈结构 |
| [叙事卡栈重构-复盘](plans/2026-06-28-叙事卡栈重构-复盘.md) | 文案/播报/地图一致性评估 |

---

## 4. TTS Realtime 鉴权修复

### 问题

Qwen-TTS Realtime WebSocket 复用 LLM 的 `DASHSCOPE_WORKSPACE_ID` 时返回 **Workspace access denied**，前端静默降级导致完全无声。

### 修复

- `config.py`：新增 `qwen_tts_workspace_id`（默认空）；`tts_configured` 仅需 API Key；`tts_workspace` 与 LLM workspace 分离。
- `qwen_tts_realtime_service.py`：WS 连接使用 `tts_workspace` 而非 `dashscope_workspace_id`。
- `useVoiceNarration.ts`：TTS 失败时 `console.warn` 留痕，避免完全静默掩盖故障。
- 单测：`backend/tests/test_tts_config.py`（4 项）。

---

## 5. Bug 修复与已知项

详见 [`bugs/BUG_REGISTRY.md`](bugs/BUG_REGISTRY.md)。

| ID | 摘要 | 状态 |
|----|------|------|
| BUG-001 | shell SOCKS 代理误伤 httpx | ✅ v2.0.5 `network_env` |
| BUG-002 | 渠化态左侧黑条（pan 偏移） | ✅ v2.0.5 |
| BUG-003 | TTS workspace 鉴权无声 | ✅ v3.0 |
| BUG-004 | 转角圆弧横穿人行横道 | ✅ v3.0 移除 buildCorners |
| BUG-005 | 叙事卡与渠化 HUD/图例布局冲突 | ✅ v3.0 布局调整 |

---

## 6. 分支与提交历史（合入 main）

```
cd3616e feat(narrative): 领导演示叙事重构
28c8a13 docs(chan): 渠化 AMap 迁移计划补执行结果
53b84e7 chore(chan): 移除 THREE/D3 旧渠化实现
9f9a189 feat(chan): 渠化下沉主图 + zoom 下钻
0c5409e feat(chan): 渠化层生命周期控制器
a3489a7 feat(chan): 阶段→标注调度器
bf4b38c feat(chan): AMap 渠化渲染器 + 阶段标注引擎
7dc7469 feat(chan): 渠化几何纯函数库 + 迁移计划
f557917 release(v2.0.5): 渠化地图融合、呈现栅栏与语音摘要
```

---

## 7. 验证

```bash
bash scripts/regression.sh          # 141 + 99
bash scripts/dev-v2.sh              # 8011 + 5568
cd backend && DEMO_MODE=1 python scripts/run_demo_rehearsal.py  # 演示彩排
```

演示路口（`DEMO_MODE=1`）：会展路与奥体中路 / 二环东路与工业南路 / 奥体中路与经十路。

---

## 8. 后续待办

- [ ] Playwright E2E：渠化态标注时序、叙事卡折叠、TTS 步骤对齐
- [ ] 治理建议段「↩ 源自民警约束」二次点亮（复盘 §3②）
- [ ] 真实浏览器像素级走查（需高德 key 域名白名单）
- [ ] 干线→单点选型过场语音强化
