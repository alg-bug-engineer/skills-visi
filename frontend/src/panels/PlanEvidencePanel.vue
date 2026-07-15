<script setup lang="ts">
import { computed } from 'vue'
import { t } from '@/labels/enums'
import type { PlanCandidate, PlanTimingEvidence } from '@/api/types'
import StageCards from '@/viz/StageCards.vue'
import DirectionIntensityPanel from '@/viz/DirectionIntensityPanel.vue'
import {
  actualCycleDelta,
  hasCoreTimingEvidence,
  isLegacyVerificationPlan,
  trialTimingOf,
} from '@/utils/planPresentation'

type ProposedTiming = PlanTimingEvidence & {
  label?: string
  target_green_delta_s?: number
  donor_green_delta_s?: number
  requested_target_green_delta_s?: number
  reason?: string
  available?: boolean
}

const props = defineProps<{ candidate: PlanCandidate | null }>()

const timing = computed<PlanTimingEvidence | null>(() => props.candidate?.timing ?? null)
const proposedTiming = computed(
  () => (props.candidate as { proposed_timing?: ProposedTiming } | null)?.proposed_timing ?? null,
)
const isVerificationBaseline = computed(() => isLegacyVerificationPlan(props.candidate))
const displayTiming = computed<PlanTimingEvidence | null>(() => trialTimingOf(props.candidate))

const stages = computed(() => {
  return displayTiming.value?.phase_stage_timing_list ?? []
})

const periodLabel = computed(() => {
  const meta = displayTiming.value?.meta ?? timing.value?.meta
  const periods = meta?.target_periods
  if (Array.isArray(periods) && periods.length) {
    return periods[0].replace('-', '–')
  }
  if (meta?.period_label) return String(meta.period_label)
  return null
})
const evidenceComplete = computed(() => hasCoreTimingEvidence(displayTiming.value))
const partialEvidenceWarning = computed(() => {
  if (!evidenceComplete.value) return null
  const shown = displayTiming.value
  const missing = shown?.missing_fields ?? []
  if (shown?.available !== false && !missing.length) return null
  return '已展示后端返回的真实配时；缺少的释放方向或供需强度将在对应位置单独标注，不影响现状与试运行秒数对照。'
})

const cycleDelta = computed(() => actualCycleDelta(displayTiming.value))

function sec(value?: number | null) {
  return typeof value === 'number' && Number.isFinite(value) ? `${value}s` : '—'
}

function delta(value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return value === 0 ? '±0s' : `${value > 0 ? '+' : ''}${value}s`
}
</script>

<template>
  <section class="evidence" data-testid="plan-evidence-panel">
    <div v-if="!evidenceComplete" class="fallback">
      <strong>{{ isVerificationBaseline ? '当前只有现状配时，尚未形成可下发方案' : '后端未返回可审计方案证据' }}</strong>
      <span>{{ proposedTiming?.reason || timing?.reason || '缺少现状周期或逐阶段现状/建议秒数，无法绘制配时对照。' }}</span>
      <ul v-if="timing?.missing_fields?.length" class="fallback-missing">
        <li v-for="field in timing.missing_fields" :key="field">
          {{ t('field_label', field.includes('.') ? field.split('.').pop()! : field) }}
        </li>
      </ul>
    </div>
    <template v-else>
      <p v-if="partialEvidenceWarning" class="audit-warning" data-testid="partial-evidence-warning">
        {{ partialEvidenceWarning }}
      </p>
      <div class="banner trial">
        <div>
          <b>建议试运行方案</b>
          <span v-if="periodLabel">时段 {{ periodLabel }}</span>
          <span v-else>现状配时 → 试运行配时</span>
        </div>
        <p>
          <span class="old">{{ sec(displayTiming?.current_cycle_s) }}</span>
          <span>→</span>
          <strong>{{ sec(displayTiming?.cycle_s) }}</strong>
          <em :class="{ neutral: cycleDelta === 0 }">{{ delta(cycleDelta) }}</em>
        </p>
      </div>
      <StageCards
        :stages="stages"
        hint="现状 → 试运行（目标加绿 / 其他相位借绿）"
      />
      <DirectionIntensityPanel :meta="displayTiming?.meta || timing?.meta" />
    </template>
  </section>
</template>

<style scoped>
.evidence {
  display: grid;
  gap: 12px;
}
.banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(0, 229, 255, 0.26);
  border-radius: 8px;
  background: linear-gradient(90deg, rgba(0, 229, 255, 0.12), rgba(109, 255, 181, 0.08));
}
.banner div {
  display: grid;
  gap: 2px;
}
.banner b {
  color: var(--primary);
  font-size: 14px;
}
.banner span {
  color: var(--text-dim);
  font-size: 12px;
}
.banner p {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0;
}
.old {
  text-decoration: line-through;
}
.banner strong {
  color: var(--protected);
  font-size: 28px;
}
.banner em {
  color: var(--alarm);
  font-style: normal;
  font-weight: 700;
}
.banner em.neutral {
  color: var(--text-dim);
  font-weight: 600;
}
.banner.verify {
  border-color: rgba(109, 255, 181, 0.28);
  background: linear-gradient(90deg, rgba(109, 255, 181, 0.1), rgba(0, 229, 255, 0.06));
}
.banner.propose {
  border-color: rgba(0, 229, 255, 0.35);
  background: linear-gradient(90deg, rgba(0, 229, 255, 0.14), rgba(109, 255, 181, 0.08));
}
.banner.propose strong {
  font-size: 18px;
}
.banner.propose.degraded {
  border-color: rgba(245, 166, 35, 0.35);
  background: rgba(245, 166, 35, 0.08);
}
.fallback {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid rgba(245, 166, 35, 0.3);
  border-radius: 8px;
  background: rgba(245, 166, 35, 0.08);
}
.fallback strong {
  color: var(--evidence);
}
.fallback span {
  color: var(--text-dim);
  font-size: 12px;
}
.fallback-missing {
  margin: 4px 0 0;
  padding-left: 18px;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.45;
}
.audit-warning {
  margin: 0;
  padding: 8px 10px;
  border-left: 2px solid var(--evidence);
  background: rgba(245, 166, 35, 0.08);
  color: var(--text-dim);
  font-size: 11px;
  line-height: 1.5;
}
</style>
