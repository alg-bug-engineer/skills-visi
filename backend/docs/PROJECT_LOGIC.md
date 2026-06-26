# 项目逻辑与特点说明

> 路口问题诊断与 Skill 固化智能体 · 后端核心设计  
> 示例路口：**奥体西路与经十路路口**（`inter_id=011wwe28ctu00001`）

---

## 1. 总体定位

本系统面向交警口语化描述，完成 **理解 → 查数 → 规则诊断 → 治理建议 → 可选固化** 的闭环。  
核心原则：**LLM 负责理解与表达，YAML 规则负责判断，用户 Skill 负责经验复用**。

```
用户自然语言
    ↓
[Skill 快路径?] ──是──→ 带参数重跑流水线
    ↓ 否
NLU 理解（可追问补全）
    ↓
路口三级匹配（精确→变体→候选）
    ↓
PostgreSQL 数据聚合（按时段 step_index）
    ↓
YAML 规则引擎（确定性）
    ↓
确认是否生成治理建议（可直接补充约束）
    ↓
公式计算 + Qwen 文案
    ↓
展示治理建议并二次确认是否固化 Skill
    ↓
确认后沉淀为路口 Skill
```

---

## 2. 特点亮点

### 2.1 多轮 NLU 与智能追问

**问题**：交警输入常不完整（只说路口、不说时段；或只说「很堵」不说类型）。

**做法**：

| 字段 | 必填 | 缺失时 |
|------|------|--------|
| `intersection` | ✅ | 追问路口 |
| `time_period` | ✅ | 追问时段 |
| `problem_type` | — | 固定 `congestion`，不追问 |
| `directions` | ✅ | 追问进口方向（如南北向、东西向） |
| `user_suggestion` | ❌ | 不追问；首轮或确认轮提供时用于治理建议，并触发 Skill 沉淀 |

**定位（tag2）**：角色为「交通智能体」，功能仅为拥堵诊断；追问不提渠化、信号配时。

**亮点**：

1. **合并重提取**：每轮追问后，将所有用户历史合并后重新调用 Qwen 提取，避免字段拼接错误。
2. **单字段追问**：一次只追问优先级最高缺失项（路口 > 时段 > 方向）。
3. **LLM 生成话术**：`FollowUpService` 根据对话历史、已识别信息与缺失字段，生成自然追问（非固定模板）；LLM 失败时降级为简短 fallback。
3. **时段归一化**：「下午四点」→ `{start:"16:00", end:"18:00", label:"晚高峰"}`。

实现：`intersection_agent/services/nlu_service.py`

### 2.2 路口名称标准化与三级降级

**问题**：口语与库中标准名不一致——顺序颠倒、缩写、后缀不同（「交叉口」vs「路口」）。

**库中标准名示例**：`奥体西路与经十路路口`（非「交叉口」）

**三级匹配策略**：

| 级别 | 策略 | 示例 |
|------|------|------|
| L1 精确 | `inter_name` 完全相等 | `奥体西路与经十路路口` |
| L2 变体 | Qwen 生成变体 + LIKE 模糊 | `经十路与奥体西路交叉口` → 命中 |
| L3 候选 | Top-K 相似名反问用户 | 用户确认后进入诊断 |

**已验证变体**（见 `scripts/probe_intersection.py`）：

- 奥体西路与经十路交叉口
- 经十路与奥体西路交叉口
- 奥体西与经十路
- 经十路和奥体西
- 奥体西路经十路路口

变体命中时响应中带 `resolution_source=variant`，并提示「已自动匹配为：XXX」。

实现：`intersection_agent/services/intersection_resolver.py`

### 2.3 数据查询时间窗（方案 D）

自然语言时段 + **参考日（默认当天，Asia/Shanghai）** 解析为 `DataWindow`：

| 字段 | 说明 |
|------|------|
| `date_from` ~ `date_to` | 滚动 7 个自然日（含参考日） |
| `time_slot` | NLU 时段，如 16:00–18:00 |
| `dow_filter` | 晚高峰/工作日 → 周一至五；周末 → 六日 |
| `step_index` | 5 分钟片 0–287 |

每次数据获取会记录 `query_trace`，其中包含：

- 已替换 `$1` / `$2` 等参数的可执行 SQL
- 原始参数
- 原始返回行
- 返回行数

