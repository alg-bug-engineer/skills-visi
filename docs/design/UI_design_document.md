# 交通智能体演示系统 - 前端 UI 界面设计规范 (优化版)

本设计规范详细描述了演示系统的前端界面布局、高德地图 (AMap) 可视化规范、三栏交互机制，以实现极佳的演示视觉冲击力 (WOW 效果) 并确保满足交通专家决策的可信度。

---

## 一、 视觉令牌与三栏布局规范 (Visual Tokens & Layout)

系统完全对接 `frontend-v2` 的三栏工作台架构，统一使用基于深色信控主题的设计令牌。

### 1. 设计令牌 (Design Tokens)

| 令牌类别 | 十六进制 (Hex) | 业务隐喻 / UI 应用场景 |
| :--- | :--- | :--- |
| **主打品牌色 (Primary)** | `#00e5ff` / `#00d4f0` | 智慧极光青。用于路径高亮、默认激活态、按钮、进行中的步骤 |
| **警示/溢流 (Alarm)** | `#ff7b7b` / `#ff5050` | 溢流霓红。用于排队溢出（排队比 ≥ 1.0）、严重拥堵、不推荐的激进策略 |
| **证据/关注 (Evidence)** | `#ffc266` / `#f5a623` | 警戒琥珀。用于上游来车溯源、问题验证证据指标高亮、中度负荷 |
| **保护/约束 (Protected)**| `#6dffb5` / `#10B981` | 协调绿。用于下游保护路段、通过安全校验的相位、绿波带、接受按钮 |
| **系统背景 (Background)**| `#020810` / `#0B0F19` | 极暗夜幕。全局底色、地图暗色图层底色 |
| **卡片面板 (Panel-BG)**  | `rgba(0, 8, 16, 0.92)` | 磨砂石板。侧边栏背景（带 `backdrop-filter: blur(12px)`） |

### 2. 布局断点与三栏栅格 (Layout Grid)

大屏分辨率基于 `1920 x 1080`，界面采用**三栏栅格系统**：

```
┌─────────────────────────────────┬──────────────────┬──────────────────┐
│                                 │                  │                  │
│       GIS 主战场 (AMap)          │ 推理证据栏        │ 理解过程栏        │
│       · 拓扑一跳与粒子流发光干线  │ (Insight Panel)  │ (Process Panel)  │
│       · 渠化小窗 / 运行数据 HUD  │                  │                  │
│       · 1fr (全屏背景)          │ 宽度: ~300px     │ 宽度: ~340px     │
│                                 │                  │                  │
└─────────────────────────────────┴──────────────────┴──────────────────┘
```

- **宽屏模式 (>1100px)**：三栏并行。
  - **GIS 舞台栏**：`1fr` 全屏底图。
  - **推理证据栏 (Insight Stack)**：居中左偏或紧贴理解过程左侧，宽度占 `300px`。
  - **理解过程栏 (Process Panel)**：位于最右侧，宽度占 `340px`。
- **窄屏模式 (≤1100px)**：右侧理解过程面板固定为右浮层；推理证据栏固定为左侧浮层，支持手动滑动收起。
- **全图模式 (Collapse FAB)**：点击右下角 `FAB`（悬浮按钮），一键收起左右两侧面板，地图（GIS 舞台）满屏无遮挡展示。

---

## 二、 高德地图 (AMap) 可视化设计规范 (AMap Viz Spec)

地图是整个演示系统的“主战场”，利用高德地图 JS API 进行多层覆盖物叠加与粒子流动动画渲染。

### 1. 路口边界与进口道高亮 (Polygon & Link Highlights)
- **路口包围框**：使用 `AMap.Polygon` 在目标路口四周绘制 dashed 虚线边界框，线宽 `2px`，线色 `#ff5050`（溢流红）。当检测到溢流状态时，填充背景 `rgba(255, 80, 80, 0.08)`，并在中央上方弹出呼吸警示气泡。
- **进口道线描边**：拉取路口对应的 `links` 路径数据（三维折线坐标数组），使用 `AMap.Polyline` 绘制基础路段线。
  - **常规进口道**：线宽 `4px`，灰色 `#475569`。
  - **目标关注进口道**：线宽 `6px`，亮色青 `#00e5ff`。
  - **保护/约束进口道**：线宽 `6px`，发光绿 `#6dffb5`。

