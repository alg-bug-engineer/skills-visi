# BUG-008：目标转向指标被进口/路口 MAX 覆盖

- **状态**：已修复
- **发现日期**：2026-07-13
- **关联需求**：`needs/34-live指标绑定与配时护栏一致性修复.md`（E1/E2/E6）

## 现象

点案例 ticket 为北左，但 `diagnosis.metrics.saturation` 取北直 1.5446；排队库容用东进口 195.68m。

## 根因

1. `metrics_for_diagnosis` 在 movement 匹配失败时回落到 intersection `saturation_max`。
2. `_row_dir8` 未识别 `dir8_code` / 中文标签，导致 detail 行匹配失败。
3. `storage_m` 取峰值排队进口间距，而非 ticket 进口。

## 修复

- movement 绑定强制；禁止单条映射兜底与路口 MAX 覆盖。
- 库容按 `dir8` 匹配 `adjacent_inter_spacing_detail`。
- 输出 `target_movement_key` / `metric_scope=movement` / `storage_direction`。
