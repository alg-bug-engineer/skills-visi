<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import { useTyping } from '@/composables/useTyping'
import { narrationFor, summaryFor, type CardKey } from '@/composables/useTimeline'
import DiagnosisTicketCard from '@/cards/DiagnosisTicketCard.vue'
import DataMetricsCard from '@/cards/DataMetricsCard.vue'
import BottleneckCard from '@/cards/BottleneckCard.vue'
import CorridorScanCard from '@/cards/CorridorScanCard.vue'
import AttributionCard from '@/cards/AttributionCard.vue'
import CauseCard from '@/cards/CauseCard.vue'
import ProblemVerificationCard from '@/cards/ProblemVerificationCard.vue'
import GovernanceStrategyCard from '@/cards/GovernanceStrategyCard.vue'
import OverflowChainCard from '@/cards/OverflowChainCard.vue'
import HealthyConclusionCard from '@/cards/HealthyConclusionCard.vue'
import ExperienceAbsorptionPanel from '@/panels/ExperienceAbsorptionPanel.vue'
import { useExperienceAbsorption } from '@/composables/useExperienceAbsorption'
import {
  voiceCueForAbsorptionDone,
  voiceCueForAbsorptionStage,
  voiceCueForAbsorptionStart,
} from '@/services/voiceAbsorptionSync'
import { DEMO_TYPING_MS, actDwellMs } from '@/config/demoPacing'

const store = usePresentationStore()
const { acts, currentAct, revealedActs, solidifyPhase } = storeToRefs(store)

const INSIGHT_CARDS: Record<string, unknown> = {
  ticket: DiagnosisTicketCard,
  metrics: DataMetricsCard,
  bottleneck: BottleneckCard,
  corridor: CorridorScanCard,
  attribution: AttributionCard,
  cause: CauseCard,
  verification: ProblemVerificationCard,
  governance: GovernanceStrategyCard,
  overflow_chain: OverflowChainCard,
  healthy: HealthyConclusionCard,
}

const panelExpanded = ref(true)
/** 已完成步骤默认折叠；用户点击后写入此集合以展开。 */
const manualExpanded = ref<Set<number>>(new Set())
type ProcessTab = 'closure' | 'solidify'
const activeTab = ref<ProcessTab>('closure')

const showSolidifyTab = computed(() => solidifyPhase.value !== 'idle')
const absorption = useExperienceAbsorption()

const instant = (() => {
  const reduced =
    typeof window !== 'undefined' &&
    !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const automation =
    typeof navigator !== 'undefined' && (navigator as Navigator).webdriver === true
  return reduced || automation
})()

const absorptionStarted = ref(false)

watch(
  () => solidifyPhase.value,
  (phase) => {
    if (phase !== 'idle' && phase !== 'prompt') activeTab.value = 'solidify'
    if (phase === 'idle') {
      activeTab.value = 'closure'
      absorptionStarted.value = false
      absorption.reset()
    }
  },
)

function visibleLines(lines: string[]): string[] {
  return lines.filter((line) => line.trim())
}

const absorptionRunKey = computed(() => `${store.mapResetSeq}:${store.skillResult?.skill_id ?? 'absorption'}`)

function enqueueAbsorptionVoice(stageKey: string) {
  const runKey = absorptionRunKey.value
  if (stageKey === '__start__') {
    store.enqueueVoice(voiceCueForAbsorptionStart(runKey))
    return
  }
  if (stageKey === '__done__') {
    store.enqueueVoice(voiceCueForAbsorptionDone(runKey))
    return
  }
  store.enqueueVoice(voiceCueForAbsorptionStage(runKey, stageKey))
}

watch(
  () => [solidifyPhase.value, store.skillResult] as const,
  ([phase, result]) => {
    if (phase === 'absorbing' && result && !absorptionStarted.value) {
      absorptionStarted.value = true
      absorption.start(result.absorption, {
        instant,
        skillId: result.skill_id,
        intersection: result.intersection ?? '',
        onStart: () => enqueueAbsorptionVoice('__start__'),
        onStageStart: (key) => enqueueAbsorptionVoice(key),
        onDone: () => {
          enqueueAbsorptionVoice('__done__')
          store.setSolidifyPhase('building')
        },
      })
    }
  },
  { immediate: true },
)

const typingLines = ref<string[]>([])
/** 仅 act 切换时更新旁白，避免 SSE 快照刷新导致同幕重复打字。 */
const typingActKey = computed(() =>
  currentAct.value >= 0 ? `${store.mapResetSeq}:${currentAct.value}` : '',
)

