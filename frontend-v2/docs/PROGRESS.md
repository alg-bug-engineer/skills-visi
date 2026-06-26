# frontend-v2 进度记录

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
