# 项目总览 · 路口问题诊断以及固化技能

> 版本：2026-06-29  
> 本文档汇总开发内容、计划进度、主要变更与部署方式，作为根仓库的权威索引。

---

## 1. 项目定位

**交通智能体 · 路口拥堵诊断 · 标准 Agent Skill 包固化**

交警以自然语言描述路口拥堵场景 → NLU 解析（路口 / 时段 / 方向）→ 地图认知与数据抓取 → YAML 规则诊断 → 问题验证证据 → 流量-配时治理建议 → 可选固化为可复用 Skill 包。

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI · Qwen（百炼）· PostgreSQL · YAML 规则引擎 |
| 前端 v2（主） | Vue 3 · Vite · 高德地图 · Three.js 渠化 · SSE 流水线 |
| 前端 v1（遗留） | Vue 3，独立仓库，本 monorepo **不纳入** |
| 信控引擎参考 | `signal_optimization_engine-main/`，外部参考，本 monorepo **不纳入** |

---

## 2. 仓库结构（根 monorepo）

```
路口问题诊断以及固化技能/          ← 根 Git 仓库
├── backend/                      # FastAPI 后端（纳入根仓库）
├── frontend-v2/                  # Vue 3 三栏信控工作台（纳入根仓库）
├── scripts/                      # dev.sh / dev-v2.sh / prod-start.sh
├── deploy/                       # Nginx 配置、systemd 单元
├── docs/                         # 业务文档、检查单、开发计划
├── docker-compose.prod.yml       # [备选] Docker 部署，非默认
└── frontend/                     # v1 前端，独立 Git，已 .gitignore
└── signal_optimization_engine-main/  # 信控参考，已 .gitignore
```

### 端口约定

| 服务 | 开发 | 生产（ECS） |
|------|------|-------------|
| 后端 API | 8011 | 8011（内网，Nginx 反代） |
| frontend-v2 | 5568 | 80（Nginx 静态 + 反代） |
| frontend v1 | 5567 | 不部署 |

---

## 3. 开发内容与里程碑

### 3.1 后端能力演进

| 阶段 | 标签/日期 | 能力 |
|------|-----------|------|
| tag2 | 2026-06-24 | 拥堵诊断流水线、标准 Skill 包、SSE、方案 D 数据窗 |
| 新增 Skills 可视化 | 2026-06-24 | 固化可视化 SSE、地图场景编排、进口道指标、方向必填 NLU |
| 0625 需求 | 2026-06-25 | 问题验证证据、约束量化、`problem_evidence` SSE |
| 交互优化 | 2026-06-25 | 治理建议二次确认、Skill 固化二次确认、SQL 证据链 |
| 技能标签 | 2026-06-26 | Skill 标签体系、命中提示、约束感知快路径 |
| 四类信控问题 | 2026-06-26 | 饱和度/失衡/空放/溢出 + `flow_timing_governance` |
| 演示嗅探 | 2026-06-27 | 演示路口 TOP3、`DEMO_MODE`、检查单阈值对齐 |
| 经验吸收演示 | 2026-06-28 | `skill_absorption` SSE、三层 tags、L3 交错落盘、`InterleavedSkillPersistVisualizer` |
| **干线扫描** | **2026-06-29** | 道路级拥堵发现、地图沿路高亮、Top3 引导、选型接单点诊断；意图 LLM+规则 |
| **语音播报 v2** | **2026-06-29** | Qwen-TTS Realtime PCM 流式播报（替代阿里云 ISI） |

### 3.2 前端 v2 能力演进

| 版本 | 日期 | 能力 |
|------|------|------|
| v2.0.0 | 2026-06-25 | 从 v1 复制骨架，独立端口 5568，`usePresentation` |
| v2.0.1 | 2026-06-25 | GIS 全屏 + 渠化右下角小窗 |
| v2.0.2 | 2026-06-25 | 三栏布局（GIS \| 推理证据 \| 理解过程），证据卡与步骤同步 |
| 渠化增强 | 2026-06-26 | ChannelizationCanvas3D、指标条、失衡横幅、配时环 |
| 经验吸收 v2 | 2026-06-28 | 右栏 `ExperienceAbsorptionPanel` + 左 `SkillBuildDrawer` 同框 L3 交错 |

### 3.3 文档与技能包

| 路径 | 说明 |
|------|------|
| `docs/路口场景认知与问题诊断检查单.md` | 37 项认知 + 16 项诊断检查单 |
| `docs/路口指标证据计算说明.md` | 指标口径与证据计算 |
| `docs/intersection/*/SKILL.md` | 场景认知、问题诊断等 Agent Skill 定义 |
| `docs/路口四维筛选与演示路口清单.md` | 演示路口筛选结果 |
| `backend/data/skills/` | 运行时固化的 Skill 包（不提交 git） |

---

## 4. 计划与进度

### 4.1 已完成

