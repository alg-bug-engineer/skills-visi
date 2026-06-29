# 路口问题诊断以及固化技能

交通智能体 · 路口拥堵诊断 · 标准 Agent Skill 包固化。

> 完整总览见 [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)

## 仓库结构

```
├── backend/          # FastAPI 后端（纳入根仓库）
├── region-scan/      # 区域路口扫描与试点选择（全域体检 + 试点榜，复用 backend 诊断；API 8100 / 前端 5570）
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
bash scripts/regression.sh  # 合并前：backend pytest + frontend vitest
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

## 发布标签

| 标签 | 说明 |
|------|------|
| `v1.0.0` | 后端基线 + 回归测试基线 |
| `tag2` | 后端完成 + 前端简单验证（对话 UI + SSE） |
| `v2.0.5` | 地图渠化融合、呈现栅栏、语音摘要 |
| **`v3.1`** | **供需匹配度主轴、`action_plan`、治理 Skill** |
| **`develop`** | **演示叙事精简（左数据右建议，删溯源/干线）— 见 [docs/BRANCH_DEVELOP.md](docs/BRANCH_DEVELOP.md)** |

详见 [docs/RELEASE_v3.0.md](docs/RELEASE_v3.0.md)、[docs/bugs/BUG_REGISTRY.md](docs/bugs/BUG_REGISTRY.md)。

## 文档索引

| 文档 | 说明 |
|------|------|
| [docs/BRANCH_DEVELOP.md](docs/BRANCH_DEVELOP.md) | **`develop` 分支说明（勿合并 main）** |
| [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) | **项目总览**（进度、变更、部署） |
| [docs/RELEASE_v3.0.md](docs/RELEASE_v3.0.md) | **v3.0 发布说明** |
| [docs/bugs/BUG_REGISTRY.md](docs/bugs/BUG_REGISTRY.md) | Bug 登记与截图 |
| [docs/REGRESSION_POLICY.md](docs/REGRESSION_POLICY.md) | **回归测试约束**（合并前必跑） |
| [docs/REGRESSION_TEST_SPEC.md](docs/REGRESSION_TEST_SPEC.md) | 全量回归测试点 |
| [backend/README.md](backend/README.md) | 后端快速开始 |
| [backend/docs/PROJECT_LOGIC.md](backend/docs/PROJECT_LOGIC.md) | 架构与亮点 |
| [backend/docs/API.md](backend/docs/API.md) | API / SSE |
| [backend/docs/CHANGELOG.md](backend/docs/CHANGELOG.md) | 变更记录 |
| [frontend-v2/README.md](frontend-v2/README.md) | v2 三栏工作台 |
| [deploy/README.md](deploy/README.md) | ECS 部署指南 |
| [docs/路口专家经验规则.md](docs/路口专家经验规则.md) | 专家规则原文 |