watch(
  typingActKey,
  (key) => {
    if (!key) {
      typingLines.value = []
      return
    }
    const idx = currentAct.value
    const act = store.acts[idx]
    if (act) typingLines.value = narrationFor(act, store.response)
  },
  { immediate: true },
)

// 旁白缓存（需求17-R2）：某幕打字完成时冻结其已输出的多行旁白，
// 折叠后再展开仍显示同一套过程旁白，消除“打字内容与展开结果不一致”的错觉。
const narrationCache = ref<Record<number, string[]>>({})
const timelineRef = ref<HTMLElement | null>(null)

/** 当前幕收尾：语音与幕间停留不受暂停打断；仅在切入下一幕前等待恢复。 */
async function finishActAndAdvance(idx: number) {
  if (store.currentAct !== idx) return
  await store.waitForVoiceBarrier()
  if (store.currentAct !== idx) return
  await store.pauseAwareSleep(actDwellMs(idx, instant, store.acts[idx]?.id))
  if (store.currentAct !== idx) return
  while (store.currentAct === idx) {
    await store.waitForStepResume()
    if (store.currentAct !== idx) return
    store.tryAdvance()
    if (!store.stepAdvancePending) break
  }
}

const { shown, done } = useTyping(typingLines, {
  instant,
  speed: DEMO_TYPING_MS,
  restartKey: typingActKey,
  onDone: () => {
    const idx = store.currentAct
    if (idx < 0) return
    narrationCache.value = { ...narrationCache.value, [idx]: typingLines.value.filter((l) => l.trim()) }
    store.onActTyped(idx)
    if (store.autoPlay) void finishActAndAdvance(idx)
  },
})

const shownLines = computed(() => visibleLines(shown.value))

function narrationOf(index: number): string[] {
  return narrationCache.value[index] ?? []
}

// 会话重置时清空缓存，避免上一轮旁白串到新一轮。
watch(
  () => store.mapResetSeq,
  () => {
    narrationCache.value = {}
  },
)

/** 可见阶段：当前及之前所有已开始的阶段 */
const visibleActs = computed(() => {
  if (currentAct.value < 0) return []
  return acts.value.slice(0, currentAct.value + 1)
})

function actStatus(index: number): 'pending' | 'typing' | 'done' {
  if (index < currentAct.value) return 'done'
  if (index === currentAct.value) return done.value ? 'done' : 'typing'
  return 'pending'
}

function isCollapsed(index: number): boolean {
  // 当前幕（打字中或刚完成未切幕）始终展开
  if (index === currentAct.value) return false
  // 已完成的历史幕：默认折叠，仅手动展开
  return !manualExpanded.value.has(index)
}

