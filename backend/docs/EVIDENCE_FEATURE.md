# 问题验证证据与约束量化（0625 需求）

> 实现日期：2026-06-25  
> 关联需求：`docs/0625.md`

## 1. 能力概述

在用户描述路口拥堵问题后，系统除规则诊断外，额外输出**可量化的问题验证证据**，并在用户补充约束时将经验性表述转为**可执行指标边界**。

| 模块 | 文件 | 职责 |
|------|------|------|
| 问题验证证据 | `services/problem_evidence_service.py` | 常发性、星期规律、排队/延误、分方向画像 |
| 约束量化 | `services/constraint_resolver_service.py` | 自然语言约束 → 指标上限 + 建议裁剪 |
| 终端报告 | `utils/terminal_report.py` | CLI / 调试日志 / 对话 Markdown 格式化 |
| 探针脚本 | `scripts/probe_evidence.py` | 独立验证 SQL 与证据逻辑 |

## 2. 证据维度与数据表

| 证据项 | 字段 | 主表 | 判定口径 |
|--------|------|------|----------|
| 常发性拥堵 | `chronic.is_chronic` | `dwd_tfc_inter_dir_perf_5min` | 近7日中 ≥4 日时段内 `stop_time≥60s` 或 `queue_len_max≥100m` 等 |
| 星期规律 | `dow_pattern.hit_rate` | 同上（按 `ISODOW` 分组） | 用户显式星期优先，否则用提问日 `primary_dow` |
| 平均停车/延误 | `metrics.avg_delay_s` | DWD `stop_time` | 秒 |
| 排队长度 | `metrics.avg_queue_m` / `max_queue_m` | DWD/DWS `queue_len_*` | 米 |
| 溢流风险(估) | `metrics.spillback_risk_max` | DWS `queue_len_avg/rid_length_m` | 作 `queue_storage_ratio` 代理 |
| 分方向 | `by_direction[]` | DWS + cognition | 东西向/南北向等 |

阈值真源：`rules/thresholds.yaml`（`chronic.min_congested_days: 4` 等）。

### 2.1 数据覆盖降级

- **有 DWD 日历数据**：常发性/星期规律基于真实日期统计（`source_tier=dwd_rolling_7d`）
- **仅 DWS**：常发性用饱和度周模式估算，并提示 `coverage_warning`
- **mock 模式**：确定性样例，供单测与无库开发

## 3. 约束量化规则

| 用户表述 | intent | 保护方向 | 量化示例 |
|----------|--------|----------|----------|
| 垂直方向不能溢出 | `no_spillback` | 与主方向正交组 | `东西向 spillback_risk ≤ baseline+0.05` |
| 排队不能加剧 | `no_queue_growth` | 正交组 | `avg_queue_m ≤ baseline×1.1` |
| 不超过 N 秒 | — | global | `delta_seconds ≤ N` |

治理建议生成时调用 `ConstraintResolverService.apply_to_delta()` 保守裁剪 `delta_seconds`。

## 4. 三层可观测性

```bash
# ① CLI 探针（真实库）
cd backend
MOCK_DB=0 .venv/bin/python scripts/probe_evidence.py \
  --intersection "经十路辅路与草山岭西路" \
  --reference-date 2026-06-14

# ② 流水线调试日志
EVIDENCE_DEBUG=1 MOCK_DB=1 uvicorn intersection_agent.main:app --port 8001

# ③ API meta
# 响应 meta.problem_evidence / meta.quantitative_constraints
```

## 5. 流水线接入点

`orchestrator._diagnose()`：

1. `data_fetch` + `cognition` 完成后
2. `ProblemEvidenceService.build()` → `data_payload.problem_evidence`
3. 若存在 `user_suggestion` → `ConstraintResolverService.resolve()`
4. 诊断确认文案 `_format_problem_confirm_message` 嵌入证据摘要
5. 生成建议时 `apply_to_delta` 裁剪并写入 Skill `quantitative_constraints`

## 6. 测试

```bash
cd backend && .venv/bin/pytest tests/test_problem_evidence.py tests/test_constraint_resolver.py tests/test_api.py -q
```

## 7. 已知限制

- 示例路口 `011wwe28ctu00001`（奥体西路×经十路）当前无 DWD/DWS 分向覆盖，探针需换有数据路口或走 `MOCK_DB=1`
- DWD `delay_index` 量纲与规则阈值（1.5）不一致，证据层主用 `stop_time`/`queue_len_*`，规则引擎仍用现有 `evaluation.delay_index`

## 8. 相关文档与脚本

| 文件 | 说明 |
|------|------|
| `docs/FRONTEND_EVIDENCE_INTEGRATION.md` | **前端对接指南**（API 字段、SSE、UI 建议、演示路口） |
| `scripts/list_demo_intersections.sql` | 演示路口完备度筛选 SQL |
| `scripts/probe_evidence.py` | CLI 证据探针 |
| `../docs/0625_IMPLEMENTATION.md` | 需求交付索引（仓库根 `docs/`） |
