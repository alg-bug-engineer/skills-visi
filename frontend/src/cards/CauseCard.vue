<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import BaseCard from './BaseCard.vue'
import { productCopy } from '@/utils/productCopy'
import type { CaseCard } from '@/api/types'

const store = usePresentationStore()
const cause = computed(() => store.cause ?? null)
const cards = computed(() => cause.value?.case_cards?.cards ?? [])
const matched = computed(() => cause.value?.case_cards?.matched_count ?? 0)
const highSim = computed(() => cause.value?.case_cards?.high_similarity_count ?? 0)
const selectedId = ref<string | null>(null)

const selectedCard = computed(() => cards.value.find((c) => c.case_id === selectedId.value) ?? null)

watch(
  cards,
  (list) => {
    if (!list.length) {
      selectedId.value = null
      return
    }
    if (!list.some((c) => c.case_id === selectedId.value)) {
      selectedId.value = list[0].case_id ?? null
    }
  },
  { immediate: true },
)

function tierLabel(tier?: string) {
  if (tier === 'high') return '高度相似'
  if (tier === 'matched') return '一般匹配'
  return ''
}

function caseHeadline(card: CaseCard): string {
  if (card.title?.trim()) return productCopy(card.title)
  const dim = card.similarity_dimensions?.[0]?.label ?? card.similarity_points?.[0]
  if (dim) return productCopy(dim)
  if (card.help_summary?.trim()) return productCopy(card.help_summary).slice(0, 42)
  return '历史治理案例'
}

function casePreview(card: CaseCard): string {
  if (card.help_summary?.trim()) return productCopy(card.help_summary)
  const action = card.transferable_actions?.[0]
  if (action) return `可借鉴：${productCopy(action)}`
  const dim = card.similarity_dimensions?.[1]?.label ?? card.similarity_points?.[1]
  if (dim) return productCopy(dim)
  return '点击展开相似维度与借鉴说明'
}

function selectCase(card: CaseCard) {
  const id = card.case_id
  if (!id) return
  selectedId.value = id
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
  <BaseCard v-if="cause" title="案例校验" :act="7" tone="evidence">
    <div class="cases" v-if="cards.length">
      <div class="cases__hd">
        <span>相似案例检索</span>
        <span
          class="mute"
          title="命中数=关键词匹配案例总数；高相似=评分≥3 的条目；下方展示评分最高的代表案例"
        >
          命中 {{ matched }} · 高相似 {{ highSim }}
        </span>
      </div>
      <p class="cases__sub">按相似度展示代表案例摘要，点击条目展开完整维度与借鉴说明</p>

      <div class="case-list" data-testid="case-carousel">
        <button
          v-for="card in cards"
          :key="card.case_id"
          type="button"
          class="case-row"
          :class="{ active: selectedId === card.case_id }"
          data-testid="case-summary-row"
          @click="selectCase(card)"
        >
          <div class="case-row__hd">
            <span class="case-row__id us-mono">{{ card.case_id }}</span>
            <span v-if="tierLabel(card.similarity_tier)" class="case-row__tier">{{ tierLabel(card.similarity_tier) }}</span>
          </div>
          <strong class="case-row__title">{{ caseHeadline(card) }}</strong>
          <p class="case-row__preview">{{ casePreview(card) }}</p>
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
.case-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.case-row {
  width: 100%;
  text-align: left;
  padding: 10px 11px;
  border: 1px solid rgba(146, 161, 181, 0.35);
  background: rgba(255, 255, 255, 0.025);
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease;
}
.case-row:hover,
.case-row.active {
  border-color: var(--primary);
  background: rgba(26, 127, 255, 0.06);
}
.case-row__hd {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.case-row__id {
  font-size: 11px;
  font-weight: 700;
  color: var(--primary);
}
.case-row__tier {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  color: var(--evidence);
  border: 1px solid rgba(46, 213, 115, 0.35);
  background: rgba(46, 213, 115, 0.08);
}
.case-row__title {
  display: block;
  font-size: 12.5px;
  line-height: 1.4;
  color: var(--text);
  margin-bottom: 4px;
}
.case-row__preview {
  margin: 0;
  font-size: 11px;
  line-height: 1.45;
  color: var(--text-dim);
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
  border-radius: var(--radius-sm);
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
