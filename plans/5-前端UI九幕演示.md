# 开发计划：5-前端 UI 九幕演示

> 目标产物目录：`frontend/`
> 需求来源：`docs/剧本.md`（叙事验收标准）、`docs/剧本字段-API对照.md`（字段契约）、`docs/前端集成指南.md`（联调）、`analysis/design/UI_design_document.md` 与 `analysis/design/interaction_logic.md`（视觉与交互）
> 地图密钥：`docs/gd-js20.md`（高德 JS API 2.0，key + securityJsCode，均经 `.gitignore` 隔离）

## 背景

需求 1～4 已交付后端五 Skill 流水线、生产化数据真源、经验沉淀与 78 项 pytest 基线；公开响应契约（`build_public_run_response`）已按剧本九幕补齐字段。`docs/项目进度.md` 中「前端 UI 剧本九幕展示」仍为 0%。本计划交付一个可独立运行的前端演示应用，把专家处理「排队溢出」的九幕链路以强视觉、可信、可回看的方式呈现。

### 已核对的关键契约现实（决定架构，务必遵守）

对 `logs/run_1/` 真实响应逐字段核对后确认：

1. **`POST /agent/run` 是一次性全量 JSON，不是 SSE。** 因此剧本「逐步打字 / 分幕揭示 / 底部任务栏推进」必须由**前端演出时间线**（presentation timeline）驱动：请求一次拿到完整响应后，按幕次节奏渐进揭示，地图运镜与左侧证据卡的显示由右侧「理解过程栏」的打字完成事件门控（对齐 `interaction_logic.md` 的 Sticky Reveal）。真正的 SSE 只有 `POST /intersection/load/stream`（路口加载进度）。
2. **字段为枚举编码**，非中文标签：`direction=east_to_west`、`period=evening_peak`、`movement=straight`、`problem_type=queue_spillover`、`overflow_verification.risk_level=low`、`downstream_diagnosis.scenario=mixed` 等。前端必须建立**枚举→中文标签字典**，禁止在业务逻辑里散落硬编码翻译。
3. **地图数据可能稀疏 / 含 null**：`spatial_scene.highlight_path` 可能仅 1 个点，`upstream_nodes/downstream_nodes` 可能为空；`map_scenes.*.adjacent_intersections[].lng/lat` 可能为 null。前端须**优雅降级**（`available=false` 时展示 `spatial_objects` 文本兜底 + 提示条），坐标缺失的覆盖物跳过渲染，禁止编造坐标。
4. **部分第八幕比选可视化字段当前后端未透出**：设计稿中的 `vc_predictions`、供给/需求强度（`supply_intensity`/`demand_intensity`）、`corridor_nodes`、`post_green_time_s/pre_green_time_s` 在现有 `plan.candidates[]` 中不存在。前端对这些子视图一律走「数据暂缺」占位（遵守 `rule.md` 第 14 条：禁止硬编码假数据）。能从 `timing` 派生的（如相位秒数、周期）正常渲染；不能派生的标注为后端待补，写入本计划「后端契约缺口」附录。
5. **枚举/秒数双写**：`timing.phase_stage_timing_list[]` 同时含 `green_time_s` 与 `greenTime`，取 snake_case 主字段。

## 目标

1. `frontend/` 下交付 React + TypeScript + Vite 单页演示应用，完整覆盖剧本九幕。
2. 三栏工作台（GIS 主战场 / 左侧推理证据栏 / 右侧理解过程栏）+ 底部 Dock 状态机（输入框→任务执行栏→方案抽屉）。
3. 高德地图 JS API 2.0 深色底图 + 逐幕图层（路口高亮、上下游、渠化小窗、干线溯源粒子流、控制范围、干线协调图）。
4. 前端演出时间线：一次请求全量响应 + 分幕节奏揭示 + 打字机门控的 Sticky Reveal。
5. 枚举标签字典、类型化 API 客户端、失败态与断线兜底、Mock 回放（用 `logs/run_1/` 真实响应做本地 fixture，非编造）。
6. 第九幕闭环：接受/拒绝、修改再生成、近期案例、回滚监听。
7. Vitest 单测 + Playwright 端到端演出校验；`frontend/README.md` 使前端可独立启动联调。

