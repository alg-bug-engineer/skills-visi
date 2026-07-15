<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import BaseCard from './BaseCard.vue'
import { productCopy } from '@/utils/productCopy'

const MECHANISM_LABEL: Record<string, string> = {
  downstream_blocked: '下游回堵',
  local_release_insufficient: '本路口放行不足',
  discharge_anomaly: '放行效率异常，待核验',
  upstream_arrival_shock: '上游冲击',
  evidence_insufficient: '证据不足',
}

const store = usePresentationStore()
const cause = computed(() => store.cause ?? null)
const diagnosis = computed(() => store.diagnosis ?? null)
const mechanism = computed(
  () =>
    (diagnosis.value as { overflow_mechanism?: { primary?: string; status?: string } } | undefined)
      ?.overflow_mechanism ??
    (cause.value as { overflow_mechanism?: { primary?: string; status?: string } } | undefined)
      ?.overflow_mechanism ??
    null,
)
const ranking = computed(() => cause.value?.cause_ranking ?? [])
const scores = computed(() => cause.value?.cause_scores ?? {})
const maxScore = computed(() => Math.max(0.001, ...Object.values(scores.value)))
const narrative = computed(() =>
  productCopy(cause.value?.cause_analysis?.narrative ?? cause.value?.cause_analysis?.primary_cause ?? ''),
)

const mechanismLine = computed(() => {
  const code = mechanism.value?.primary
  if (!code) return null
  const label = MECHANISM_LABEL[code] ?? code
  const status = mechanism.value?.status
  if (status === 'hypothesis') return `${label}（待核验，非已确认主因）`
  return label
})

/** 机制锁定时，主因与机制行合并展示，ranking 只列次因/诱因，避免重复。 */
const displayRanking = computed(() => {
  const code = mechanism.value?.primary
  if (!code) return ranking.value
  return ranking.value.filter((r) => r.role !== '主因')
})

function roleTone(role?: string) {
  if (role?.includes('主')) return 'alarm'
  if (role?.includes('次')) return 'evidence'
  return 'primary'
}
</script>

<template>
  <BaseCard v-if="cause" title="归因分析" :act="4" tone="evidence">
    <p v-if="mechanismLine" class="mechanism" data-testid="attribution-mechanism">
      溢出机制：{{ mechanismLine }}
    </p>
    <ul v-if="displayRanking.length" class="rank" data-testid="attribution-ranking">
      <li v-for="r in displayRanking" :key="`${r.rank}-${r.role}`" :class="`tone-${roleTone(r.role)}`">
        <span class="rank__role">{{ r.role }}</span>
        <span class="rank__cause">{{ productCopy(r.cause) }}</span>
        <span
          v-if="r.cause && scores[r.cause] != null"
          class="rank__bar"
          :style="{ width: `${(scores[r.cause] / maxScore) * 100}%` }"
        />
      </li>
    </ul>

    <p v-if="narrative" class="narrative" data-testid="attribution-narrative">{{ narrative }}</p>
    <p v-else-if="!displayRanking.length" class="empty">暂无归因结果</p>
  </BaseCard>
</template>

<style scoped>
.mechanism {
  margin: 0 0 10px;
  padding: 8px 10px;
  border-left: 2px solid var(--evidence);
  background: rgba(255, 255, 255, 0.03);
  font-size: 12.5px;
  color: var(--text);
}
.rank {
  list-style: none;
  margin: 0 0 12px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rank li {
  position: relative;
  padding: 6px 8px;
  border-radius: 0;
  background: rgba(255, 255, 255, 0.03);
  overflow: hidden;
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.narrative {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--text-dim);
}
.rank__role {
  font-size: 11px;
  font-weight: 700;
  flex: 0 0 auto;
  color: var(--primary);
}
.tone-alarm .rank__role {
  color: var(--alarm);
}
.tone-evidence .rank__role {
  color: var(--evidence);
}
.rank__cause {
  font-size: 12.5px;
  color: var(--text-dim);
  position: relative;
  z-index: 1;
}
.rank__bar {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 2px;
  background: var(--evidence);
}
.tone-alarm .rank__bar {
  background: var(--alarm);
}
.empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-mute);
}
</style>
