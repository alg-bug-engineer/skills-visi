<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ProcessStepState } from '../composables/useUnderstandingProcess'
import { parseTerminalLine, splitTerminalLines } from '../utils/terminalLines'

export interface ConversationTurn {
  role: 'user' | 'assistant'
  content: string
  tag?: string
}

const props = defineProps<{
  steps: ProcessStepState[]
  active: boolean
  mode: 'idle' | 'conversation' | 'analysis'
  conversation: ConversationTurn[]
  missingFields?: string[]
  /** 嵌入工作台右栏时勿占满整列高度 */
  embedded?: boolean
  /** 经验吸收阶段：默认折叠为摘要条，可点击展开回看 */
  stackSummaryMode?: boolean
}>()

const emit = defineEmits<{
  toggle: [index: number]
}>()

const panelExpanded = ref(true)

watch(
  () => props.stackSummaryMode,
  (enabled) => {
    if (enabled) panelExpanded.value = false
  },
  { immediate: true },
)

const doneStepCount = computed(() => props.steps.filter((s) => s.status === 'done').length)

const missingFieldLabels: Record<string, string> = {
  intersection: '路口',
  corridor: '干线',
  time_period: '时段',
  problem_type: '问题类型',
  directions: '方向',
}

const activeStepIndex = computed(() => {
  const typing = props.steps.find((s) => s.status === 'typing')
  return typing?.index ?? -1
})

function displayedLines(step: ProcessStepState): string[] {
  const text = step.fullText.slice(0, step.displayedLength)
  return splitTerminalLines(text)
}

function terminalLineParts(line: string) {
  return parseTerminalLine(line)
}

function stepIconKind(step: ProcessStepState): 'diamond' | 'square' | 'dot' {
  if (step.status === 'typing') return 'dot'
  if (step.index === 0) return 'diamond'
  return 'square'
}
</script>

<template>
  <aside class="process-panel" :class="{ embedded, 'summary-mode': stackSummaryMode && !panelExpanded }">
    <header class="panel-header">
      <span class="eyebrow">{{ mode === 'conversation' ? 'DIALOGUE' : 'ANALYSIS' }}</span>
      <h2>{{ mode === 'conversation' ? '对话追问' : '理解过程' }}</h2>
      <span v-if="active" class="pulse-dot" title="处理中" />
    </header>

    <button
      v-if="stackSummaryMode && mode === 'analysis' && steps.length"
      type="button"
      class="summary-strip"
      @click="panelExpanded = !panelExpanded"
    >
      <span>{{ panelExpanded ? '▾' : '▸' }}</span>
      <span>理解过程 · {{ doneStepCount }} 步已完成</span>
      <span class="summary-hint">{{ panelExpanded ? '点击收起' : '点击展开回看' }}</span>
    </button>

    <section v-if="mode === 'conversation' && conversation.length" class="conversation">
      <p v-if="missingFields?.length" class="missing-hint">
        待补充：{{ missingFields.map((f) => missingFieldLabels[f] ?? f).join('、') }}
      </p>
      <article
        v-for="(turn, i) in conversation"
        :key="i"
        :class="['turn', `role-${turn.role}`]"
      >
        <span class="turn-tag">{{ turn.role === 'user' ? '用户' : turn.tag ?? '助手' }}</span>
        <p class="turn-text">{{ turn.content }}</p>
      </article>
    </section>

    <section v-else-if="steps.length" class="reasoning-block">
      <div class="reasoning-head">
        <span class="reasoning-icon" aria-hidden="true" />
        <h3 class="reasoning-title">智能体推理</h3>
        <button type="button" class="panel-toggle" @click="panelExpanded = !panelExpanded">
          {{ panelExpanded ? '收起' : '展开过程' }}
        </button>
      </div>

      <ol v-show="panelExpanded" class="timeline">
        <li
          v-for="(step, i) in steps"
          :key="step.index"
          :class="[
            'step-item',
            `status-${step.status}`,
            { collapsed: step.collapsed, active: step.index === activeStepIndex },
          ]"
        >
          <div class="rail" aria-hidden="true">
            <span :class="['rail-icon', stepIconKind(step)]" />
            <span v-if="i < steps.length - 1" class="rail-line" />
          </div>

          <div class="step-main">
            <button
              type="button"
              class="step-head"
              :disabled="step.status === 'typing'"
              @click="emit('toggle', step.index)"
            >
              <span v-if="step.status === 'typing'" class="caret open" aria-hidden="true" />
              <span v-else-if="!step.collapsed" class="caret open" aria-hidden="true" />
              <span v-else class="caret" aria-hidden="true" />

              <span class="step-label">{{ step.label }}</span>

              <span v-if="step.status === 'typing'" class="status-indicator typing" title="执行中" />
              <span
                v-else-if="activeStepIndex >= 0 && step.index > activeStepIndex"
                class="status-indicator pending"
                title="等待中"
              />
              <span v-else class="status-indicator done" title="已完成">✓</span>
            </button>

            <div v-show="!step.collapsed" class="step-body terminal-body">
              <p
                v-for="(line, lineIdx) in displayedLines(step)"
                :key="lineIdx"
                class="terminal-line"
              >
                <span v-if="terminalLineParts(line).prompt" class="terminal-prompt">{{
                  terminalLineParts(line).prompt
                }}</span>
                <span class="terminal-text">{{ terminalLineParts(line).body }}</span>
                <span
                  v-if="step.status === 'typing' && lineIdx === displayedLines(step).length - 1"
                  class="cursor"
                >|</span>
              </p>
              <p v-if="step.status === 'typing' && !displayedLines(step).length" class="terminal-line">
                <span class="cursor">|</span>
              </p>
            </div>
          </div>
        </li>
      </ol>
    </section>

    <p v-else class="empty-hint">
      {{
        mode === 'conversation'
          ? '正在等待回复…'
          : '发送消息后，将按步骤展示理解、匹配、关联 link 与诊断过程。'
      }}
    </p>
  </aside>
