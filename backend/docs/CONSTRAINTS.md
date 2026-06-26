# 开发约束

## 代码规范

1. 遵循 [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)。
2. 所有公开函数/类必须有类型注解与 Google 风格 docstring。
3. 单文件不超过 400 行；复杂逻辑拆至 `services/`。
4. 禁止在生产路径使用裸 `eval()`；公式仅通过 `simpleeval` + 白名单变量。
5. 禁止将 API Key、数据库密码提交至 Git。

## 架构约束

1. **LLM 职责边界**：Qwen 仅用于 NLU、路口名规范化、建议文案；业务判断必须走 YAML 规则引擎。
2. **Skill 定义**：用户 Skill 是诊断快照（rule_ids + data_query_spec + formula），不是替代流水线。
3. **会话状态**：所有多轮交互必须由 `Session.state` 驱动，禁止在 handler 内隐式全局状态。
4. **数据版本**：查询 road6 维表必须带 `version_id`（默认从 `dim_data_version` 或配置读取）。
5. **软删除**：xianchang 表查询必须 `is_deleted = 0`。

## 依赖约束

- Python ≥ 3.11
- 数据库：PostgreSQL（pg_trgm 扩展推荐，无则降级 LIKE）
- LLM：阿里百炼 DashScope OpenAI 兼容接口

## 测试约束

- 核心模块必须有单元测试。
- API 集成测试使用 `MOCK_LLM=1 MOCK_DB=1` 默认可离线运行。
- 合并前 `pytest` 全绿。

## 日志约束

- 使用标准库 `logging`，格式：`%(asctime)s %(levelname)s [%(name)s] %(message)s`
- 禁止记录完整 API Key 与用户敏感信息。
- 请求 ID 通过 `X-Request-ID` 或自动生成 UUID 贯穿日志。
