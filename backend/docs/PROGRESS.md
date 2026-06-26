# 开发进度

> 最后更新：2026-06-24 · 标签 `新增 Skills 可视化`

## 里程碑状态

| 里程碑 | 状态 | 说明 |
|--------|------|------|
| M1–M8（tag2） | ✅ | 见 [RELEASE_tag2.md](RELEASE_tag2.md) |
| M9 Skills 可视化 | ✅ | SSE skill_build + 真实写盘 + 前端 overlay |
| M10 地图主舞台 | ✅ | map_scene 分阶段 + 进口道标注 |
| M11 NLU 方向 | ✅ | directions 必填 + 追问 |
| M12 测试 | ✅ | pytest 39 项 |

## 本标签新增模块

| 模块 | 路径 | 状态 |
|------|------|------|
| 固化可视化 | `skills/skill_build_visualizer.py` | ✅ |
| 地图场景 | `services/map_presentation_service.py` | ✅ |
| 路口认知 | `services/intersection_cognition_service.py` | ✅ |
| 地图舞台 | `frontend/.../MapStage.vue` | ✅ |
| 固化 UI | `frontend/.../SkillBuildOverlay.vue` | ✅ |
| 地图标注 | `frontend/.../mapMarkers.ts` | ✅ |

## 待办（后续版本）

- [ ] Redis Session 持久化
- [ ] 专家规则 YAML 全量对齐
- [ ] 前端权限与生产部署
- [ ] Skill 包同步至 `.cursor/skills/` 可选配置