</template>

<style scoped>
.process-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  padding: 16px 14px;
  background: linear-gradient(180deg, rgba(8, 18, 34, 0.97) 0%, rgba(4, 10, 20, 0.95) 100%);
  color: #e8f4ff;
  border-left: 1px solid rgba(94, 184, 255, 0.12);
  overflow-y: auto;
  backdrop-filter: blur(12px);
}

.process-panel.embedded {
  height: auto;
  border-left: none;
}

.panel-header {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(94, 184, 255, 0.1);
}

.eyebrow {
  color: rgba(94, 200, 255, 0.75);
  letter-spacing: 2px;
  font-size: 10px;
  text-transform: uppercase;
}

.panel-header h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: rgba(232, 244, 255, 0.95);
}

.pulse-dot {
  position: absolute;
  top: 18px;
  right: 4px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #38bdf8;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.9);
  }
  50% {
    opacity: 1;
    transform: scale(1.15);
  }
}

.reasoning-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.reasoning-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.reasoning-icon {
  width: 8px;
  height: 8px;
  background: linear-gradient(135deg, #38bdf8, #0ea5e9);
  transform: rotate(45deg);
  flex-shrink: 0;
  box-shadow: 0 0 8px rgba(56, 189, 248, 0.5);
}

.reasoning-title {
  flex: 1;
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: rgba(186, 230, 253, 0.95);
}

.panel-toggle {
  padding: 3px 10px;
  border-radius: 2px;
  border: 1px solid rgba(94, 184, 255, 0.35);
  background: rgba(14, 165, 233, 0.08);
  color: rgba(186, 230, 253, 0.85);
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}

.panel-toggle:hover {
  border-color: rgba(94, 184, 255, 0.55);
  background: rgba(14, 165, 233, 0.14);
}

.timeline {
  list-style: none;
  margin: 0;
  padding: 4px 0 0;
  display: flex;
  flex-direction: column;
}

.step-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  min-height: 0;
}

.step-item.collapsed .step-main {
  padding-bottom: 4px;
}

.rail {
  position: relative;
  width: 16px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  align-self: stretch;
}

.rail-icon {
  position: relative;
  z-index: 1;
  flex-shrink: 0;
}

.rail-icon.diamond {
  width: 7px;
  height: 7px;
  margin-top: 10px;
  background: rgba(94, 184, 255, 0.55);
  transform: rotate(45deg);
}

.rail-icon.square {
  width: 7px;
  height: 7px;
  margin-top: 10px;
  background: rgba(94, 184, 255, 0.4);
  border-radius: 1px;
}

.rail-icon.dot {
  width: 8px;
  height: 8px;
  margin-top: 9px;
  border-radius: 50%;
  background: #38bdf8;
  box-shadow: 0 0 10px rgba(56, 189, 248, 0.65);
  animation: dot-pulse 1.4s ease-in-out infinite;
}

