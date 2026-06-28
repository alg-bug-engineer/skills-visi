# frontend-v2 进度记录

## v2.0.6（2026-06-28）— 汇报向叙事 · 地图呈现时序

### 已完成

- [x] 理解过程 8 步业务化标签（理解描述 → 经验固化）
- [x] 每步 `leadingSummary` + 「查看详情」折叠明细（link / Skill ID 等）
- [x] 后端 narration `step_summary` + `focus_step_index`（RT-PRES-SUMMARY）
- [x] `usePresentationSequence`：MetricStrip / InsightStack / 证据 note / HUD / 配时环错峰揭示
- [x] Skill 复用：锁定路口步内摘要 + `skillReuseHint` TTS
- [x] 暂停 toast：「分析暂停 · 空格继续」
- [x] 语音引导语业务化（`voice_narration.json`）

### 文档

- [docs/plans/2026-06-28-领导演示叙事与地图呈现重构-需求理解.md](../../docs/plans/2026-06-28-领导演示叙事与地图呈现重构-需求理解.md)
- [docs/plans/2026-06-28-领导演示叙事与地图呈现重构-开发方案.md](../../docs/plans/2026-06-28-领导演示叙事与地图呈现重构-开发方案.md)
- [docs/plans/2026-06-28-领导演示叙事与地图呈现重构-UI交互.md](../../docs/plans/2026-06-28-领导演示叙事与地图呈现重构-UI交互.md)

### 单测

- vitest 新增 `usePresentationSequence.spec`、`presentationCopy.spec`

---

## v2.0.5（2026-06-28）— 地图渠化融合 · 语音精简 · 呈现同步栅栏

### 已完成

- [x] 地图 + 3D 渠化融合（R2）：底图可见、overlay 透明、渠化态 pan offset=0
- [x] **标注分层**：渠化态禁用 AMap Marker/Polyline；`applyArmSceneLabels` 路臂 3D 标签；HUD 迁入 overlay 顶栏
- [x] 语音：`voiceCueExtractors` 接线（认知轴路名、分向、饱和度、失衡、干线 narration）；`voiceTextSummarize` 关键点播报
- [x] 空格演示暂停：`usePresentationPause` + `AnalysisQueue.pause`
- [x] 呈现同步栅栏：`usePresentationBarrier.whenSettled`（理解过程 + TTS + 吸收面板）
- [x] 方向角色高亮 + 图例；后端 `axis_roads` / `speakable` narration
- [x] Bug：SOCKS 代理误伤 httpx（后端 `network_env`）；左侧黑条；底图标注杂乱

### 文档

- [docs/RELEASE_v2.0.5.md](../../docs/RELEASE_v2.0.5.md)
- [docs/PRESENTATION_SYNC_BARRIER.md](../../docs/PRESENTATION_SYNC_BARRIER.md)（强制约束）
- [docs/地图语音暂停交互增强开发计划.md](../../docs/地图语音暂停交互增强开发计划.md)

### 单测

- vitest **43+** 项（含 `voiceTextSummarize`、`channelArmLabels`、`usePresentationBarrier` 等）

### 待办

- [ ] Playwright：渠化态无 AMap marker、栅栏时序
- [ ] Phase 2：`AMap.GLCustomLayer` 地理精确对齐 Three

---

## v2.0.4（2026-06-27）— 语音步骤同步 + 饱和度口径

### 已完成

- [x] 语音文案外置 `src/config/voice_narration.json`，`voiceConfig.ts` 统一加载
- [x] `voiceStepSync.ts` + `useUnderstandingProcess.onStepStart`：旁白与理解过程步骤首次展示对齐
- [x] 移除 `App.vue` 分散 `voice.enqueue`；PCM 播放器源追踪 + 可配置 `cueGapMs` / `drainTailMs`
- [x] 饱和度全链路改为小数（`formatSaturation`）：证据卡、地图 marker、渠化条、语音模板
- [x] 修复「暂不固化」误触发新分析；`declined_create/update` 后重置会话
- [x] 单测：`voiceStepSync.spec.ts`、`useUnderstandingProcess.spec.ts`（共 24 项 vitest）

