<script setup lang="ts">
import { computed } from 'vue'
import type { PlanCandidate, PlanTimingEvidence } from '@/api/types'
import StageCards from '@/viz/StageCards.vue'
import DirectionIntensityPanel from '@/viz/DirectionIntensityPanel.vue'

const props = defineProps<{ candidate: PlanCandidate | null }>()

const timing = computed<PlanTimingEvidence | null>(() => props.candidate?.timing ?? null)
const stages = computed(() => timing.value?.phase_stage_timing_list ?? [])
const intensity = computed(() => timing.value?.meta?.direction_intensity_list ?? [])
const evidenceComplete = computed(() => {
  if (!timing.value || timing.value.available === false) return false
  if (timing.value.current_cycle_s == null || timing.value.cycle_s == null) return false
  if (!stages.value.length || !stages.value[0]?.current_timing || !stages.value[0]?.movements?.length) return false
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
        <li v-for="field in timing.missing_fields" :key="field">{{ field }}</li>
      </ul>
    </div>
    <template v-else>
      <div class="banner">
        <div>
          <b>优化对比</b>
          <span>现状 vs 优化方案</span>
        </div>
        <p>
          <span class="old">{{ sec(timing?.current_cycle_s) }}</span>
          <span>→</span>
          <strong>{{ sec(timing?.cycle_s) }}</strong>
          <em>{{ delta(timing?.cycle_delta_s) }}</em>
        </p>
      </div>
      <StageCards :stages="stages" />
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
