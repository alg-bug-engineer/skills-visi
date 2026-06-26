# 演示路口彩排记录

> 执行时间：2026-06-27  
> 命令：`cd backend && DEMO_MODE=1 uv run python scripts/run_demo_rehearsal.py`  
> 锚定日：**2026-06-13（周五）** 晚高峰 17:00–19:00

## 彩排结果

| 角色 | 路口 | inter_id | 投诉件数 | 诊断 | 命中规则（前5） | 四维命中 |
|------|------|----------|---------|------|----------------|---------|
| 主秀 | 会展路与奥体中路路口 | `011wwe29jbf00001` | 0 | ✅ | oversaturation, green_insufficient, spillback, empty_green, turn_imbalance | 饱和/失衡/空放 |
| 辅秀 | 二环东路与工业南路路口 | `011wwe2854m00001` | **6** | ✅ | 同上 + `rule_public_complaint_demo` | 饱和/失衡/空放 |
| 备秀 | 奥体中路与经十路路口 | `011wwe291ey00001` | 2 | ✅ | + approach_high_delay | 饱和/失衡/空放 |

\* 彩排脚本未加载 `timing_profile`，完整 orchestrator 流水线会输出 `weak/mismatch` 及 Spearman τ。

## 汇报话术（固定 NLU 输入）

见 `backend/config/demo_intersections.yaml` → `demo.nlu_prompts`：

1. **主秀**：会展路与奥体中路路口晚高峰东向西拥堵，配时跟不上流量  
2. **辅秀**：二环东路与工业南路晚高峰排队长，有群众投诉  
3. **备秀**：奥体中路与经十路晚高峰饱和高、部分方向空放  

## 启用演示模式

```bash
# backend/.env
DEMO_MODE=1
```

或在生产启动前：

```bash
export DEMO_MODE=1
bash scripts/prod-start.sh
```

## 单测

```bash
cd backend && uv run pytest tests/ -q
# 79 passed
```

## 验收勾选

- [x] TOP3 路口 `missing_dws=false`
- [x] 主秀命中失衡 + 空放规则
- [x] 阈值 `green.low_utilization_diagnosis = 0.60`
- [x] 饱和度展示 cap ≤ 1.5（经十路路口）
- [x] `flow_timing_governance` 含 expert_rules / checklist_refs
- [x] 前端四维诊断卡片 `FlowTimingGovernanceCard`
