# 项目状态快照 · 新增 Skills 可视化

> 标签：`新增 Skills 可视化`  
> 日期：2026-06-24  
> 仓库：`backend/` + `frontend/`（各自独立 Git，同标签）

---

## 1. 项目是什么

**交通智能体 · 拥堵诊断**

交警自然语言描述路口拥堵 → NLU（含方向必填）→ 地图认知与数据展示 → PostgreSQL 查数 → YAML 规则诊断 → 治理建议 → 可选**可视化固化**为标准 Agent Skill 包。

技术栈：FastAPI · Qwen · PostgreSQL · 高德地图 · Vue 3 · SSE

---

## 2. 本标签相对 tag2 的新增能力

| 能力 | 状态 | 说明 |
|------|------|------|
| Skills 固化可视化 | ✅ | 全屏 overlay + SSE 分阶段 + 真实写盘 + zip 下载 |
| 地图主舞台 | ✅ | 分阶段 map_scene，进口道指标与证据链 |
| 进口道锚点 | ✅ | 指标在路段停线附近，不外推边框 |
| 方向路段强调 | ✅ | 认知阶段按向闪烁/配色 |
| NLU 方向必填 | ✅ | 追问路口 → 时段 → 方向 |
| 地图复位 | ✅ | 技能完成后飞回济南默认视角 |

---

## 3. 目录结构（增量）

```
backend/intersection_agent/
├── skills/skill_build_visualizer.py   # 固化可视化
├── services/map_presentation_service.py
├── services/intersection_cognition_service.py
└── hooks/execution_emitter.py         # + emit_skill_build

frontend/src/
├── components/MapStage.vue
├── components/SkillBuildOverlay.vue
├── utils/mapMarkers.ts
└── composables/useSkillBuildProcess.ts
```

---

## 4. 快速启动

```bash
bash scripts/dev.sh          # 根目录，8011 + 5567
MOCK_LLM=1 MOCK_DB=1 pytest -q   # 后端 39 项
```

---

## 5. 文档索引

| 文档 | 内容 |
|------|------|
| [RELEASE_新增Skills可视化.md](RELEASE_新增Skills可视化.md) | **本标签发布说明** |
| [CHANGELOG.md](CHANGELOG.md) | 变更记录 |
| [API.md](API.md) | SSE / 下载 API |

---

## 6. Git 标签

```bash
git checkout 新增-Skills-可视化
```

标签说明：**Skills 固化可视化 + 地图主舞台 + 进口道指标呈现**（Git 标签名：`新增-Skills-可视化`）
