---
name: intersection-flow-timing-governance
description: 基于四维信控诊断与供需匹配度主轴，生成数据支撑、可落地的治理建议。Use when generating flow-timing governance narrative or user-facing suggestions.
metadata:
  skill_id: intersection_flow_timing_governance
  display_name: 流量-配时治理建议
  phase: flow_timing_governance
  scenarios: [intersection]
  triggers: [saturation, imbalance, empty_green, spillback, suggestion_ready]
  version: "0.1.0"
  enabled: true
  reference_files:
    - references/governance_rules.yaml
    - ../../common/路口专家经验规则.md
---

# 流量-配时治理建议

## 作用

在问题诊断与四维扫描（饱和度 / 失衡 / 绿灯空放 / 溢出）之后，结合**供需匹配度主轴**与运行数据，给出符合交通工程专业判断的治理建议。禁止「只看公式、一律加绿灯」的简化输出。

## 上游输入

- `flow_timing_governance.primary_diagnosis`：主诊断类型（`timing_optimizable` / `capacity_bottleneck` / `basically_matched`）及 headline、lever
- `flow_timing_governance.problems[]`：四维命中与证据
- `traffic_flow`：转向饱和度、spread、路口饱和度
- `evaluation`：绿灯利用率、空放率、失衡系数
- `granularity.by_turn`：分转向饱和度与绿灯利用率
- `timing_profile`：最小绿亏空、流量-绿信比评价
- 用户约束 `user_suggestion`、量化约束 `quantitative_constraints`

## 专家推理原则

1. **先判能不能靠配时解决**：spread 大且存在空放/低利用 → 绿信比再分配；spread 小且普遍高饱和 → 能力瓶颈，出路在非配时手段。
2. **加绿的前提**：关键方向过饱和 **且** 绿灯利用率仍有空间（通常 &lt; 0.75）**且** 不存在可对侧压缩的空放相位。
3. **失衡**：部分转向过饱和、其他空闲 → 重划绿信比，不是单纯加总绿灯。
4. **空放**：压缩低利用相位，转给过饱和转向；不与「一律加绿」混用。
5. **溢出**：防锁死优先，上游控流、出口优先、周期与边界措施；不单靠加绿消解排队。
6. **用户约束**不为「无」时，正文必须优先回应。

## 分维度治理方向（默认文案真源）

规则文件：[references/governance_rules.yaml](references/governance_rules.yaml)。后端 `GovernanceGuidanceService` 按条件匹配；业务专家可直接编辑 YAML 调整措辞与优先级。

| 维度 | 典型落点 |
|------|----------|
| 饱和度 | 利用率低→可加绿；空放/失衡并存→再分配；全饱和→周期/协调/渠化 |
| 失衡 | 转向极差大→重划绿信比；进口差异→压缩低需求侧 |
| 绿灯空放 | 压缩低利用相位，转给拥堵方向 |
| 溢出 | 上游控流、防外溢、出口优先 |

## 输出约束

- 面向交警：禁止 DWS/DWD/表名/dir8 等数据仓术语。
- 无数据支撑的维度不写具体数值结论。
- 治理建议正文须与 `primary_diagnosis.lever` 一致，不得与能力瓶颈判定矛盾（全饱和时禁止暗示「加绿即可解决」）。

## 结构化动作方案 `action_plan`

`FlowTimingGovernanceService.build()` 会附加 `action_plan`，供建议生成与前端展示共用：

| 字段 | 含义 |
|------|------|
| `action_type` | `reallocate_green` / `increase_green` / `capacity_non_timing` / `spillback_control` / `maintain` / `guidance_only` |
| `transfer_seconds` | 数据推导的挪绿/加绿秒数（非 `sat×12` 公式） |
| `donor_turn` / `recipient_turn` | 供绿方与受绿方转向及饱和度、利用率、绿信比 |
| `narrative_template` | 带证据的模板正文，LLM 只可润色不可改数 |
| `headline` | 渠化图右上角摘要 |

优先级：溢流严重 → 非配时能力瓶颈 → 转向级挪绿 → 定向加绿 → 四维文案兜底。
