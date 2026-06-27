# 开发进度

> 最后更新：2026-06-28

## 里程碑状态

| 里程碑 | 状态 | 说明 |
|--------|------|------|
| M1–M8（tag2） | ✅ | 见 [RELEASE_tag2.md](RELEASE_tag2.md) |
| M9 Skills 可视化 | ✅ | SSE skill_build + 真实写盘 + 前端 overlay |
| M10 地图主舞台 | ✅ | map_scene 分阶段 + 进口道标注 |
| M11 NLU 方向 | ✅ | directions 必填 + 追问 |
| M12 0625 证据/约束 | ✅ | problem_evidence、quantitative_constraints |
| M13 四类信控问题 | ✅ | flow_timing_governance、演示嗅探 |
| M14 经验吸收 v2 | ✅ | skill_absorption + L3 交错落盘 + 三层 tags |
| M15 测试 | ✅ | pytest **89** 项（`.venv/bin/pytest -q`） |

## 经验吸收 v2 新增模块

| 模块 | 路径 | 状态 |
|------|------|------|
| 吸收报告 | `skills/experience_absorption.py` | ✅ |
| 模板渲染 | `skills/absorption_renderer.py` | ✅ |
| 分阶段 emit | `skills/absorption_stage_emitter.py` | ✅ |
| L3 交错编排 | `skills/interleaved_skill_persist_visualizer.py` | ✅ |
| 演示控速 | `skills/demo_pacing.py` | ✅ |
| 三层 tags | `services/skill_matcher.py` | ✅ |
| 前端吸收面板 | `frontend-v2/.../ExperienceAbsorptionPanel.vue` | ✅ |
| 前端落盘抽屉 | `frontend-v2/.../SkillBuildDrawer.vue` | ✅ |

## 待办（后续版本）

- [ ] 领导彩排三场（CREATE / UPDATE / 快路径）现场验证
- [ ] 地图 `experience_absorbed` 脉冲（P2 可选）
- [ ] Redis Session 持久化
- [ ] 专家规则 YAML 全量对齐
