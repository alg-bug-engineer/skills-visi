<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import type { CardKey } from '@/composables/useTimeline'
import DiagnosisTicketCard from '@/cards/DiagnosisTicketCard.vue'
import DataMetricsCard from '@/cards/DataMetricsCard.vue'
import BottleneckCard from '@/cards/BottleneckCard.vue'
import CorridorScanCard from '@/cards/CorridorScanCard.vue'
import CauseCard from '@/cards/CauseCard.vue'
import StrategyBoundaryCard from '@/cards/StrategyBoundaryCard.vue'

const store = usePresentationStore()
const { revealedActs } = storeToRefs(store)

const INSIGHT_CARDS: Record<string, unknown> = {
  ticket: DiagnosisTicketCard,
  metrics: DataMetricsCard,
  bottleneck: BottleneckCard,
  corridor: CorridorScanCard,
  cause: CauseCard,
  strategy: StrategyBoundaryCard,
}

const visible = computed(() =>
  revealedActs.value
    .map((i) => store.acts[i]?.reveal as CardKey | null)
    .filter((k): k is CardKey => !!k && k in INSIGHT_CARDS),
)

const scroller = ref<HTMLElement | null>(null)
watch(
  () => visible.value.length,
  async () => {
    await nextTick()
    scroller.value?.scrollTo({ top: scroller.value.scrollHeight, behavior: 'smooth' })
  },
)
</script>

<template>
  <aside class="insight" data-testid="insight-panel">
    <header class="insight__hd us-panel">
      <span class="dot" />
      <h2>诊断证据链</h2>
    </header>
    <div ref="scroller" class="insight__scroll">
      <TransitionGroup name="rise">
        <component :is="INSIGHT_CARDS[k]" v-for="(k, i) in visible" :key="k + i" />
      </TransitionGroup>
      <p v-if="!visible.length" class="hint">证据卡将随分析进程逐幕浮现…</p>
    </div>
  </aside>
</template>

<style scoped>
.insight {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 10px;
  overflow: hidden;
}
.insight__hd {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  flex: 0 0 auto;
}
.insight__hd h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 15px;
  letter-spacing: 3px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--evidence);
  box-shadow: var(--glow-primary);
}
.insight__scroll {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-right: 4px;
}
.hint {
  color: var(--text-mute);
  font-size: 13px;
  text-align: center;
  margin-top: 40px;
}
.rise-enter-active {
  transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
}
.rise-enter-from {
  opacity: 0;
  transform: translateY(24px) scale(0.98);
}
</style>
