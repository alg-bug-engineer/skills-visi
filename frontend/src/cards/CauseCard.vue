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
const cards = computed(() => cause.value?.case_cards?.cards ?? [])
const matched = computed(() => cause.value?.case_cards?.matched_count ?? 0)
const highSim = computed(() => cause.value?.case_cards?.high_similarity_count ?? 0)
const narrative = computed(() => productCopy(cause.value?.cause_analysis?.narrative ?? cause.value?.cause_analysis?.primary_cause ?? ''))
const caseIds = computed<string[]>(() =>
  cards.value.map((c) => c.case_id).filter((id): id is string => !!id),
)

function roleTone(role?: string) {
  if (role?.includes('主')) return 'alarm'
  if (role?.includes('次')) return 'evidence'
  return 'primary'
}

function openCase(caseId: string) {
  window.dispatchEvent(
    new CustomEvent('open-case-library', {
      detail: { tab: 'intersection', refId: `inter-case-${caseId}` },
    }),
  )
}
</script>

<template>
  <BaseCard v-if="cause" title="成因判断 · 相似案例" :act="6" tone="evidence">
    <ul class="rank">
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

    <p v-if="narrative" class="narrative">{{ narrative }}</p>

    <div class="cases" v-if="caseIds.length">
      <div class="cases__hd">
        <span>相似案例检索</span>
        <span class="mute">命中 {{ matched }} · 高相似 {{ highSim }}</span>
      </div>
      <p class="cases__sub">从高相似案例中选取 {{ caseIds.length }} 例代表案例，点击编号查看详情</p>
      <div class="case-ids" data-testid="case-carousel">
        <button
          v-for="id in caseIds"
          :key="id"
          type="button"
          class="case-id-chip us-mono"
          data-testid="case-id-chip"
          @click="openCase(id)"
        >
          {{ id }}
        </button>
      </div>
    </div>
    <p v-else class="empty">暂无高相似历史案例（数据暂缺）</p>
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
  margin: 0 0 12px;
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
.cases__hd {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 12px;
  color: var(--text);
  margin-bottom: 6px;
}
.cases__hd .mute {
  color: var(--text-mute);
  font-size: 11px;
}
.cases__sub {
  margin: 0 0 8px;
  font-size: 11px;
  color: var(--text-mute);
  line-height: 1.45;
}
.case-ids {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.case-id-chip {
  padding: 3px 10px;
  border-radius: 12px;
  border: 1px solid var(--primary);
  background: var(--primary-dim);
  color: var(--primary);
  font-size: 11.5px;
  cursor: pointer;
  transition: all 0.16s ease;
}
.case-id-chip:hover {
  background: var(--primary);
  color: var(--bg, #04101c);
}
.empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-mute);
}
</style>
