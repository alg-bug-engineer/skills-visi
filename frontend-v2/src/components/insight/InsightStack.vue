<script setup lang="ts">
import { computed } from 'vue'
import type { InsightCardEntry } from '../../types/insight'
import DataMetricsCard from './DataMetricsCard.vue'
import ChronicHeatmapCard from './ChronicHeatmapCard.vue'

const props = defineProps<{
  cards: InsightCardEntry[]
  active?: boolean
}>()

/** 悬浮展示运行数据与常发日历 */
const sidebarCards = computed(() =>
  props.cards.filter((c) => c.kind === 'data' || c.kind === 'chronic'),
)
</script>

<template>
  <div v-if="sidebarCards.length" class="insight-stack">
    <TransitionGroup name="stack-in" tag="div" class="stack-list">
      <div v-for="card in sidebarCards" :key="card.id" class="stack-item">
        <DataMetricsCard v-if="card.kind === 'data'" :insight="card.insight" />
        <ChronicHeatmapCard v-else-if="card.kind === 'chronic'" :evidence="card.evidence" />
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.insight-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: fit-content;
  max-width: 100%;
}

.stack-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stack-item {
  min-width: 0;
  width: fit-content;
  max-width: 100%;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45);
}

.stack-in-enter-active {
  transition: opacity 0.4s ease, transform 0.4s ease;
}

.stack-in-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.stack-in-move {
  transition: transform 0.35s ease;
}
</style>