### 2. 流量溯源粒子流动动画 (Particle Flow Spec)
当系统进入第五幕“干线协调”与“流量溯源”阶段，地图全面切换为**溯源动画层**，隐藏其他静态诊断遮罩，仅保留单链路发光干线与粒子动画：
- **流动粒子设计**：沿 `links` 折线几何使用 `AMap.Marker` 渲染粒子（Marker 内容为 `<div class="us-particle"></div>`），粒子颜色由流量流向属性定义。
- **来向溯源 (UPSTREAM - 琥珀色暖色带)**：
  - **干线发光**：使用双层 Polyline 绘制，外层 Polyline 使用琥珀色 `#f5a623`，线宽 `18px`，透明度 `0.2` 作为发光底带；内层 Polyline 亮核线使用 `#ffcf7a`，线宽 `6px`，透明度 `0.95`，带箭头（`showDir: true`）。
  - **流动粒子**：琥珀色光点粒子沿上游路口向目标路口流动，利用 `requestAnimationFrame` (rAF) 沿折线进行线性插值，粒子流动速度与来向流量（VPH）正相关。
- **去向溯源 (DOWNSTREAM - 青蓝色冷色带)**：
  - **干线发光**：外层发光带使用天蓝色 `#0ea5e9`，透明度 `0.2`；内层核心亮线使用天蓝色 `#38bdf8`，透明度 `0.95`。
  - **流动粒子**：天蓝色粒子流从目标路口出发驶向游各个去向相邻节点。
- **节点脉冲与占比标签**：
  - 各来向/去向的一跳相邻路口中心绘制带呼吸发光波纹的 `AMap.Marker`。
  - 标记显示途经占比标签（如 `西进口 ➔ 北出口 直行占比: 42%`）。如果是严重瓶颈路口，Marker 带红色 `[饱和瓶颈]` 发光字样，点击可交互弹出小气泡展示具体排队指标。

### 3. 微观渠化小窗与配时环图 (Micro Overlay UI)
- **右下角渠化小窗 (Channelization Mini Window)**：
  - 常驻右下角（避开输入框）。读取 `arms` 属性，可视化当前路口的车道布局（如左转、直行、右转车道箭头指示），并为每条车道上色以呈现饱和状态（健康为绿、中度为橙、饱和为红）。
- **运行数据卡片下侧配时环图 (Timing Ring Window)**：
  - 当流水线走到“运行配时”时，在左侧面板下方滑出环图小窗。利用 Canvas/SVG 绘制双环/三环配时图，显示当前路口的信号相位周期及执行秒数。

---

## 三、 逐幕界面详细设计规范 (对齐剧本叙事与后端接口)

根据 `references/frontend-v2` 提出的“**缓冲数据，按时序揭示**”原则，左侧推理证据卡片由右侧理解步骤的打字打完事件驱动，不抢跑展示。每一幕的元素布局、文本与后端接口路径绑定定义如下：

### 第一幕：接到问题，先整理成诊断工单 (NLU & Ticket Generation)
- **【剧本叙事逻辑】**：用户输入自然语言问题，系统解析并结构化输出诊断工单。
- **【右侧理解栏 (Process Panel)】**：
  - **步骤状态**：步骤 0 “理解问题”激活，打印机动画输出实体解析的文字日志（从 `user_input` 识别目标、时间、转向、约束）。
  - **后端接口路径**：`POST /api/v1/agent/run` 请求中的 `user_input` 参数。
- **【左侧推理证据栏 (Insight Panel)】**：
  - **展示卡片**：**诊断任务工单卡 (DiagnosisTicketCard)**。
  - **数据渲染与接口字段**：
    - 目标路口名称 ➔ `diagnosis_ticket.intersection_name`
    - 时段与时间范围 ➔ `diagnosis_ticket.period` / `diagnosis_ticket.time_range`
    - 关注方向与转向 ➔ `diagnosis_ticket.direction` / `diagnosis_ticket.movement`
    - 问题诊断类型 ➔ `diagnosis_ticket.problem_type` (高亮显示 `排队溢出`)
    - 约束条件列表 ➔ `diagnosis_ticket.constraints` (显示 `优先避免下游继续外溢`)
    - 解析置信度 ➔ `diagnosis_ticket.match_confidence`
