# frontend-v2 UI 规范

## 设计令牌

沿用 v1 深色信控主题（`theme.ts` / `TA_THEME`）：

- 主色：`#00e5ff` / `#00d4f0`
- 告警：`#ff7b7b`
- 关注/证据：`#ffc266`
- 保护/约束：`#6dffb5`
- 背景：`#020810`

## 布局断点

| 宽度 | 行为 |
|------|------|
| >1100px | 三栏：GIS + 推理证据（~280px）+ 理解过程（~340px） |
| ≤1100px | 证据栏固定左侧浮层；理解过程固定右侧浮层 |
| 收起 | 「收起」FAB 隐藏证据栏与理解过程，仅保留 GIS |

## 组件约定

1. **结构化证据走 InsightStack 卡片**，不走 `enqueueProcess` 纯文本（证据/约束/运行指标）
2. **揭示时序**：卡片由理解过程 `onStepComplete` 触发，SSE 只缓冲（`patch*` / `mergeDataInsight`）
3. **同类型合并**：运行数据仅一张卡，指标按 `label` 合并更新
4. **地图 Marker kind**：`metric` | `evidence` | `protected` | `suggestion` | `rule`
5. **约束 baseline≈0** 须在约束卡显示解释文案
6. **data-testid**：`send-button`、`confirm-yes`、`confirm-no`

## 类型

- 证据：`src/types/evidence.ts`（与后端 meta 对齐）
- 洞察卡：`src/types/insight.ts`
- 呈现：`src/types/presentation.ts`（含 `dataInsightBuffer`、`revealedInsightSteps`）
