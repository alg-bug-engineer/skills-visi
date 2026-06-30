<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { CognitionPayload } from '../../types/map'
import type { ProblemEvidence, FlowTimingGovernance } from '../../types/evidence'
import type {
  GovernanceSuggestionPayload,
  PipelinePhase,
  RuntimeMetrics,
} from '../../types/presentation'
import type { DataInsight } from '../../types/insight'
import type { CaseScenario, ExperienceLevel, ExperienceSedimentItem } from '../../types/experience'
import {
  dedupeExperienceSediment,
  filterReusedExperienceBadges,
} from '../../utils/experienceDedup'
import { STEP_INDICES } from '../../constants'
import { buildNarrativeRuntimeItems } from '../../utils/narrativeStack'
import { buildEvidenceListItems, buildSuggestionListItems } from '../../utils/channelizationCopy'

const props = defineProps<{
  visible: boolean
  cognition: CognitionPayload | null
  highlightDirs?: string[]
  protectedDirs?: string[]
  runtimeMetrics?: RuntimeMetrics | null
  dataInsight?: DataInsight | null
  evidence?: ProblemEvidence | null
  governanceSuggestion?: GovernanceSuggestionPayload | null
  flowTimingGovernance?: FlowTimingGovernance | null
  reusedExperience?: string[]
  caseExperience?: CaseScenario[]
  experienceSediment?: ExperienceSedimentItem[]
  focusStepIndex: number
  /** 理解过程进入「运行数据」步骤后为 true（与 focusStepIndex 解耦，避免地图阶段抢跑） */
  runtimePanelRevealed?: boolean
  phase?: PipelinePhase
  /** 新一轮分析递增，重置粘性揭示 */
  runKey?: number
  /** 技能写入终端展开时隐藏左侧路口信息卡 */
  hideLeftPanel?: boolean
}>()

const emit = defineEmits<{ openCase: [id: string] }>()

/** 治理建议的可溯源依据（案例/经验）。 */
const suggestionReferences = computed(() => props.governanceSuggestion?.references ?? [])

/* ── 认知头 ─────────────────────────────────────────────────────────────── */
const intersection = computed(() => props.cognition?.intersection ?? null)
const armCount = computed(() => props.cognition?.arms?.length ?? 0)
const laneCount = computed(() =>
  (props.cognition?.arms ?? []).reduce((s, a) => s + (a.lane_num || a.lanes?.length || 0), 0),
)

function formatDirRoles(dirs?: string[]): string {
  if (!dirs?.length) return ''
  return dirs
    .map((d) => (d.endsWith('向') ? d : `${d}向`))
    .join('、')
}
const focusRole = computed(() => formatDirRoles(props.highlightDirs))
const protectRole = computed(() => formatDirRoles(props.protectedDirs))

/* ── 运行数据（逐项追加）────────────────────────────────────────────────── */
const runtimeItems = computed(() =>
  buildNarrativeRuntimeItems({
    runtimeMetrics: props.runtimeMetrics,
    dataInsight: props.dataInsight,
    evidence: props.evidence,
    flowTimingGovernance: props.flowTimingGovernance,
  }),
)
const showRuntime = computed(
  () => Boolean(props.runtimePanelRevealed) && runtimeItems.value.length > 0,
)

/* ── 问题验证（默认展开，可手动折叠）──────────────────────────────────────── */
const evidenceRevealed = ref(false)
const evidenceCollapsed = ref(false)
const evidenceItems = computed(() =>
  props.evidence ? buildEvidenceListItems(props.evidence) : [],
)
const showEvidence = computed(() => evidenceRevealed.value && evidenceItems.value.length > 0)
const evidenceSummary = computed(() => evidenceItems.value[0] ?? '问题已印证')

/* ── 治理建议 ───────────────────────────────────────────────────────────── */
const suggestionRevealed = ref(false)
const suggestionItems = computed(() =>
  buildSuggestionListItems(props.governanceSuggestion, props.flowTimingGovernance),
)
const showSuggestion = computed(
  () => suggestionRevealed.value && suggestionItems.value.length > 0,
)

