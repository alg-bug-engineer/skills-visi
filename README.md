# 路口问题诊断以及固化技能

交通智能体 · 路口拥堵诊断 · 标准 Agent Skill 包固化。

> 完整总览见 [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)

## 仓库结构

```
├── backend/          # FastAPI 后端（纳入根仓库）
├── frontend-v2/      # Vue 3 三栏信控工作台 v2（纳入根仓库，端口 5568）
├── scripts/          # dev.sh / dev-v2.sh / prod-start.sh
├── deploy/           # Nginx、systemd 配置
├── docs/             # 业务/数据文档、开发计划
├── frontend/         # Vue 3 前端 v1（独立 Git，不纳入根仓库）
└── signal_optimization_engine-main/  # 信控引擎参考（不纳入根仓库）
```

## 快速开始

```bash
bash scripts/dev-v2.sh   # 推荐：v2 工作台 5568 + 后端 8011
bash scripts/dev.sh      # v1 前端 5567（需 frontend/ 独立仓库）
```

- 后端：http://127.0.0.1:8011  
- 前端 v2：http://127.0.0.1:5568  
- 前端 v1：http://127.0.0.1:5567  

### 阿里云 ECS

**开发阶段（推荐）：**

```bash
cp backend/.env.example backend/.env
bash scripts/prod-dev.sh
# http://<ECS公网IP>:5568/
```

**预发布 / 稳定演示：** `bash scripts/prod-start.sh`（build + Nginx）

- 前端默认 **5568** 端口（Nginx），**不使用 80**；后端 `0.0.0.0:8011` 仅本机反代
- 演示汇报：设置 `DEMO_MODE=1`
- 详见 [deploy/README.md](deploy/README.md)

局域网调试：`BIND_HOST=0.0.0.0 bash scripts/dev-v2.sh`

## 发布标签（backend 历史）

| 标签 | 说明 |
|------|------|
| `tag2` | 后端完成 + 前端简单验证（对话 UI + SSE） |
| **`新增-Skills-可视化`** | Skills 固化全屏可视化 + 地图主舞台 + 进口道指标 + 方向必填 |

详见 [backend/docs/RELEASE_新增Skills可视化.md](backend/docs/RELEASE_新增Skills可视化.md)。

## 文档索引

| 文档 | 说明 |
|------|------|
| [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) | **项目总览**（进度、变更、部署） |
| [backend/README.md](backend/README.md) | 后端快速开始 |
| [backend/docs/PROJECT_LOGIC.md](backend/docs/PROJECT_LOGIC.md) | 架构与亮点 |
| [backend/docs/API.md](backend/docs/API.md) | API / SSE |
| [backend/docs/CHANGELOG.md](backend/docs/CHANGELOG.md) | 变更记录 |
| [frontend-v2/README.md](frontend-v2/README.md) | v2 三栏工作台 |
| [deploy/README.md](deploy/README.md) | ECS 部署指南 |
| [docs/路口专家经验规则.md](docs/路口专家经验规则.md) | 专家规则原文 |
