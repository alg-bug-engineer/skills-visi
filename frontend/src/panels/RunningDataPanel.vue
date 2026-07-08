<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import DataMetricsCard from '@/cards/DataMetricsCard.vue'

const store = usePresentationStore()
const { diagnosis, revealedActs, acts } = storeToRefs(store)

const metricsReady = computed(() => {
  const idx = acts.value.findIndex((a) => a.reveal === 'metrics')
  if (idx < 0) return false
  return revealedActs.value.includes(idx) && !!diagnosis.value?.metrics
})
</script>

<template>
  <section
    v-show="metricsReady"
    class="running-data us-panel"
    data-testid="running-data-panel"
  >
    <header class="running-data__hd">
      <span class="dot" />
      <h2>运行数据</h2>
    </header>
    <div class="running-data__body">
      <DataMetricsCard variant="detail" />
    </div>
  </section>
</template>

<style scoped>
.running-data {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  flex: 0 1 42%;
}
.running-data__hd {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  flex: 0 0 auto;
  border-bottom: 1px solid var(--panel-border);
}
.running-data__hd h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 14px;
  letter-spacing: 2px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--evidence);
  box-shadow: var(--glow-primary);
}
.running-data__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 10px 10px;
}
.running-data__body :deep(.card) {
  margin: 0;
  border: none;
  background: transparent;
  box-shadow: none;
}
</style>
