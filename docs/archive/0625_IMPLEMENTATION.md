# 0625 需求实现说明（问题验证证据 + 约束量化）

> 需求原文：`./0625.md`  
> 后端实现：`backend/docs/EVIDENCE_FEATURE.md`  
> **前端对接：`backend/docs/FRONTEND_EVIDENCE_INTEGRATION.md`**

## 交付清单

| 类别 | 路径 |
|------|------|
| 问题验证服务 | `backend/intersection_agent/services/problem_evidence_service.py` |
| 约束量化服务 | `backend/intersection_agent/services/constraint_resolver_service.py` |
| 终端/对话格式化 | `backend/intersection_agent/utils/terminal_report.py` |
| CLI 探针 | `backend/scripts/probe_evidence.py` |
| 演示路口 SQL | `backend/scripts/list_demo_intersections.sql` |
| 阈值配置 | `backend/rules/thresholds.yaml` |
| 前端类型 | `frontend/src/types/evidence.ts` |
| 单测 | `backend/tests/test_problem_evidence.py`、`test_constraint_resolver.py` |

## 联调要点

1. API `meta.problem_evidence`、`meta.quantitative_constraints`
2. SSE 步骤 `problem_evidence`
3. 真实库联调使用 `reference-date 2026-06-14`，推荐路口见前端对接文档 §6
4. `奥体西路×经十路` 无 DWD 分向数据，勿作全链路真实库验收路口

## 快速验证

```bash
cd backend && .venv/bin/pytest -q
MOCK_DB=0 .venv/bin/python scripts/probe_evidence.py \
  --intersection "奥体西路与经十路交叉口" --reference-date 2026-06-14
```
