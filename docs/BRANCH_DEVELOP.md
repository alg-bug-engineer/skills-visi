# `develop` 分支说明（已归档）

> 最后更新：2026-06-30  
> **状态：已合并进 `main`，标签 `0630`。** 本地 `develop` / `0630-demo` 分支已删除。

## 归档说明

原 `develop` 线为「信控演示叙事精简 + 四类问题动态诊断 + 三级经验沉淀」；
`0630-demo` 在其上增加经验 store 去重与经验沉淀卡左下角。

2026-06-30 已全部合并到 `main` 并打标 **`0630`**。请以以下文档为准：

| 文档 | 内容 |
|------|------|
| [RELEASE_0630.md](RELEASE_0630.md) | **0630 发布说明（权威）** |
| [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | 项目总览与里程碑 |
| [plans/2026-06-29-develop-信控演示叙事精简-复盘.md](plans/2026-06-29-develop-信控演示叙事精简-复盘.md) | 叙事精简变更清单 |

## 当前工作流

```bash
git checkout main
git pull origin main
bash scripts/dev-v2.sh
```

无需再 checkout `develop`。
