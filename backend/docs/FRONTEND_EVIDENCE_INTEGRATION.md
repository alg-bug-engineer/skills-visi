# 前端对接指南 · 问题验证证据与约束量化

> 后端实现：2026-06-25（`docs/0625.md`）  
> 读者：前端 / 联调 / 产品验收  
> 后端细节：`docs/EVIDENCE_FEATURE.md`

---

## 1. 能力摘要

诊断成立后，除规则结论外，后端额外提供：

1. **`meta.problem_evidence`** — 用数据验证用户描述（常发性、星期规律、排队/延误、分方向）
2. **`meta.quantitative_constraints`** — 将用户约束（如「垂直方向不能溢出」）量化为指标边界
3. **对话 Markdown** — `reply.content` 已嵌入「问题验证」与「约束量化」摘要（可解析或直接用 `meta` 结构化渲染）

SSE 新增步骤：`problem_evidence`（`status=completed`）。

---

## 2. API 响应扩展

### 2.1 `meta.problem_evidence`

```json
{
  "inter_id": "011wwe295cm00001",
  "intersection": "奥体中路与新泺大街路口",
  "time_label": "晚高峰",
  "source_tier": "dwd_rolling_7d",
  "coverage_warning": null,
  "target_dow": 3,
  "target_dow_label": "周三",
  "summary": "近7日中7日该时段运行指标超标，属常发性拥堵；…",
  "chronic": {
    "is_chronic": true,
    "congested_days": 7,
    "window_days": 7,
    "rate": 1.0,
    "congested_dates": ["2026-06-08", "..."],
    "verdict": "近7日中7日该时段运行指标超标，属常发性拥堵",
    "method": "dwd_calendar"
  },
  "dow_pattern": {
    "target_dow": 3,
    "dow_label": "周三",
    "hit_days": 1,
    "total_days": 1,
    "hit_rate": 1.0,
    "verdict": "周三该时段 1/1 日指标超标，呈周期性拥堵",
    "method": "dwd_calendar"
  },
  "metrics": {
    "avg_delay_s": 24.0,
    "delay_index": 1.82,
    "saturation_rate": 0.92,
    "imbalance_index": 0.35,
    "avg_queue_m": 18.2,
    "max_queue_m": 311.0,
    "queue_storage_ratio_max": 0.063,
    "spillback_risk_max": 0.063
  },
  "by_direction": [
    {
      "group": "东西向",
      "focused": true,
      "avg_queue_m": 16.5,
      "max_queue_m": 311.0,
      "avg_delay_s": 28.7,
      "queue_storage_ratio": 0.05,
      "saturation": 0.92
    }
  ],
  "thresholds_used": {
    "min_congested_days": 4,
    "window_days": 7,
    "excess_delay_s": 60,
    "long_queue_m": 100,
    "saturation_high": 0.8,
    "queue_storage_ratio_high": 0.8
  }
}
```

| 字段 | 前端展示建议 |
|------|----------------|
| `chronic.is_chronic` + `verdict` | 常发性徽章 + 一句话 |
| `dow_pattern.hit_rate` + `dow_label` | 「每逢周 X」命中率进度条 |
| `metrics.*` | 指标卡片（饱和度、平均停车、排队） |
| `by_direction[]` | 地图/列表分向对比；`focused=true` 高亮用户关注方向 |
| `coverage_warning` | 黄色提示条（数据不完整时） |
| `source_tier` | 小字标注：`dwd_rolling_7d` / `dws_weekday_pattern` / `mock` |

### 2.2 `meta.quantitative_constraints`

```json
{
  "raw_text": "要考虑垂直方向不能溢出",
  "intent": "no_spillback",
  "primary_directions": ["东西向"],
  "protected_directions": ["南北向"],
  "narrative": "已将「…」量化为：南北向溢流风险不超过 0.47（当前约 0.42，上限 0.80）",
  "constraints": [
    {
      "metric": "spillback_risk",
      "scope": "南北向",
      "operator": "<=",
      "value": 0.47,
      "baseline": 0.42,
      "threshold_ref": "spillback.risk_high"
    }
  ]
}
```

| `intent` | 含义 |
|----------|------|
| `no_spillback` | 防溢流（含「垂直方向」） |
| `no_queue_growth` | 排队不能加剧 |
| `no_worsen` | 泛化「不能/避免」 |
| `saturation_cap` | 保障某方向饱和度 |

前端可在治理建议卡片旁展示 `narrative`，并用 `constraints[]` 渲染「保护边界」列表。

### 2.3 Skill 包字段

`skill.meta.json` 新增 `quantitative_constraints`（与 API 同结构）。固化后前端 Skill 详情页可一并展示。

---

## 3. SSE 事件

在 `data_fetch` → `rule_engine` 之间插入：