## 非目标

- 后端字段变更（第八幕比选缺口仅登记，不在本计划实现后端补齐）。
- 移动端适配（仅面向 1920×1080 大屏演示 + ≤1100px 浮层降级）。
- 用户鉴权、多路口并发会话管理、真实回滚下发执行（回滚仅前端监听告警）。
- 向 `knowledge_qa.jsonl` 写入。

---

## 技术选型

| 维度 | 选型 | 理由 |
|------|------|------|
| 框架 | React 18 + TypeScript + Vite | 设计文档以 React 组件/hook（`usePresentation`、`UpstreamTraceLayer.ts`）描述；Vite 启动快、代理简单 |
| 状态 | Zustand | 轻量、适合演出时间线与多栏协同的集中 store |
| 地图 | 高德 JS API 2.0（`@amap/amap-jsapi-loader`） | 集成指南与设计稿强约束；密钥来自 `docs/gd-js20.md` |
| 动效 | Framer Motion + CSS | 卡片 slide-up、打字机、粒子/发光走 CSS/rAF |
| 图表 | ECharts（`echarts` + 按需引入） | 时序排队比折线、供需柱状；数据密集大屏 |
| 样式 | CSS 变量（设计令牌）+ CSS Modules | 精确控制 bespoke 深色信控主题 |
| 测试 | Vitest + React Testing Library + Playwright | 单测 + 组件 + 端到端演出 |
| 联调 | Vite dev proxy `/api` → `http://localhost:8000` | 免 CORS；生产可 `npm run build` 出静态资源 |

**主分支**：`20260707140643-5-前端UI九幕演示`

---

## 目录结构（frontend/）

```
frontend/
  index.html
  package.json  tsconfig.json  vite.config.ts  .env.example
  README.md
  src/
    main.tsx  App.tsx
    theme/tokens.css              # 设计令牌（青/红/琥珀/绿/夜幕）
    labels/enums.ts               # 枚举→中文字典（direction/period/movement/problem_type/scenario/risk...）
    api/
      client.ts                   # fetch 封装 + 错误规整
      sse.ts                      # /intersection/load/stream EventSource 封装
      types.ts                    # 响应类型（镜像 剧本字段-API对照）
      endpoints.ts                # run / load / decision / regenerate / cases / health
    store/
      presentationStore.ts        # 运行生命周期、幕次、缓冲、揭示门控、Dock 状态机
      selectors.ts
    presentation/
      timeline.ts                 # 幕 → 过程步骤 → 地图场景 → 证据卡 的编排表
      typing.ts                   # 打字机 hook（onStepComplete → reveal）
    map/
      AMapProvider.tsx            # 加载器 + securityJsCode 注入
      MapController.ts            # flyTo / setPitch / 图层生命周期
      layers/
        IntersectionLayer.ts      # 路口 Polygon 虚线框 + 溢流填充
        HighlightPathLayer.ts     # highlight_path 发光折线 + 上下游节点
        ChannelizationMini.tsx    # 右下角渠化小窗（arms → 车道饱和上色）
        UpstreamTraceLayer.ts     # 干线溯源双层发光 Polyline + rAF 粒子 + 节点气泡
        ControlScopeLayer.ts      # 控制范围（控流闸口/目标/下游盾牌）
        CorridorLayer.ts          # 第八幕干线协调节点/绿波
    panels/
      ProcessPanel/               # 右栏：步骤 checklist + 打字机日志
      InsightPanel/               # 左栏：Sticky 证据卡容器
      BottomDock/                 # 输入框 / 任务执行栏 / 信号灯 / 全屏 FAB
      PlanDrawer/                 # 第八幕底部抽屉（阶段方案 / 多方案比选）
    cards/
      DiagnosisTicketCard.tsx     # 幕一
      RecognitionSteps.tsx        # 幕二（也在 ProcessPanel）
      DataMetricsCard.tsx         # 幕三（+ 时序折线）
      OverflowVerdict.tsx         # 幕三 中央判定
      BottleneckCard.tsx          # 幕四
      CorridorScanCard.tsx        # 幕五
      CauseCard.tsx / CaseCarousel.tsx  # 幕六
      StrategyBoundaryCard.tsx    # 幕七
      PlanStageView.tsx / PlanCompareMatrix.tsx  # 幕八
      FeedbackPanel.tsx           # 幕九
    utils/  format.ts  vc.ts（供需比派生，仅当字段存在）  guards.ts
    mock/  run_1_fixture.json     # 从 logs/run_1 拷贝的真实响应，供离线回放
  tests/                          # Vitest 单测
  e2e/                            # Playwright 演出校验
```

