# Release · 新增 Skills 可视化

> 标签：`新增 Skills 可视化`  
> 日期：2026-06-24  
> 范围：后端 `backend/` + 前端 `frontend/`（相对 tag2 的增量交付）

---

## 1. 本阶段交付摘要

| 维度 | 状态 | 说明 |
|------|------|------|
| Skills 固化可视化 | ✅ | 确认固化后全屏 overlay，SSE 分阶段推送，真实写盘 Skill 包 |
| 技能包下载 | ✅ | `GET /api/v1/skills/{skill_id}/download` 返回 zip |
| 地图主舞台 | ✅ | 高德地图 + 路口认知 / 运行数据 / 规则 / 证据链 / 建议分阶段呈现 |
| 进口道指标锚点 | ✅ | 指标贴在四向进口道停线附近，不外推到外围边框 |
| 路段方向强调 | ✅ | 认知阶段按东→西→南→北轮流闪烁整条进口道 |
| 多样 marker 样式 | ✅ | link-info / saturation / imbalance / delay / evidence / suggestion 等 |
| NLU 方向必填 | ✅ | `directions` 恢复必填，追问优先级：路口 → 时段 → 方向 |
| 技能完成后地图复位 | ✅ | 飞回济南默认视角，重建会话 |
| 自动化测试 | ✅ | pytest **39** 项（含地图场景、路口认知） |

---

## 2. Skills 固化可视化

### 2.1 产品决策（五项）

1. **全屏 overlay**：自底部升起，覆盖地图主舞台  
2. **真实写入**：非 mock，按标准 Agent Skill 包结构落盘  
3. **更新 diff 高亮**：更新已有技能时展示变更行  
4. **全文打字效果**：分块流式输出文件内容  
5. **完成后渐出**：左下角下载按钮 + 地图回到初始状态  

### 2.2 后端新增/变更

| 模块 | 路径 | 说明 |
|------|------|------|
| 可视化编排 | `intersection_agent/skills/skill_build_visualizer.py` | 分阶段 `skill_build_*` SSE 事件 + 真实写盘 |
| Skill 服务 | `intersection_agent/services/skill_service.py` | `upsert_from_session_visual()` |
| 执行发射器 | `intersection_agent/hooks/execution_emitter.py` | `emit_skill_build()` |
| 包构建器 | `intersection_agent/skills/package_builder.py` | `build_file_contents` / `package_zip` / `write_file` |
| 编排器 | `intersection_agent/services/orchestrator.py` | 确认固化走可视化写包路径 |
| API | `intersection_agent/api/routes.py` | `GET /skills/{skill_id}/download` |

### 2.3 SSE `skill_build` 事件

| type | 说明 |
|------|------|
| `skill_build_start` | 开始沉淀，含 action（create/update） |
| `skill_build_stage` | 阶段切换：understanding → planning → writing_* → packaging |
| `skill_build_thought` | 工作台思考区文案 |
| `skill_build_file_start` | 开始写入某文件 |
| `skill_build_file_chunk` | 文件内容分块（打字效果） |
| `skill_build_file_done` | 单文件完成 |
| `skill_build_diff` | 更新场景的 diff 行 |
| `skill_build_done` | 完成，含 `download_url`、`skill_dir` |

### 2.4 前端新增

| 模块 | 路径 |
|------|------|
| 全屏 overlay | `src/components/SkillBuildOverlay.vue` |
| 文件树 | `src/components/SkillFileTree.vue` |
| 状态机 | `src/composables/useSkillBuildProcess.ts` |
| 类型 | `src/types/skillBuild.ts` |
| 集成 | `src/App.vue`、`src/api/client.ts`（`onSkillBuild`） |

参考交互原型目录：`前端可视化技能创建/`（仅作协议参考，**主项目不 import**）。

---

## 3. 地图主舞台与场景编排

### 3.1 架构

- **主舞台**：`MapStage.vue`（高德地图，深色交通风主题）  
- **理解过程抽屉**：右侧 `UnderstandingProcessPanel.vue`（380px）  
- **场景数据**：`map_presentation_service.build_map_scene()` 按流水线阶段生成 `map_scene`  
- **标注工具**：`mapMarkers.ts`（锚点、样式、进口道高亮）  

### 3.2 地图阶段（`map_scene`）

| phase | 表现 |
|-------|------|
| `locate` | 定位路口、飞入视角 |
| `highlight_links` | 各进口道 LINK 气泡 + **按方向轮流闪烁**整条路段 |
| `traffic` | 四向进口道饱和度 marker（锚在路段停线附近） |
| `direction` / `saturation` / `imbalance` | 对应指标 + 路段脉冲高亮 |
| `rule` / `conclusion` | 证据链 marker + HUD 扩展 |
| `suggestion` | 治理建议地图标注 |

### 3.3 锚点与样式原则（重要）

- **禁止**将指标外推到路口外围虚线框  
- 锚点算法 `linkSegmentAnchor`：在 link 折线上取靠近路口中心的停线点，沿路段向内半步  
- 各 marker `variant` 对应独立 CSS：左边条色、图标、标签（饱和/失衡/证据/建议等）  
- 进口道按方向配色：东青、西浅蓝、南橙、北紫等  

### 3.4 后端新增

| 模块 | 路径 |
|------|------|
| 地图场景 | `intersection_agent/services/map_presentation_service.py` |
| 路口认知 | `intersection_agent/services/intersection_cognition_service.py` |
| 编排集成 | `orchestrator.py` → `_emit_map_sequence` |

### 3.5 前端新增

| 模块 | 路径 |
|------|------|
| 地图舞台 | `src/components/MapStage.vue` |
| 标注 | `src/utils/mapMarkers.ts` |
| 高亮 | `src/utils/mapHighlight.ts`、`channelizationDraw.ts` |
| 类型 | `src/types/map.ts` |
| 工具 | `src/utils/amap.ts`（含 `JINAN_CENTER`） |
| 理解面板 | `UnderstandingProcessPanel.vue`、`ProcessTimeline.vue` 等 |

---

## 4. NLU 与追问（相对 tag2 变更）

| 字段 | tag2 | 本标签 |
|------|------|--------|
| `intersection` | 必填 | 必填 |
| `time_period` | 必填 | 必填 |
| `directions` | 未强制 | **必填**（东西向/南北向或具体进口） |

追问优先级：`intersection` → `time_period` → `directions`  
`FollowUpService` 对方向字段提供上下文引导话术。

---

## 5. 测试与构建

```bash
# 后端（39 项）
cd backend && MOCK_LLM=1 MOCK_DB=1 pytest -q

# 前端
cd frontend && npm run build

# 联调
bash scripts/dev.sh   # 8011 / 5567
```

新增测试：

- `tests/test_map_presentation.py`
- `tests/test_intersection_cognition.py`
- NLU / SSE / API 用例补充方向字段

---

## 6. Git 标签

```bash
# 后端
cd backend && git checkout 新增-Skills-可视化

# 前端
cd frontend && git checkout 新增-Skills-可视化
```

> Git 标签名不允许空格，故使用 `新增-Skills-可视化`（语义等同「新增 Skills 可视化」）。

相对 `tag2`：后端完成 Skills 可视化管线 + 地图场景服务；前端完成地图主舞台 + 固化 overlay + 理解过程 UI。
