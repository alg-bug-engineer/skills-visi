# Release tag2 · 后端完成开发，前端简单验证完成

> 标签：`tag2`  
> 日期：2026-06-24  
> 后端仓库：`backend/` · 前端仓库：`frontend/`（独立 Git）

---

## 1. 本阶段交付摘要

| 维度 | 状态 | 说明 |
|------|------|------|
| 后端核心流水线 | ✅ 完成 | NLU → 路口解析 → 数据查询 → 规则诊断 → 建议 → Skill 固化 |
| SSE 执行钩子 | ✅ 完成 | 中间步骤实时推送，供前端展示 |
| 数据查询方案 D | ✅ 完成 | 近 7 日 DWD 优先，无数据时 DWS 按提问日星期降级 |
| 角色与功能收窄 | ✅ 完成 | **交通智能体 · 拥堵诊断**（不再追问渠化/配时类型） |
| Skill 标准包沉淀 | ✅ 完成 | `SKILL.md` + `reference.md` + `scripts/` + `skill.meta.json` |
| Skill 快路径 | ✅ 完成 | 一致跳过确认 / 有 diff 询问更新 / 首次询问固化 |
| LLM 追问话术 | ✅ 完成 | `FollowUpService` 上下文生成，非写死模板 |
| 前端对话 UI | ✅ 简单验证 | Vue 3 + SSE 执行面板 + 调试日志，联调通过 |
| 自动化测试 | ✅ 35 项 | pytest 全绿（含 SSE、Skill 包、快路径、数据窗） |

---

## 2. 本次讨论与决策记录

### 2.1 产品定位

- **角色固定**：交通智能体  
- **功能固定**：拥堵诊断  
- NLU 必填字段收窄为 `intersection` + `time_period`，`problem_type` 内部固定为 `congestion`  
- 追问与建议文案不再引导渠化、信号配时等非拥堵话题  

### 2.2 Skill 存储演进

| 阶段 | 方案 | 结论 |
|------|------|------|
| v1.0.0 | SQLite `skills.db` | 已废弃 |
| 中间尝试 | 单文件 JSON | 不符合 Agent Skill 规范，已废弃 |
| **tag2** | **标准 Skill 包目录** | 当前方案 |

每个固化技能目录示例：

```
data/skills/congestion-{inter_id}-{time-period}/
├── SKILL.md                 # YAML frontmatter + 执行流程（Cursor Agent 可加载）
├── skill.meta.json          # 机器索引（快路径匹配）
├── reference.md             # 规则、结论、数据窗口
└── scripts/
    ├── fetch_traffic_data.py
    └── fetch_traffic_data.sql
```

### 2.3 数据查询（方案 D）

1. 优先 `dwd_tfc_inter_dir_perf_5min`：近 7 自然日 + 时段 + `dow_filter`  
2. DWD 无样本 → DWS 降级为 `primary_dow`（提问日星期几）  
3. `meta.data_window` 透出 `source_tier`、`fallback_reason` 等，前端执行面板可展示  

### 2.4 前端联调

- 一键启动：`bash scripts/dev.sh`（根目录，后端 8011 / 前端 5567）  
- SSE：`POST /api/v1/sessions/{id}/messages/stream`  
- 已验证：对话、执行步骤、诊断、Skill 固化/快路径基本流程  

---

## 3. 关键新增/变更模块

| 模块 | 路径 |
|------|------|
| Skill 包构建器 | `intersection_agent/skills/package_builder.py` |
| Skill 领域模型 | `intersection_agent/models/skill.py` |
| 追问服务 | `intersection_agent/services/follow_up_service.py` |
| 数据时间窗 | `intersection_agent/utils/data_window.py` |
| SSE | `intersection_agent/api/sse.py` |
| 执行钩子 | `intersection_agent/hooks/` |
| Skill 清理 | `scripts/clear_skills.sh` |

---

## 4. 运行与验证

```bash
# 根目录一键启动
bash scripts/stop-dev.sh && bash scripts/dev.sh

# 后端单测
cd backend && MOCK_LLM=1 MOCK_DB=1 pytest -q

# 清空 Skill 包（重复测试）
bash backend/scripts/clear_skills.sh --force
```

| 服务 | 地址 |
|------|------|
| 前端 | http://127.0.0.1:5567 |
| 后端 | http://127.0.0.1:8011/health |

---

## 5. 已知限制（tag2 后）

- Session 内存存储，多实例需 Redis  
- 规则 YAML 仍含非 congestion 规则条目，运行时仅诊断 congestion  
- 前端为**测试验证 UI**，非生产级产品设计  
- 根目录 `scripts/dev.sh` 未纳入 backend/frontend Git，需随项目一起分发  

---

## 6. Git 标签

```bash
# 后端
cd backend && git checkout tag2

# 前端
cd frontend && git checkout tag2
```

标签说明：**后端完成开发，前端简单验证完成**
