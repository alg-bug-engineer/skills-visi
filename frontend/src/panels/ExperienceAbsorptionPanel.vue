<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { ExperienceAbsorptionState } from '@/types/skillAbsorption'
import { productCopy } from '@/utils/productCopy'

const props = defineProps<{
  state: ExperienceAbsorptionState
}>()

const traceRef = ref<HTMLElement | null>(null)

const pulsing = computed(() => props.state.active && props.state.currentStage !== 'done')

const traceFingerprint = computed(() => props.state.lines.map((l) => l.seq).join(','))

watch(
  [traceFingerprint, () => props.state.valueSnapshot],
  () => {
    nextTick(() => {
      const el = traceRef.value
      if (el) el.scrollTop = el.scrollHeight
    })
  },
  { flush: 'post' },
)
</script>

<template>
  <section class="absorption us-panel" data-testid="absorption-panel">
    <header class="absorption__hd">
      <span class="absorption__icon" aria-hidden="true">◆</span>
      <h2>经验吸收</h2>
      <span v-if="pulsing" class="pulse-dot" title="吸收中" data-testid="absorption-pulse" />
    </header>

    <div ref="traceRef" class="trace" data-testid="absorption-trace">
      <ol v-if="state.lines.length" class="trace__list">
        <li v-for="line in state.lines" :key="line.seq" class="trace__item">
          <div class="trace__meta">
            <span class="stage-badge">{{ line.label }}</span>
            <span v-if="line.durationMs != null" class="duration">{{ line.durationMs }}ms</span>
          </div>
          <p class="monologue">{{ productCopy(line.monologue) }}</p>
          <TransitionGroup v-if="line.chips.length" name="chip-fade" tag="div" class="chip-row">
            <span v-for="chip in line.chips" :key="chip.key" class="chip" :title="chip.key">
              <span class="chip__label">{{ chip.label }}</span>
              <span class="chip__value">{{ chip.value }}</span>
            </span>
          </TransitionGroup>
        </li>
      </ol>
      <p v-else class="placeholder">等待吸收追踪…</p>
    </div>

    <div v-if="state.valueSnapshot?.why_rows?.length" class="value-block">
      <h3 class="value-block__title">价值前后对照</h3>
      <table class="value-table" data-testid="absorption-value-table">
        <thead>
          <tr>
            <th>维度</th>
            <th>吸收前</th>
            <th>吸收后</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in state.valueSnapshot.why_rows" :key="row.key">
            <td>{{ row.label }}</td>
            <td>{{ productCopy(row.before) }}</td>
            <td>{{ productCopy(row.after) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.absorption {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  padding: 12px 14px;
  border-radius: var(--radius);
  background: rgba(4, 13, 24, 0.92);
}
.absorption__hd {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex: 0 0 auto;
}
.absorption__hd h2 {
  flex: 1;
  margin: 0;
  font-size: 15px;
  color: var(--text);
}
.absorption__icon {
  color: var(--evidence);
  font-size: 12px;
}
.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--evidence);
  box-shadow: 0 0 8px var(--evidence);
  animation: pulse 1.2s ease-in-out infinite;
}
@keyframes pulse {
  0%,
  100% {
    opacity: 0.4;
  }
  50% {
    opacity: 1;
  }
}
.trace {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 120px;
  padding-right: 4px;
}
.trace__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.trace__item {
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--panel-border);
}
.trace__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.stage-badge {
  font-size: 11px;
  color: var(--primary);
  font-weight: 600;
}
.duration {
  font-size: 10px;
  color: var(--text-mute);
}
.monologue {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--text-dim);
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
.chip {
  display: inline-flex;
  gap: 4px;
  font-size: 10.5px;
  padding: 2px 7px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--panel-border);
}
.chip__label {
  color: var(--text-mute);
}
.chip__value {
  color: var(--text);
}
.chip-fade-enter-active {
  transition:
    opacity 0.35s ease,
    transform 0.35s ease;
}
.chip-fade-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.value-block {
  flex: 0 0 auto;
  margin-top: 10px;
}
.value-block__title {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--text-dim);
}
.value-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.value-table th,
.value-table td {
  border: 1px solid var(--panel-border);
  padding: 6px 8px;
  text-align: left;
  color: var(--text-dim);
}
.value-table th {
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-mute);
}
.value-table td:last-child {
  color: var(--protected);
}
.placeholder {
  margin: 0;
  font-size: 12px;
  color: var(--text-mute);
}
</style>
