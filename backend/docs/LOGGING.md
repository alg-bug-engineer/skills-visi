# 日志系统说明

## 概述

后端采用标准库 `logging`，统一格式、请求 ID 贯穿、关键业务事件结构化记录。

## 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FILE` | `data/logs/app.log` | 滚动日志文件路径 |

日志同时输出到 **控制台** 与 **文件**（10MB × 5 份轮转）。

## 日志格式

```
2026-06-24 10:00:00 INFO [intersection_agent.api.routes] [req=abc-123] event=message.received | session_id=... | input=...
```

- `req=`：请求 ID，来自 `X-Request-ID` 头或自动生成
- 响应头会回写 `X-Request-ID`，便于前后端联调追踪

## 事件清单

| event | 模块 | 说明 |
|-------|------|------|
| `http.request` / `http.response` / `http.error` | middleware | HTTP 入站/出站/异常 |
| `session.created` | routes | 新建会话 |
| `message.received` / `message.completed` / `message.failed` | routes | 用户消息处理 |
| `message.stream.received` / `message.stream.completed` / `message.stream.failed` | routes | SSE 流式消息 |
| `orchestrator.start` | orchestrator | 状态机入口 |
| `nlu.parsed` / `nlu.incomplete` / `nlu.error` | nlu / orchestrator | NLU 结果 |
| `intersection.resolved` | orchestrator | 路口匹配结果 |
| `data.fetched` | orchestrator | PG 指标摘要 |
| `rules.diagnosed` | orchestrator | 规则命中 |
| `suggestion.generated` | orchestrator | 治理建议 |
| `skill.fast_path` / `skill.created` | orchestrator | Skill 快路径/固化 |
| `llm.request` / `llm.response` / `llm.error` | qwen_client | 大模型调用 |

## 排查示例

```bash
# 实时查看
tail -f data/logs/app.log

# 按请求 ID 过滤
grep 'req=your-uuid' data/logs/app.log

# 只看 LLM 调用
grep 'event=llm' data/logs/app.log

# 只看错误
grep 'ERROR' data/logs/app.log
```

## 安全

- 日志 **不记录** API Key、数据库密码
- 用户输入与模型输出做长度截断（默认 300–500 字符）
- 调试时可设 `LOG_LEVEL=DEBUG` 查看 mock 分支
