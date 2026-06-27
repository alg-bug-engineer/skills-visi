# 开发进度

> 最后更新：2026-06-27

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
| M15 测试 | ✅ | pytest **119** 项（`.venv/bin/pytest -q`） |
| M16 语音步骤同步 | ✅ | `voice_narration.json` + `onStepStart` 旁白对齐 |
| M17 饱和度口径 | ✅ | 前后端统一小数（0.92） |
| M18 约束裁剪修复 | ✅ | delta 先裁剪再生成建议 narrative |

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

## 本阶段修复（2026-06-27）

| 问题 | 修复 |
|------|------|
| 语音与理解过程不同步 | `voiceStepSync` + `onStepStart` 统一步骤旁白 |
| 饱和度百分比与业务口径不一致 | 全链路改为小数展示 |
| 用户约束「不能超过 N 秒」未识别 | 约束解析 regex 扩展 |
| delta 裁剪未写入建议 narrative | orchestrator 裁剪顺序 + `delta_override` |
| 点「暂不固化」误开新分析 | `awaiting_confirm` 态排除 `prepareNewAnalysisRun` |

## 待办（后续版本）

- [ ] 领导彩排三场（CREATE / UPDATE / 快路径）现场验证
- [ ] 地图 `experience_absorbed` 脉冲（P2 可选）
- [ ] Redis Session 持久化
- [ ] 专家规则 YAML 全量对齐
- [ ] Playwright E2E（语音步骤时序 + 证据卡同步）