---

## 阶段划分

```
F0 脚手架 + 主题令牌 + AMap 底图 + 环境变量        (P0)
   ↓
F1 类型化 API 客户端 + 枚举字典 + Mock 回放         (P0)
   ↓
F2 三栏骨架 + 底部 Dock 状态机 + 演出时间线/打字揭示 (P0)
   ↓
F3 幕一~二：诊断工单卡 + 地图 flyTo + 识别步骤 + 上下游/highlight + 渠化小窗 (P0)
   ↓
F4 幕三~四：运行数据卡 + 时序图 + 溢出判定 + 瓶颈判据 + 车道级视图 (P0)
   ↓
F5 幕五：干线溯源粒子流层 + 节点气泡 + 干线卡        (P1)
   ↓
F6 幕六~七：成因/案例卡(轮播) + 策略边界卡 + 控制范围地图层 (P0/P1)
   ↓
F7 幕八：方案抽屉（阶段方案 + 多方案比选 + 干线协调图）+ 地图联动 + 缺口降级 (P0)
   ↓
F8 幕九：接受/拒绝/再生成 + cases 列表 + 回滚监听 + 断线/mock 兜底 (P0)
   ↓
F9 联调打磨 + 全屏 FAB + 打包 + README + 进度文档更新 (P0)
```

---

## 阶段明细

### F0：脚手架、主题令牌与地图底图

| 项 | 内容 |
|----|------|
| 脚手架 | `npm create vite@latest frontend -- --template react-ts`；接入 zustand / framer-motion / echarts / @amap/amap-jsapi-loader |
| 代理 | `vite.config.ts` 配 `server.proxy['/api'] → http://localhost:8000` |
| 令牌 | `theme/tokens.css` 落地设计令牌（`--primary:#00e5ff`、`--alarm:#ff5050`、`--evidence:#f5a623`、`--protected:#6dffb5`、`--bg:#020810`、`--panel:rgba(0,8,16,.92)`）；深色磨砂面板 + backdrop-filter |
| 字体 | 选用有辨识度的显示体 + 中文正文体（非 Inter/Arial）；数字用等宽以稳住大屏跳动 |
| 地图 | `AMapProvider` 通过 loader 加载 2.0；`window._AMapSecurityConfig.securityJsCode` 注入 secret；深色自定义样式；济南全域微光网格底图 |
| 环境 | `VITE_AMAP_KEY` / `VITE_AMAP_SECURITY` 走 `.env.local`（不入 git）；`.env.example` 给占位；key/secret 取自 `docs/gd-js20.md` |
| 安全备注 | JS API 2.0 secret 前端可见，仅本地演示可接受；生产建议加高德服务代理（写入 README 风险提示） |

