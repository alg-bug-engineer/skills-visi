# frontend-v2 · 三栏信控工作台

路口问题诊断智能体的 **v2 前端**：在保留叙事流水线（二次确认 + Skill 固化）的基础上，集成 0625 **问题验证证据**与**约束量化**，采用 **GIS + 推理证据 + 理解过程** 三栏布局。

## 快速启动

```bash
# 项目根目录（后端 8011 + frontend-v2 5568）
bash scripts/dev-v2.sh
```

或手动：

```bash
cd backend && source .venv/bin/activate
uvicorn intersection_agent.main:app --host 127.0.0.1 --port 8011

cd frontend-v2 && npm install && npm run dev
```

- 后端：http://127.0.0.1:8011  
- **v2 前端**：http://127.0.0.1:5568  
- v1 前端（并存）：http://127.0.0.1:5567  

## 功能概览

| 能力 | 说明 |
|------|------|
| 三栏工作台 | GIS 全屏 \| 推理证据侧栏 \| 理解过程（可折叠） |
| 证据时序对齐 | 卡片随理解过程步骤打完字后出现，不抢跑 |
| 运行数据单卡 | 多场景 HUD 指标合并为一张运行数据卡 |
| 0625 证据 | 问题验证 + 分向画像 + 地图 Marker |
| 0625 约束 | 治理边界 + 保护方向高亮 |
| 渠化小窗 | 右下角浮动，分向/饱和阶段自动弹出 |
| 叙事保留 | `AnalysisQueue`、治理建议确认、Skill 固化 |

## 演示输入

### 市委书记汇报 TOP3（`DEMO_MODE=1`）

在 `backend/.env` 设置 `DEMO_MODE=1` 后，使用 `backend/config/demo_intersections.yaml` 中的固定话术：

| 角色 | NLU 输入 |
|------|----------|
| 主秀 | 会展路与奥体中路路口晚高峰东向西拥堵，配时跟不上流量 |
| 辅秀 | 二环东路与工业南路晚高峰排队长，有群众投诉 |
| 备秀 | 奥体中路与经十路晚高峰饱和高、部分方向空放 |

锚定日：**2026-06-13** 晚高峰。彩排：`cd backend && DEMO_MODE=1 uv run python scripts/run_demo_rehearsal.py`

### 通用联调

```
奥体西路与经十路交叉口，晚高峰南北向经常拥堵，垂直方向不能溢出
```

联调需真实库：`reference-date=2026-06-14`（后端配置）。

## 脚本

| 命令 | 说明 |
|------|------|
| `npm run dev` | 开发服务（5568） |
| `npm run build` | 类型检查 + 生产构建 |
| `npm run test` | Vitest 单元测试 |
| `npm run typecheck` | 仅 TS 检查 |

## 文档

- [架构](docs/ARCHITECTURE.md)
- [进度](docs/PROGRESS.md)
- [UI 规范](docs/STYLE_GUIDE.md)
- 后端对接：[FRONTEND_EVIDENCE_INTEGRATION.md](../backend/docs/FRONTEND_EVIDENCE_INTEGRATION.md)

## 环境变量

| 变量 | 默认 |
|------|------|
| `VITE_DEV_PROXY_TARGET` | `http://127.0.0.1:8011` |
| `VITE_DEV_PORT` | `5568` |
| `VITE_AMAP_KEY` | 见 `.env.development` |

## 与 frontend (v1) 关系

- `frontend/`：稳定版，端口 5567  
- `frontend-v2/`：工作台重构版，纳入根 monorepo，可并行迭代  
