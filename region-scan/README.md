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

## 数据与口径说明

### 区域过滤（Task 1.2 决策：暂不实现）

`road6.dim_inter_info`（19 列）**无行政区字段**，也无 bbox 经纬度 min/max 字段，仅有
`geom_center`（WKT POINT）与 `geom_boundary`（WKT 多边形）。因此按计划「仅当 DB 有
行政区/bbox 字段时实现」的前提不成立，**Task 1.2 跳过**。如需区域收敛，可后续在前端
按 `geom_center` 经纬度做 bbox 客户端过滤，无需改库。

当前版本 `20260501` 下 `is_signalized=1` 且有坐标的信号路口共 **5447** 个。

### 分层口径真实库冒烟（Task 4.3）

对有流量数据的 5 个路口跑「早高峰」诊断，人工核对坐标落点与分层合理（济南二环东路一带）：

| 路口 | 饱和度 | problem_band | pilot | 说明 |
|------|-------:|------|------:|------|
| 二环东路出口与二环东路辅路 | 1.85 | 工程可解 | — | 严重过饱和，配时无效 ✓ |
| 二环东路辅路与燕山东路 | 1.03 | 工程可解 | — | 过饱和 ✓ |
| 浆水泉西路与浆水泉路 | 0.24 | 配时可解 | 60.0 | 低饱和但有绿灯空放/溢出，可优化 ✓ |
| 浆水泉路与荆山东路 | 0.86 | 配时可解 | 60.0 | 未过饱和，检出失衡/空放 ✓ |
| 二环东路与浆水泉西路 | — | 数据不足 | — | 该时段无运行数据 ✓ |

坐标 `lon≈117.07 / lat≈36.63` 落点正确（济南二环东路），与现有干线扫描高德渲染约定一致。