**测试 F0**：`tests/tokens.test.ts` 断言令牌变量存在；`AMapProvider` 加载失败时抛出可捕获错误（离线可跑）。

### F1：类型化 API 客户端 + 枚举字典 + Mock 回放

- `api/types.ts`：按 `docs/剧本字段-API对照.md` + 真实响应定义 `RunResponse`、`DiagnosisTicket`、`Phases`（intent/diagnosis/cause/strategy）、`PlanBlock`、`PlanCandidate`、`PhaseResult`、`MapScene` 等；可空字段一律 `| null`。
- `api/client.ts`：统一 `postJSON`，非 2xx → 规整 `{ ok:false, reason }`；超时与网络错误捕获。
- `api/endpoints.ts`：`runAgent`、`loadIntersection`、`loadIntersectionStream`、`submitDecision`、`regeneratePlan`、`listCases`、`health`。
- `labels/enums.ts`：`direction`/`movement`/`period`/`problem_type`/`scenario`/`risk_level`/`data_source`/`match_method`/`experience_type`/`plan_id`/`status` 的中文映射 + `t(enum, value)` 安全回退（未知值原样透出，不抛错）。
- `mock/run_1_fixture.json`：从 `logs/run_1/*_steps.json` 的 `public_response` 拷贝为离线 fixture；`?mock=1` 或 `VITE_MOCK=1` 时 `runAgent` 走回放（明确标注来源，非默认生产路径）。

**测试 F1**：`tests/enums.test.ts`（含未知枚举回退）；`tests/adapters.test.ts`（fixture → 类型断言、null 安全）；`tests/vc.test.ts`（供需比派生仅在字段存在时计算，缺失返回 null）。

### F2：三栏骨架 + 底部 Dock 状态机 + 演出时间线

- 三栏 CSS Grid（`1fr | 300px | 340px`），≤1100px 转左右浮层；右下角全屏 FAB 收起两侧。
- `store/presentationStore.ts`：
  - 生命周期 `idle → submitting → running(act:1..9) → done|error`
  - `dataInsightBuffer`（证据卡挂起）、`revealedCards`（已揭示常驻）
  - Dock 状态：`input | task-running | plan-drawer`
  - `phaseResults`、`pipelineComplete`、`completed` 映射底部状态灯
- `presentation/timeline.ts`：编排表——每幕对应「过程步骤文案（打字）→ 完成事件 → 揭示的证据卡 → 触发的地图场景」。数据源自单次响应，按幕节奏推进；用户可点击「跳到某幕」回看（Sticky 卡不消失）。
- `presentation/typing.ts`：打字机 hook，`onStepComplete` 触发 `revealInsightsForProcessStep`。

**测试 F2**：`tests/store.test.ts`（reveal 门控：卡片先入 buffer，步骤完成才 revealed；Sticky 不因切幕消失）；`tests/timeline.test.ts`（九幕编排完整、幕→卡→场景映射齐全）。

### F3：幕一~二（工单 + 落到路网）

- `DiagnosisTicketCard`：渲染 `diagnosis_ticket.*`，`problem_type` 高亮溢流红；`constraints` 芯片；`match_confidence` 进度；`user_experiences` 折叠。
- `RecognitionSteps`：`spatial_scene.recognition_steps[]` 逐行打勾（`status=done` 绿勾）。
- 地图：`MapController.flyTo(lng,lat)` → `IntersectionLayer` 画虚线框；`HighlightPathLayer` 画 `highlight_path` 发光折线 + `upstream_nodes/downstream_nodes` 发光点。
- 降级：`spatial_scene.available=false` 或节点为空 → 展示 `spatial_objects` 文本 + 「拓扑数据不足，建议 POST /intersection/load」提示条。
- 底部：输入框下沉为任务执行栏，状态「正在解析口头描述…」。

**测试 F3**：`tests/ticketCard.test.tsx`（枚举翻译、约束/置信度渲染）；`tests/recognitionSteps.test.tsx`（5 步状态）；`tests/mapController.test.ts`（flyTo 参数、坐标 null 跳过）。

