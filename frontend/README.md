# 交通智能体 · 排队溢出九幕演示前端

一个独立的 **Vue 3 + TypeScript + Vite** 前后端分离 SPA，围绕「排队溢出」诊断到方案的**九幕递进演出**，把后端智能体的一次性 JSON 响应，以电影化节奏逐幕揭示在 GIS 底图上。

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
│  ├─ viz/            # PhaseDiagram（相位配时）、TimeSpaceDiagram（绿波）
│  ├─ cards/          # 左侧证据卡（工单/数据/瓶颈/干线/成因/策略）
│  ├─ panels/         # InsightPanel / ProcessPanel / BottomDock / PlanDrawer …
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

对接的接口：`POST /api/v1/agent/run`、`POST /api/v1/agent/plan/regenerate`、`POST /api/v1/agent/plan/decision`、`GET /api/v1/agent/cases`、`GET /api/v1/health`、`POST /api/v1/intersection/load[/stream]`。

> 提示：`VITE_MOCK=1` 时前端完全离线回放 `src/mock/`，**不访问后端**——用于无后端时演示；真实联调务必设为 `0`。真实 `/agent/run` 会调用 Qwen + PG，单次可能耗时数秒到数十秒，属正常。

## 与后端的契约现实（重要）

- `/api/v1/agent/run` 返回**一次性完整 JSON**（非流式）。九幕的「递进感」由前端 `useTimeline` + `useTyping` 编排节奏，而非后端分片。
- 字段多为**枚举编码**（如 `east_to_west`、`evening_peak`），前端 `labels/enums.ts` 统一翻译，未知值原样回退。
- 地图坐标常**稀疏或为空**（`highlight_path` 仅 1 点、上下游节点无坐标等）。所有覆盖物均做 `hasCoord` 守卫，无坐标则跳过并在面板显示文本兜底。
- 设计稿提及但后端**当前未透出**的字段（如逐车道 V/C、时距图节点间距/绝对相位）：一律显示「数据暂缺」，**绝不编造**（见 `utils/vc.ts`、`viz/TimeSpaceDiagram.vue`）。
- 真 SSE 仅 `/intersection/load/stream`；`api/sse.ts` 提供带最多 3 次重连的状态机骨架，失败回调可切 Mock 兜底。

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
