<script setup lang="ts">
import { THRESHOLDS } from '../../constants'
</script>

<template>
  <div class="metric-legend">
    <span class="legend-title">图例</span>
    <div class="legend-item">
      <span class="swatch high" />
      <span>饱和 ≥ {{ (THRESHOLDS.saturationHigh * 100).toFixed(0) }}%</span>
    </div>
    <div class="legend-item">
      <span class="swatch focus" />
      <span>关注方向</span>
    </div>
    <div class="legend-item">
      <span class="swatch protect" />
      <span>保护方向</span>
    </div>
    <div class="legend-item">
      <span class="swatch evidence" />
      <span>验证证据</span>
    </div>
  </div>
</template>

<style scoped>
.metric-legend {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 14px;
  padding: 8px 12px;
  background: rgba(0, 10, 20, 0.85);
  border-top: 1px solid rgba(0, 212, 240, 0.12);
  font-size: 10px;
  color: rgba(200, 230, 255, 0.55);
}

.legend-title {
  font-weight: 600;
  letter-spacing: 0.5px;
  color: rgba(0, 229, 255, 0.7);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
}

.swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

.swatch.high {
  background: #ff7b7b;
}

.swatch.focus {
  background: #ffc266;
}

.swatch.protect {
  background: #6dffb5;
  border: 1px dashed rgba(255, 255, 255, 0.4);
}

.swatch.evidence {
  background: #9ec5ff;
}
</style>
