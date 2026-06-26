# 交通智能体 · 拥堵诊断 · 后端

基于 FastAPI + Qwen + PostgreSQL + YAML 规则引擎的路口拥堵诊断与标准 Skill 包固化 API。

> 当前标签：**`新增 Skills 可视化`** — Skills 固化可视化 + 地图场景编排。  
> 上一标签：`tag2` — 后端完成开发，前端简单验证。详见 [docs/RELEASE_新增Skills可视化.md](docs/RELEASE_新增Skills可视化.md) · [docs/RELEASE_tag2.md](docs/RELEASE_tag2.md)

## 快速开始

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# 离线开发可设置 MOCK_LLM=1 MOCK_DB=1

uvicorn intersection_agent.main:app --host 127.0.0.1 --port 8011
```

项目根目录 `bash scripts/dev.sh` 可同时启动前端（5567）。

## 测试脚本

```bash
MOCK_LLM=1 MOCK_DB=1 pytest -q

bash scripts/curl_tests.sh http://127.0.0.1:8011
bash scripts/clear_skills.sh --force
python3 scripts/probe_intersection.py
MOCK_DB=0 python3 scripts/probe_evidence.py --intersection "奥体西路与经十路交叉口" --reference-date 2026-06-14
```

## 文档

| 文档 | 说明 |
|------|------|
| [docs/RELEASE_新增Skills可视化.md](docs/RELEASE_新增Skills可视化.md) | **当前发布说明（必读）** |
| [docs/RELEASE_tag2.md](docs/RELEASE_tag2.md) | tag2 发布说明 |
| [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md) | 项目状态快照 |
| [docs/PROJECT_LOGIC.md](docs/PROJECT_LOGIC.md) | 架构与亮点 |
| [docs/API.md](docs/API.md) | API / SSE 参考 |
| [docs/EVIDENCE_FEATURE.md](docs/EVIDENCE_FEATURE.md) | 问题验证证据与约束量化（0625） |
| [docs/FRONTEND_EVIDENCE_INTEGRATION.md](docs/FRONTEND_EVIDENCE_INTEGRATION.md) | **前端对接指南** |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | 变更记录 |

## 架构概览

```
POST /api/v1/sessions/{id}/messages[/stream]
  → Orchestrator
      → SkillMatcher（标准 Skill 包快路径）
      → NLUService（拥堵诊断 + LLM 追问）
      → IntersectionResolver
      → DataFetcher（方案 D）
      → ProblemEvidenceService（问题验证证据）
      → RuleEngine
      → ConstraintResolverService（约束量化，生成建议时裁剪 delta）
      → SuggestionConfirm（确认是否生成治理建议，可补充约束）
      → SuggestionService
      → SkillConfirm（生成建议后再次确认是否固化）
      → SkillPackageBuilder（确认后固化 SKILL.md + scripts）
```

## 当前交互流程

- 首轮 NLU 需要识别路口、时段、方向，默认案例统一使用“南北向”。
- 数据获取会在日志和响应 `meta.query_trace` 中留存可直接执行的 SQL 与原始返回数据，便于复盘抓数正确性。
- 若诊断成立但用户未提供约束/建议，先停在“是否生成治理建议”，用户可确认、拒绝或直接补充约束。
- 若用户在首轮或确认轮提供约束/建议，先生成治理建议并展示给用户，再进入“是否固化 Skill”的二次确认。
- 只有用户确认固化后才写入标准 Skill 包；若用户只是确认生成建议且未补充约束，则不触发 Skill 沉淀。