/* ── 经验沉淀与复用 ─────────────────────────────────────────────────────── */
const sedimentItems = computed(() =>
  dedupeExperienceSediment(props.experienceSediment ?? []),
)
const reusedItems = computed(() =>
  filterReusedExperienceBadges(props.reusedExperience ?? [], sedimentItems.value),
)
const caseItems = computed(() => props.caseExperience ?? [])
const showExperience = computed(
  () => sedimentItems.value.length > 0 || reusedItems.value.length > 0 || caseItems.value.length > 0,
)
const LEVEL_DEFAULT_TAGS: Record<ExperienceLevel, string[]> = {
  cognition: ['认知画像', '问题记录'],
  diagnosis: ['诊断经验', '用户口述'],
  solution: ['方案经验', '治理措施'],
}
function itemTags(item: ExperienceSedimentItem): string[] {
  const base = item.tags?.length ? [...item.tags] : [...(LEVEL_DEFAULT_TAGS[item.level] ?? [])]
  if (item.level === 'cognition') {
    base.push(item.status === 'verified' ? '已验证' : '待验证')
  }
  return [...new Set(base)]
}
/* 三类经验分组：认知画像（问题记录）/ 诊断经验（用户口述原因）/ 方案诊断经验（用户治理经验）。 */
const EXPERIENCE_GROUPS: Array<{ level: ExperienceLevel; title: string }> = [
  { level: 'cognition', title: '认知画像' },
  { level: 'diagnosis', title: '诊断经验' },
  { level: 'solution', title: '方案诊断经验' },
]
const groupedSediment = computed(() =>
  EXPERIENCE_GROUPS.map((g) => ({
    ...g,
    items: sedimentItems.value.filter((it) => it.level === g.level),
  })).filter((g) => g.items.length > 0),
)
function statusLabel(status?: 'verified' | 'pending'): string {
  return status === 'verified' ? '已验证' : '待验证'
}

/* ── 粘性揭示（只增不减，避免阶段切换闪烁）──────────────────────────────── */
watch(
  () => props.focusStepIndex,
  (idx) => {
    if (idx >= STEP_INDICES.PROBLEM_EVIDENCE) {
      evidenceRevealed.value = true
    }
    if (idx >= STEP_INDICES.SUGGESTION) {
      suggestionRevealed.value = true
    }
  },
  { immediate: true },
)

watch(
  () => props.runKey,
  () => {
    evidenceRevealed.value = false
    evidenceCollapsed.value = false
    suggestionRevealed.value = false
  },
)

function toggleEvidence() {
  evidenceCollapsed.value = !evidenceCollapsed.value
}

function sevClass(sev?: string): string {
  return sev ? `sev-${sev}` : ''
}
</script>