### 已知问题 / 待优化

- [ ] 高优先级 cue 打断默认关闭（`interruptOnHighPriority: false`），可按演示需求调整
- [ ] Playwright E2E 语音步骤时序断言

### 配置入口

| 文件 | 用途 |
|------|------|
| `src/config/voice_narration.json` | 固定引导语、模板、播放参数 |
| `src/services/voiceStepSync.ts` | 理解过程步骤 ↔ 旁白映射 |

---

## v2.0.3（2026-06-28）— 经验吸收 + L3 交错落盘

### 已完成

- [x] SSE `skill_absorption`：回顾 → 解构 → 检索 → 比对 → 价值 → 转化
- [x] `useExperienceAbsorption` + `ExperienceAbsorptionPanel`（右栏追踪流）
- [x] `SkillBuildDrawer` 左抽屉终端落盘（**替代**全屏 `SkillBuildOverlay`）
- [x] L3 交错：每写一文件，右栏联动行 ∥ 左抽屉 `file_delta` 同步
- [x] 理解过程折叠摘要（`forcedCollapsed`）+ 右栏 `stacked` 布局
- [x] 单测：`useExperienceAbsorption.spec.ts`、`terminalLines.spec.ts`

### 待办

- [ ] 领导彩排三场（见开发计划 §8）
- [ ] E2E Playwright 吸收 + 抽屉时序断言

---

## v2.0.2（2026-06-25）— 推理证据侧栏与时序对齐

### 已完成

- [x] 三栏布局：**GIS | 推理证据 | 理解过程**（证据贴在理解过程左侧）
- [x] `InsightStack` + `DataMetricsCard` / `EvidenceStackCard` / `ConstraintStackCard`
- [x] 证据卡与理解过程**步骤同步**：`onStepComplete` 驱动揭示，SSE 仅缓冲
- [x] 运行数据**单卡合并**（`dataInsightBuffer` + 按 label 合并指标）
- [x] `applyMetaEvidence` 改为 `patch*`，不抢跑出卡
- [x] `map_scene`：先合并 HUD 再等旁白 idle
- [x] 修复「暂不固化」按钮对比度（深底浅字）
- [x] 后端 `problem_evidence` SSE 扩展：`by_direction`、`quantitative_constraints`

### 待办

- [ ] E2E Playwright 正式脚本（证据卡时序断言）
- [ ] 常发日历热力图（`congested_dates`）
- [ ] 清理未引用的 `MapEvidenceOverlay` / `MapConstraintOverlay`（备用）

---

## v2.0.1 交互重构（2026-06-25）

- [x] 取消画中画：主舞台 **始终全屏 GIS**
- [x] 渠化改为 **右下角浮动小窗**
- [x] 布局由「地图浮卡」演进为「侧栏证据堆叠」

---

## v2.0.0（2026-06-25）

### 已完成

- [x] 从 `frontend/` 复制骨架，独立 `frontend-v2` 包（port 5568）
- [x] `usePresentation` 统一呈现状态
- [x] 0625 `problem_evidence` + `quantitative_constraints`
- [x] 渠化视图、叙事队列、二次确认、Skill 固化 overlay
- [x] 单元测试 `vitest`（`evidencePresentation.spec.ts`）
- [x] `scripts/e2e-v2.sh` 联调冒烟

### 联调演示路口

| 路口 | inter_id | 场景 |
|------|----------|------|
| 奥体西路与经十路交叉口 | `011wwe28ctu00001` | 默认联调演示 |
| 经十路辅路与草山岭西路路口 | `011wwe293dv00001` | 约束 baseline 非零 |

`reference-date`: `2026-06-14`