### F4：幕三~四（溢出验证 + 瓶颈判断）

- `DataMetricsCard`：`metrics.queue_ratio` 大字（≥1.0 红 / ≥0.8 琥珀 / else 青）；排队/蓄车长度、饱和度、绿灯利用率（低利用琥珀预警）、停车、延误；ECharts 时序折线（`time_series_trend` 有序列则画，否则占位）。
- `OverflowVerdict`：中央玻璃态卡片 = `overflow_verification.message`，色随 `risk_level`。
- `BottleneckCard`：`downstream_diagnosis.release_answer` 突出；`judgment_criteria[]` 清单；`can_simple_add_green=false` 红色禁令。
- 地图：切路口车道级视角，目标进口标红闪烁；`ChannelizationMini` 从右下滑入，`arms` 车道按排队比上色（<0.6 绿 / 0.6~0.9 橙 / ≥0.9 红 + `!`）。

**测试 F4**：`tests/metricsCard.test.tsx`（阈值配色）；`tests/bottleneckCard.test.tsx`；`tests/channelization.test.tsx`（车道配色阈值）。

### F5：幕五（干线溯源粒子流）

- `UpstreamTraceLayer.ts`：读取 `map_scenes.downstream_trace_map` / `flow_trace.entry_traces` / `arterial_analysis`。清除前序诊断覆盖物；双层发光 Polyline（来向琥珀、去向青蓝）；rAF 沿折线插值粒子，速度与 VPH 正相关；节点脉冲 Marker，`click` 弹磨砂气泡（路口名 + 转向 + `share_pct`）。
- 坐标/`share_pct` 为 null 的项跳过或标「占比未知」。
- `CorridorScanCard`：上游到达/放行强度、目标剩余空间、下游承接、`need_upstream_metering`、`summary`。

**测试 F5**：`tests/traceLayer.test.ts`（粒子插值纯函数、空 path 不崩、null 坐标跳过）；`tests/corridorCard.test.tsx`。

### F6：幕六~七（成因/案例 + 策略边界）

- `CauseCard`：`cause_analysis.primary_cause/secondary_causes/optimizable_points/data_gaps` + `cause_ranking` 条形；`cause_scores` 六维雷达（ECharts）。
- `CaseCarousel`：`case_cards.cards[]` 横向轮播（title/similarity/action/outcome/lesson）；`matched_count`/`high_similarity_count` 徽标。
- `StrategyBoundaryCard`：`strategy.principles`（防溢流优先高亮）、`recommended`、`not_recommended`（红框禁令）、`hard_constraints`。
- 地图：`ControlScopeLayer` 读 `control_scope_map`——目标「小步释放」Marker、上游「控流闸口」红 Marker、下游「盾牌」绿 Marker；`upstream_metering_points` 为空则仅渲染已知节点。

**测试 F6**：`tests/causeCard.test.tsx`、`tests/caseCarousel.test.tsx`、`tests/strategyCard.test.tsx`、`tests/controlScopeLayer.test.ts`。

### F7：幕八（方案生成与比选抽屉）

- `PlanDrawer`：底部上弹抽屉，`planActiveTab: stage_generation | plan_comparison`。
- Tab1 `PlanStageView`（数据源 `plan.recommended`）：相位卡（`phase_stage_timing_list[]` 秒数/黄/全红 + 流向箭头）、周期/绿信比派生、`upstream_control`、`phase_offset_sec`、`pedestrian_constraints`、`downstream_risk`、`expected_effect`、`rollback_condition`、`guardrail_pass`/`validation_errors`。
- Tab2 `PlanCompareMatrix`（数据源 `plan.candidates[]`，数量动态、横向滚动）：候选卡 + 推荐结论 `recommendation.rationale`。
- **契约缺口降级**：`vc_predictions`、供给/需求强度、`corridor_nodes` 后端未透出 → 对应子图渲染「该维度数据暂缺（后端待补）」占位；能从 `timing` 派生的（周期/秒数/相位数）正常展示。登记于「后端契约缺口」附录。
- 地图联动：`stage_generation` → FlyTo 车道级、转向箭头着色；`plan_comparison` → Zoom Out 干网 + `CorridorLayer`（坐标缺失则退化为示意图）。

