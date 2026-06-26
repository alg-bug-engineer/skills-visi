# 路口诊断智能体 · 后端开发计划

> 版本：1.0.0  
> 更新：2026-06-24  
> 范围：API 后端（FastAPI），支持 curl 端到端测试

---

## 1. 目标与交付物

| 交付物 | 说明 |
|--------|------|
| REST API | 会话创建、消息交互、Skill 查询 |
| 状态机 | NLU 补全、路口降级、诊断、固化确认 |
| 数据层 | PostgreSQL（road6 + xianchang）三级路口匹配 |
| 规则引擎 | YAML 确定性诊断 + 安全公式求值 |
| LLM 层 | 阿里百炼 Qwen（NLU / 文案 / 路口规范化） |
| 测试 | pytest 单元 + 集成；`scripts/curl_tests.sh` |
| 文档 | 计划、进度、约束、排障、API |

---

## 2. 架构

```
Client (curl)
    │
    ▼
FastAPI (/api/v1)
    │
    ├── SessionStore (内存 + 可选 Redis)
    ├── SkillStore (SQLite 本地持久化)
    │
    └── Orchestrator (状态机)
            ├── SkillMatcher (快路径)
            ├── NLUService (Qwen + 字段补全)
            ├── IntersectionResolver (精确→变体→候选)
            ├── DataFetcher (PG 多表聚合)
            ├── RuleEngine (YAML)
            └── SuggestionService (公式 + Qwen 文案)
```

---

## 3. 会话状态机

| 状态 | 触发 | 下一状态 |
|------|------|----------|
| `idle` | 创建会话 | — |
| `nlu_incomplete` | 必填字段缺失 | 用户补全 → `processing` |
| `intersection_ambiguous` | 路口未命中，有候选 | 用户选择 → `processing` |
| `processing` | 数据+规则+建议 | `awaiting_confirm` 或 `done`(无诊断) |
| `awaiting_confirm` | 等待固化 | 确认 → `done` + Skill；否定 → `done` |
| `done` | 会话结束 | — |

---

## 4. API 契约

### 4.1 创建会话

```http
POST /api/v1/sessions
Response: { "session_id": "uuid", "state": "idle" }
```

### 4.2 发送消息

```http
POST /api/v1/sessions/{session_id}/messages
Body: { "content": "..." }
Response: MessageResponse (见 schemas)
```

### 4.3 查询会话 / Skill

```http
GET /api/v1/sessions/{session_id}
GET /api/v1/skills?intersection=...
GET /health
```

---

## 5. 分支与边界覆盖

### 5.1 NLU

- [x] 完整输入一次通过
- [x] 缺路口 → 追问路口
- [x] 缺时段 → 追问时段
- [x] 缺问题类型 → 追问类型
- [x] 多轮合并重提取（非字段拼接）
- [x] 缺方向/建议 → 不追问
- [x] JSON 解析失败 → 友好错误

### 5.2 路口匹配

- [x] L1 精确匹配 `dim_inter_info`
- [x] L2 Qwen 变体 + pg_trgm / LIKE 模糊
- [x] L3 Top-K 候选反问
- [x] 完全无数据 → 明确提示
- [x] 变体命中 → 告知实际匹配名

### 5.3 数据获取

- [x] DWS 有覆盖 → 聚合指标
- [x] 无 DWS → `missing_dws_coverage` 降级
- [x] 时段映射：自然语言 → step_index 区间

### 5.4 规则诊断

- [x] 单规则命中
- [x] 多规则按 priority 取首条
- [x] 无命中 → `diagnosed: false` + 原因码
- [x] 非信控主因预留 `control_ceiling: low/none`

### 5.5 Skill

- [x] 确认词：是/可以/确认/好/行/ok/yes
- [x] 否定词：否/不/取消
- [x] 否定词优先于确认词（「不是」不误触）
- [x] 快路径：Skill 命中跳过 NLU

### 5.6 Mock 模式

- `MOCK_LLM=1`：固定 NLU/文案，离线测试
- `MOCK_DB=1`：内存假数据，离线测试

---

## 6. 里程碑

| 阶段 | 内容 | 验收 |
|------|------|------|
| M1 | 工程脚手架、配置、文档 | git init, pytest 空跑 |
| M2 | 状态机 + API 骨架 | curl 创建会话 |
| M3 | NLU + 路口解析 | 追问分支 curl 通过 |
| M4 | PG 数据层 + 降级 | 真实/ mock 查数 |
| M5 | 规则引擎 + 建议 | 诊断结果 JSON |
| M6 | Skill 固化 + 快路径 | 二次对话固化 |
| M7 | 全量测试 + curl 脚本 | pytest 绿 |
| M8 | 执行钩子 + SSE 流式 API | 前端实时步骤展示 |
| M9 | Vue 3 前端对话测试 | `frontend/` 联调通过 |

---

## 10. 前端（frontend/）

独立 Vue 3 工程，详见 `frontend/docs/DEVELOPMENT_PLAN.md`。

- 对话式完整交互测试
- SSE 执行过程面板
- Vite 开发代理 → `localhost:8000`

---

## 7. 技术栈

- Python 3.11+
- FastAPI + Uvicorn
- Pydantic v2
- asyncpg（PostgreSQL）
- httpx（Qwen OpenAI 兼容接口）
- simpleeval（安全公式）
- pytest + pytest-asyncio
- SQLite（Skill 持久化）

---

## 8. 规范

- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- 类型注解 + Google docstring
- `ruff` lint，`pytest` 测试覆盖率目标 ≥ 80% 核心模块
- 密钥仅 `.env`，不入库（`.gitignore`）

---

## 9. 目录结构

```
backend/
├── intersection_agent/     # 主包
├── rules/                  # YAML 规则
├── tests/
├── scripts/curl_tests.sh
├── docs/
├── pyproject.toml
├── .env.example
└── README.md
```
