# Bug 排查指南

## 1. 服务无法启动

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| `ModuleNotFoundError` | 未安装依赖 | `pip install -e ".[dev]"` |
| 端口占用 | 8000 已被占用 | `PORT=8001 uvicorn ...` |
| 配置缺失 | 无 `.env` | 复制 `.env.example` 并填写 |

## 2. LLM 调用失败

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 401 Unauthorized | API Key 错误 | 检查 `DASHSCOPE_API_KEY` |
| 404 model not found | 模型名错误 | 确认 `QWEN_MODEL=qwen3.6-flash-2026-04-16` |
| Timeout | 网络或限流 | 增大 `LLM_TIMEOUT_S`；检查百炼控制台配额 |
| JSON 解析失败 | 模型输出非纯 JSON | 查看日志中 `raw_response`；NLU prompt 已约束仅 JSON |

**离线调试**：设置 `MOCK_LLM=1` 跳过真实调用。

## 3. 数据库连接失败

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| Connection refused | 主机/端口错误 | 对照 `docs/postgresql_info.md` |
| 认证失败 | 用户名密码 | 检查 `PGPASSWORD` |
| 表不存在 | search_path | 确认 `PGSCHEMA=road6`, `PG_FLOW_SCHEMA=xianchang` |

**离线调试**：设置 `MOCK_DB=1`。

## 4. 路口查不到

1. 查看响应 `meta.resolution_source`：`exact` / `variant` / `candidates` / `not_found`
2. L1 失败 → 检查 NLU 提取的路口名是否与 `dim_inter_info.inter_name` 一致
3. L2 变体失败 → 确认 pg_trgm 或 LIKE 降级日志
4. L3 有候选 → 用户需回复完整路口名或从列表选择

## 5. 规则未命中

1. 检查 `diagnosis.matched_rules` 为空时的 `reason_code`
2. 对照 `rules/traffic_rules.yaml` 阈值与 `rules/thresholds.yaml`
3. 确认 `problem_type` 映射（NLU → 规则 filter）
4. 数据缺失时部分条件返回 `None`，条件视为不成立

## 6. Skill 误触发 / 未命中

- 命中键：`inter_id` + `problem_type`（固定 congestion）+ 时段 label + 关键词
- 「不是」等否定句不应触发确认：检查 `intent_detector`
- 清空 Skill 包：`bash scripts/clear_skills.sh --force`，无需重启服务
- 旧 Skill 在规则 YAML 变更后可能失效：删除对应 `data/skills/{包}/` 或重新固化
- Skill 包须含 `SKILL.md` + `skill.meta.json`；仅有 JSON 单文件为已废弃格式

## 7. 日志位置

- 控制台：uvicorn 默认 stderr
- 调整级别：`LOG_LEVEL=DEBUG`

## 8. 常用 curl 自检

```bash
curl -s http://localhost:8000/health | jq .
bash scripts/curl_tests.sh http://localhost:8000
```
