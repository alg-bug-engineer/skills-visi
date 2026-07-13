# 计划 32：下游承接判定与 capacity 对齐

对应 `bugs/BUG-007-downstream-sat-08-false-blocked.md`。

## 改动

1. `app/metrics/traffic.py`：`downstream_saturation_high` 0.8 → 0.85
2. `app/trace/downstream_diagnosis.py`：优先 `primary.capacity.blocked`
3. 更新/新增单测；Case A `--live` 重采验证