<template>
  <Transition name="narrative-fade">
    <div v-if="visible && intersection" class="narrative-wrap">
      <!-- 左侧：路口身份与运行数据 -->
      <aside
        v-if="!hideLeftPanel"
        class="narrative-stack narrative-stack--left"
        aria-label="路口认知与运行数据"
      >
        <header class="head">
          <h3>{{ intersection.name }}</h3>
          <p v-if="intersection.inter_id" class="sub">
            <span class="id">{{ intersection.inter_id }}</span>
          </p>
          <div class="meta-grid">
            <div class="meta wide">
              <span class="k">进口车道</span>
              <span class="v">{{ armCount }} 进口 · {{ laneCount }} 车道</span>
            </div>
          </div>
          <div v-if="focusRole || protectRole" class="roles">
            <span v-if="focusRole" class="role focus">关注 {{ focusRole }}</span>
            <span v-if="protectRole" class="role protect">保护 {{ protectRole }}</span>
          </div>
        </header>

        <section v-if="showRuntime" class="block runtime">
          <span class="block-title">运行数据</span>
          <TransitionGroup name="item-in" tag="ul" class="list">
            <li v-for="item in runtimeItems" :key="item.id" class="row" :class="sevClass(item.severity)">
              <span class="tick">✓</span>
              <span class="label">{{ item.label }}</span>
              <span class="value">{{ item.value }}</span>
            </li>
          </TransitionGroup>
        </section>
      </aside>

      <!-- 右侧：问题验证、治理建议各为独立卡片（治理建议在验证下方） -->
      <div
        v-if="showEvidence || showSuggestion"
        class="narrative-right-column"
        aria-label="问题验证与治理建议"
      >
        <aside
          v-if="showEvidence"
          class="narrative-stack narrative-card evidence-card"
          aria-label="问题验证"
        >
          <section class="block evidence" :class="{ collapsed: evidenceCollapsed }">
            <button type="button" class="block-title toggle" @click="toggleEvidence">
              <span class="caret">{{ evidenceCollapsed ? '▸' : '▾' }}</span>
              问题验证
              <span v-if="evidenceCollapsed" class="collapsed-sum">{{ evidenceSummary }}</span>
            </button>
            <ul v-show="!evidenceCollapsed" class="list">
              <li v-for="(item, i) in evidenceItems" :key="i" class="row plain">
                <span class="tick">✓</span><span class="text">{{ item }}</span>
              </li>
            </ul>
          </section>
        </aside>

        <aside
          v-if="showSuggestion"
          class="narrative-stack narrative-card suggestion-card"
          aria-label="治理建议"
        >
          <section class="block suggestion">
            <span class="block-title accent">治理建议</span>
            <ul class="list">
              <li v-for="(item, i) in suggestionItems" :key="i" class="row plain accent">
                <span class="tick">→</span><span class="text">{{ item }}</span>
              </li>
            </ul>
            <div v-if="suggestionReferences.length" class="references">
              <span class="ref-label">参考依据</span>
              <div class="ref-chips">
                <button
                  v-for="ref in suggestionReferences"
                  :key="ref.id"
                  type="button"
                  class="ref-chip"
                  :class="`ref-${ref.type}`"
                  :title="`${ref.type === 'industry' ? '行业案例' : '路口案例'} · ${ref.id}\n${ref.summary ?? ''}\n点击查看案例库`"
                  @click="emit('openCase', ref.id)"
                >
                  <span class="ref-dot" />{{ ref.title }}
                </button>
              </div>
            </div>
          </section>
        </aside>
      </div>

      <!-- 经验沉淀卡：地图舞台右下角独立卡片 -->
      <aside
        v-if="showExperience"
        class="narrative-stack narrative-card experience-card experience-card--bottom-right"
        aria-label="经验沉淀与复用"
      >
        <span v-if="sedimentItems.length" class="card-title sediment-title">经验沉淀</span>
        <section
          v-for="grp in groupedSediment"
          :key="grp.level"
          class="block sediment"
        >
          <span class="block-title" :class="`lvl-title-${grp.level}`">{{ grp.title }}</span>
          <TransitionGroup name="item-in" tag="ul" class="list">
            <li
              v-for="(item, i) in grp.items"
              :key="`${grp.level}-${i}`"
              class="row plain"
            >
              <span
                v-for="tag in itemTags(item)"
                :key="tag"
                class="exp-tag"
                :class="{
                  'is-verified': tag === '已验证',
                  'is-pending': tag === '待验证',
                }"
              >{{ tag }}</span>
              <span class="text">{{ item.text }}</span>
            </li>
          </TransitionGroup>
        </section>

        <section v-if="reusedItems.length" class="block reused">
          <span class="block-title reused-title">经验复用</span>
          <ul class="list">
            <li v-for="(item, i) in reusedItems" :key="i" class="row plain">
              <span class="tick reuse-tick">↺</span><span class="text">{{ item }}</span>
            </li>
          </ul>
        </section>

        <section v-if="caseItems.length" class="block case">
          <span class="block-title case-title">同类场景专家经验</span>
          <div v-for="(sc, i) in caseItems" :key="i" class="case-scenario">
            <p class="case-name">{{ sc.scenario_name }}</p>
            <ul class="list">
              <li
                v-for="(p, pi) in sc.problems"
                :key="pi"
                class="row plain case-problem"
              >
                <span class="text">
                  <strong>{{ p.problem }}</strong>
                  <template v-if="p.solutions?.length">
                    —— {{ p.solutions.map((s) => s.name).join('、') }}
                  </template>
                </span>
              </li>
            </ul>
          </div>
        </section>
      </aside>
    </div>
  </Transition>
</template>