```json
{
  "event": "step",
  "step": "problem_evidence",
  "status": "completed",
  "data": {
    "summary": "...",
    "chronic": { "is_chronic": true, "congested_days": 7 },
    "dow_pattern": { "dow_label": "周三", "hit_rate": 1.0 },
    "metrics": { "saturation_rate": 0.92, "avg_queue_m": 96.0 },
    "by_direction": [{ "group": "东向", "saturation": 0.92, "focused": true }],
    "quantitative_constraints": { "narrative": "...", "constraints": [] }
  }
}
```

`quantitative_constraints` 仅在用户输入含约束且解析成功时出现。

**建议 UI（frontend-v2）**：理解过程「问题验证」步骤打字结束后，在左侧 `InsightStack` 揭示问题验证卡与治理边界卡；运行数据在「获取数据」步骤结束后以**单卡合并**展示。

---

## 4. TypeScript 类型

见前端 `src/types/evidence.ts`（与后端字段对齐）。

```typescript
import type { ProblemEvidence, QuantitativeConstraints } from './evidence'

// MessageResponse.meta 使用
meta?.problem_evidence as ProblemEvidence | undefined
meta?.quantitative_constraints as QuantitativeConstraints | undefined
```

---

## 5. 推荐 UI 改造点

| 区域 | 改造 |
|------|------|
| `ChatPanel` | 诊断确认气泡除规则结论外，展示证据卡片（常发/周规律/指标） |
| `UnderstandingProcessPanel` | 时间轴增加 `problem_evidence` 步骤 |
| `MapStage` | 按 `by_direction` 分向标注排队/饱和；`focused` 方向加强高亮 |
| 治理建议卡片 | 展示 `quantitative_constraints.narrative`；若 `delta_seconds` 被裁剪，显示后端 narrative 中的括号说明 |
| 开发/验收 | 使用下方演示路口 + `reference-date`（真实库） |

---

## 6. 演示路口与参考日

**日历数据边界**（联调必读）：

| 数据源 | 区间 | `reference-date` 建议 |
|--------|------|------------------------|
| DWD 感知 | 2026-06-08 ~ 2026-06-14 | `2026-06-14` |
| 车道流量 | 20260601 ~ 20260609 | `2026-06-09`（流量演示） |

**五表齐全、可跑全链路**（详见 `scripts/list_demo_intersections.sql`）：

| 路口 | inter_id | 演示场景 | 建议方向 |
|------|----------|----------|----------|
| 奥体中路与新泺大街路口 | `011wwe295cm00001` | 全能：高饱和+失衡+常发 | 东向 / 东西向 |
| 二环东路与和平路路口 | `011wwe281cy00001` | 超长排队（东向 max 460m） | 东向 |
| 经十路辅路与洪山路路口 | `011wwe288ct00001` | 非南北：东西向均衡堵 | 东西向 |
| 二环东路出口与二环东路辅路路口 | `011wwe0rvxj00001` | 5 进口 + 失衡 | 东南向 |
| 经十路辅路与草山岭西路路口 | `011wwe293dv00001` | 约束量化 baseline 正常 | 西向 |

**反例**：`奥体西路与经十路路口`（`011wwe28ctu00001`）无 DWD/分向 DWS，仅适合 mock 或周模式片段演示。

探针命令：

```bash
cd backend
MOCK_DB=0 .venv/bin/python scripts/probe_evidence.py \
  --intersection "奥体西路与经十路交叉口" \
  --reference-date 2026-06-14 \
  --directions "南北向" \
  --context "晚高峰南北向经常拥堵，垂直方向不能溢出"
```

---

## 7. 约束量化解读（给产品/前端文案）

用户：「垂直方向不能溢出」+ 主方向「东西向」→ 保护 **南北向**。

公式（`rules/thresholds.yaml`）：

```text
baseline = 保护方向当前 queue_storage_ratio（排队/进口道长度，作溢流风险代理）
cap      = min(baseline + 0.05, 0.80)
```

含义：**治理后保护方向溢流风险不得比现状恶化超过 5 个百分点，且不超过 0.80 红线**。

当 `baseline ≈ 0` 时 cap 可能显示为 `0.05`，需在 UI 中解释为「在现状几乎无排队基础上，最多升至 0.05」，而非绝对上限就是 0.05。优先选用 **草山岭西路** 等 baseline 非零路口演示。

---

## 8. 环境变量

| 变量 | 说明 |
|------|------|
| `EVIDENCE_DEBUG=1` | 后端终端打印完整证据块（联调） |
| `MOCK_DB=1` | 返回确定性 mock 证据（无 PG） |

---

## 9. 相关文件

| 文件 | 说明 |
|------|------|
| `docs/EVIDENCE_FEATURE.md` | 后端实现与表结构 |
| `docs/API.md` | HTTP/SSE 字段总表 |
| `scripts/probe_evidence.py` | CLI 证据探针 |
| `scripts/list_demo_intersections.sql` | 演示路口筛选 SQL |
| `frontend/src/types/evidence.ts` | 前端类型定义 |
