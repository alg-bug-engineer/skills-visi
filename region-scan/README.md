# region-scan · 区域路口扫描与试点选择

把"单路口诊断"能力规模化到**全区域所有信号路口**，产出一张"全域体检地图"，
并筛出**配时可解、改善潜力高**的路口作为试点候选 —— 让领导从"逐路口拍脑袋"
变成"看榜单选试点"。

- 设计文档：[`../docs/plans/2026-06-29-区域路口扫描与试点选择-design.md`](../docs/plans/2026-06-29-区域路口扫描与试点选择-design.md)
- 实现计划：[`../docs/plans/2026-06-29-区域路口扫描与试点选择.md`](../docs/plans/2026-06-29-区域路口扫描与试点选择.md)

## 架构

四层：区域批量扫描引擎 → 快照存储 → 扫描 API → 高德前端。批处理离线跑、写快照；
地图只读快照。Python 侧**复用 `backend/intersection_agent`** 的 PG 访问、认知、诊断、
信控治理服务，不重复造轮子。

## 环境

本项目依赖 backend 包 `intersection_agent`，须在能 import 它的同一 Python 环境中运行。
默认复用 backend 的虚拟环境：

```bash
# 安装（开发态，path 依赖指向 ../backend）
cd region-scan
uv pip install -e ".[dev]"   # 或复用 backend/.venv
```

DB 连接走 backend 现有 `intersection_agent.config.get_settings()` + `backend/.env`
（PGHOST 等），**不在本项目硬编码连接串**。

## 跑扫描

```bash
python -m region_scan.cli scan          # 全区域扫描，产出快照到 snapshots/
```

## 起 API

```bash
uvicorn region_scan.api:app --reload --port 8100
```

## 跑前端

```bash
cd frontend
npm install
npm run dev
```

## 测试

```bash
MOCK_DB=1 python -m pytest        # 不连库的单元测试
```
