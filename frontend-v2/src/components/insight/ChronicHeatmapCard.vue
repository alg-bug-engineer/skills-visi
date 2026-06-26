<script setup lang="ts">
import { computed } from 'vue'
import type { ProblemEvidence } from '../../types/evidence'

const props = defineProps<{
  evidence: ProblemEvidence
}>()

const chronic = computed(() => props.evidence.chronic)
const windowDays = computed(() => chronic.value?.window_days ?? 7)
const dates = computed(() => chronic.value?.congested_dates ?? [])

const hasData = computed(() => {
  const c = chronic.value
  if (!c?.is_chronic) return false
  return (c.congested_days ?? 0) > 0 || dates.value.length > 0
})

/** 有真实日期列表时按日期高亮，否则按 congested_days 数量展示 */
const cells = computed(() => {
  const set = new Set(dates.value)
  const count = chronic.value?.congested_days ?? 0
  if (set.size) {
    return Array.from({ length: windowDays.value }, (_, i) => ({
      label: `D${i + 1}`,
      hit: set.size > i,
    }))
  }
  return Array.from({ length: windowDays.value }, (_, i) => ({
    label: `D${i + 1}`,
    hit: i < count,
  }))
})
</script>

<template>
  <article v-if="hasData" class="stack-card chronic-card">
    <header class="card-head">
      <div>
        <span class="eyebrow">常发日历</span>
        <h3>近 {{ windowDays }} 日拥堵分布</h3>
      </div>
      <span class="badge">{{ chronic?.congested_days }}/{{ windowDays }}</span>
    </header>

    <div class="heatmap">
      <div
        v-for="cell in cells"
        :key="cell.label"
        class="cell"
        :class="{ hit: cell.hit }"
        :title="cell.hit ? '拥堵日' : '正常'"
      />
    </div>

    <p v-if="dates.length" class="legend dates">{{ dates.join(' · ') }}</p>
  </article>
</template>

<style scoped>
.stack-card {
  border-radius: 4px;
  padding: 8px 10px;
  background: rgba(0, 12, 26, 0.96);
  color: rgba(226, 246, 255, 0.92);
}

.chronic-card {
  border: 1px solid rgba(255, 138, 101, 0.35);
  border-left: 2px solid #ff8a65;
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.eyebrow {
  display: block;
  font-size: 8px;
  letter-spacing: 0.8px;
  color: #ffab91;
}

.card-head h3 {
  margin: 1px 0 0;
  font-size: 11px;
  font-weight: 600;
}

.badge {
  font-size: 10px;
  font-family: ui-monospace, monospace;
  padding: 2px 6px;
  border-radius: 999px;
  color: #ffccbc;
  background: rgba(255, 87, 34, 0.18);
  border: 1px solid rgba(255, 138, 101, 0.4);
}

.heatmap {
  display: flex;
  gap: 4px;
  margin-top: 8px;
}

.cell {
  flex: 1;
  height: 22px;
  border-radius: 3px;
  background: rgba(0, 40, 60, 0.55);
  border: 1px solid rgba(0, 212, 240, 0.12);
  transition: background 0.25s ease, box-shadow 0.25s ease;
}

.cell.hit {
  background: linear-gradient(180deg, #ff7043 0%, #bf360c 100%);
  border-color: rgba(255, 171, 145, 0.65);
  box-shadow: 0 0 10px rgba(255, 112, 67, 0.45);
}

.legend {
  margin: 6px 0 0;
  font-size: 9px;
  color: rgba(255, 204, 188, 0.75);
  line-height: 1.4;
}

.legend.dates {
  font-family: ui-monospace, monospace;
}
</style>
