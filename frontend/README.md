# 交通信控智能体 · 九幕演示前端

一个独立的 **Vue 3 + TypeScript + Vite** 前后端分离 SPA，面向**交通信控智能体**能力叙事，以「排队溢出」为典型示例场景，呈现诊断到方案的**九幕递进演出**。后端以 **SSE 逐 phase 流式**推送结果，前端**边算边渲染**：意图理解一完成，第一张证据卡就浮现，后续 phase 的计算与当前幕动画重叠，用「错位」掩盖步间延时。

设计权威来源：`../docs/design/`（Progressive Disclosure / GIS-UI 联动 / 专家领域语言）。

## 技术栈

| 关注点 | 选型 |
| --- | --- |
| 框架 / 构建 | Vue 3（`<script setup>` SFC） + TypeScript + Vite 6 |
| 状态 | Pinia |
| 地图 | 高德 AMap JS API 2.0（`@amap/amap-jsapi-loader`，3D 视角） |
| 可视化 | 纯 SVG/CSS 自绘（相位配时图、时距图、粒子流），零重型图库 |
| 单测 | Vitest + jsdom |
| 视觉/布局/遮挡测试 | Playwright（截图 + 包围盒断言） |

## 目录结构

```
frontend/
├─ src/
│  ├─ api/            # 类型、client、endpoints、SSE 封装（含 Mock 回放）
│  ├─ labels/         # 枚举 → 中文字典（未知值安全回退）
│  ├─ utils/          # format / guards / vc（缺失即降级，不编造）
│  ├─ composables/    # useTimeline（九幕定义）、useTyping（打字机）
│  ├─ stores/         # presentation：运行生命周期 + 演出状态
│  ├─ map/            # AMapProvider + MapController（逐幕 2D/3D 场景）
│  ├─ viz/            # 方案证据可视化（StageCards / StageMovementCanvas / 方向强度 …）；协调时距见 panels/CoordinationDiagram
│  ├─ cards/          # 左侧证据卡（工单/数据/瓶颈/干线/成因/策略）
│  ├─ panels/         # ProcessPanel / BottomDock / PlanDrawer / UnderstandingPanel …
│  ├─ theme/tokens.css# 设计令牌（深色信控主题）
│  ├─ mock/           # run_1_fixture.json（真实响应回放，非编造）
│  └─ App.vue / main.ts
├─ tests/unit/        # Vitest 用例
├─ e2e/               # Playwright 用例 + 截图产物
└─ .env.example
```

## 快速开始

```bash
cd frontend
cp .env.example .env.local   # 填入高德 KEY / SECURITY（见 ../docs/gd-js20.md）
npm install
npm run dev                  # http://localhost:5173
```

`.env.local` 关键项：

- `VITE_AMAP_KEY` / `VITE_AMAP_SECURITY`：高德密钥（gitignored，勿提交）。
- `VITE_API_TARGET`：后端地址，dev 下 `/api` 反代到此（默认 `http://localhost:8000`）。
- `VITE_MOCK=1`：离线回放 `src/mock/run_1_fixture.json`，不依赖后端。设 `0` 走真实后端。

## 对接后端（真实联调）

后端是 FastAPI + uvicorn，端口 `8000`，路由前缀 `/api/v1`，与前端调用一一对应；dev 下由 Vite 把 `/api` 反代到后端，**无需 CORS**。

**终端 A · 启动后端**（项目根目录，`.env` 已含 Qwen 密钥与 PG 真源）：

```bash
cd ..                      # 到项目根 traffic-agent-0706-zql
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# 健康检查：curl http://localhost:8000/api/v1/health
# → {"status":"ok","llm_mock":false,"model":"qwen3.7-plus","pg_configured":true}
```

**终端 B · 启动前端并连真实后端**：

```bash
cd frontend
# 把 .env.local 里的 VITE_MOCK 改为 0（关闭离线回放，改走真实接口）
#   VITE_MOCK=0
#   VITE_API_TARGET=http://localhost:8000   # 后端非本机/非 8000 时改这里
npm run dev                # 打开 http://localhost:5173，点「开始推演」即调用真实 /agent/run
```

对接的接口：`POST /api/v1/agent/run/stream`（流式，默认）、`POST /api/v1/agent/run`（一次性，降级兜底）、`POST /api/v1/agent/plan/regenerate`、`POST /api/v1/agent/plan/decision`、`GET /api/v1/agent/cases`、`GET /api/v1/health`。

> 提示：`VITE_MOCK=1` 时前端完全离线**模拟流式**回放 `src/mock/`（按 phase 定时推送），**不访问后端**——用于无后端时演示；真实联调设为 `0`，走 `/agent/run/stream`。真实流程会调用 Qwen + PG，各 phase 依次数秒返回，属正常。

## 刷新 mock 数据（沉淀一次真实请求）

`src/mock/run_1_fixture.json` 是一次**真实完整请求**的公开响应（结构等同 `/agent/run`：`phases/plan/diagnosis_ticket/phase_results`）。想更新它用仓库根目录脚本 `scripts/capture_frontend_mock.py`：