function toggleAct(index: number) {
  if (actStatus(index) === 'typing') return
  // 当前幕已打完仍保持展开；可折叠需先切到下一幕
  if (index === currentAct.value) return
  const next = new Set(manualExpanded.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  manualExpanded.value = next
}

function cardKeyFor(index: number): CardKey | null {
  const act = acts.value[index]
  if (!act?.reveal || !(act.reveal in INSIGHT_CARDS)) return null
  if (!revealedActs.value.includes(index)) return null
  return act.reveal
}

/** 追加证据卡键：与主卡同门控（阶段已揭示才展示），组件缺失时过滤。 */
function extraCardKeysFor(index: number): CardKey[] {
  const act = acts.value[index]
  if (!revealedActs.value.includes(index)) return []
  const keys = [...(act?.extraCards ?? [])]
  // 健康核验：在「证据核验」幕追加健康结论卡（诊断/策略/处置文案）。
  if (store.isHealthy && act?.id === 'act3_overflow') keys.push('healthy')
  return keys.filter((k) => k in INSIGHT_CARDS)
}

function cardPropsFor(key: CardKey | null): Record<string, unknown> {
  if (key === 'metrics') return { variant: 'summary' }
  return {}
}

watch(currentAct, (idx, prev) => {
  // 切入下一幕后，自动收起上一幕（若用户先前展开过也收起，保证「完成后折叠」）
  if (typeof prev === 'number' && prev >= 0 && prev !== idx) {
    const next = new Set(manualExpanded.value)
    next.delete(prev)
    manualExpanded.value = next
  }
  void scrollTimelineToActive()
})

watch(
  () => store.mapResetSeq,
  () => {
    manualExpanded.value = new Set()
  },
)

watch(shown, () => {
  void scrollTimelineToActive()
})

async function scrollTimelineToActive() {
  await nextTick()
  const root = timelineRef.value
  if (!root || currentAct.value < 0) return
  const active = root.querySelector<HTMLElement>(`[data-act-index="${currentAct.value}"]`)
  if (typeof active?.scrollIntoView === 'function') {
    active.scrollIntoView({ behavior: instant ? 'auto' : 'smooth', block: 'nearest' })
  }
}
</script>

<template>
  <aside class="reasoning us-panel" data-testid="process-panel">
    <header class="reasoning__hd">
      <span class="reasoning-icon" aria-hidden="true">◆</span>
      <h2>处置闭环</h2>
      <div v-if="showSolidifyTab" class="tab-switch" role="tablist">
        <button
          type="button"
          role="tab"
          class="tab-switch__btn"
          :class="{ active: activeTab === 'closure' }"
          data-testid="process-tab-closure"
          @click="activeTab = 'closure'"
        >
          闭环过程
        </button>
        <button
          type="button"
          role="tab"
          class="tab-switch__btn"
          :class="{ active: activeTab === 'solidify' }"
          data-testid="process-tab-solidify"
          @click="activeTab = 'solidify'"
        >
          经验固化
        </button>
      </div>
      <button
        v-if="activeTab === 'closure'"
        type="button"
        class="panel-toggle"
        @click="panelExpanded = !panelExpanded"
      >
        {{ panelExpanded ? '收起' : '展开过程' }}
      </button>
    </header>

    <div v-if="activeTab === 'solidify'" class="solidify-body" data-testid="process-solidify-tab">
      <ExperienceAbsorptionPanel :state="absorption.state" />
    </div>

    <p
      v-else-if="activeTab === 'closure' && currentAct < 0 && store.status === 'running'"
      class="empty-hint"
      data-testid="process-waiting-first-phase"
    >
      正在{{ store.computingLabel || '等待后端' }}…首阶段完成后将展示推理明细
    </p>

    <ol v-else-if="panelExpanded && currentAct >= 0" ref="timelineRef" class="timeline" data-testid="reasoning-timeline">
      <li
        v-for="(act, i) in visibleActs"
        :key="act.id"
        class="step-item"
        :data-act-index="act.index"
        :class="{
          active: i === currentAct && !done,
          done: actStatus(act.index) === 'done',
          collapsed: isCollapsed(act.index),
        }"
      >
        <div class="rail" aria-hidden="true">
          <span class="rail-icon" :class="{ pulse: actStatus(act.index) === 'typing' }" />
          <span v-if="i < visibleActs.length - 1" class="rail-line" />
        </div>

        <div class="step-main">
          <button
            type="button"
            class="step-head"
            :disabled="actStatus(act.index) === 'typing'"
            @click="toggleAct(act.index)"
          >
            <span class="caret" :class="{ open: !isCollapsed(act.index) }">▸</span>
            <span class="step-label">{{ act.processTitle }}</span>
            <span v-if="actStatus(act.index) === 'typing'" class="status-dot typing" />
            <span v-else class="status-done">✓</span>
          </button>

          <div v-show="!isCollapsed(act.index)" class="step-body">
            <!-- 进行中：流式子步骤 -->
            <div v-if="act.index === currentAct && !done" class="detail-lines" data-testid="process-typing">
              <p v-for="(l, li) in shownLines" :key="li" class="detail-line">
                <span class="check">✓</span>{{ l
                }}<span v-if="li === shownLines.length - 1" class="caret-blink">▍</span>
              </p>
            </div>

            <!-- 已完成：冻结旁白全文（与打字一致）+ 可选证据卡 -->
            <template v-else>
              <div
                v-if="narrationOf(act.index).length"
                class="detail-lines detail-lines--frozen"
                data-testid="process-narration-frozen"
              >
                <p v-for="(l, li) in visibleLines(narrationOf(act.index))" :key="li" class="detail-line">
                  <span class="check">✓</span>{{ l }}
                </p>
              </div>
              <p v-else class="step-summary">{{ summaryFor(act, store.response) }}</p>
              <div
                v-if="cardKeyFor(act.index) || extraCardKeysFor(act.index).length"
                class="evidence-slot"
              >
                <component
                  v-if="cardKeyFor(act.index)"
                  :is="INSIGHT_CARDS[cardKeyFor(act.index)!]"
                  v-bind="cardPropsFor(cardKeyFor(act.index))"
                  data-testid="insight-card"
                />
                <component
                  v-for="key in extraCardKeysFor(act.index)"
                  :key="key"
                  :is="INSIGHT_CARDS[key]"
                />
              </div>
            </template>
          </div>

          <!-- 折叠态仅显示汇总 -->
          <p v-if="isCollapsed(act.index)" class="step-summary collapsed-summary">
            {{ summaryFor(act, store.response) }}
          </p>
        </div>
      </li>
    </ol>

    <p v-else-if="activeTab === 'closure' && !panelExpanded && currentAct >= 0" class="summary-strip">
      处置闭环 · {{ currentAct + 1 }} / {{ acts.length }} 步
    </p>
    <p v-else-if="activeTab === 'closure' && currentAct < 0" class="empty-hint">推演开始后，将按阶段展示推理明细…</p>
  </aside>
