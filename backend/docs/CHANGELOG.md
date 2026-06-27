# 变更日志

## 干线扫描与路口发现 + 意图 LLM 分类 (2026-06-29)

### 干线扫描（Corridor Scan）

- 新增首轮分支：**干线扫描** vs **单点路口诊断**；扫描三要素（干线、时段、拥堵），缺时段追问、不问具体路口名。
- 会话态：`corridor_nlu_incomplete` → `awaiting_corridor_pick` → 选型后接单点 NLU（只追问方向）。
- 后端：`LineResolver`、`CorridorScanService`（PG 批量排名）、`CorridorNarrativeService`、`build_corridor_scan_scene`。
- 路网可视化：按路口顺序链化 link 几何（`corridor_geometry`），单条 polyline + 路口 snap；修复「多条平行直线」问题。
- 选型：`corridor_pick_resolver` 支持排名口语、「奥体西与经十路」等简称；前端列表/地图点击自动提交路口名。
- 前端：`CorridorScanSidebar`、MapStage 沿路高亮与下钻、三栏布局。

### 意图识别

- 首轮 **LLM 二分类**（`IntentClassifierService`）+ **规则兜底**（`intent_router`）；`enable_thinking=False`、短 prompt、无重试。
- 规则扩展：支持「路口有哪些」倒装、经常拥堵、哪里堵等表述。

### 语音（feature/tts）

- TTS 迁移至 Qwen-TTS Realtime；移除阿里云 ISI 实现；关键点引导式播报。

- 后端单测 **118** 项。

详见 `docs/plans/2026-06-27-干线扫描与路口发现.md`。

## 经验吸收可视化 v2 (2026-06-28)

- 用户确认固化后，由 `InterleavedSkillPersistVisualizer` 统一编排 **L3 交错**：`skill_absorption` 头脑阶段 → `write_phase_start` → 每文件右栏联动行 ∥ 左抽屉 `skill_build` 打字 → `drawer_close`。
- `skill_absorption` SSE 阶段：回顾 → 解构 → 检索 → 比对 → 价值 → 转化；自言自语文案由后端模板 + 真实 session/技能库数据生成（`AbsorptionRenderer` / `AbsorptionNarrativeService`），禁止 LLM 即兴旁白。
- Skill 标签扩展为 `match` / `content` / `meta` 三层结构，写入 `skill.meta.json`；`diff_with_session` 扩展 content 层比对。
- frontend-v2：右栏 `ExperienceAbsorptionPanel`（理解过程折叠摘要 + 吸收追踪）+ 左 `SkillBuildDrawer`（终端风格落盘，**替代**全屏 `SkillBuildOverlay`）；演示节奏由 `demo_pacing.py` 控速（≤40s）。
- 后端单测 **89** 项（含 absorption / interleaved SSE 顺序断言）。

详见 `docs/plans/2026-06-28-经验吸收与技能固化演示开发计划.md`。

## problem_evidence SSE 扩展 (2026-06-25 · frontend-v2 联调)

- `problem_evidence` 步骤 `data` 增加 `by_direction`、`quantitative_constraints`（约束解析后一并下发，便于前端与理解过程同步展示）。
- 约束解析移至 SSE 发射之前，保证单次事件携带完整证据与约束子集。

## 问题验证证据与约束量化 (2026-06-25 · 0625 需求)

### 问题验证证据

- 新增 `ProblemEvidenceService`：常发性（近7日≥4日超标）、星期规律、排队/延误、分方向画像。
- 诊断确认文案嵌入量化证据摘要；API `meta.problem_evidence` 透出。
- 新增 `scripts/probe_evidence.py` CLI 探针；`EVIDENCE_DEBUG=1` 终端打印完整证据块。

### 约束量化

- 新增 `ConstraintResolverService`：将「垂直方向不能溢出」等经验约束转为指标边界。
- 治理建议 `delta_seconds` 保守裁剪；Skill 包沉淀 `quantitative_constraints`。
- API `meta.quantitative_constraints` 透出。

