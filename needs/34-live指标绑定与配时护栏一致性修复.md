# 需求 34 · 点/线典型路口 live 指标绑定与配时护栏一致性修复

> **状态：典型 Case 已收敛为两例并完成 live 重采（main）** · 点 `ce4c64fa635b4d18` / 线 `084f7916f29e4b0e` 均为五幕；两例方案均因周期护栏无可行解（`completed=false`，不伪造推荐）  
> 分支：`main`（用户指定主干开发）  
> 证据分析：`analysis/两个典型路口-live链路复核-20260713.md`  
> 正式 Case：`docs/典型输入案例-点线优化.md` · `frontend/src/mock/cases/manifest.json`

## 一、背景

2026-07-13 对两个真实数据库候选进行了 live 采集：

| 类型 | 目标流向 | trace_id | live结果 |
|---|---|---|---|
| 点优化 | 坤顺路×奥体西路北进口左转→坤顺路×礼耕路 | `40dfc09d49f94f6d` | 前4阶段成功，方案阶段失败，`completed=false` |
| 线优化 | 解放东路×奥体中路南进口直行→坤顺路×奥体中路 | `1d066b56a45d4bcb` | 5阶段成功，`completed=true` |

两例的上下游拓扑和点/线策略方向基本正确，但 live 暴露出目标转向指标错绑、排队库容方向错配、流量覆盖率超过100%、配时基线冲突、护栏误判通过、状态字段矛盾以及方案场景文案反转等问题。依据 `docs/rule.md` 第14—18条，这些问题会使生产输出含有不可信指标或不可下发配时，必须修复后才能把两个路口升级为正式典型案例。

## 二、证据链

### E1 · 点案例目标转向被进口最大值覆盖

原始证据：`frontend/src/mock/cases/case_a_fixture.json`，trace `40dfc09d49f94f6d`。

- ticket：北向南、左转。
- `diagnosis.metrics.saturation=1.5446`。
- `diagnosis.metrics.by_movement`：北直1.5446、北左1.2365。
- 结论：综合指标使用了北进口最大转向值，而非请求的北左值。

### E2 · 点案例排队库容方向错配

- live：`queue_length_m=163.0`、`storage_length_m=195.68`、`queue_ratio=0.833`。
- 静态路网复核：北进口间距357.21m；195.68m为东进口间距。
- 结论：北左排队比使用了其他进口的库容分母，溢流预警不可作为目标转向证据。

### E3 · 点案例下游有余量，但诊断/方案文案反转

- 礼耕下游：排队5.4m、排队比0.0397、饱和度0.8、剩余空间130.76m、`blocked=false`、`release_guard=downstream_has_slack`。
- 同一响应仍输出“复合瓶颈、不能简单加绿”，候选场景出现“礼耕路承接不足/接不住”。
- 策略包实际为`incremental_release`，建议增绿5s。
- 结论：事实层、诊断层、方案模板没有使用同一份下游判定。

### E4 · 流量追踪比例越界

- 点案例下游流向占比201.9%，上游来源覆盖286.39%。
- 线案例上游来源77.28%，在合理范围。
- 结论：点案例存在跨时段/跨转向聚合或分母口径错误；任何`share_pct/raw_coverage>100`不得进入生产叙事。

### E5 · 点案例配时基线冲突并正确失败

- 诊断：现状周期60s。
- 方案：`current_cycle_s=164`，优化周期123s。
- 策略硬约束：周期≤90s。
- 结果：三个候选均因123s>90s失败，无推荐方案，`completed=false`。
- 结论：护栏拦截结果正确，但现状周期源不一致，导致优化器输入本身不可信。

### E6 · 线案例目标转向指标疑似错绑

原始证据：`data/live-validation/jiefangdong-aotizhong-south-through-line.json`，trace `1d066b56a45d4bcb`。

- ticket：南向北、直行。
- live综合饱和度：1.7734。
- 同窗口数据库复核：南直约1.0641，南左约1.7628。
- 结论：live值更接近南左，需验证是否仍采用进口最大值。

### E7 · 线案例周期护栏误判通过

- 策略硬约束：`max_cycle_s=180`。
- 三个候选：`cycle_s=190`。
- 输出：候选`guardrail_pass=true`、顶层`all_guardrails_passed=true`、`completed=true`。
- 结论：违反硬约束的方案被推荐，是阻断上线的P0问题。

### E8 · 线案例配时基线和状态语义冲突

- 诊断配时：150s；方案`current_cycle_s=164`。
- `problem_confirmed=false`、`healthy=false`，但继续完成策略和方案。
- 部分现状阶段绿灯1s/3s，策略最小绿14s；部分转向流量为0或缺失。
- 结论：配时方案选择、阶段标准化和流水线完成条件需要统一。

## 三、目标

### G1 · 目标进口+转向原子绑定

从意图识别到诊断、成因、策略、方案，全链路使用统一`movement_key=(inter_id, dir8_code, turn_dir_no, time_window)`；目标指标不得被进口或路口MAX覆盖。

### G2 · 排队比使用正确方向库容

`queue_ratio`必须使用目标进口方向的`adjacent_inter_spacing_m`；无匹配库容时返回`available:false + reason`，禁止借用其他进口长度。