**测试 F7**：`tests/planStage.test.tsx`（秒数/缺口占位）、`tests/planCompare.test.tsx`（动态候选数、推荐高亮）、`tests/planDrawer.test.tsx`（Tab 切换驱动地图 action）。

### F8：幕九（反馈闭环 + 兜底）

- `FeedbackPanel`：绿「接受并下发」/红「拒绝」；拒绝展开意见文本域 + 重启点选择（成因/策略/方案）→ `POST /agent/plan/regenerate`；勾选「沉淀为推荐/风险案例」随 `POST /agent/plan/decision`。
- 再生成 Differ：新旧配时对比，变化秒数 3 秒黄底高亮渐灭。
- 近期案例：`GET /agent/cases`（category textbook/recommended/risk）侧栏列表。
- 回滚监听：接受后订阅 `/intersection/load/stream`（或轮询），命中回滚条件顶部红色横幅。
- 断线/异常：`sse.ts` 重连 3 次；失败 Toast 提示「使用预置演示数据（Mock）」切回放。

**测试 F8**：`tests/feedback.test.tsx`（accept/reject payload）、`tests/regenerate.test.tsx`（Differ 高亮）、`tests/cases.test.tsx`、`tests/sse.test.ts`（重连状态机）。

### F9：联调打磨与交付

- 页面载入编排：一段式 staggered reveal；全屏 FAB；信号灯 connecting/open/closed 状态。
- Playwright 端到端（`e2e/`）：`VITE_MOCK=1` 回放 fixture，断言九幕依次揭示、地图 action 触发、抽屉与反馈可交互。
- `frontend/README.md`：环境变量、`npm run dev`（需后端 :8000 或 mock）、`npm run build`、AMap 密钥与安全提示。
- 更新 `docs/项目进度.md`：前端 UI 行进度、九幕前端状态。

**测试 F9**：`e2e/nine-acts.spec.ts` 全流程；`npm run build` 通过。

---

## 联调与运行

```bash
# 后端
source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000
# 前端
cd frontend && npm install && npm run dev      # 代理 /api → :8000
# 离线回放
VITE_MOCK=1 npm run dev
```

---

## 测试总览

```
frontend/tests/
  tokens.test.ts  enums.test.ts  adapters.test.ts  vc.test.ts
  store.test.ts   timeline.test.ts
  ticketCard/recognitionSteps/mapController.test.*
  metricsCard/bottleneckCard/channelization.test.*
  traceLayer/corridorCard.test.*
  causeCard/caseCarousel/strategyCard/controlScopeLayer.test.*
  planStage/planCompare/planDrawer.test.*
  feedback/regenerate/cases/sse.test.*
frontend/e2e/
  nine-acts.spec.ts
```

| 用例 ID | 阶段 | 场景 |
|---------|------|------|
| F-01 | F1 | 未知枚举回退不抛错 |
| F-02 | F1 | fixture → 类型/ null 安全 |
| F-03 | F2 | 卡片先入 buffer，步骤完成才揭示 |
| F-04 | F2 | Sticky 卡切幕不消失 |
| F-05 | F3 | spatial 不可用时文本兜底 |
| F-06 | F3 | 坐标 null 跳过渲染 |
| F-07 | F4 | queue_ratio 阈值配色 |
| F-08 | F4 | 车道饱和度配色 |
| F-09 | F5 | 空 path / null 坐标不崩 |
| F-10 | F6 | not_recommended 红框禁令 |
| F-11 | F7 | 缺口字段走占位而非假数据 |
| F-12 | F7 | Tab 切换驱动地图 action |
| F-13 | F8 | accept/reject/ regenerate payload |
| F-14 | F8 | SSE 重连状态机 |
| F-15 | F9 | 端到端九幕揭示 |

