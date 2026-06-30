# 后端运行时数据目录

本目录存放路口诊断系统的**持久化数据**（不入库 PG 的部分）。

| 子路径 | 用途 | 对应 UI |
|--------|------|---------|
| `profiles/` | 路口三级经验档案（认知 / 诊断 / 方案引用） | **经验库** · 认知 / 诊断 |
| `skills/` | 固化技能包（`SKILL.md`、量化措施等） | **经验库** · 方案 |
| `expert_knowledge.md` | 行业专家场景案例（19 个场景） | **案例库** · 行业案例 |
| `logs/` | 应用日志 | — |

配置项见 `intersection_agent/config.py`：`profile_dir_path`、`skill_dir_path`、`case_library_path`。

**路口案例库**（`/cases/intersections`）不单独落盘，由 `profiles/` + `skills/` 聚合生成。
