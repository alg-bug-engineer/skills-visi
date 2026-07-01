# Release 0630 · 四类问题动态诊断 · 三级经验沉淀 · 演示叙事整合

> 日期：2026-06-30  
> Git 标签：`0630`  
> 分支：`main`（已合并原 `develop` / `0630-demo` 全部提交）  
> 基线：`cb43750`（信控演示叙事精简）→ 合并 `main` 转向指标增强

---

## 1. 概述

`0630` 是 **诊断主线重构 + 经验沉淀闭环** 的整合发布：

1. **四类问题动态诊断**：NLU 多标签分类（拥堵 / 溢出 / 空放 / 冲突），按问题类型激活维度子集。
2. **三级经验沉淀**：认知 / 诊断 / 方案经验在理解过程中逐级写入路口认知档案，复用时按步注入并高亮。
3. **专家经验库**：`docs/expert_knowledge.md` 接入方案生成与轻量 knowledge_qa 匹配。
4. **严格栅栏播报**：每步产出落库后再播报，与理解过程对齐。
5. **演示叙事整合**：保留演示精简叙事（左数据右建议）；移除干线扫描入口；经验沉淀卡移至地图左下角。
6. **转向指标增强**（来自 `main`）：`turn_metrics` 后端/前端模块、地图 marker 与渠化阶段标注增强。

---

## 2. 后端能力

| 模块 | 说明 |
|------|------|
| `dimension_pack_service.py` | 问题类型 → 维度包配置（`problem_dimension_packs.yaml`） |
| `nlu_service.py` | 四类问题多标签分类 |
| `orchestrator.py` | pipeline 按类型激活维度；三级经验写入挂点；严格栅栏 |
| `intersection_profile_store.py` | 路口认知档案；三类经验 store 层去重 + 认知状态升级 |
| `experience_extractor.py` / `experience_reuse_service.py` | LLM 抽取归一化 + 分类型复用注入 |
| `case_library_service.py` | 专家经验库匹配与方案生成注入 |
| `execution_emitter.py` | 播报栅栏：步骤落库后再 emit |

**移除**：干线扫描相关服务（`corridor_scan_*`、`corridor_context_service`、`line_resolver` 等）。

---

## 3. 前端能力（frontend-v2）

| 模块 | 说明 |
|------|------|
| `ExperienceLibraryPanel.vue` | 经验库面板 |
| `IntersectionNarrativeStack.vue` | 经验沉淀卡左下角；经验复用高亮 |
| `useExperienceLibrary.ts` | 经验库 API 对接 |
| `usePresentation.ts` | 经验沉淀型呈现 |
| `turnMetrics.ts` / `mapMarkers.ts` | 转向指标与地图标注（合并自 main） |

---

## 4. 设计与计划文档

| 文档 | 内容 |
|------|------|
| [四类问题动态诊断与三级经验沉淀 · 设计](plans/2026-06-29-四类问题动态诊断与三级经验沉淀-design.md) | 重构目标、决策记录、架构 |
| [四类问题动态诊断与三级经验沉淀 · 实施计划](plans/2026-06-29-四类问题动态诊断与三级经验沉淀.md) | 分阶段任务 |
| [三类经验去重与认知数据验证](plans/2026-06-30-三类经验去重与认知数据验证-设计与计划.md) | store 判重、UI 左下角 |
| [路口诊断 UI 优化与诊断闭环](plans/2026-06-29-路口诊断UI优化与诊断闭环-设计与计划.md) | 前端闭环 |
| [develop 信控演示叙事精简 · 复盘](plans/2026-06-29-develop-信控演示叙事精简-复盘.md) | 叙事精简基线 |
| [expert_knowledge.md](expert_knowledge.md) | 专家经验库原文 |

---

## 5. 分支演进（已收敛）

```
cb43750 共同祖先
├── main: update（转向指标）
└── develop: 12 commits（四类诊断 + 三级经验）
    └── 0630-demo: +1 commit（经验去重 + UI）
         ↓ 合并到 main（冲突以 0630 为准）
      6e6d1c1 → tag 0630
```

- 本地 `develop`、`0630-demo` 分支已删除，能力全部在 `main`。
- 远程 `origin/develop` 仍停在 `cb43750`，以 `main` + 标签 `0630` 为准。

---

## 6. 回归与启动

```bash
bash scripts/regression.sh      # 合并/发布前必跑
bash scripts/dev-v2.sh          # backend 8011 + frontend-v2 5568
```

演示模式：`DEMO_MODE=1`，详见 [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) §7。

---

## 7. 已知取舍

| 项 | 说明 |
|----|------|
| 干线扫描 | 已移除入口与服务，区域扫描能力保留在 `region-scan/` 子模块 |
| develop 分支 | 已合并进 main，不再维护独立 develop 线 |
| main vs 0630 冲突 | 合并时以 0630 为准；`turn_metrics` 等非冲突增强保留 |
