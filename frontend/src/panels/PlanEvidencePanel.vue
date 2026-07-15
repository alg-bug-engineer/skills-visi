<script setup lang="ts">
import { computed } from 'vue'
import { t } from '@/labels/enums'
import type { PlanCandidate, PlanTimingEvidence } from '@/api/types'
import StageCards from '@/viz/StageCards.vue'
import DirectionIntensityPanel from '@/viz/DirectionIntensityPanel.vue'

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
const isVerificationBaseline = computed(
  () =>
    props.candidate?.plan_id === 'verification_plan' ||
    Boolean(timing.value?.verification_baseline),
)

type StageRow = NonNullable<PlanTimingEvidence['phase_stage_timing_list']>[number]

/** 核验门控：优先展示后端 proposed；无提案时只展示现状，前端不自行借绿编造 */
const stages = computed(() => {
  const proposed = proposedTiming.value?.phase_stage_timing_list
  if (proposed?.length) return proposed
  return timing.value?.phase_stage_timing_list ?? []
})

const showingProposedStages = computed(
  () =>
    isVerificationBaseline.value &&
    Boolean(proposedTiming.value?.phase_stage_timing_list?.length) &&
    stages.value.some((s) => (s.green_delta_s ?? 0) !== 0),
)

function deltasFromStages(list: StageRow[] | undefined) {
  let target = 0
  let donor = 0
  let sawTarget = false
  let sawDonor = false
  for (const s of list ?? []) {
    const d = Number(s.green_delta_s ?? 0) || 0
    const role = (s as StageRow & { role?: string }).role
    if (role === 'target') {
      target = d
      sawTarget = true
    } else if (role === 'donor') {
      donor = d
      sawDonor = true
    } else if (!sawTarget && d > target) {
      target = d
    } else if (!sawDonor && d < donor) {
      donor = d
    }
  }
  return { target, donor }
}

const proposedDelta = computed(() => {
  const p = proposedTiming.value
  if (!p || p.available === false) return null
  const fromStages = deltasFromStages(p.phase_stage_timing_list)
  const green =
    typeof p.target_green_delta_s === 'number' ? p.target_green_delta_s : fromStages.target
  const donor =
    typeof p.donor_green_delta_s === 'number' ? p.donor_green_delta_s : fromStages.donor
  const cycle = typeof p.cycle_delta_s === 'number' ? p.cycle_delta_s : 0
  if (!p.phase_stage_timing_list?.length && green === 0 && donor === 0) return null
  return { green, donor, cycle }
})

const proposedBannerHint = computed(() => {
  const d = proposedDelta.value
  if (!d) return ''
  return `目标相位 ${delta(d.green)} / 借绿相位 ${delta(d.donor)} / 周期 ${delta(d.cycle)}`
})

const intensity = computed(() => timing.value?.meta?.direction_intensity_list ?? [])
const periodLabel = computed(() => {
  const meta = timing.value?.meta
  const periods = meta?.target_periods
  if (Array.isArray(periods) && periods.length) {
    return periods[0].replace('-', '–')
  }
  if (meta?.period_label) return String(meta.period_label)
  return null
})
const evidenceComplete = computed(() => {
  if (!timing.value || timing.value.available === false) return false
  if (timing.value.current_cycle_s == null || timing.value.cycle_s == null) return false
  const baseStages = timing.value.phase_stage_timing_list ?? []
  if (!baseStages.length || !baseStages[0]?.current_timing) return false
  if (isVerificationBaseline.value) return true
  if (!stages.value[0]?.movements?.length) return false
  return intensity.value.length > 0
})

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
      <strong>后端未返回可审计方案证据</strong>
      <span>{{ timing?.reason || '缺少现状配时、释放方向或供需强度字段，前端不补假数据。' }}</span>
      <ul v-if="timing?.missing_fields?.length" class="fallback-missing">
        <li v-for="field in timing.missing_fields" :key="field">
          {{ t('field_label', field.includes('.') ? field.split('.').pop()! : field) }}
        </li>
      </ul>
    </div>
    <template v-else>
      <div class="banner" :class="{ verify: isVerificationBaseline }">
        <div>
          <b>{{ isVerificationBaseline ? '门控前 · 现状配时（不下发改配）' : '优化对比' }}</b>
          <span v-if="periodLabel">时段 {{ periodLabel }}</span>
          <span v-else-if="isVerificationBaseline">安全门控：先完成现场/检测动作</span>
          <span v-else>现状 vs 优化方案</span>
        </div>
        <p v-if="isVerificationBaseline">
          <strong>{{ sec(timing?.current_cycle_s) }}</strong>
          <em class="neutral">维持不变</em>
        </p>
        <p v-else>
          <span class="old">{{ sec(timing?.current_cycle_s) }}</span>
          <span>→</span>
          <strong>{{ sec(timing?.cycle_s) }}</strong>
          <em>{{ delta(timing?.cycle_delta_s) }}</em>
        </p>
      </div>
      <div
        v-if="isVerificationBaseline && proposedDelta"
        class="banner propose"
        data-testid="proposed-timing-banner"
      >
        <div>
          <b>门控后信控方案</b>
          <span>{{ proposedBannerHint }}</span>
        </div>
        <p>
          <strong>有效绿 {{ delta(proposedDelta.green) }}</strong>
          <em class="neutral">周期 {{ delta(proposedDelta.cycle) }}</em>
        </p>
      </div>
      <div
        v-else-if="isVerificationBaseline && proposedTiming?.available === false"
        class="banner propose degraded"
        data-testid="proposed-timing-unavailable"
      >
        <div>
          <b>门控后信控方案</b>
          <span>{{ proposedTiming.reason || '未能生成拟实施借绿配时，请核验相位命名/direction 是否可匹配' }}</span>
        </div>
      </div>
      <StageCards
        :stages="stages"
        :hint="showingProposedStages ? '现状 → 门控后拟实施（目标加绿 / 借绿相位）' : undefined"
      />
      <DirectionIntensityPanel :meta="timing?.meta" />
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
</style>
