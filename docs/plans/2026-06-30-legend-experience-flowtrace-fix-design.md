# 图例删除 / 经验沉淀重构 / 流量溯源重做 — 设计

> 版本：2026-06-30 状态：已确认方向，待实施
> 分支：feat/upstream-governance-trace

## 背景

三项用户反馈（均"完全不符合预期/需求"）：

1. 右下角图例多余 —— 删除。
2. 经验沉淀分类错误 —— 移到右下角，并按"认知画像 / 诊断经验 / 方案诊断经验"三类用大模型重新理解归一。
3. 流量溯源抽象、需手动点击 —— 改为"沿干线逐跳查上游 → 按转向拆分流量 → 地图自动标注"，全自动运镜、无控制条。

## 一、删除右下角图例

- 现状：`ChannelizationStageOverlay.vue` 内 `ChannelizationLegend`（`right:12px; bottom:12px`）。
- 改动：移除该组件引用与 import，删除 `ChannelizationLegend.vue` 及其 spec；不再呈现图例与对应数据。

## 二、经验沉淀重构（三类 + LLM 归一 + 右下角）

### 三类定义（用户口径）

| 类型 | 含义 | 状态 |
|------|------|------|
| 认知画像 cognition | 问题记录：某路口/某方向/某时段拥堵 | 有数据支撑=已验证；无=待验证 |
| 诊断经验 diagnosis | 用户口述、库内无记录的原因（如"附近学校放学"） | 用户提供 |
| 方案诊断经验 solution | 用户治理经验（对向不溢出、绿灯±x 秒、加左转车道） | 用户提供 |

### 后端

- 新增 `ExperienceClassifier`（QwenClient.chat_json）：输入用户原话，输出
  `{cognition:{problem}, diagnosis:[{cause}], solution:[{measure}]}`。
- `_record_problem_experience` 接入：
  - cognition.status = `verified`（数据诊断成立）/ `data_doubt`（坚持但数据不显著=待验证）。
  - diagnosis 逐条写 `source=user`；solution 逐条写 qualitative。
- LLM 不可用时确定性兜底：cognition 由 NLU（路口+方向+时段+"拥堵"）拼装；diagnosis 空；solution 取 user_suggestion。
- SSE `experience_cognition/diagnosis/solution` 透传 status 与文本。

### 前端

- `ExperienceSedimentItem` 增 `status?: 'verified' | 'pending'`。
- `IntersectionNarrativeStack` 经验卡：左下角 → 右下角；标题改"经验沉淀"，三段按类显示，认知画像加"已验证/待验证"徽标。

## 三、流量溯源重做（上游逐跳拆分 + 自动标注）

### 后端

- `UpstreamGovernanceTraceService` 改产出"上游链路标注"而非抽象治理落点树：
  - 从过饱和进口道沿来流方向找上一个上游路口（1 跳为主，仍饱和再上溯，最多 2 跳）。
  - 每个上游路口节点：`{inter_id,name,lng,lat,hop,approach,saturation,turn_split:[{turn,share,to}]}`。
  - storyboard.frames 改为"逐路口运镜帧"：每帧 `{center,zoom,reveal:[node_id],narration}`。

### 前端（MapStage）

- 移除 `UpstreamGovernanceCard` 侧卡 + `UpstreamControlBar` 控制条及相关手动交互。
- 自动播放：逐帧 `panTo/setZoomAndCenter` 平滑运镜到每个上游路口，落地浮动文本标注（路口名 + 饱和度 + 转向拆分），引导线连接，防重叠（按相对方位错位锚点）。
- 用户全程不点击。

## 验收（对照用户例子）

奥体西路 × 经十路、下午晚高峰、南北向拥堵 →
自动从南/北进口沿干线找上一个上游路口，地图运镜逐个聚焦，标注每个上游路口的饱和度与转向拆分占比，无重叠遮挡。
