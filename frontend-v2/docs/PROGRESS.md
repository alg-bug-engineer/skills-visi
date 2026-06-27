# frontend-v2 进度记录

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
