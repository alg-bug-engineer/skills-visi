# 需求 5：前端 UI 九幕演示

## 需求概述

在需求 1～4 已交付后端五 Skill 流水线、生产化数据真源、经验沉淀与稳定前端契约（`build_public_run_response`）的基础上，实现 `docs/剧本.md` 所述「专家处理排队溢出」九幕叙事的**前端演示应用**，产物置于 `frontend/`。

前端定位为**面向交通决策专家的决策支持中心**，以强视觉、可信、可回看的方式串起：听懂问题 → 定位对象 → 验证溢出 → 判断成因 → 引入案例 → 生成策略 → 形成方案 → 人工可控 → 反馈沉淀。

**工程形态**：采用 **Vue 3 + TypeScript + Vite** 的**独立前后端分离工程（CS 架构）**——独立仓内目录、自带 dev server、独立 `npm run build` 产出可被 nginx/任意静态服务托管的 SPA，通过 REST（`/agent/run` 等）+ SSE（`/intersection/load/stream`）消费后端，**非嵌入式单页 HTML**。

**设计起点（唯一权威）**：`docs/design/`（`README.md` 设计理念 + `UI_design_document.md` 界面规范 + `interaction_logic.md` 交互数据流）。视觉基调对齐 `docs/design/README.md` 引用的决策控制台 mockup（暗色 HUD、3D 等距路网、霓虹排队墙/发光流向、底部流水线进度条）。

## 与需求 4 的边界

| 需求 4（已完成，后端就绪） | 需求 5（本需求，前端实现） |
|---------------------------|---------------------------|
| 公开响应字段补齐、策略/方案透出 | 消费上述字段渲染九幕卡片与地图 |
| 分步执行 `skill_ids` / `stop_after` | 前端演出时间线消费全量响应（`/agent/run` 非 SSE）分幕揭示 |
| `POST /intersection/load(/stream)` | 第二/三幕拓扑加载与 SSE 进度、回滚监听 |
| `plan/regenerate`、`GET /agent/cases` | 第九幕接受/拒绝/再生成/近期案例交互 |
| 集成文档与字段对照 | 依据文档建立类型化客户端与枚举字典 |

---

## 设计原则（对齐 docs/design/README.md）

1. **渐进式披露（Progressive Disclosure）**：流水线式逐幕披露，右侧过程栏打字完成后再揭示左侧证据卡（Sticky Reveal），避免信息超载与抢跑。
2. **三维立体化地网联动（GIS-UI Co-linking）**：地图随流水线在路网微观（2D 俯视）↔ 干线宏观（3D 等距 `pitch/rotation`）间切换，配合发光流向与粒子。
3. **专家级业务表达（Expert Domain Language）**：使用排队比 / 饱和度 / 绿灯利用率 / 上游控流削峰等专业指标；方案层提供双向时距图与相位结构图。

## 已核对的契约现实（约束前端实现）

1. `POST /agent/run` 为**一次性全量 JSON，非 SSE** → 九幕流式效果由**前端演出时间线**驱动；真 SSE 仅 `POST /intersection/load/stream`。`docs/design/interaction_logic.md` 时序图中「SSE 推送 intent/场景/指标」的假设据此调整为前端节奏揭示。
2. 字段为**枚举编码**（`east_to_west`/`evening_peak`/`queue_spillover`…）→ 需统一枚举→中文字典。
3. 地图数据**可能稀疏 / 含 null**（`highlight_path` 可能 1 点、节点可空、`adjacent_intersections[].lng/lat` 可空）→ 必须优雅降级，禁止编造坐标。
4. 第八幕比选部分可视化字段（`vc_predictions`、供给/需求强度、`corridor_nodes`、`pre/post_green_time_s`、时距图上下游绿窗）**当前后端未透出** → 走「数据暂缺」占位，遵守 `rule.md` 第 14 条禁编造假数据；登记于开发计划附录 B。

---

## 需求条目

### 1. 三栏工作台 + 底部 Dock（P0）
GIS 主战场（1fr）+ 左侧推理证据栏（~300px）+ 右侧理解过程栏（~340px）；底部 Dock 状态机（输入框 → 任务执行栏 → 方案抽屉）+ 常驻流水线进度条（命名节点、ACTIVE 闪电、护栏红点）；右下角全屏 FAB 一键收起两侧无遮挡看图；≤1100px 转浮层降级。