详见 `docs/EVIDENCE_FEATURE.md`。

## 系统优化：诊断确认、治理建议确认与 SQL 证据链 (2026-06-25)

### 数据复盘

- 数据抓取日志新增可直接执行的 SQL，不再只输出 `$1` / `$2` 参数占位。
- 响应 `meta.query_trace` 留存 SQL、参数、原始返回行与行数，便于复盘抓数正确性。

### 交互状态机

- 诊断成立后，若首轮没有用户约束/建议，先进入“是否生成治理建议”确认，不再自动生成或替用户填补建议。
- 用户可在确认轮直接补充约束；治理建议生成时会优先体现该约束。
- 治理建议生成后新增 Skill 固化二次确认，用户能先看到治理建议，再决定是否沉淀 Skill。
- 仅确认生成建议且未补充约束时，不触发 Skill 沉淀。

### NLU 与 Skill

- NLU 新增 `user_suggestion` 维度，支持识别“绿灯延长”“垂直方向不能溢出”等约束或建议。
- Skill 包新增用户约束沉淀，写入 `skill.meta.json`、`SKILL.md` 与 `reference.md`。
- 默认案例与测试口径统一调整为“南北向”。

## 新增 Skills 可视化 (2026-06-24)

### Skills 固化可视化

- 新增 `SkillBuildVisualizer`：分阶段 SSE `skill_build` 事件，真实写入标准 Skill 包
- `SkillService.upsert_from_session_visual()`；编排器确认固化走可视化路径
- `package_builder` 支持 `build_file_contents` / `package_zip` / `write_file`
- `GET /api/v1/skills/{skill_id}/download` 下载 zip 包
- 前端 `SkillBuildOverlay` + 文件树 + 打字效果 + diff 高亮 + 完成后下载

### 地图主舞台

- 新增 `map_presentation_service`：按诊断阶段生成 `map_scene`（定位、认知、流量、规则、证据、建议）
- 新增 `intersection_cognition_service`：渠化/车道认知数据
- 指标锚点在**四向进口道停线附近**，禁止外推到外围边框
- 认知阶段进口道按方向轮流闪烁/变色；多样 marker 样式（saturation、imbalance、evidence 等）
- 技能完成后地图飞回济南默认视角

### NLU

- `directions` 恢复**必填**；追问优先级：路口 → 时段 → 方向
- `FollowUpService` 方向引导话术；mock LLM 识别东西/南北向

### 测试

- pytest **39** 项（+地图场景、路口认知）

---

## tag2 (2026-06-24) — 后端完成开发，前端简单验证完成

### 产品

- 角色固定为 **交通智能体**，功能固定为 **拥堵诊断**
- NLU 不再追问 `problem_type`，内部固定 `congestion`
- 追问话术由 `FollowUpService` LLM 生成，不提渠化/配时

### Skill

- 废弃 SQLite / 单 JSON，改为 **标准 Agent Skill 包**：
  - `SKILL.md`、`skill.meta.json`、`reference.md`、`scripts/fetch_traffic_data.*`
- 快路径：结论一致 `verified` 跳过确认；有 diff `awaiting_update`；首次 `awaiting_create`
- `SkillService.diff_with_session()` / `upsert_from_session()`

### 数据与 API

- **方案 D**：近 7 日 DWD + DWS 降级；`meta.data_window` 元数据
- **SSE**：`POST /api/v1/sessions/{id}/messages/stream` + 执行钩子
- CORS；`GET /skills` 返回 `skill_dir`

### 测试

- pytest **35 项**（SSE、Skill 包、快路径、数据窗、追问等）

### 前端（独立仓库 tag2）

- Vue 3 对话 UI + 执行面板 + 调试日志
- 端口 5567 / 8011，`scripts/dev.sh` 一键联调

---

## v1.0.0 (2026-06-24)

### 新增

- FastAPI 后端基线：会话 API、NLU、路口匹配、规则引擎
- Git 标签 `v1.0.0`
