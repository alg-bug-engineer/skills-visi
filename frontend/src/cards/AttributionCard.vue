<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import BaseCard from './BaseCard.vue'
import { productCopy } from '@/utils/productCopy'

const store = usePresentationStore()
const cause = computed(() => store.cause ?? null)
const ranking = computed(() => cause.value?.cause_ranking ?? [])
const scores = computed(() => cause.value?.cause_scores ?? {})
const maxScore = computed(() => Math.max(0.001, ...Object.values(scores.value)))
const narrative = computed(() =>
  productCopy(cause.value?.cause_analysis?.narrative ?? cause.value?.cause_analysis?.primary_cause ?? ''),
)

function roleTone(role?: string) {
  if (role?.includes('主')) return 'alarm'
  if (role?.includes('次')) return 'evidence'
  return 'primary'
}
</script>

<template>
  <BaseCard v-if="cause" title="归因分析" :act="4" tone="evidence">
    <ul v-if="ranking.length" class="rank" data-testid="attribution-ranking">
      <li v-for="r in ranking" :key="r.rank" :class="`tone-${roleTone(r.role)}`">
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
    <p v-else-if="!ranking.length" class="empty">暂无归因结果</p>
  </BaseCard>
</template>

<style scoped>
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
