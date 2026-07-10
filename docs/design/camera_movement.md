# 地图镜头运镜逻辑

本文档梳理九幕演示中高德地图（AMap）的镜头推进规则，对应实现位于 `frontend/src/map/`。

---

## 一、触发链路

```
store.currentAct 变化
  → AMapProvider watch
    → MapController.applyScene(act.scene, response, { replayCamera: true })
      → moveCamera()（用户未手动干预时）
      → 绘制该幕覆盖物（路口框 / 渠化 / 溯源 / 控制范围 …）

store.response.phases.diagnosis 流式补齐（同一幕）
  → AMapProvider watch
    → applyScene(..., { replayCamera: false })   // 仅补绘，不重放镜头

store.mapResetSeq 变化（重置）
  → clear() + resetToCity() → zoom 11，pitch 20
```

**关键文件**

| 文件 | 职责 |
| --- | --- |
| `composables/useTimeline.ts` | 每幕 `ActMapScene`：`kind` / `pitch` / `zoom` |
| `map/AMapProvider.vue` | 监听 act / diagnosis / reset，调用 `applyScene` |
| `map/MapController.ts` | 运镜编排、覆盖物绘制、用户干预标记 |
| `map/amapUtils.ts` | `flyTo` / `drillToIntersection` / `smoothPullback` / `panToVisualCenter` |
| `map/sceneEvidencePolicy.ts` | 各幕应显示的地图证据层 |

---

## 二、场景类型与 zoom 常量

| 常量 | 值 | 含义 |
| --- | --- | --- |
| `CHANNELIZATION_ZOOM` | 18 | 车道级渠化详情 |
| `ARTERIAL_ZOOM` | 17 | 干线 / 溯源视角 |
| 城市概览 | 11 | act1 默认 |

### 九幕镜头配置（`ACT_DEFS`）

| 幕 | act id | scene.kind | pitch | zoom | 运镜策略 |
| --- | --- | --- | --- | --- | --- |
| 1 诊断对象识别 | act1_ticket | city | 20 | 11 | 飞到济南中心 / 工单坐标 |
| 2 路网对象定位 | act2_locate | intersection | 15 | 16 | 单调下钻至路口级 |
| 3 溢出证据核验 | act3_overflow | lane | 0 | 18 | 单调下钻至渠化级 |
| 4 下游承接能力 | act4_bottleneck | lane | 10 | 18 | 保持 / 续接下钻至 18 |
| 5 上下游流向溯源 | act5_corridor | trace | 50 | 17 | 从 ≈18 **平滑抬升**至 17 |
| 6 成因归因 | act6_cause | lane | 10 | 18 | 单调下钻回渠化级 |
| 7 治理策略 | act7_strategy | control | 45 | 18 | 下钻至控制范围观察级 |
| 8 配时方案 | act8_plan | lane | 20 | 18 | 渠化级 |
| 9 方案确认 | act9_feedback | corridor | 50 | 17 | 平滑抬升至干线级 |

---

## 三、运镜算法

### 1. 单调下钻（`intersection` / `lane` / `control`）

- 使用 `drillToIntersection(map, center, finalZoom)`。
- `drillSteps(current, target)` 生成中间锚点 `[14, 16.2, 17.5]` 中 **严格大于当前 zoom 且小于目标** 的步序，最后落到目标。
- 每步调用 `flyTo`（≈700ms），避免「先缩小再放大」的跳变。
- `clampZoomUp(current, next)` 保证 zoom 只增不减。
- 到位后 `panToVisualCenter`：将路口偏移到屏幕视觉中心（默认 X 偏移 -120px，为左侧栏留空）。

### 2. 平滑抬升（`trace` / `corridor`）

- 使用 `smoothPullback(map, center, zoom, duration)`，单次 `flyTo` 动画。
- 允许相对当前镜头 **受控降低 zoom**（从车道级 ≈18 回到干线级 17）。
- 目标 zoom 不低于 `ARTERIAL_ZOOM`（17）。
- 动画时长：`|current - target| > 1` 时 1000ms，否则 800ms。
- 随后 `panToVisualCenter` 校正构图。

### 3. 城市概览（`city`）

- 单次 `flyTo` 到 `scene.zoom ?? 11`，时长 900ms。
- 无工单坐标时使用济南默认中心 `[117.02, 36.66]`。

### 4. pitch

- 每幕切换时 `map.setPitch(scene.pitch ?? 0)`，在运镜前设置俯仰角。
- 溯源 / 反馈幕 pitch 50°，呈现 3D 干线走廊视角。

---

## 四、用户干预与防闪烁

### 用户手动操作

- 监听 `dragend` / `zoomend`：若非程序触发的 zoom，设置 `userInteracted = true`。
- 一旦用户干预，后续 `applyScene` **跳过重放镜头**（`replayCamera && !userInteracted`），仅更新覆盖物。
- 重置（`mapResetSeq`）时清除 `userInteracted`，回到系统驱动运镜。

### 程序运镜标记

- `withProgrammatic()` 包裹镜头动画，`programmatic` 计数 > 0 时 zoomend 不视为用户操作。

### 流式数据去抖

- `diagnosis` phase 到达时 **不重放镜头**（`replayCamera: false`），避免 SSE 补齐数据导致二次运镜闪烁。
- 换幕时 `clear()` 旧覆盖物再绘制新层；镜头仅在 act 切换且未干预时播放。

---

## 五、调试

- 地图左上角 **zoom 指示器**（`AMapProvider` 内 `data-testid="zoom-indicator"`）实时显示当前 zoom，便于核对各幕目标值。
- 单元测试：`frontend/tests/unit/camera.test.ts`（`drillSteps` / `clampZoomUp` 纯函数）。

---

## 六、相关需求与验收

- 需求：`needs/8-流量溯源前端可视化与镜头连贯.md`
- 计划：`plans/8-流量溯源前端可视化与镜头连贯.md`
- 交互总览：`docs/design/interaction_logic.md` § 地图运镜触发
