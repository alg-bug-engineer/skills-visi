# 呈现同步栅栏（语音 · 理解过程 · 经验吸收）

> 版本：2026-06-28  
> 状态：**强制约束** — 新增演示步骤、SSE 子步骤或面板输出时必须遵守  
> 实现入口：`frontend-v2/src/composables/usePresentationBarrier.ts` · `App.vue` · `useVoiceNarration.whenIdle`

---

## 1. 问题背景

演示流由三条**并行**输出组成：

| 流 | 模块 | 典型输出 |
|----|------|----------|
| 理解过程 | `useUnderstandingProcess` | 打字机面板全文 |
| 语音 TTS | `useVoiceNarration` | 关键点摘要（非全文朗读） |
| 经验吸收 | `useExperienceAbsorption` | 吸收面板 trace 行（`status: running`） |

若仅等待理解过程打字结束就推进 `AnalysisQueue` 下一步，会出现：

- 语音还在播，地图/渠化已进入下一阶段；
- 或理解过程还在输出，下一步 SSE 已触发。

---

## 2. 栅栏规则（必须）

**步骤切换前**必须调用 `whenPresentationSettled()`，同时等待：

1. `whenProcessIdle()` — 理解过程队列空且当前无打字；
2. `voice.whenIdle()` — TTS 队列空且不在播放（语音关闭时跳过）；
3. 吸收面板无 `status === 'running'` 的行（吸收未激活时跳过）。

三者 **全部** 完成后，才允许：

- `AnalysisQueue` 进入下一个 task；
- `pushMapAction` 触发下一阶段地图/渠化；
- 诊断收尾、`revealSkillStep` 等 UI 推进。

### 2.1 禁止写法

```typescript
// ❌ 只等理解过程
await whenProcessIdle()
pushMapAction(action)

// ❌ 不等待任何呈现流
handleNarration(action)
pushMapAction(action)
```

### 2.2 正确写法

```typescript
handleNarration(action)
applySceneHighlight(action)
enqueueSceneVoice(action)
await whenPresentationSettled()
pushMapAction(action)
```

---

## 3. 语音文案原则

- **面板**：可展示完整 SSE / 后端 narrative 文本。
- **TTS**：只播关键点，由 `voiceTextSummarize.summarizeNarrationForVoice` 或 `voiceCueExtractors` 模板生成，**禁止**把理解过程全文入队。
- 固定步骤引导语维护在 `frontend-v2/src/config/voice_narration.json`；修改后须跑 `voiceStepSync.spec.ts`。

---

## 4. 地图 + 渠化融合（R2）与标注分层

- 渠化全屏时 **不得** `visibility: hidden` 隐藏底图；底图仅作道路背景。
- 渠化模式下地图 **pan 偏移为 0**（`setCenter`，不用 `panToVisualCenter(-120)`），避免左侧黑条。
- **标注分层（强制）**：
  - **AMap 底图**：仅 tile + 道路；干线扫描（`corridor_scan`）阶段可保留地理 pin/polyline。
  - **进入渠化后**（`channelizationLocked`）：禁止在 AMap 上绘制 Marker/Polyline；语义标注走 `channelizationLayer.applyArmSceneLabels`（3D 路臂标签）与 `ChannelizationStageOverlay` DOM（HUD、证据卡、图例）。
  - 转换逻辑：`utils/channelArmLabels.buildArmLabelsFromScene`。
- 修改标注时勿回退为「底图 HTML Marker 叠加」。

---

## 5. 新增步骤时的检查清单

- [ ] SSE / `map_scene` 任务末尾是否 `await whenPresentationSettled()`？
- [ ] 若新增 TTS，是否走 extractors / summarize，而非直接 `action.text`？
- [ ] 若新增吸收 trace 行，是否在 `stage_done` 前保持 `running`？
- [ ] 是否更新 `REGRESSION_TEST_SPEC.md` 对应用例？

---

## 6. 相关测试

| 文件 | 覆盖 |
|------|------|
| `usePresentationBarrier.spec.ts` | 栅栏等待 process + voice |
| `voiceTextSummarize.spec.ts` | 旁白摘要 |
| `voiceCueExtractors.spec.ts` | 各 phase TTS 模板 |
| `voiceStepSync.spec.ts` | 步骤引导语与 config 一致 |

合并前：`bash scripts/regression.sh` 全绿。

---

## 7. 经验吸收 / 技能固化流水线（2026-06-28 增补）

与地图 `map_scene` 不同，吸收 / 固化含 **SSE 流式 delta**，禁止把每个 delta 塞进 `AnalysisQueue` 并在 start 事件上 `whenSettled`。

### 7.1 规则

| 事件 | 处理方式 |
|------|----------|
| `thought_delta` / `evidence` / `file_delta` 等 | **同步 apply**（SSE 顺序即呈现顺序） |
| `stage_done`（吸收） | apply 后 enqueue pause gate → `whenPresentationSettled()` |
| `stage_done` / `file_done`（固化） | apply 后 enqueue pause gate → `whenProcessAndVoiceSettled()` |
| 暂停态 | 事件进 buffer；恢复后 `rAF` 逐帧回放流式项 |

### 7.2 禁止写法

```typescript
// ❌ stage_start 后 whenSettled — 吸收 running 行永不 idle，死锁
analysisQueue.enqueue(async () => {
  apply({ type: 'stage_start' })
  await whenPresentationSettled()
})

// ❌ 全部 SSE 进队列 + start 上 settle — delta 堆积，打字机失效
analysisQueue.enqueue(async () => {
  apply({ type: 'thought_delta' })
})
```

### 7.3 实现入口

- `frontend-v2/src/utils/skillPresentationDispatch.ts`
- `App.vue` · `dispatchSkillAbsorptionEvent` / `dispatchSkillBuildEvent`
- 详见 [2026-06-28-经验吸收技能固化空格暂停与呈现修复-复盘.md](./plans/2026-06-28-经验吸收技能固化空格暂停与呈现修复-复盘.md)

### 7.4 相关测试

| 文件 | 覆盖 |
|------|------|
| `skillPresentationDispatch.spec.ts` | RT-PAUSE-ABS |
| `usePresentationBarrier.spec.ts` | `whenProcessAndVoiceSettled` |
