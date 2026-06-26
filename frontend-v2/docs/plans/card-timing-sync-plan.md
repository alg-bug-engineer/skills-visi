# 卡片时机与地图动作同步 — 开发计划

## 目标

1. 推理过程与地图/侧栏卡片**同拍出现**，避免「先缺失、后出现数值」。
2. 获取数据阶段：配时适配性 → 地图 HUD/配时小窗；干线协调 → 干线小窗；转向问题 → 渠化箭头强调。
3. 运行数据单卡承载饱和度/延误；推理证据卡**不再重复**同类指标。
4. 渠化底部固定展示东/南/西/北进口排队与饱和度。
5. 「流量-配时匹配 · 四维诊断」仅在**规则诊断**步骤揭示。

## 任务

| ID | 内容 | 文件 |
|----|------|------|
| T1 | `runtimeMetrics` 缓冲 + `buildHighlightEvidence` 多源回退，无数据不显示「数据缺失」 | `usePresentation.ts`, `cognitionChannelAdapter.ts`, `ChannelizationCanvas3D.vue` |
| T2 | 四向饱和度多源合并（metrics_by_arm / direction_groups / evidence） | `cognitionChannelAdapter.ts`, `ChannelizationMetricStrip.vue` |
| T3 | 配时/干线小窗移入 MapStage，z-index 高于渠化全屏 | `MapStage.vue`, `WorkbenchLayout.vue` |
| T4 | `granularity` map_scene + `highlight_turn` 转向高亮 | `map_presentation_service.py`, `channelizationLayer.js`, types |
| T5 | 侧栏证据卡去重；timing/corridor 仅地图展示 | `EvidenceStackCard.vue`, `usePresentation.ts` |
| T6 | data_fetch 预载 timing/corridor 并联动 `setPhase` 小窗 | `App.vue`, `usePresentation.ts` |

## 验收

- [ ] 饱和度阶段不再闪现「数据缺失」后又有数值
- [ ] 底部四进口均显示饱和度（有数据时）
- [ ] timing 叙述时地图可见配时 HUD/环图；corridor 叙述时可见干线小窗
- [ ] granularity 提到西左转时对应车道箭头高亮
- [ ] 推理证据卡无饱和度/延误/分向列表重复
- [ ] 四维诊断卡仅在规则诊断步骤出现
