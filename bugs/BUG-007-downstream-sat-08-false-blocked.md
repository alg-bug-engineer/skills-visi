# BUG-007：下游 sat=0.8 误判「接不住」导致与库容余量矛盾

## 现象

Case A 下游礼耕：排队比≈0.04、剩余≈131m、`capacity.blocked=false`，面板显示「有承接余量」；但结论仍为「下游承接不足」，策略走防溢流减绿。

## 根因

- `assess_downstream_capacity`：`sat>=0.85` 才 blocked
- `build_downstream_diagnosis` / `classify_release_bottleneck`：`downstream_saturation_high=0.8`，sat=0.80 即视为 blocked
- 前端 `downstreamConclusion` 见 `downstream_near_saturation` 即输出「承接不足」

## 修复

1. `THRESHOLDS["downstream_saturation_high"]` 改为 **0.85**，与 capacity 一致
2. `build_downstream_diagnosis` 的 `downstream_blocked` **以 `capacity.blocked` 为准**（有 capacity 时不再用 0.8 旁路 OR）
3. 单测锁定 sat=0.80 + 低排队 → 可加绿；重采 Case A live
