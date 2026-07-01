# Bug 登记册

> 维护日期：2026-06-28 · 关联发布：[`RELEASE_v3.0.md`](../releases/RELEASE_v3.0.md)

本文件汇总演示与开发过程中发现的问题、截图证据与修复状态。截图存放于 [`artifacts/bugs/`](../../artifacts/bugs/)。

---

## 已修复

### BUG-001 · shell SOCKS 代理误伤后端 HTTP

| 项 | 内容 |
|----|------|
| 现象 | 后端 httpx 请求 DashScope 报 `socksio` 缺失或连接失败 |
| 根因 | 终端 export 的 `all_proxy=socks5://…` 被 Python 进程继承 |
| 修复 | `network_env.disable_shell_proxy_env()` + `httpx.AsyncClient(trust_env=False)` |
| 版本 | v2.0.5 |
| 文档 | [`DEV_CONSTRAINTS.md`](../DEV_CONSTRAINTS.md)、[`RELEASE_v2.0.5.md`](../releases/RELEASE_v2.0.5.md) |

---

### BUG-002 · 渠化全屏时地图左侧黑条

| 项 | 内容 |
|----|------|
| 现象 | 渠化模式下地图 pan 补偿导致左侧出现黑条 |
| 根因 | 右栏宽度补偿误用于渠化 locked 态 |
| 修复 | 渠化态 `pan offset = 0`，底图居中 |
| 版本 | v2.0.5 |
| 截图 | [`artifacts/bugs/主路口.png`](../../artifacts/bugs/主路口.png) |

---

### BUG-003 · TTS Realtime 完全无声

| 项 | 内容 |
|----|------|
| 现象 | 开启语音开关后无任何播报，控制台无明确错误 |
| 根因 | TTS WS 复用 LLM `DASHSCOPE_WORKSPACE_ID` → Workspace access denied |
| 修复 | `qwen_tts_workspace_id` 独立配置，默认不传 workspace；前端 warn 留痕 |
| 版本 | v3.0 |
| 单测 | `backend/tests/test_tts_config.py` |

---

### BUG-004 · 渠化转角圆弧横穿人行横道

| 项 | 内容 |
|----|------|
| 现象 | 路口内部出现多余曲线，视觉上横穿斑马线区域 |
| 根因 | `buildCorners` 贝塞尔控制点以路口中心为锚，弧线向内弯曲 |
| 修复 | 移除 `buildCorners` 装饰层（清晰度优先） |
| 版本 | v3.0 |
| 代码 | `frontend-v2/src/lib/channelizationAmap.ts` |

---

### BUG-005 · 叙事卡与渠化 HUD/图例布局冲突

| 项 | 内容 |
|----|------|
| 现象 | 右上角叙事卡与图例、迷你窗、渠化 header 互相遮挡 |
| 根因 | v2.0.6 叙事卡栈与 v2.0.5 图例/迷你窗位置未统一调整 |
| 修复 | 叙事卡 → 左上；图例 → 右下；迷你窗右对齐；`suppressStageHud` 去重 |
| 版本 | v3.0 |
| 参考 | [`artifacts/bugs/右上角图例参考.png`](../../artifacts/bugs/右上角图例参考.png)、[`列表样式.png`](../../artifacts/bugs/列表样式.png) |

---

## 已知 / 待优化

| ID | 摘要 | 优先级 | 备注 |
|----|------|--------|------|
| KNOWN-001 | 高优先级 cue 打断默认关闭 | 低 | `interruptOnHighPriority: false`，可按演示调 |
| KNOWN-002 | 经验约束在治理建议段不够显眼 | 中 | 复盘建议加「↩ 源自民警约束」标记 |
| KNOWN-003 | 缺少 Playwright E2E | 中 | 证据卡/栅栏/渠化时序 |
| KNOWN-004 | AMap 地理精确对齐 Three（Phase 2） | 低 | 可选 `AMap.GLCustomLayer` |

---

## UI 截图索引

| 文件 | 用途 |
|------|------|
| `artifacts/bugs/主路口.png` | 主路口演示态参考 |
| `artifacts/bugs/右上角图例参考.png` | 图例位置参考（v3.0 已迁至右下） |
| `artifacts/bugs/列表样式.png` | 干线列表样式参考 |
| `artifacts/ui-screenshots/*.png` | 回归/UI 走查截图 |
| `artifacts/ui-screenshots/report.json` | 截图元数据 |
