# BUG-006：下游承接判定误用排队峰值 / 未按进口过滤

## 现象

Case A（坤顺×奥体西 · 北左 → 礼耕）筛选口径下游 slack，live 诊断却 `queue_ratio≈0.86` 判 blocked。

## 根因

1. `_aggregate_metrics` 取 `max(queue_len_max or queue_len_avg)`；
2. `metrics_for_diagnosis` 的 `queue_length_m` 用整路口 `queue_m`，未按接收进口+转向过滤。

## 修复（收窄范围）

- **仅 Case A 目标路口** `011wwe28fty00001`（坤顺×奥体西）的下游富化：按接收进口道方向 + `queue_len_avg` 均值。
- 其他目标路口：保持整路口 `queue_m`（max）原逻辑，不做全局切换。

## 验证

`pytest tests/test_queue_avg_judgment.py -q`