</template>

<style scoped>
.reasoning {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 12px 10px;
  overflow: hidden;
  border-radius: 8px;
  border-color: rgba(118, 177, 222, 0.26);
  background:
    linear-gradient(180deg, rgba(0, 229, 255, 0.06), transparent 34%),
    rgba(4, 13, 24, 0.9);
}
.reasoning__hd {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex: 0 0 auto;
}
.reasoning__hd h2 {
  flex: 1;
  margin: 0;
  font-size: 15px;
  letter-spacing: 0;
}
.reasoning-icon {
  color: var(--primary);
  font-size: 12px;
}
.panel-toggle {
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid var(--panel-border);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
}
.panel-toggle:hover {
  color: var(--primary);
  border-color: var(--primary);
}
.tab-switch {
  display: flex;
  gap: 4px;
  margin-left: auto;
  margin-right: 6px;
}
.tab-switch__btn {
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid var(--panel-border);
  background: transparent;
  color: var(--text-mute);
  font-size: 11px;
  cursor: pointer;
}
.tab-switch__btn.active {
  border-color: var(--primary);
  background: var(--primary-dim);
  color: var(--text);
}
.solidify-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.solidify-body > :deep(*) {
  flex: 1;
  min-height: 0;
}
.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.step-item {
  display: flex;
  gap: 10px;
  padding: 4px 0;
}
.rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 16px;
  flex: 0 0 16px;
}
.rail-icon {
  width: 9px;
  height: 9px;
  border-radius: 1px;
  border: 1.5px solid var(--primary);
  background: var(--primary-dim);
  flex: 0 0 auto;
}
.rail-icon.pulse {
  border-radius: 50%;
  animation: pulse 1.2s ease-in-out infinite;
}
.rail-line {
  flex: 1;
  width: 1px;
  min-height: 12px;
  background: var(--panel-border);
  margin: 4px 0;
}
.step-main {
  flex: 1;
  min-width: 0;
}
.step-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 5px 7px;
  border: 1px solid transparent;
  background: rgba(255, 255, 255, 0.02);
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}
.step-item.done .step-head,
.step-item.active .step-head {
  border-color: rgba(0, 229, 255, 0.14);
}
.step-head:disabled {
  cursor: default;
}
.step-item.active .step-head {
  color: var(--primary);
}
.step-item.done .step-head {
  color: var(--protected);
}
.caret {
  font-size: 10px;
  color: var(--text-mute);
  transition: transform 0.15s;
  flex: 0 0 auto;
}
.caret.open {
  transform: rotate(90deg);
}
.step-label {
  flex: 1;
}
.status-dot.typing {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
  box-shadow: var(--glow-primary);
  animation: pulse 1s infinite;
}
.status-done {
  font-size: 11px;
  color: var(--protected);
}
.step-body {
  padding: 2px 0 6px;
}
.detail-lines {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding-left: 6px;
}
.detail-lines--frozen .detail-line {
  color: var(--text-dim);
}
.detail-line {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-dim);
}
.detail-line .check {
  color: var(--protected);
  margin-right: 6px;
  font-size: 11px;
}
.caret-blink {
  color: var(--primary);
  animation: blink 1s step-end infinite;
}
.step-summary {
  margin: 0;
  padding: 5px 8px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-dim);
  border-left: 2px solid var(--primary);
  background: rgba(0, 229, 255, 0.04);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
.collapsed-summary {
  margin-top: 2px;
  padding-left: 6px;
  border-left: none;
  background: transparent;
  font-size: 11.5px;
  color: var(--text-mute);
}
.evidence-slot {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.evidence-slot :deep(.card) {
  margin: 0;
}
.summary-strip,
.empty-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-mute);
  text-align: center;
}
@keyframes pulse {
  50% {
    opacity: 0.35;
  }
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