### 2. 高德地图逐幕图层（P0）
JS API 2.0（`viewMode:'3D'`，secret 经 `.gitignore` 隔离）；图层：路口高亮框、进口道/`highlight_path` 发光折线、上下游节点、渠化小窗（车道饱和上色）、干线溯源双层发光 Polyline + rAF 粒子 + 可点击气泡、控制范围（控流闸口/目标/下游盾牌）、干线协调图；2D↔3D 视点随幕平滑过渡。

### 3. 前端演出时间线与揭示门控（P0）
单次响应 → 按幕节奏推进；右侧过程栏打字完成事件门控左侧证据卡揭示；卡片 Sticky 常驻可回看；地图运镜与幕次联动。

### 4. 九幕卡片与数据渲染（P0）
逐幕消费 `docs/剧本字段-API对照.md` 字段（见开发计划附录 A）：工单卡、识别步骤、运行数据卡 + 时序折线、溢出判定、瓶颈判据、干线溯源卡、成因卡 + 案例轮播、策略边界卡、方案抽屉（阶段方案 + 相位结构图 + 时距图 + 多方案比选）、反馈面板。全部枚举中文化；缺口字段占位不造假。

### 5. 第九幕闭环与异常兜底（P0）
接受/拒绝/修改再生成（`/plan/decision`、`/plan/regenerate`）+ 再生成秒数 Differ 高亮；近期案例 `GET /agent/cases`；接受后监听 `/intersection/load/stream` 触发回滚告警；断线重连 3 次 + Mock 回放兜底。

### 6. 配置与约束（P0）
- 遵循 `docs/rule.md`：禁止 demo 静默 fallback（第 14 条）；剧本字段为验收标准（第 17 条）；先写计划再开分支（第 18 条）；`references/` 禁止 import（第 11 条）。
- 密钥来自 `docs/gd-js20.md`，走 `.env.local`（不入 git）；`.env.example` 给占位；README 标注生产需服务端代理。
- 分支命名 `yyyymmddhhmmss-5-前端UI九幕演示`；禁止直接合入 `main`（第 1 条）。

---

## 测试要求

- **Vitest 逻辑单测**：枚举回退、适配器 null 安全、供需比派生、store 揭示门控、九幕编排、坐标 null 守卫。
- **Playwright 截图视觉自动化（重点）**：以截图方式自动化校验**布局排版、UI、是否遮挡**——
  - 视口矩阵 1920×1080 / 1440×900 / 1100×800；各幕全屏 + 分栏基线截图归档供人工审阅与像素回归。
  - 遮挡/溢出断言（`boundingBox`）：三栏不重叠、Dock/进度条不遮卡片、渠化小窗避开输入框/抽屉、抽屉弹出时策略卡可见、文字不横向截断、地图气泡不被视口裁剪、FAB 收起地图满屏、≤1100px 降级正常。
  - 开发期由 `webapp-testing` skill 的 `scripts/with_server.py` 拉起 dev server 即时取证，沉淀为 `frontend/e2e/` 回归套件。

---

## 验收标准

- [ ] `frontend/` 可 `npm run dev`（代理后端 :8000）与 `npm run build`；`VITE_MOCK=1` 可离线回放
- [ ] 九幕在真实后端与 Mock 回放下均能完整演出，地图随幕 2D↔3D 联动
- [ ] 三栏 + Dock + 小窗 + 抽屉 + 全屏 FAB + ≤1100px 降级均无遮挡、无溢出
- [ ] 枚举全部中文化；null 与 `available=false` 优雅降级，无空屏崩溃
- [ ] 第八幕缺口字段显示「数据暂缺」，无任何硬编码假数据
- [ ] 第九幕接受/拒绝/再生成/案例列表/回滚告警可用
- [ ] Vitest F-01~F-14 全绿；Playwright 截图套件 V-01~V-16 通过并归档各幕基线
- [ ] `frontend/README.md` 可独立联调；`docs/项目进度.md` 前端 UI 行更新
- [ ] 分支未直接合入 main；如遇陷阱记录 `bugs/`

---

## 参考

- 开发计划：`plans/5-前端UI九幕演示.md`
- 设计起点：`docs/design/`（README + UI_design_document + interaction_logic）
- 叙事验收：`docs/剧本.md`；字段映射：`docs/剧本字段-API对照.md`；联调：`docs/前端集成指南.md`
- 地图密钥：`docs/gd-js20.md`
- 前置需求：`needs/4-前端就绪与剧本补齐.md`