### G3 · 下游判定单一真源

下游`blocked/slack`由结构化判定对象统一供诊断、策略评分、候选场景、推荐理由和前端叙事消费，禁止各阶段重新推断或使用固定场景模板。

### G4 · 流量追踪守恒

同一时段、同一入口、同一分母下的来源覆盖率必须在`[0,100]`；跨时段数据不得累加。越界时返回结构化质量错误，不得展示“每100辆来自286辆”。

### G5 · 配时基线单一真源

`timing_profile.cycle_s`、优化器`current_cycle_s`、候选现状阶段总时长必须来自同一激活方案。若激活方案无法唯一解析，方案阶段失败并返回原因。

### G6 · 护栏强一致

候选的最小绿、最大绿、最大周期、黄灯、全红、行人清空等任一硬约束失败时：

- `guardrail_pass=false`；
- 不得成为`recommended`；
- 若无候选通过，`recommended_plan_id=null`、`all_guardrails_passed=false`、方案阶段失败；
- 顶层`completed`不得为true。

### G7 · 状态机一致

明确`problem_confirmed`、`healthy`、phase success、pipeline complete与`completed`的关系；禁止`problem_confirmed=false`且无明确降级原因时继续输出可下发方案。

## 四、功能需求

### FR-1 诊断指标绑定

- `metrics`增加`target_movement_key`和`metric_scope=movement|approach|intersection`。
- 面向目标问题的`queue_length_m/queue_ratio/saturation/green_utilization`必须为movement粒度。
- approach/intersection聚合仅放在对比字段，不得覆盖目标指标。

### FR-2 库容匹配与证据

- 输出`storage_length_m`同时输出`storage_direction`、`storage_source`、`spacing_version_id`。
- 校验`storage_direction == ticket.direction`。
- 左转/直行共享进口物理库容时应显式标注`scope=approach_storage`。

### FR-3 下游事实对象

新增或统一：

```json
{
  "movement_key": "d0_t1",
  "downstream_inter_id": "...",
  "receiving_dir8_code": 6,
  "receiving_turn_dir_no": 1,
  "queue_ratio": 0.0397,
  "saturation": 0.8,
  "blocked": false,
  "decision": "slack",
  "source": "pg"
}
```

策略和方案只能引用该对象，不得根据用户输入中的“有空间/接不住”直接覆盖数据库判定。

### FR-4 流量守恒校验

- 统一时间窗与分母，修复跨时段膨胀。
- `share_pct>100`或`share_pct<0`时`available=false`并记录trace日志。
- 不允许`vehicles_of_100>100`。

### FR-5 激活配时解析

- 诊断和方案优化器共用同一`signal_plan_snapshot_id`。
- 输出`current_cycle_s`与阶段总时长的校验差；超容差时阻断方案生成。
- 禁止把其他plan_no、全天方案或拆分stage片段混为当前方案。

### FR-6 护栏执行顺序

1. 生成候选；
2. 标准化阶段；
3. 校验最小绿/最大绿/周期/安全间隔；
4. 剔除失败候选；
5. 仅对通过候选评分推荐；
6. 聚合顶层状态。

### FR-7 典型案例重采

- 点案例必须严格使用北左→礼耕流向。
- 线案例必须严格使用南直→坤顺路×奥体中路流向，不得复用旧“北直”Case D。
- fixture只能由live采集生成，禁止人工补数。

## 五、非目标

- 不调整0.8/0.85/0.9等业务阈值。
- 不以放宽最大周期绕过护栏。
- 不新增demo指标、固定配时秒数或静默fallback。
- 不直接下发现场信号控制。

## 六、验收标准

- [ ] 点案例目标指标明确绑定北左，不能再返回北直1.5446作为北左饱和度。
- [ ] 点案例`storage_direction`为北进口，排队比不再使用东进口195.68m。
- [ ] 点案例礼耕下游`blocked=false`时，策略和候选文案不得称其“接不住”。
- [ ] 所有来源/去向比例均在0—100%，越界数据结构化降级。
- [ ] 点案例诊断周期与方案`current_cycle_s`完全一致。
- [ ] 线案例目标指标绑定南直，不得使用南左峰值。
- [ ] 线案例190s>180s时必须`guardrail_pass=false`且不得推荐。
- [ ] `all_guardrails_passed`等于全部可推荐候选护栏结果的真实聚合。
- [ ] `problem_confirmed/healthy/completed`满足状态机规则。
- [ ] 两次live重采均有trace日志、PG真源标识和完整证据字段。
- [ ] 点案例有至少一个合规小步释放候选并完成，或返回明确“约束下无可行解”；不得伪造通过。
- [ ] 线案例仅在存在≤180s合规候选时完成并推荐干线联控。

## 七、优先级

| 优先级 | 问题 |
|---|---|
| P0 | 190s超过180s仍通过并推荐；目标转向指标错绑 |
| P1 | 配时基线60/150与164冲突；排队库容方向错配；比例超过100% |
| P1 | 下游事实与策略/方案文案反转 |
| P2 | `problem_confirmed/healthy/completed`状态语义不一致 |