- **【高德地图 (AMap) 状态】**：
  - **视点**：济南城市全域微弱发光网格底图。
- **【底部状态控制栏】**：
  - **状态**：输入框下沉至左侧。状态条亮青色显示“正在解析口头描述，提取实体中...”，右侧显示 `completed=false`。

---

### 第二幕：把一句话落到真实路网 (Corridor Grid Positioning)
- **【剧本叙事逻辑】**：地图飞向并定位目标路口，展示拓扑链路识别步骤。
- **【右侧理解栏 (Process Panel)】**：
  - **步骤状态**：步骤 1 “空间定位”激活，逐行亮起打勾 checklist，展示五步识别步骤。
  - **数据渲染与接口字段**：步骤文本列表 ➔ `phases.intent.spatial_scene.recognition_steps[]`，状态为 `success` 时展示绿色打勾图标。
- **【左侧推理证据栏 (Insight Panel)】**：
  - 继承第一幕工单卡，锁定于左侧。
- **【高德地图 (AMap) 状态】**：
  - **视点**：镜头平滑 FlyTo 缩放聚焦至 `diagnosis_ticket` 指示的经纬度 `(lng, lat)`。
  - **覆盖物渲染**：
    - 目标路口 ➔ 绘制 `AMap.Polygon` 虚线框。
    - 目标进口道与直行连线 ➔ `phases.intent.spatial_scene.highlight_path` 折线发光显示。
    - 标记上下游节点 ➔ `phases.intent.spatial_scene.upstream_nodes[]` 与 `downstream_nodes[]` 位置渲染小型发光点。
- **【底部状态控制栏】**：
  - 显示：“已锁定地理空间拓扑结构，加载运行历史指标中...”。

---

### 第三幕：先验证溢出是否成立 (Overflow Verification)
- **【剧本叙事逻辑】**：加载实时数据，计算排队比、绿灯利用率等核心指标，确证溢出是否成立。
- **【右侧理解栏 (Process Panel)】**：
  - **步骤状态**：步骤 2 “指标加载”打字中，输出关键判定阈值逻辑（`排队比 > 1.0` 即为溢流）。
- **【左侧推理证据栏 (Insight Panel)】**：
  - **展示卡片**：打字结束后滑入**“运行数据单卡 (DataMetricsCard)”**。
  - **数据渲染与接口字段**：
    - 排队比 ➔ `phases.diagnosis.metrics.queue_ratio`（大字红色显示 `1.08`）
    - 排队长度 / 蓄车长度 ➔ `queue_length_m` / `storage_length_m`
    - 饱和度 / 平均延误 ➔ `saturation` (94%) / `avg_delay_s`
    - 绿灯利用率 ➔ `green_utilization` (42% 黄色低利用预警)
    - 时序排队比折线图 ➔ 根据 `time_series_trend` 绘制折线。
- **【高德地图 (AMap) 状态】**：
  - **视点**：切换为路口微观车道级视角。
  - **覆盖物渲染**：目标进口道（东向西直行）标红闪烁，并在尾部叠加红色溢流警示 Marker（`kind: 'evidence'`）。
  - **右下浮窗**：自动弹出渠化小窗，东直行车道以红色高饱和高亮。
- **【底部状态控制栏】**：
  - 中央浮现诊断玻璃态判定卡片：`phases.diagnosis.overflow_verification.message`。

---

### 第四幕：区分“本路口放不出去”还是“下游接不住” (Bottleneck Diagnosis)
- **【剧本叙事逻辑】**：分析瓶颈类型，通过多维度判据验证下游承接状况。
- **【右侧理解栏 (Process Panel)】**：
  - **步骤状态**：步骤 3 “成因诊断”激活，打印本路口与下游瓶颈判定问答。
  - **数据渲染与接口字段**：打印文本 ➔ `phases.diagnosis.downstream_diagnosis.narrative`。