---

## 剧本字段映射（附录 A：幕→数据源）

| 幕 | 主数据源 | 前端载体 |
|----|----------|----------|
| 一 | `diagnosis_ticket` | DiagnosisTicketCard |
| 二 | `phases.intent.spatial_scene` | RecognitionSteps + Highlight/Intersection Layer |
| 三 | `phases.diagnosis.metrics` / `overflow_verification` / `scenario_report` | DataMetricsCard + OverflowVerdict + ChannelizationMini |
| 四 | `phases.diagnosis.downstream_diagnosis` / `bottleneck_analysis` | BottleneckCard |
| 五 | `phases.diagnosis.arterial_analysis` / `flow_trace` / `map_scenes` | CorridorScanCard + UpstreamTraceLayer |
| 六 | `phases.cause` | CauseCard + CaseCarousel |
| 七 | `phases.strategy` / `control_scope_map` | StrategyBoundaryCard + ControlScopeLayer |
| 八 | `plan` / `phases.plan` | PlanDrawer（Stage + Compare） |
| 九 | `/plan/decision`、`/plan/regenerate`、`/agent/cases` | FeedbackPanel |
| 全局 | `phase_results[]` / `pipeline_complete` / `completed` | BottomDock 状态灯 |

## 后端契约缺口（附录 B：仅登记，不在本计划实现后端）

| 缺口字段 | 设计稿用途 | 前端处理 |
|----------|-----------|----------|
| `plan.candidates[].vc_predictions` | 多方案供需比矩阵 | 「数据暂缺」占位 |
| `supply_intensity` / `demand_intensity` | 各方向供需强度柱状 | 占位；如有 `timing` 可派生则派生 |
| `plan.recommended.corridor_nodes` | 干线协调图节点 | 退化为示意图 |
| `pre_green_time_s` / `post_green_time_s` | 阶段优化前后对比 | 仅显示 `green_time_s`，无「优化前」列 |
| `scenario_report`（部分运行为空） | 检查单摘要 | `available=false` 时隐藏该卡 |

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 误把 `/agent/run` 当 SSE | 明确一次性响应 + 前端演出时间线；SSE 仅用于 load 进度 |
| 地图数据稀疏导致空屏 | 全覆盖物 null 守卫 + 文本兜底 + 提示条 |
| 第八幕比选字段缺失被「假数据」填充 | 一律占位并登记附录 B，遵守 rule 14 |
| AMap secret 前端暴露 | 本地演示接受；README 标注生产需服务代理；密钥经 gitignore 隔离 |
| 枚举翻译散落 | 统一 `labels/enums.ts` + `t()` 回退 |
| 演出节奏与真实耗时不符 | 时间线可配置节拍；`phase_results.duration_ms` 仅作展示 |

## 完成定义（Definition of Done）

- [ ] F0~F9 交付物齐备，`frontend/` 可 `npm run dev` 与 `npm run build`
- [ ] 九幕在真实后端与 `VITE_MOCK=1` 回放下均可完整演出
- [ ] 枚举全部中文化；地图/卡片对 null 与 `available=false` 优雅降级
- [ ] 第八幕缺口字段走占位，无任何硬编码假数据（rule 14）
- [ ] Vitest 单测 F-01~F-14 全绿；Playwright F-15 通过
- [ ] `frontend/README.md` 可被前端同学独立联调
- [ ] `docs/项目进度.md` 前端 UI 行更新
- [ ] 分支未直接合入 main（rule 1）；如遇 API 陷阱记录 `bugs/`