<style scoped>
.narrative-wrap {
  position: absolute;
  inset: 0;
  z-index: 16;
  pointer-events: none;
}

.narrative-stack {
  position: absolute;
  top: 12px;
  z-index: 16;
  width: min(300px, 40vw);
  max-height: calc(100% - 24px);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0;
  border-radius: 6px;
  background: rgba(6, 12, 22, 0.92);
  border: 1px solid rgba(0, 212, 240, 0.22);
  box-shadow: 0 10px 32px rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(6px);
  pointer-events: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 212, 240, 0.3) transparent;
  font-family: 'Inter', system-ui, sans-serif;
}

.narrative-stack--left {
  left: 12px;
}

.narrative-right-column {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 16;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: calc(100% - 24px);
  overflow-y: auto;
  pointer-events: none;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 212, 240, 0.3) transparent;
}

.narrative-right-column::-webkit-scrollbar {
  width: 4px;
}
.narrative-right-column::-webkit-scrollbar-thumb {
  border-radius: 2px;
  background: rgba(0, 212, 240, 0.3);
}

.narrative-right-column .narrative-stack {
  position: relative;
  top: auto;
  right: auto;
  max-height: none;
  flex-shrink: 0;
}

.suggestion-card {
  border-color: rgba(109, 255, 181, 0.28);
}

.references {
  margin-top: 8px;
  padding-top: 7px;
  border-top: 1px dashed rgba(120, 180, 150, 0.28);
}

.ref-label {
  display: block;
  margin-bottom: 5px;
  font-size: 10px;
  letter-spacing: 0.5px;
  color: rgba(170, 220, 190, 0.8);
}

.ref-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.ref-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid rgba(109, 255, 181, 0.32);
  background: rgba(109, 255, 181, 0.08);
  color: #d6ffe9;
  font-size: 10.5px;
  cursor: pointer;
  transition: background 0.16s ease;
}

.ref-chip:hover {
  background: rgba(109, 255, 181, 0.18);
}

.ref-chip .ref-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #6dffb5;
}

.ref-chip.ref-intersection {
  border-color: rgba(56, 189, 248, 0.4);
  background: rgba(56, 189, 248, 0.08);
  color: #d6f0ff;
}

.ref-chip.ref-intersection .ref-dot {
  background: #38bdf8;
}

.experience-card {
  border-color: rgba(201, 162, 39, 0.4);
}

/* 经验沉淀卡固定在地图舞台右下角（图例已删除腾出位置，最高 60% 高度，溢出内部滚动）。 */
.experience-card--bottom-right {
  right: 12px;
  bottom: 12px;
  top: auto;
  left: auto;
  max-height: calc(60% - 24px);
}
.card-title.sediment-title {
  display: block;
  padding: 10px 14px 4px;
  font-size: 11px;
  letter-spacing: 1px;
  font-weight: 700;
  color: #c9a227;
}
.lvl-title-cognition {
  color: #6dd0ff;
}
.lvl-title-diagnosis {
  color: #ffc266;
}
.lvl-title-solution {
  color: #6dffb5;
}
.block-title.reused-title {
  color: #ffb86b;
}
.block-title.case-title {
  color: rgba(0, 229, 255, 0.7);
}
.status-badge {
  flex-shrink: 0;
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid transparent;
  line-height: 1.5;
}
.status-badge.is-verified {
  color: #6dffb5;
  border-color: rgba(109, 255, 181, 0.45);
  background: rgba(109, 255, 181, 0.12);
}
.status-badge.is-pending {
  color: #ffb86b;
  border-color: rgba(255, 184, 107, 0.45);
  background: rgba(255, 184, 107, 0.12);
}
.exp-tag {
  flex-shrink: 0;
  display: inline-block;
  margin-right: 4px;
  margin-bottom: 2px;
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid rgba(126, 200, 255, 0.28);
  line-height: 1.5;
  color: #9ec8ff;
  background: rgba(126, 200, 255, 0.1);
}
.exp-tag.is-verified {
  color: #6dffb5;
  border-color: rgba(109, 255, 181, 0.45);
  background: rgba(109, 255, 181, 0.12);
}
.exp-tag.is-pending {
  color: #ffb86b;
  border-color: rgba(255, 184, 107, 0.45);
  background: rgba(255, 184, 107, 0.12);
}
.reuse-tick {
  color: #ffb86b !important;
}
.case-scenario {
  margin-bottom: 8px;
}
.case-name {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 700;
  color: #9fe0ff;
}
.case-problem .text {
  font-size: 10px;
  line-height: 1.5;
  color: rgba(210, 230, 245, 0.85);
}

