<script setup lang="ts">
import type { CorridorContext } from '../../types/evidence'

defineProps<{
  context: CorridorContext
}>()
</script>

<template>
  <article class="stack-card corridor-card">
    <header class="card-head">
      <div>
        <span class="eyebrow">干线上下文</span>
        <h3>协调与绿波</h3>
      </div>
      <span v-if="context.in_corridor" class="badge">协调路口</span>
    </header>

    <p v-if="context.narrative" class="narrative">{{ context.narrative }}</p>

    <div v-if="context.line_metrics?.length" class="lines">
      <div v-for="line in context.line_metrics" :key="line.line_name" class="line">
        <span class="name">{{ line.line_name }}</span>
        <span class="vals">
          延时 {{ line.delay_index?.toFixed(2) ?? '—' }}
          · {{ line.travel_speed_kmh?.toFixed(0) ?? '—' }} km/h
          · {{ line.total_stop_times?.toFixed(1) ?? '—' }} 停
        </span>
      </div>
    </div>

    <p v-if="context.green_wave_break_risk" class="risk">
      协调方向停车偏高，单点加绿灯可能恶化绿波，宜从走廊视角优化。
    </p>
  </article>
</template>

<style scoped>
.stack-card {
  border-radius: 4px;
  padding: 12px 14px;
  background: rgba(0, 12, 26, 0.96);
  color: rgba(226, 246, 255, 0.92);
}

.corridor-card {
  border: 1px solid rgba(52, 211, 153, 0.35);
  border-left: 3px solid #34d399;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.eyebrow {
  display: block;
  font-size: 9px;
  letter-spacing: 1px;
  color: #6ee7b7;
}

.card-head h3 {
  margin: 2px 0 0;
  font-size: 13px;
  font-weight: 600;
}

.badge {
  font-size: 9px;
  padding: 2px 6px;
  border: 1px solid rgba(52, 211, 153, 0.4);
  color: #6ee7b7;
  border-radius: 2px;
}

.narrative {
  margin: 8px 0 0;
  font-size: 11px;
  line-height: 1.55;
}

.lines {
  margin-top: 10px;
}

.line {
  padding: 6px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  font-size: 10px;
}

.name {
  display: block;
  color: rgba(200, 230, 255, 0.7);
  margin-bottom: 2px;
}

.vals {
  font-family: 'Courier New', monospace;
  color: #6ee7b7;
}

.risk {
  margin: 10px 0 0;
  padding: 6px 8px;
  font-size: 10px;
  color: #ffc266;
  background: rgba(255, 194, 102, 0.08);
  border: 1px solid rgba(255, 194, 102, 0.25);
}
</style>
