<script setup lang="ts">
import type { ProblemEvidence } from '../../types/evidence'
import { formatPercent, formatSaturation } from '../../utils/evidencePresentation'
import { THRESHOLDS } from '../../constants'

defineProps<{
  evidence: ProblemEvidence
}>()
</script>

<template>
  <article class="stack-card gran-card">
    <header class="card-head">
      <div>
        <span class="eyebrow">多粒度画像</span>
        <h3>进口 · 转向 · 车道</h3>
      </div>
    </header>

    <section v-if="evidence.by_turn?.length" class="block">
      <h4>转向级（饱和度 Top）</h4>
      <ul class="rows">
        <li v-for="row in evidence.by_turn.slice(0, 5)" :key="row.label">
          <span>{{ row.label }}</span>
          <span
            class="val"
            :class="{ high: (row.turn_saturation ?? 0) >= THRESHOLDS.saturationHigh }"
          >
            {{ formatSaturation(row.turn_saturation) }}
            <em v-if="row.green_utilization != null">
              · 绿利用 {{ formatPercent(row.green_utilization) }}
            </em>
          </span>
        </li>
      </ul>
    </section>

    <section v-if="evidence.by_approach?.length" class="block">
      <h4>进口级（延误 Top）</h4>
      <ul class="rows">
        <li v-for="row in evidence.by_approach.slice(0, 4)" :key="row.dir8_label">
          <span>{{ row.dir8_label }}</span>
          <span class="val">
            {{ row.stop_time_sec?.toFixed(0) ?? '—' }}s
            <em v-if="row.stop_times != null">· {{ row.stop_times.toFixed(1) }} 停</em>
          </span>
        </li>
      </ul>
    </section>
  </article>
</template>

<style scoped>
.stack-card {
  border-radius: 4px;
  padding: 12px 14px;
  background: rgba(0, 12, 26, 0.96);
  color: rgba(226, 246, 255, 0.92);
}

.gran-card {
  border: 1px solid rgba(56, 189, 248, 0.35);
  border-left: 3px solid #38bdf8;
}

.eyebrow {
  display: block;
  font-size: 9px;
  letter-spacing: 1px;
  color: #7dd3fc;
}

.card-head h3 {
  margin: 2px 0 0;
  font-size: 13px;
  font-weight: 600;
}

.block {
  margin-top: 10px;
}

.block h4 {
  margin: 0 0 6px;
  font-size: 10px;
  font-weight: 600;
  color: rgba(200, 230, 255, 0.55);
  letter-spacing: 0.5px;
}

.rows {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 11px;
}

.rows li {
  display: flex;
  justify-content: space-between;
  padding: 5px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.val {
  font-family: 'Courier New', monospace;
  color: #00e5ff;
}

.val.high {
  color: #ff7b7b;
}

.val em {
  font-style: normal;
  font-size: 10px;
  color: rgba(200, 230, 255, 0.55);
}
</style>