@keyframes dot-pulse {
  0%,
  100% {
    box-shadow: 0 0 6px rgba(56, 189, 248, 0.4);
  }
  50% {
    box-shadow: 0 0 14px rgba(56, 189, 248, 0.85);
  }
}

.rail-line {
  flex: 1;
  width: 1px;
  min-height: 12px;
  margin-top: 4px;
  background: linear-gradient(180deg, rgba(94, 184, 255, 0.35), rgba(94, 184, 255, 0.08));
}

.step-main {
  flex: 1;
  min-width: 0;
  padding-bottom: 8px;
  overflow: hidden;
}

.step-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 0;
  border: none;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  font: inherit;
}

.step-head:disabled {
  cursor: default;
}

.caret {
  width: 0;
  height: 0;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 5px solid rgba(148, 196, 230, 0.45);
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

.caret.open {
  transform: rotate(90deg);
}

.step-label {
  flex: 1;
  font-size: 12px;
  font-weight: 500;
  color: rgba(220, 240, 255, 0.88);
  letter-spacing: 0.2px;
}

.step-item.active .step-label {
  color: #e0f2fe;
  font-weight: 600;
}

.step-item.status-done.collapsed .step-label {
  color: rgba(186, 215, 240, 0.72);
}

.status-indicator {
  flex-shrink: 0;
  font-size: 11px;
  line-height: 1;
}

.status-indicator.typing {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #38bdf8;
  box-shadow: 0 0 8px rgba(56, 189, 248, 0.6);
}

.status-indicator.pending {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(148, 196, 230, 0.35);
}

.status-indicator.done {
  color: #4ade80;
  font-weight: 700;
  font-size: 12px;
}

.step-body {
  margin-left: 4px;
}

.terminal-body {
  padding: 8px 10px;
  border-radius: 4px;
  background: rgba(1, 6, 12, 0.88);
  border: 1px solid rgba(0, 229, 255, 0.14);
  box-shadow: inset 0 1px 0 rgba(0, 229, 255, 0.04);
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-family: ui-monospace, 'Courier New', Courier, monospace;
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
  color: rgba(0, 229, 255, 0.72);
  user-select: none;
}

.terminal-text {
  flex: 1;
  min-width: 0;
  color: rgba(197, 230, 220, 0.9);
  word-break: break-word;
}

.step-line {
  margin: 0;
  font-size: 11px;
  line-height: 1.55;
  color: rgba(200, 230, 255, 0.78);
  word-break: break-word;
}

.typing-line {
  min-height: 1em;
}

.cursor {
  color: #38bdf8;
  animation: blink 0.65s step-end infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.empty-hint {
  margin: 0;
  font-size: 11px;
  color: rgba(186, 215, 240, 0.45);
  line-height: 1.6;
}

.conversation {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.missing-hint {
  margin: 0;
  padding: 8px 10px;
  border-radius: 2px;
  font-size: 11px;
  color: #fbbf24;
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.22);
}

.turn {
  padding: 10px 12px;
  border-radius: 2px;
  border: 1px solid rgba(94, 184, 255, 0.12);
  background: rgba(8, 16, 30, 0.55);
}

.turn.role-user {
  border-color: rgba(56, 189, 248, 0.25);
}

.turn.role-assistant {
  border-color: rgba(251, 191, 36, 0.3);
  border-left: 2px solid #fbbf24;
}

.turn-tag {
  display: inline-block;
  margin-bottom: 6px;
  font-size: 10px;
  letter-spacing: 0.5px;
  color: rgba(125, 211, 252, 0.9);
}

.turn.role-assistant .turn-tag {
  color: #fbbf24;
}

.turn-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
  color: rgba(232, 244, 255, 0.9);
  white-space: pre-wrap;
}

.summary-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  border-bottom: 1px solid rgba(0, 212, 240, 0.1);
  background: rgba(0, 10, 20, 0.85);
  color: #9ecae8;
  font-size: 12px;
  cursor: pointer;
  text-align: left;
}

.summary-hint {
  margin-left: auto;
  font-size: 10px;
  color: #6a8a9a;
}

.process-panel.summary-mode {
  flex: 0 0 auto;
  max-height: 42%;
  overflow: hidden;
}
</style>