`query_trace` 同步进入服务日志与响应 `meta.query_trace`，用于诊断抓数口径和复盘数据来源。

**查询优先级**：

1. **DWD 明细** `dwd_tfc_inter_dir_perf_5min`：按日历窗 + 每日时段聚合（`source_tier=dwd_rolling_7d`）
2. **DWS 周模式** 降级：按 `dow_filter` + `step_index`（`source_tier=dws_weekday_pattern`）
3. 均无数据 → `missing_dws_coverage`

响应 `meta.data_window` 与 SSE `data_fetch` 步骤同步透出，Skill 快照写入 `data_query_spec.data_window`。

实现：`intersection_agent/utils/data_window.py`、`intersection_agent/services/data_fetcher.py`

### 2.4 确定性规则引擎（非 LLM 判断）

业务规则与代码解耦，交通工程师维护 `rules/traffic_rules.yaml`：

```yaml
conditions:
  - metric: evaluation.delay_index
    operator: ">"
    threshold: 1.5
  - metric: signal_plan.green_ratio
    operator: "<"
    threshold: 0.35
logic: AND
```

- 支持 `AND` / `OR`、优先级排序
- 公式通过 `simpleeval` 安全求值（禁止裸 `eval`）
- 未命中时返回 `reason_code`（如 `no_rule_matched`、`missing_dws_coverage`）

实现：`intersection_agent/services/rule_engine.py`

### 2.5 治理建议：数值确定 + 文案 LLM

| 部分 | 来源 | 示例 |
|------|------|------|
| `delta_seconds` | YAML 公式 | `min(saturation * cycle * 0.15, 20)` |
| `direction` | 规则 action | `increase` / `decrease` |
| `narrative` | Qwen 生成 | ≤100 字自然语言 |
| `confidence` | 规则配置 | 0.85 |

治理建议生成前后有两段用户确认：

1. **诊断成立后**：若首轮没有识别到 `user_suggestion`，进入 `suggestion_action=awaiting_generate`，暂停等待用户确认或补充约束。
2. **治理建议生成后**：若用户提供了约束/建议，先展示治理建议，再进入 `skill_action=awaiting_create`，等待用户确认是否沉淀 Skill。

若用户仅回复“是”生成治理建议，且没有额外约束/建议，则返回 `skill_action=skipped_no_user_suggestion`，不沉淀 Skill。

实现：`intersection_agent/services/suggestion_service.py`

### 2.8 问题验证证据与约束量化（0625）

**问题**：仅回复「确实拥堵」无法体现智能体价值；用户经验约束（如垂直方向不能溢出）需转化为可量化边界。

**做法**：

| 能力 | 说明 |
|------|------|
| 问题验证证据 | 常发性（近7日≥4日超标）、星期规律（显式星期优先）、排队/延误、分方向画像 |
| 约束量化 | 「垂直方向不能溢出」→ 正交方向 `spillback_risk`/`queue_m` 上限；裁剪 `delta_seconds` |
| 可观测性 | CLI `probe_evidence.py`、`EVIDENCE_DEBUG=1` 终端报告、API `meta.problem_evidence` |

实现：`problem_evidence_service.py`、`constraint_resolver_service.py`、`utils/terminal_report.py`  
详见：`docs/EVIDENCE_FEATURE.md`

### 2.6 用户 Skill 固化与快路径

**Skill 不是重写流程**，而是可加载的 **标准 Agent Skill 包**（诊断快照 + 查数脚本）：

```
data/skills/congestion-{inter_id}-{period}/
├── SKILL.md
├── skill.meta.json
├── reference.md
└── scripts/fetch_traffic_data.{py,sql}
```

索引字段：`inter_id` + `problem_type` + 时段 label + `match_keywords`；快照含 `rule_ids`、`data_query_spec`、`suggestion_formula`。

**快路径**：命中后带 `rule_ids` 重跑查数 + 规则；结论一致则 `skill_action: verified` 直接结束。

`user_suggestion` 会写入 `skill.meta.json`、`SKILL.md` 与 `reference.md`，作为后续治理建议生成时必须优先体现的约束。

实现：`intersection_agent/services/skill_service.py`、`intersection_agent/skills/package_builder.py`

### 2.7 会话状态机