| 计划文档 | 状态 |
|----------|------|
| [0625 需求实现](0625_IMPLEMENTATION.md) | ✅ 问题验证 + 约束量化 |
| [技能沉淀与匹配逻辑](技能沉淀与匹配逻辑开发计划.md) | ✅ 标签、快路径、命中提示 |
| [四类问题与 ECS 部署](plans/2026-06-26-四类问题与ECS部署开发计划.md) | ✅ P1–P4 完成；P5 改为**原生部署** |
| [演示路口嗅探](plans/2026-06-27-演示路口嗅探与检查单对齐开发计划.md) | ✅ TOP3 路口、`DEMO_MODE` |
| [经验吸收与技能固化演示](plans/2026-06-28-经验吸收与技能固化演示开发计划.md) | ✅ skill_absorption SSE + 右栏叠层 UI |
| [干线扫描与路口发现](plans/2026-06-27-干线扫描与路口发现.md) | ✅ 意图 LLM+规则、PG 排名、地图沿路高亮、选型接单点 |
| [frontend-v2 开发计划](../frontend-v2/docs/DEVELOPMENT_PLAN.md) | ✅ P0–P2.1；P3 待办 |

### 4.2 待办

| 项 | 说明 |
|----|------|
| Playwright E2E | 证据卡时序断言 |
| 常发日历热力图 | `congested_dates` 可视化 |
| HTTPS | ECS 证书（certbot，范围外） |
| K8s / 多实例 | 范围外 |

---

## 5. 主要变更记录（摘要）

详见 [backend/docs/CHANGELOG.md](../backend/docs/CHANGELOG.md)。

| 日期 | 变更 |
|------|------|
| 2026-06-25 | `problem_evidence` SSE 扩展 `by_direction`、`quantitative_constraints` |
| 2026-06-25 | `ProblemEvidenceService`、`ConstraintResolverService` |
| 2026-06-25 | 治理建议 / Skill 固化二次确认状态机 |
| 2026-06-24 | Skills 固化可视化、地图主舞台、`map_scene` SSE |
| 2026-06-24 | 标准 Skill 包目录结构、快路径匹配 |
| 2026-06-26 | `FlowTimingGovernanceService`、四类信控问题 |
| 2026-06-26 | 车道通行能力联表、`diagnose_focused` |
| 2026-06-27 | 演示路口嗅探脚本、`demo_intersections.yaml` |
| 2026-06-28 | `skill_absorption` SSE、三层 Skill tags、L3 交错落盘（吸收 + 写文件同框） |
| 2026-06-28 | frontend-v2 `ExperienceAbsorptionPanel` + `SkillBuildDrawer`（替代全屏 overlay） |
| 2026-06-29 | **干线扫描**：`corridor_scan` 流水线、意图 LLM 二分类+规则兜底、路网链化可视化 |
| 2026-06-29 | **语音 v2**：Qwen-TTS Realtime；选型口语匹配「奥体西与经十路」 |

---

## 6. 部署方式

### 6.1 本地开发

```bash
bash scripts/dev-v2.sh    # 推荐：backend 8011 + frontend-v2 5568
bash scripts/dev.sh       # v1 前端 5567（需 frontend/ 独立仓库）
```

局域网调试：`BIND_HOST=0.0.0.0 bash scripts/dev-v2.sh`

### 6.2 阿里云 ECS 生产（默认：原生部署）

与开发环境一致，**不使用 Docker**：

1. 宿主机安装 Python 3.11、Node 22、Nginx
2. `bash scripts/prod-start.sh` 构建前端、启动 uvicorn、配置 Nginx
3. 安全组放行 **5568** 端口

```
公网 → ECS:5568 (Nginx，默认，禁止 80)
         ├─ /        → frontend-v2/dist 静态资源
         ├─ /api/*   → 127.0.0.1:8011
         └─ /health  → 127.0.0.1:8011
```

详见 [deploy/README.md](../deploy/README.md)。

### 6.3 Docker 部署（备选）

`docker-compose.prod.yml` 与 `deploy/Dockerfile.*` 保留作备选，**非默认路径**。

---

## 7. 演示路口（市委书记汇报）

设置 `backend/.env` 中 `DEMO_MODE=1`：

| 角色 | 路口 | inter_id |
|------|------|----------|
| 主秀 | 会展路与奥体中路 | `011wwe29jbf00001` |
| 辅秀 | 二环东路与工业南路 | `011wwe2854m00001` |
| 备秀 | 奥体中路与经十路 | `011wwe28ctu00001` |

锚定日：**2026-06-13** 晚高峰。彩排：`cd backend && DEMO_MODE=1 python scripts/run_demo_rehearsal.py`

---

## 8. 文档索引

| 文档 | 说明 |
|------|------|
| [README.md](../README.md) | 快速开始 |
| [backend/README.md](../backend/README.md) | 后端 API |
| [backend/docs/API.md](../backend/docs/API.md) | SSE / REST 参考 |
| [backend/docs/PROJECT_LOGIC.md](../backend/docs/PROJECT_LOGIC.md) | 架构与编排 |
| [frontend-v2/README.md](../frontend-v2/README.md) | v2 工作台 |
| [frontend-v2/docs/PROGRESS.md](../frontend-v2/docs/PROGRESS.md) | 前端进度 |
| [路口场景认知与问题诊断检查单.md](路口场景认知与问题诊断检查单.md) | 业务检查单 |
| [路口指标证据计算说明.md](路口指标证据计算说明.md) | 指标口径 |
| [deploy/README.md](../deploy/README.md) | ECS 部署指南 |

---

## 9. 测试

```bash
# 后端单测（需 Python 3.11+，推荐 backend/.venv）
cd backend && MOCK_LLM=1 MOCK_DB=1 .venv/bin/pytest -q   # 89 项

# 前端单测
cd frontend-v2 && npm run test

# 联调冒烟
bash scripts/e2e-v2.sh
```
