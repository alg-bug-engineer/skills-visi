# 前端 Mock 数据采集指南

`scripts/capture_frontend_mock.py` 用于把后端真实跑出的一次「完整九幕」数据，固化成前端离线回放用的 mock fixture，方便反复调试页面 UI/布局，而不必每次都发起真实请求（真实请求要连 Qwen + PostgreSQL，耗时数十秒且受模型时延影响）。

## 产物

- 默认输出：`frontend/src/mock/run_1_fixture.json`
- 结构与 `POST /api/v1/agent/run` 的返回（`build_public_run_response`）完全一致：

```json
{
  "trace_id": "...",
  "completed": true,
  "pipeline_complete": true,
  "diagnosis_ticket": {...},
  "phases": {...},
  "plan": {...},
  "phase_results": [...]
}
```

- 前端 `frontend/src/api/endpoints.ts` 在 MOCK 模式下会 `import` 该文件，用于「单次回放」和「模拟流式」两种消费方式。

## 三种采集方式

在项目根目录执行（用项目自带虚拟环境 `.venv`）。

### 1. 从最新完整日志提取（默认，推荐）

不打模型、稳定。自动在 `logs/run_1/` 下取最新一条 `completed=true` 的运行日志，复用其中已存的 `public_response`。

```bash
.venv/bin/python scripts/capture_frontend_mock.py
```

可选：指定输出路径（覆盖默认 fixture 路径）。

```bash
.venv/bin/python scripts/capture_frontend_mock.py frontend/src/mock/run_1_fixture.json
```

若 `logs/run_1/` 下没有 `completed=true` 的日志，会报错提示，需要先跑一次真实请求（见下），或改用 `--live` 现采。

### 2. 从指定日志文件提取

已经知道某条日志跑得完整，直接指定它。

```bash
.venv/bin/python scripts/capture_frontend_mock.py --from-log logs/run_1/xxxx.json
# 可选：追加自定义输出路径
.venv/bin/python scripts/capture_frontend_mock.py --from-log logs/run_1/xxxx.json frontend/src/mock/run_1_fixture.json
```

> 注意：不要指定以 `_steps.json` 结尾的日志；脚本只识别完整的运行日志。若该运行 `completed != true`（有 phase 失败），脚本会告警并且不建议作为 mock。

### 3. 实时现采（发起一次真实请求）

直连 Qwen/PG，跑一遍完整流水线后固化结果。耗时数十秒。

```bash
# 用脚本内置默认问题
.venv/bin/python scripts/capture_frontend_mock.py --live
# 或自定义问题
.venv/bin/python scripts/capture_frontend_mock.py --live "转山西路与经十路交叉口，六点十分到六点半，东向西排队溢出到上游，优先避免下游继续外溢。"
# 可选：再追加输出路径
.venv/bin/python scripts/capture_frontend_mock.py --live "自定义问题" frontend/src/mock/run_1_fixture.json
```

前置条件：

- `.env` 中 `LLM_MOCK=false`（否则采集到的是规则化 mock 数据，脚本会告警）
- PostgreSQL 可达、`QWEN_API_KEY` 已配置

若流水线未完整完成（个别 phase 失败/超时），脚本不会覆盖已有 fixture，返回码 `2`，建议重试。

## 参数与退出码

| 用法 | 参数位置 |
| --- | --- |
| `capture_frontend_mock.py` | `[输出路径]`（可选） |
| `capture_frontend_mock.py --from-log <日志路径> [输出路径]` | 日志路径必填 |
| `capture_frontend_mock.py --live ["问题"] [输出路径]` | 均可选 |

退出码：`0` 成功；`1` 未找到日志/日志不存在；`2` 数据未完整完成（未覆盖）。

## 让前端用上新 fixture

fixture 是被前端 `import` 的静态 JSON，采集后需要重启/热更新 Vite 才能生效：

1. 确认 `frontend/.env.local` 中 `VITE_MOCK=1`（开启 mock 回放）。
2. 重新采集覆盖 `frontend/src/mock/run_1_fixture.json`。
3. 重启前端开发服务器（`npm run dev`），页面即以离线数据回放整套九幕流程。

将 `VITE_MOCK` 置为 `0` 或删除，前端则改为请求真实后端（`VITE_API_TARGET`）。