.narrative-stack::-webkit-scrollbar {
  width: 4px;
}
.narrative-stack::-webkit-scrollbar-thumb {
  border-radius: 2px;
  background: rgba(0, 212, 240, 0.3);
}

/* 认知头 */
.head {
  padding: 12px 14px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #f0f8ff;
  letter-spacing: 0.3px;
}
.sub {
  margin: 3px 0 0;
  font-size: 10px;
  color: rgba(180, 200, 220, 0.65);
}
.sub .id {
  font-family: ui-monospace, monospace;
  letter-spacing: 0.4px;
}
.sub .dot {
  margin: 0 4px;
}
.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-top: 10px;
}
.meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  border-radius: 3px;
  background: rgba(0, 16, 32, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.meta.wide {
  grid-column: 1 / -1;
  flex-direction: row;
  align-items: baseline;
  justify-content: space-between;
}
.meta .k {
  font-size: 9px;
  letter-spacing: 0.5px;
  color: rgba(180, 205, 225, 0.55);
}
.meta .v {
  font-size: 13px;
  font-weight: 700;
  font-family: ui-monospace, monospace;
  color: #00e5ff;
}
.roles {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.role {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid transparent;
}
.role.focus {
  color: #ff8a6b;
  border-color: rgba(255, 107, 74, 0.45);
  background: rgba(255, 107, 74, 0.1);
}
.role.protect {
  color: #6dffb5;
  border-color: rgba(109, 255, 181, 0.4);
  background: rgba(109, 255, 181, 0.08);
}
.hint {
  margin: 10px 0 0;
  font-size: 9px;
  line-height: 1.5;
  color: rgba(170, 195, 215, 0.5);
}

/* 通用块 */
.block {
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.block:last-child {
  border-bottom: none;
}
.block-title {
  display: block;
  font-size: 10px;
  letter-spacing: 1px;
  color: rgba(0, 229, 255, 0.7);
  margin-bottom: 8px;
}
.block-title.accent {
  color: #6dffb5;
}
.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.row {
  display: flex;
  align-items: baseline;
  gap: 7px;
  font-size: 11px;
  line-height: 1.5;
  color: rgba(226, 246, 255, 0.92);
}
.row .tick {
  flex-shrink: 0;
  font-size: 10px;
  color: #00e5ff;
}
.row.accent .tick {
  color: #6dffb5;
}
.row .label {
  flex-shrink: 0;
  color: rgba(200, 222, 240, 0.7);
}
.row .value {
  margin-left: auto;
  font-family: ui-monospace, monospace;
  font-weight: 600;
  color: #e8f6ff;
  text-align: right;
}
.row.sev-high .value {
  color: #ff7b7b;
}
.row.sev-medium .value {
  color: #ffc266;
}
.row.sev-low .value {
  color: #6dffb5;
}
.row.plain .text {
  color: rgba(226, 246, 255, 0.9);
}

/* 问题验证折叠 */
.evidence .toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  font-family: inherit;
  text-align: left;
}
.evidence .caret {
  font-size: 9px;
}
.evidence .collapsed-sum {
  margin-left: 6px;
  font-size: 10px;
  letter-spacing: 0;
  color: rgba(200, 222, 240, 0.6);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.evidence.collapsed {
  background: rgba(0, 16, 32, 0.3);
}

/* 动效 */
.item-in-enter-active {
  transition: opacity 0.35s ease, transform 0.35s ease;
}
.item-in-enter-from {
  opacity: 0;
  transform: translateX(10px);
}
.item-in-move {
  transition: transform 0.3s ease;
}
.narrative-fade-enter-active,
.narrative-fade-leave-active {
  transition: opacity 0.4s ease, transform 0.4s ease;
}
.narrative-fade-enter-from,
.narrative-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
