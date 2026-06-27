# frontend-v2 开发计划

## 目标

将诊断前端升级为 **GIS + 推理证据 + 理解过程** 三栏工作台，在不影响 v1 的前提下交付可联调、可测试的 v2 包。

## 阶段

| 阶段 | 内容 | 状态 |
|------|------|------|
| P0 骨架 | 复制 frontend、独立端口 5568、纳入根 monorepo | ✅ |
| P0 布局 | WorkbenchLayout 三栏 + 响应式折叠 | ✅ |
| P0 0625 | InsightStack + SSE `problem_evidence` | ✅ |
| P1 渠化 | ChannelizationMiniWindow + GIS 全屏 | ✅ |
| P1 叙事 | AnalysisQueue、二次确认、Skill 固化（继承 v1） | ✅ |
| P2 质量 | vitest、`scripts/e2e-v2.sh` | ✅ |
| P2.1 时序 | 证据卡与理解过程步骤同步、运行数据单卡合并 | ✅ |
| P2.2 经验吸收 | skill_absorption + SkillBuildDrawer L3 交错 | ✅ |
| P3 迭代 | 常发日历热力、Playwright E2E、清理遗留 overlay 组件 | 待办 |

## 验收标准

1. `npm run build` / `npm run test` 通过  
2. `bash scripts/e2e-v2.sh` 返回 `problem_evidence` + `quantitative_constraints`  
3. 浏览器可见：  
   - 三栏：GIS + 推理证据 + 理解过程  
   - 「获取数据」步骤完成后出现**一张**运行数据卡  
   - 「问题验证」步骤完成后出现验证卡与约束卡  
   - 理解过程 8 步时间轴  

## 分支策略

- `frontend/`：稳定线，仅修 bug  
- `frontend-v2/`：特性线，完成后可替换 v1 入口或并行发布  