- **【左侧推理证据栏 (Insight Panel)】**：
  - **展示卡片**：揭示**“问题验证证据卡 (EvidenceStackCard)”**。
  - **数据渲染与接口字段**：
    - 核心诊断结论 ➔ `phases.diagnosis.downstream_diagnosis.release_answer` (突出 `下游承接不足`)。
    - 判断依据明细 ➔ `phases.diagnosis.downstream_diagnosis.judgment_criteria[]` (以清单形式罗列各转向与路段数据)。
- **【高德地图 (AMap) 状态】**：
  - **视点**：视点向东向西下游平移，锁定下游相邻路口。
  - **覆盖物渲染**：下游出口道连线高亮，下游相邻节点叠加红色拥堵 Marker。
- **&【底部状态控制栏】**：
  - 状态显示：“当前瓶颈类型：下游溢流传导受阻，禁止单点加绿”。

---

### 第五幕：把问题拉到干线，看上游来车是否需要干预 (Corridor Tracing)
- **【剧本叙事逻辑】**：将视角扩大至干线，渲染流量来向去向占比，研判定时截流。
- **【右侧理解栏 (Process Panel)】**：
  - **步骤状态**：步骤 4 “流量溯源”激活，打印来车溯源与干线拥堵传播计算。
  - **数据渲染与接口字段**：干线计算文本 ➔ `phases.diagnosis.arterial_analysis.summary`。
- **【左侧推理证据栏 (Insight Panel)】**：
  - 在运行数据卡下侧滑出展示**“干线流量溯源卡 (CorridorScanSidebar)”**。
  - **数据渲染与接口字段**：
    - 上游到达 / 放行强度 ➔ `upstream_arrival_flow_vph` / `upstream_release_intensity_vph`
    - 目标进口剩余空间 / 下游容量 ➔ `target_remaining_storage_m` / `downstream_remaining_capacity`
    - 控流建议 ➔ `need_upstream_metering` (显示 `上游截流: 建议执行`)
- **【高德地图 (AMap) 状态】**：
  - **视点**：地图视角拉远至干线俯仰三维视角。
  - **覆盖物渲染**：彻底隐藏第四幕前所有静态遮罩，切换为**流向发光粒子层 (Trace Layer)**：
    - 上游来车 (UPSTREAM) ➔ 渲染琥珀色发光底线（`#f5a623`）与琥珀色流动粒子，流向目标路口。
    - 游路口中心 ➔ 挂载可点击的脉冲 Marker，点击展开气泡标签，展示途经占比（`phases.diagnosis.flow_trace.entry_traces[].share_pct`）。
    - 下游去向 (DOWNSTREAM) ➔ 渲染青蓝色发光底线（`#0ea5e9`）与天蓝色流动粒子。
- **【底部状态控制栏】**：
  - 状态显示：“已开启干线流量追踪，捕获上游倾泻流量中...”。

---

### 第六幕：形成成因判断，并引入相似案例增强可信度 (Cases Alignment)
- **【剧本叙事逻辑】**：确立主次成因，拉取相似失败/成功案例卡片供专家研判。
- **【右侧理解栏 (Process Panel)】**：
  - **步骤状态**：步骤 5 “相似检索”激活，输出案例相似度比对日志。
- **【左侧推理证据栏 (Insight Panel)】**：
  - **展示卡片**：滑入**“相似案例卡 (CaseLibraryPanel)”**，以 Carousel 横向滑动形式展示案例 A (失败) 与案例 B (成功)。
  - **数据渲染与接口字段**：
    - 案例卡片数组 ➔ `phases.cause.case_cards.cards[]` (包含 `title`, `similarity`, `action`, `outcome`, `lesson`)。
    - 主次成因权重图 ➔ 根据 `primary_cause` 与 `secondary_causes` 进行图表绘制。
- **【高德地图 (AMap) 状态】**：
  - 保持干线发光模式。
- **【底部状态控制栏】**：
  - 状态显示：“案例检索完成，匹配 2 个强相关历史处置记录”。

---

### 第七幕：生成治理策略，从“单点加绿”升级为“干线联控” (Strategy Setup)
- **【剧本叙事逻辑】**：结合实时与案例，生成治理策略原则与控制边界。
- **【右侧理解栏 (Process Panel)】**：
  - **步骤状态**：步骤 6 “策略推荐”激活，打印协同放行、分段控流策略文案。
