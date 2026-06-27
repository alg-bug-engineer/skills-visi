# 项目状态快照 · 干线扫描 + 语音 v2

> 日期：2026-06-29  
> 分支：`main`（自 `feature/tts` 合并）  
> 单测：backend **118** passed

---

## 1. 本阶段新增能力

| 能力 | 状态 | 说明 |
|------|------|------|
| 干线扫描 | ✅ | 道路级拥堵发现、PG 排名、Top3 引导 |
| 意图 LLM 分类 | ✅ | 首轮二分类 + 规则兜底，禁 thinking |
| 路网可视化 | ✅ | link 链化单 polyline，左侧路口列表 |
| 路口选型 | ✅ | 排名/口语/列表点击 → 单点诊断 |
| Qwen-TTS Realtime | ✅ | PCM 流式播报，替代阿里云 ISI |

---

## 2. 关键文档

| 文档 | 内容 |
|------|------|
| [干线扫描功能说明](../../docs/plans/2026-06-27-干线扫描与路口发现.md) | 流程、状态机、模块索引 |
| [CHANGELOG.md](CHANGELOG.md) | 变更记录 |
| [PROJECT_LOGIC.md](PROJECT_LOGIC.md) | 总体逻辑（含干线分支） |
| [PROJECT_OVERVIEW.md](../../docs/PROJECT_OVERVIEW.md) | 根仓库索引 |

---

## 3. 快速启动

```bash
bash scripts/dev-v2.sh          # 8011 + 5568
cd backend && pytest -q         # 118 项
```

环境：`backend/.env` 参考 `.env.example`（`MOCK_LLM=0` + PG 可查真实干线）

---

## 4. 验证用例

1. 「奥体西路有哪些拥堵路口在早高峰」→ 地图 + 左侧列表  
2. 「奥体西与经十路」→ 选定经十路路口，追问方向  
3. 点击左侧 #1 路口 → 自动进入诊断流程  
