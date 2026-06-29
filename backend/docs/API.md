# API 参考

Base URL: `http://localhost:8000`

## Health

```bash
curl -s http://localhost:8000/health
```

响应：

```json
{"status": "ok", "mock_llm": false, "mock_db": false}
```

## 创建会话

```bash
curl -s -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json"
```

## 发送消息

```bash
SESSION_ID="<from create>"
curl -s -X POST "http://localhost:8000/api/v1/sessions/${SESSION_ID}/messages" \
  -H "Content-Type: application/json" \
  -d '{"content": "奥体西路与经十路交叉口，下午四点南北向经常拥堵，应该绿灯更长一点"}'
```

### 治理建议与 Skill 固化确认

诊断成立后的确认分为两段：

1. `suggestion_action=awaiting_generate`：问题已诊断成立，等待用户确认是否生成治理建议。用户可回复“是”，也可直接输入约束或建议。
2. `skill_action=awaiting_create`：治理建议已生成并展示，等待用户确认是否固化为 Skill。只有此时再次确认，才会写入 Skill 包。

如果用户仅确认生成建议且没有补充约束，响应会返回 `skill_action=skipped_no_user_suggestion`，不进行技能沉淀。

## 发送消息（SSE 流式，含执行过程）

前端联调推荐使用此端点，实时推送 NLU、数据查询、规则诊断等中间步骤。

```bash
curl -N -X POST "http://localhost:8000/api/v1/sessions/${SESSION_ID}/messages/stream" \
  -H "Content-Type: application/json" \
  -d '{"content": "奥体西路与经十路交叉口，下午四点南北向拥堵"}'
```

响应 `Content-Type: text/event-stream`，每行 `data: {...}`：

| event | 说明 |
|-------|------|
| `step` | 执行步骤：`step`, `status`（running/completed/failed）, `label`, `data` |
| `result` | 最终 `MessageResponse`（与同步接口相同结构） |
| `error` | 执行异常 |
| `done` | 流结束 |

步骤 ID：`orchestrator.start` → `nlu` → `skill_match` → `intersection` → `intersection_cognition` → `map_action` → `data_fetch` → **`problem_evidence`** → `rule_engine` → `suggestion` → `confirm_intent` → `skill_create` → `complete`

### SSE 扩展事件

| event | 说明 |
|-------|------|
| `skill_build` | 技能固化可视化（`skill_build_start` / `drawer_open` / `skill_build_file_chunk` / `drawer_close` / `skill_build_done` 等） |
| `skill_absorption` | 经验吸收可视化（`skill_absorption_start` / `stage_start` / `thought_delta` / `evidence` / `skill_absorption_done` 等） |
| `map_scene` | 地图场景数据（phase、markers、highlights、hud） |

`skill_build_done` 载荷含 `download_url`，对应下载接口。

### skill_absorption 事件（经验吸收）

在用户确认固化后、`skill_build` 之前推送。`type` 取值：

| type | 说明 |
|------|------|
| `skill_absorption_start` | 开始吸收，含 `skill_id`、`intersection`、`action`（CREATE/UPDATE/UNCHANGED） |
| `stage_start` | 阶段开始：`recap` / `decompose` / `retrieve` / `compare` / `value` / `blueprint` |
| `thought_delta` | 系统自言自语日志流（模板 + 真实字段） |
| `evidence` | 结构化证据：`chips`、`candidates`、`changes` 等 |
| `stage_done` | 阶段结束，含 `duration_ms` |
| `skill_absorption_done` | 吸收完成，`progress: 100` |

`skill_absorption_done` 之后衔接 `write_phase_start`（同属 `skill_absorption` 事件）→ `skill_build_start` / `drawer_open` → 逐文件 L3 交错写入 → `drawer_close` → `skill_build_done`。

### skill_build 抽屉事件（v2 · L3 交错）

| type | 说明 |
|------|------|
| `drawer_open` | 左抽屉滑入，开始终端风格落盘展示 |
| `skill_build_file_chunk` | 单文件内容增量（与右栏吸收联动行同步） |
| `drawer_close` | 抽屉收起前完成态 |
| `skill_build_done` | 落盘结束，含 `download_url` |

## 下载 Skill 包

```bash
curl -s -o skill.zip "http://localhost:8011/api/v1/skills/${SKILL_ID}/download"
```

返回 `application/zip`。

## 查询会话

```bash
curl -s "http://localhost:8000/api/v1/sessions/${SESSION_ID}"
```

## 列出 Skill

```bash
curl -s "http://localhost:8000/api/v1/skills"
curl -s "http://localhost:8000/api/v1/skills?intersection=奥体"
curl -s "http://localhost:8000/api/v1/skills/leaderboard?sort=hits"
```

## 响应字段说明

| 字段 | 说明 |
|------|------|
| `state` | 会话状态 |
| `reply.type` | `text` / `follow_up` / `diagnosis` / `skill_created` / `error` |
| `reply.content` | 展示给用户的 Markdown 文本 |
| `meta.matched_skill` | 是否走 Skill 快路径 |
| `meta.resolution_source` | 路口匹配级别 |
| `meta.suggestion_action` | 治理建议确认状态：`awaiting_generate` / `generated` / `generated_with_user_suggestion` / `declined` |
| `meta.skill_action` | Skill 固化状态：`awaiting_create` / `created` / `updated` / `verified` / `skipped_no_user_suggestion` |
| `meta.query_trace` | 数据抓取可执行 SQL、参数与原始返回数据（用于复盘） |
| `meta.problem_evidence` | 问题验证证据：常发性、星期规律、排队/延误、分方向（见 `docs/FRONTEND_EVIDENCE_INTEGRATION.md`） |
| `meta.quantitative_constraints` | 用户约束量化：`narrative` + `constraints[]` 指标边界 |
| `diagnosis` | 结构化诊断（如有） |

`problem_evidence` SSE 步骤 `data` 含 `summary`、`chronic`、`dow_pattern`、`metrics`、`by_direction`；若已解析用户约束，另含 `quantitative_constraints`（与 `meta` 同结构）。

前端对接详见 **`docs/FRONTEND_EVIDENCE_INTEGRATION.md`**；演示路口 SQL：`scripts/list_demo_intersections.sql`。

完整 curl 场景见 `scripts/curl_tests.sh`。

## 语音合成（Qwen-TTS Realtime）

前端关键点引导式播报，后端代理 DashScope WebSocket，需配置 `DASHSCOPE_API_KEY` 与 `DASHSCOPE_WORKSPACE_ID`。

| 端点 | 说明 |
|------|------|
| `POST /api/v1/tts/synthesize` | 整段 WAV（回退） |
| `POST /api/v1/tts/synthesize/stream` | PCM 流式（首选，低延迟） |

请求体：`{"text": "开始分析运行数据。", "cue_id": "step:3:data_fetch"}`（`text` ≤300 字）

流式响应头：`X-Audio-Sample-Rate`（24000）、`X-Audio-Channels`（1）、`X-Audio-Sample-Width`（2）。

环境变量：`TTS_ENABLED=1`、`QWEN_TTS_MODEL=qwen3-tts-flash-realtime`、`QWEN_TTS_VOICE=Cherry`、`QWEN_TTS_MODE=commit`。