- **【左侧推理证据栏 (Insight Panel)】**：
  - **展示卡片**：滑入显示**“治理边界卡 (ConstraintStackCard)”**。
  - **数据渲染与接口字段**：
    - 策略原则列表 ➔ `phases.strategy.strategy.principles` (高亮显示 `防溢流优先`、`下游保护`)。
    - 不推荐/禁用策略 ➔ `phases.strategy.strategy.not_recommended` (红色框线显示 `禁用单点激进加绿`)。
- **【高德地图 (AMap) 状态】**：
  - **覆盖物渲染**：地图转换为控制范围图层，目标路口浮现“小步释放”Marker，上游路口覆盖红色发光“控流闸口”Marker，下游保护节点覆盖绿色“盾牌”防护 Marker (数据源 ➔ `phases.strategy.control_scope_map`)。
- **【底部状态控制栏】**：
  - 状态显示：“策略包 `downstream_protection` 生成完毕，准备计算配时秒数”。

---

### 第八幕：信控方案比选与生成 (Plan Generation & Comparison)
- **【剧本叙事逻辑】**：从底部向上弹出抽屉，微观显示推荐方案的阶段秒数与车道供需，宏观比选多套候选方案的供需表及协调范围图。
- **【右侧理解栏 (Process Panel)】**：
  - **步骤状态**：步骤 7 “方案决策”激活，提示进行人工确认或微调。
- **【底部抽屉控制台 (PlanDiffDrawer)】**：
  - **展示卡片**：从底部向上弹出抽屉式面板，左侧维持第七幕“治理边界卡”无遮挡。
  - **数据渲染与接口字段**：
    - **Tab 1: 阶段方案生成** (数据源 ➔ `plan.recommended`)：
      - 相位卡片秒数及流向箭头 ➔ `timing.phase_stage_timing_list[]`
      - 供需强度柱状图 ➔ 各方向的供给强度 `supply_intensity` 与需求强度 `demand_intensity`
      - 周期与总绿灯 ➔ `cycle_s` 与 `post_green_time_s`
    - **Tab 2: 多方案比选** (数据源 ➔ `plan.candidates[]`，数量动态不固定，支持横向滚动)：
      - 候选卡指标 ➔ 通行效率、延误降低、溢出风险
      - 预测供需比矩阵表 ➔ `vc_predictions` (以 HSL 渐变色条渲染，极佳指标加挂绿色 `“优”` 状态标签)
      - 干线链路图 ➔ `corridor_nodes` (绿色 `━━` 代表目标，红色 `━━` 代表堵塞)
- **【高德地图 (AMap) 状态】**：
  - **视点**：与抽屉 Tab 键联动。
    - 处于 `stage_generation` 时：FlyTo 聚焦单路口车道级，以蓝/绿/橙色箭头标注其行驶流向。
    - 处于 `plan_comparison` 时：视角拉远聚焦干网，以发光光圈标记协调节点，以绿波模拟粒子流渲染干网。

---

### 第九幕：专家反馈与案例沉淀 (Feedback & Knowledge Loop)
- **【剧本叙事逻辑】**：专家提交接受或拒绝决策，接受方案则沉淀并下发，拒绝则支持微调并重跑。
- **【右侧理解栏 (Process Panel)】**：
  - 状态展示：“等待方案下发确认”。
- **【底部抽屉控制台 (PlanDiffDrawer)】**：
  - 展现绿色的 **“接受方案并下发”** 与红色的 **“拒绝方案”** 按钮。
  - 拒绝方案点击后展开“修改意见文本域”，并可选重启阶段（成因/策略/方案），点击调用重跑 API ➔ `POST /api/v1/agent/plan/regenerate`。
  - 勾选 `沉淀为推荐案例` 或 `风险规避案例` ➔ 随 `decision` 下发至 `POST /api/v1/agent/plan/decision`。
- **【高德地图 (AMap) 状态】**：
  - 下发后，地图上干线绿波带的流光强度与粒子速度双重增强，浮现“方案执行中”发光水印。
- **【底部状态控制栏】**：
  - 连接灯变绿，显示 `completed=true`，分析流程结束，耗时归档。
