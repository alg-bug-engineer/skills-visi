<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { pct } from '@/utils/format'
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
const casePreview = computed(() => cards.value.slice(0, 2))

function roleTone(role?: string) {
  if (role?.includes('主')) return 'alarm'
  if (role?.includes('次')) return 'evidence'
  return 'primary'
}

function openCaseLibrary() {
  window.dispatchEvent(new CustomEvent('open-case-library'))
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

    <div class="cases" v-if="cards.length">
      <div class="cases__hd">
        <span>检测到相似案例</span>
        <span class="mute">匹配 {{ matched }} · 高相似 {{ highSim }}</span>
      </div>
      <div class="case-summary" data-testid="case-carousel">
        <article v-for="(c, i) in casePreview" :key="c.case_id ?? i" class="case">
          <header>
            <span class="case__title">{{ productCopy(c.title ?? '案例') }}</span>
            <span v-if="c.similarity != null" class="case__sim">{{ pct(c.similarity, 0) }}</span>
          </header>
          <p v-if="c.lesson" class="case__lesson">{{ productCopy(c.lesson) }}</p>
        </article>
      </div>
      <button type="button" class="case-link" @click="openCaseLibrary">查看案例库</button>
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
.case-summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.case {
  padding: 8px 10px;
  border-radius: 0;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(146, 161, 181, 0.35);
}
.case header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 4px;
}
.case__title {
  font-size: 12.5px;
  color: var(--text);
  font-weight: 600;
}
.case__sim {
  font-size: 11px;
  color: var(--primary);
}
.case p {
  margin: 3px 0;
  font-size: 11.5px;
  line-height: 1.45;
  color: var(--text-dim);
}
.case__lesson {
  color: var(--evidence-2) !important;
}
.case-link {
  margin-top: 8px;
  padding: 6px 0;
  border: 0;
  border-top: 1px solid rgba(146, 161, 181, 0.35);
  background: transparent;
  color: var(--primary);
  cursor: pointer;
  font-size: 12px;
  text-align: left;
}
.empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-mute);
}
</style>
