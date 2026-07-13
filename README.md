# 交通信控智能体

面向交通决策场景的信控诊断与方案演示系统：后端 FastAPI 多 Skill 流水线 + 前端 Vue3 九幕渐进演出（SSE 边算边渲染）。

## 快速开始

拉取仓库后按 **[docs/部署指南.md](docs/部署指南.md)** 安装依赖并启动。三种路径：

1. **前端 Mock** — 只起 Vite，离线回放（最快看 UI）
2. **本地联调** — `scripts/start-all.sh`（LLM Mock / Demo 回退可选）
3. **PG 真源** — 配置 `PG_DSN`，关闭 Demo 回退

```bash
# 依赖（摘要，细节见部署指南）
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
cp .env.example .env
cp frontend/.env.example frontend/.env.local   # 填入高德等密钥

bash scripts/start-all.sh   # 或先 VITE_MOCK=1 只跑前端
```

## 仓库结构

| 路径 | 说明 |
|------|------|
| `app/` | 后端 API、Skill 编排、PG 适配、指标与溯源 |
| `frontend/` | Vue3 + TS + Vite 演示 SPA |
| `skills/` | 各阶段 Skill 脚本与配置 |
| `docs/` | 现行设计、剧本、集成与**部署指南** |
| `needs/`、`plans/` | **现行**需求与计划（编号 29+） |
| `bugs/` | 缺陷台账 |
| `archive/` | 历史需求/计划（1–28）与过期分析文档 |
| `scripts/` | 启停、`package-local.sh` 本地打包（含 env）等 |
| `tests/` | 后端 pytest |

## 文档索引

| 文档 | 用途 |
|------|------|
| [docs/部署指南.md](docs/部署指南.md) | **新人部署入口** |
| [docs/rule.md](docs/rule.md) | 开发约束 |
| [docs/剧本.md](docs/剧本.md) / [剧本字段-API对照.md](docs/剧本字段-API对照.md) | 九幕叙事与字段 |
| [docs/design/](docs/design/) | UI / 交互 / 运镜 |
| [docs/典型输入案例-点线优化.md](docs/典型输入案例-点线优化.md) | 演示用一句话 query |
| [frontend/README.md](frontend/README.md) | 前端细节 |
| [archive/README.md](archive/README.md) | 归档说明 |

## 开发提示

- 密钥：根目录 `.env`、前端 `.env.local` 已 gitignore；向团队索取，勿提交。
- 回归：`.venv/bin/python -m pytest tests/ -q`；`cd frontend && npm test && npm run build`。
- 现行需求见 `needs/`，对应计划见 `plans/`。