```bash
cd ..   # 到项目根

# 方式一（推荐·稳定）：从最新一条 completed 的运行日志提取，不再打模型
PYTHONPATH=. .venv/bin/python scripts/capture_frontend_mock.py
# 指定日志：… scripts/capture_frontend_mock.py --from-log logs/run_1/<trace>.json

# 方式二：现场发起一次真实请求（需 .env LLM_MOCK=false 且 PG 可达，耗时数十秒）
PYTHONPATH=. .venv/bin/python scripts/capture_frontend_mock.py --live "转山西路与经十路交叉口，六点十分到六点半，东向西排队溢出到上游"
```

产物直接覆盖 `frontend/src/mock/run_1_fixture.json`（单次回放与模拟流式共用）。改后跑 `npm test` 确认九幕旁白/门控仍成立。
> 实时采集偶发模型超时（`httpx.ReadTimeout`，reasoning 模型时延）导致只跑通部分 phase；脚本对 `completed != true` 会拒绝覆盖并提示重试，优先用「从日志提取」。

## 流式渐进（路径 B）

- 后端 `POST /agent/run/stream` 每完成一个 phase 推 SSE 事件：`phase_start` → `phase_done`（含**截至当前**的完整公开快照）→ … → `pipeline_complete`；单 phase 失败推 `error` 并停止。见 `needs/6` / `plans/6`。
- 前端 `api/sse.ts` 用 `fetch + ReadableStream` 解析（POST，EventSource 不支持），含最多 3 次重连；`store` 事件驱动。
- **门控推进**：某幕所属 phase（`ACT_DEFS[i].phase`）未在快照 `phases` 中就绪时，不进入该幕，Dock 显示「正在（阶段）推演…」；数据到达后自动续推。同一逻辑天然兼容单次 JSON（全 phase 一开始即就绪）。
- **优雅降级**：流式连接失败超重试 → 自动回退 `POST /agent/run` 单次 JSON + 原节奏，仍可走完九幕。

## 与后端的契约现实（重要）

- 流式 `phase_done.snapshot` 为**同结构公开响应**，`phases`/`plan` 随 phase 增长逐步补齐；前端整包覆盖 store，卡片经 getters 自动更新（无需 diff）。
- 字段多为**枚举编码**（如 `east_to_west`、`evening_peak`），前端 `labels/enums.ts` 统一翻译，未知值原样回退。
- 地图坐标常**稀疏或为空**（`highlight_path` 仅 1 点、上下游节点无坐标等）。所有覆盖物均做 `hasCoord` 守卫，无坐标则跳过并在面板显示文本兜底。
- 设计稿提及但后端**当前未透出**的字段（如逐车道 V/C）：一律显示「数据暂缺」，**绝不编造**（见 `utils/vc.ts`）。干线协调时距图 `panels/CoordinationDiagram.vue` 仅消费后端真实 `diagnosis.coordination.nodes`，缺间距/绝对相位/速度即 `available:false` 降级。

## 九幕 → 组件映射

| 幕 | 内容 | 证据卡 / 组件 | 地图场景 |
| --- | --- | --- | --- |
| 1 | 理解问题（工单） | `DiagnosisTicketCard` | 城市俯瞰 → 飞向路口 |
| 2 | 空间定位（识别步骤） | 过程栏 checklist | 路口 3D |
| 3 | 指标加载 + 溢出验证 | `DataMetricsCard` | 车道近景（近 2D） |
| 4 | 瓶颈：能不能加绿 | `BottleneckCard` | 车道 |
| 5 | 干线溯源 | `CorridorScanCard` + 粒子流 | 干线 3D |
| 6 | 成因 + 相似案例 | `CauseCard` | 干线 |
| 7 | 策略边界（可做/不可做） | `StrategyBoundaryCard` | 控制范围 |
| 8 | 方案决策（相位图/时距图/比选） | `PlanDrawer` | 路口 |
| 9 | 接受 / 拒绝再生成 | `PlanDrawer` 页脚 | 干线 |

## 语音播报模板

固定播报文案集中在 `src/config/voiceTemplates.json`，便于核对与修改：

- 各幕 `stepTitle` / `purpose` / `methodTemplate`（固定部分）
- `{method}`：方法词槽，取值见同文件 `methods[actId]`
- `{conclusion}`：结论词槽，运行时从诊断快照填充，不可写死在 JSON
- `compose`：`full` | `conclusionOnly` | `titleOnly` 控制拼接方式
- `absorption`：经验吸收阶段的固定播报

改 JSON 后重新 `npm run dev` 或 `npm run build` 即可生效。合成逻辑见 `src/config/voiceTemplates.ts`。

## 测试

```bash
npm test        # Vitest 单测（逻辑：枚举回退、格式化、坐标守卫、V/C 不编造、九幕构建）
npm run e2e     # Playwright 截图 + 布局/遮挡断言（自动以 MOCK 启动 dev）
```

Playwright 首次需安装浏览器：`npx playwright install chromium`。截图产物在 `e2e/shots/`。

## 构建部署

```bash
npm run build   # vue-tsc 类型检查 + vite 产出 dist/（纯静态）
npm run preview
```

`dist/` 为纯静态资源，可由 Nginx 等任意静态服务托管；生产环境将 `/api` 反代到后端即可。
生产建议改用**服务端代理签名**替代前端可见的 `securityJsCode`。