```
idle → nlu_incomplete → processing
     → intersection_ambiguous → processing
     → awaiting_confirm(suggestion_action=awaiting_generate)
     → done(仅生成建议，无约束不沉淀)
     → awaiting_confirm(skill_action=awaiting_create)
     → done(+ skill)
```

实现：`intersection_agent/services/orchestrator.py`

---

## 3. 数据层设计

双 Schema：

| Schema | 职责 | 关键表 |
|--------|------|--------|
| `road6` | 路网/渠化 | `dim_inter_info`, `dwd_tfc_rltn_wide_inter_ft_link` |
| `xianchang` | 运行/信控 | `dws_inter_evaluation_5min_mm`, `dws_turn_saturation_5min_mm`, `dwd_ctl_inter_plan_cfg` |

聚合指标：

- 饱和度：`dws_turn_saturation_5min_mm` / `dws_inter_evaluation_5min_mm`
- 延误指数：`dwd_tfc_inter_dir_perf_5min.delay_index`
- 绿信比：配时方案阶段绿 / 周期
- 失衡：`unbalance_index`

---

## 4. 测试与运维脚本

| 脚本 | 用途 |
|------|------|
| `scripts/clear_skills.sh` | 清空本地 Skill 包目录 |
| `scripts/probe_intersection.py` | 路口变体解析 + DWS 时段指标嗅探 |
| `scripts/boundary_tests.sh` | NLU/路口/时段/治理/Skill 边界全覆盖 |
| `scripts/curl_tests.sh` | 快速冒烟测试 |

**真实联调推荐顺序**：

```bash
bash scripts/clear_skills_db.sh --force
python3 scripts/probe_intersection.py
MOCK_LLM=0 MOCK_DB=0 uvicorn intersection_agent.main:app --port 8001
bash scripts/boundary_tests.sh http://127.0.0.1:8001
```

---

## 5. 与 docs/ 目录关系

| 文档 | 关系 |
|------|------|
| `docs/taolun.md` | 原始设计讨论 |
| `docs/路口专家经验规则.md` | 规则阈值与专家经验（YAML 可对齐扩展） |
| `docs/PG_DATABASE_SCHEMA.md` | 数据库表结构真源 |
| `docs/ali-bailian.md` | Qwen 模型与 API Key |

---

## 7. LLM 结构化输出（NLU）

### 7.1 模型是否支持？

**支持。** `qwen3.6-flash-2026-04-16` 在阿里百炼 **非思考模式** 下支持 JSON Object 结构化输出。

官方文档：[如何让千问生成 JSON 字符串](https://help.aliyun.com/zh/model-studio/qwen-structured-output)

| 要求 | 说明 |
|------|------|
| `response_format` | `{"type": "json_object"}` |
| 提示词含 JSON | system 或 user 中必须出现 "JSON" |
| `enable_thinking` | 必须为 `false`（思考模式不支持 JSON Mode） |
| 勿设 `max_tokens` | 截断会导致非法 JSON |

### 7.2 如何保证业务 schema？

JSON Mode 只保证 **合法 JSON**，不保证字段名与 schema 一致（模型可能返回 `location` 而非 `intersection`）。

本项目采用 **四层保障**：

1. **JSON Mode**：`QwenClient.chat_json()` 开启 `response_format`
2. **严格 Prompt**：在 system 中给出完整字段示例，禁止别名
3. **字段归一化**：`NluService._normalize_raw()` 映射 `location→intersection`、`issue→problem_type`、字符串时段→对象
4. **解析重试**：JSON 解析失败时追加纠错提示重试（最多 2 次）

治理建议文案不走 JSON Mode，仅 NLU 与路口变体归一化使用。

### 7.3 终端报错说明

`boundary_tests.sh` 出现 `JSONDecodeError: Expecting value` 通常表示 **API 返回空体或 500**，而非模型 JSON 格式问题。常见根因：

- 数据库字段与 SQL 不一致（已修复 `delay_index`、`empty_green_rate` 查询）
- 服务未启动或请求超时

修复后 500 会返回 JSON 格式 `{"reply":{"type":"error",...},"detail":"..."}`。

---

## 8. 后续演进方向

- 场景认知独立阶段（供给-需求-状态画像）
- 规则「不成立」时的委婉分析分支
- Redis 多实例 Session 持久化
- pg_trgm 相似度替代纯 LIKE 模糊匹配
