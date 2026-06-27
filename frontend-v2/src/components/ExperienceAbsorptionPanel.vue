<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { AbsorptionTraceLine, ExperienceAbsorptionState } from '../types/skillAbsorption'
import { parseTerminalLine, splitTerminalLines } from '../utils/terminalLines'

const props = defineProps<{
  state: ExperienceAbsorptionState
  embedded?: boolean
}>()

const traceRef = ref<HTMLElement | null>(null)

const visibleLines = computed(() => props.state.lines.filter((line) => line.text || line.chips?.length))

const traceFingerprint = computed(() =>
  props.state.lines
    .map((line) => `${line.seq}|${line.text ?? ''}|${line.chips?.map((c) => c.key).join(',') ?? ''}|${line.status}`)
    .join('\n'),
)

function scrollTraceToBottom() {
  nextTick(() => {
    const el = traceRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch(traceFingerprint, () => scrollTraceToBottom(), { flush: 'post' })

watch(
  () => props.state.valueSnapshot,
  () => scrollTraceToBottom(),
  { flush: 'post' },
)

function stageLabel(stage: string): string {
  const map: Record<string, string> = {
    recap: 'recap',
    decompose: 'decompose',
    retrieve: 'retrieve',
    compare: 'compare',
    value: 'value',
    blueprint: 'blueprint',
  }
  return map[stage] ?? stage
}

function traceLines(line: AbsorptionTraceLine): string[] {
  if (!line.text) return []
  return splitTerminalLines(line.text).map((row) => (row.startsWith('> ') ? row : `> ${row}`))
}

function terminalLineParts(text: string) {
  return parseTerminalLine(text)
}
</script>

<template>
  <aside class="absorption-panel" :class="{ embedded, active: state.active }">
    <header class="panel-header">
      <span class="eyebrow">ABSORPTION</span>
      <h2>经验吸收</h2>
      <span v-if="state.active && state.currentStage !== 'done'" class="pulse-dot" title="吸收中" />
    </header>

    <div ref="traceRef" class="trace-stream">
      <ol v-if="visibleLines.length" class="trace-list">
        <li
          v-for="(line, index) in visibleLines"
          :key="`${line.seq}-${index}`"
          :class="['trace-item', `status-${line.status}`, `kind-${line.kind}`]"
        >
          <div class="trace-meta">
            <span class="stage-badge">{{ stageLabel(line.stage) }}</span>
            <span v-if="line.durationMs != null" class="duration">{{ line.durationMs }}ms</span>
          </div>
          <div v-if="line.text" class="terminal-block">
            <p
              v-for="(row, rowIdx) in traceLines(line)"
              :key="rowIdx"
              class="terminal-line"
            >
              <span class="terminal-prompt">{{ terminalLineParts(row).prompt || '> ' }}</span>
              <span class="terminal-text">{{ terminalLineParts(row).body }}</span>
            </p>
          </div>
          <TransitionGroup name="chip-fade" tag="div" v-if="line.chips?.length" class="chip-row">
            <span v-for="chip in line.chips" :key="chip.key" class="chip" :title="chip.key">
              <span class="chip-label">{{ chip.label }}</span>
              <span class="chip-value">{{ chip.value }}</span>
            </span>
          </TransitionGroup>
        </li>
      </ol>
      <p v-else class="placeholder">等待吸收追踪事件…</p>
    </div>

    <table v-if="state.valueSnapshot" class="value-table">
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
          <td>{{ row.before }}</td>
          <td>{{ row.after }}</td>
        </tr>
      </tbody>
    </table>
  </aside>
</template>

<style scoped>
.absorption-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  background: #060c12;
  border-top: 1px solid rgba(120, 140, 160, 0.2);
  color: #b8c4d0;
}

.absorption-panel.embedded {
  border-radius: 0;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(120, 140, 160, 0.15);
  flex-shrink: 0;
}

.eyebrow {
  font-size: 10px;
  letter-spacing: 0.12em;
  color: #7a8a9a;
}

.panel-header h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #d0dae4;
}

.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c9a227;
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

.trace-stream {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 10px 12px;
  min-height: 120px;
  scroll-behavior: smooth;
}

.trace-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.trace-item {
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px dashed rgba(120, 140, 160, 0.12);
}

.trace-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.stage-badge {
  font-size: 10px;
  text-transform: lowercase;
  color: #8a9aaa;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.duration {
  font-size: 10px;
  color: #5a8a6a;
}

.mono {
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  color: #c5d0dc;
}

.terminal-block {
  padding: 6px 8px;
  border-radius: 4px;
  background: rgba(1, 6, 12, 0.92);
  border: 1px solid rgba(0, 229, 255, 0.12);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.terminal-line {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 0;
  font-size: 11px;
  line-height: 1.55;
  min-height: 1.55em;
}

.terminal-prompt {
  flex-shrink: 0;
  color: rgba(0, 229, 255, 0.7);
  user-select: none;
}

.terminal-text {
  flex: 1;
  min-width: 0;
  color: rgba(197, 230, 220, 0.92);
  word-break: break-word;
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
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(80, 100, 120, 0.2);
  border: 1px solid rgba(120, 140, 160, 0.2);
}

.chip-label {
  color: #8a9aaa;
}

.chip-value {
  color: #d8e4f0;
}

.chip-fade-enter-active {
  transition: opacity 0.35s ease, transform 0.35s ease;
}

.chip-fade-enter-from {
  opacity: 0;
  transform: translateY(4px);
}

.value-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  margin-top: auto;
  flex-shrink: 0;
}

.value-table th,
.value-table td {
  border: 1px solid rgba(120, 140, 160, 0.15);
  padding: 6px 8px;
  text-align: left;
}

.value-table th {
  background: rgba(40, 50, 60, 0.4);
  color: #9aa8b8;
}

.placeholder {
  margin: 0;
  font-size: 12px;
  color: #6a7a8a;
}
</style>
