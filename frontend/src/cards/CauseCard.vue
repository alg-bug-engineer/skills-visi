<script setup lang="ts">
import { computed, ref } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import BaseCard from './BaseCard.vue'
import { productCopy } from '@/utils/productCopy'
import type { CaseCard } from '@/api/types'

const store = usePresentationStore()
const cause = computed(() => store.cause ?? null)
const ranking = computed(() => cause.value?.cause_ranking ?? [])
const scores = computed(() => cause.value?.cause_scores ?? {})
const maxScore = computed(() => Math.max(0.001, ...Object.values(scores.value)))
const cards = computed(() => cause.value?.case_cards?.cards ?? [])
const matched = computed(() => cause.value?.case_cards?.matched_count ?? 0)
const highSim = computed(() => cause.value?.case_cards?.high_similarity_count ?? 0)
const narrative = computed(() => productCopy(cause.value?.cause_analysis?.narrative ?? cause.value?.cause_analysis?.primary_cause ?? ''))
const selectedId = ref<string | null>(null)

const selectedCard = computed(() => cards.value.find((c) => c.case_id === selectedId.value) ?? null)

function roleTone(role?: string) {
  if (role?.includes('主')) return 'alarm'
  if (role?.includes('次')) return 'evidence'
  return 'primary'
}

function tierLabel(tier?: string) {
  if (tier === 'high') return '高度相似'
  if (tier === 'matched') return '一般匹配'
  return ''
}

function selectCase(card: CaseCard) {
  const id = card.case_id
  if (!id) return
  selectedId.value = selectedId.value === id ? null : id
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

    <div class="cases" v-if="cards.length">
      <div class="cases__hd">
        <span>相似案例检索</span>
        <span
          class="mute"
          title="命中数=关键词匹配案例总数；高相似=评分≥3 的条目；下方展示评分最高的 3 条代表案例"
        >
          命中 {{ matched }} · 高相似 {{ highSim }}
        </span>
      </div>
      <p class="cases__sub">从高相似案例中选取 {{ cards.length }} 例代表案例，点击编号展开相似维度与借鉴说明</p>
      <div class="case-ids" data-testid="case-carousel">
        <button
          v-for="card in cards"
          :key="card.case_id"
          type="button"
          class="case-id-chip us-mono"
          :class="{ active: selectedId === card.case_id }"
          data-testid="case-id-chip"
          @click="selectCase(card)"
        >
          {{ card.case_id }}
          <span v-if="tierLabel(card.similarity_tier)" class="tier">{{ tierLabel(card.similarity_tier) }}</span>
        </button>
      </div>

      <article v-if="selectedCard" class="case-detail" data-testid="case-detail">
        <header class="case-detail__hd">
          <strong>{{ selectedCard.case_id }}</strong>
          <span v-if="selectedCard.title" class="case-detail__title">{{ selectedCard.title }}</span>
        </header>

        <p v-if="selectedCard.help_summary" class="help" data-testid="case-help">
          {{ selectedCard.help_summary }}
        </p>

        <section v-if="selectedCard.structured_tags && Object.keys(selectedCard.structured_tags).length" class="block">
          <h4>案例标签</h4>
          <div class="tag-groups" data-testid="case-structured-tags">
            <div
              v-for="(values, group) in selectedCard.structured_tags"
              :key="group"
              class="tag-group"
            >
              <span class="tag-group__label">{{ group }}</span>
              <span v-for="(v, i) in values" :key="`${group}-${i}`" class="tag-chip">{{ v }}</span>
            </div>
          </div>
        </section>

        <section v-if="selectedCard.similarity_dimensions?.length" class="block">
          <h4>为何相似</h4>
          <ul class="dim-list" data-testid="case-dimensions">
            <li v-for="(d, i) in selectedCard.similarity_dimensions" :key="`${d.key}-${i}`">
              {{ d.label }}
            </li>
          </ul>
        </section>
        <section v-else-if="selectedCard.similarity_points?.length" class="block">
          <h4>为何相似</h4>
          <ul class="dim-list" data-testid="case-dimensions">
            <li v-for="(p, i) in selectedCard.similarity_points" :key="i">{{ p }}</li>
          </ul>
        </section>

        <section v-if="selectedCard.transferable_actions?.length" class="block">
          <h4>可借鉴</h4>
          <ul class="action-list" data-testid="case-transferable">
            <li v-for="(a, i) in selectedCard.transferable_actions" :key="i">{{ a }}</li>
          </ul>
        </section>

        <section v-if="selectedCard.caveats?.length" class="block">
          <h4>不宜直接套用</h4>
          <ul class="caveat-list" data-testid="case-caveats">
            <li v-for="(c, i) in selectedCard.caveats" :key="i">{{ c }}</li>
          </ul>
        </section>

        <button
          v-if="selectedCard.case_id"
          type="button"
          class="link-btn"
          data-testid="case-open-library"
          @click="openCase(selectedCard.case_id!)"
        >
          在沉淀面板查看完整条目 →
        </button>
      </article>
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
  cursor: help;
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
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.case-id-chip.active {
  background: var(--primary);
  color: var(--bg, #04101c);
}
.case-id-chip:hover {
  background: var(--primary);
  color: var(--bg, #04101c);
}
.tier {
  font-size: 9px;
  opacity: 0.85;
}
.case-detail {
  margin-top: 10px;
  padding: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
}
.case-detail__hd {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}
.case-detail__title {
  font-size: 11px;
  color: var(--text-mute);
  line-height: 1.4;
}
.help {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--text);
  line-height: 1.5;
}
.block {
  margin-bottom: 8px;
}
.block h4 {
  margin: 0 0 4px;
  font-size: 10.5px;
  font-weight: 700;
  color: var(--text-mute);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.dim-list,
.action-list,
.caveat-list {
  margin: 0;
  padding-left: 16px;
  font-size: 11.5px;
  line-height: 1.45;
  color: var(--text-dim);
}
.caveat-list {
  color: var(--alarm);
}
.link-btn {
  margin-top: 4px;
  padding: 0;
  border: none;
  background: none;
  color: var(--primary);
  font-size: 11px;
  cursor: pointer;
}
.tag-groups {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.tag-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.tag-group__label {
  font-size: 10px;
  color: var(--text-mute);
  flex: 0 0 auto;
  min-width: 52px;
}
.tag-chip {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-dim);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-mute);
}
</style>
