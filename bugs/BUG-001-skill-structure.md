# BUG-001：Skill 结构不符合标准文件夹规范

## 基本信息

- **Bug ID**：BUG-001
- **发现日期**：2026-07-07
- **修复日期**：2026-07-07
- **严重程度**：P0
- **状态**：已修复
- **关联需求**：needs/1-初始化后端.md
- **关联分支**：20260707093100-1-初始化后端

## 问题描述

初版实现将 Skill 写为 `skills/*.py` 单文件，后改为 `skill.yaml` + `handler.py`，均未遵循项目规范。

`docs/rule.md` 第 9 条「每个 skill 禁止单独的 md 文档」的真实含义是：

> **禁止一个 Skill 只有 md 而没有配套脚本、参考等资源**；标准形态应为 `SKILL.md` + `scripts/` + `references/` + `resources/` + `handler.py`。

## 错误理解

1. 第一次：将 Skill 实现为顶层 `.py` 单文件
2. 第二次：用 `skill.yaml` 替代 `SKILL.md`，且缺少 `references/`、`resources/`

## 修复方案

1. 每个 Skill 目录包含：
   - `SKILL.md`（YAML frontmatter + 正文说明）
   - `handler.py`（运行时执行入口）
   - `scripts/`（确定性脚本）
   - `references/`（规则、阈值等参考文档）
   - `resources/`（提示词、演示数据等资源文件）
2. `skill_loader.py` 解析 `SKILL.md` frontmatter，并校验目录结构完整性
3. 删除 `skill.yaml` 与顶层 `prompts/` 目录

## 验证

- `tests/test_skill_registry.py::test_skill_folders_are_standard_layout` 校验五项结构
- 全部 17+ 单元测试通过

## 经验教训

- 开发前需对照 `references/intersection/*/SKILL.md` 标准结构
- `rule.md` 中「禁止单独 md」= 禁止只有 md、没有 scripts/references/resources
