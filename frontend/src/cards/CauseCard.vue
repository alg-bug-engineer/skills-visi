<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { pct } from '@/utils/format'
import BaseCard from './BaseCard.vue'

const store = usePresentationStore()
const cause = computed(() => store.cause ?? null)
const ranking = computed(() => cause.value?.cause_ranking ?? [])
const scores = computed(() => cause.value?.cause_scores ?? {})
const maxScore = computed(() => Math.max(0.001, ...Object.values(scores.value)))
const cards = computed(() => cause.value?.case_cards?.cards ?? [])
const matched = computed(() => cause.value?.case_cards?.matched_count ?? 0)
const highSim = computed(() => cause.value?.case_cards?.high_similarity_count ?? 0)

function roleTone(role?: string) {
  if (role?.includes('主')) return 'alarm'
  if (role?.includes('次')) return 'evidence'
  return 'primary'
}
</script>

<template>
  <BaseCard v-if="cause" title="成因判断 · 相似案例" :act="6" tone="evidence">
    <ol class="rank">
      <li v-for="r in ranking" :key="r.rank" :class="`tone-${roleTone(r.role)}`">
        <span class="rank__role">{{ r.role }}</span>
        <span class="rank__cause">{{ r.cause }}</span>
        <span
          v-if="r.cause && scores[r.cause] != null"
          class="rank__bar"
          :style="{ width: `${(scores[r.cause] / maxScore) * 100}%` }"
        />
      </li>
    </ol>

    <div class="cases" v-if="cards.length">
      <div class="cases__hd">
        <span>相似案例</span>
        <span class="mute">匹配 {{ matched }} · 高相似 {{ highSim }}</span>
      </div>
      <div class="cases__scroll" data-testid="case-carousel">
        <article v-for="(c, i) in cards" :key="c.case_id ?? i" class="case">
          <header>
            <span class="case__title">{{ c.title ?? '案例' }}</span>
            <span v-if="c.similarity != null" class="case__sim">{{ pct(c.similarity, 0) }}</span>
          </header>
          <p v-if="c.action || c.historical_action" class="case__act">措施：{{ c.action ?? c.historical_action }}</p>
          <p v-if="c.outcome" class="case__out">结果：{{ c.outcome }}</p>
          <p v-if="c.lesson" class="case__lesson">经验：{{ c.lesson }}</p>
        </article>
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
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.03);
  overflow: hidden;
  display: flex;
  align-items: baseline;
  gap: 8px;
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
.cases__scroll {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.case {
  flex: 0 0 220px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: rgba(0, 229, 255, 0.05);
  border: 1px solid var(--panel-border);
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
.empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-mute);
}
</style>
