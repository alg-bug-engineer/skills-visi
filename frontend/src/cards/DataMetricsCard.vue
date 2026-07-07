<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { pct, ratio, meters, num, ratioTone } from '@/utils/format'
import { t } from '@/labels/enums'
import BaseCard from './BaseCard.vue'

const store = usePresentationStore()
const m = computed(() => store.diagnosis?.metrics ?? null)
const ov = computed(() => store.diagnosis?.overflow_verification ?? null)
const qrTone = computed(() => ratioTone(m.value?.queue_ratio))
const guTone = computed(() => {
  const g = m.value?.green_utilization
  return typeof g === 'number' && g < 0.5 ? 'evidence' : 'primary'
})
const verdictTone = computed(() => {
  const r = ov.value?.risk_level
  return r === 'high' || r === 'critical' ? 'alarm' : r === 'medium' ? 'evidence' : 'primary'
})
</script>

<template>
  <BaseCard v-if="m" title="运行数据单" :act="3" :tone="qrTone === 'alarm' ? 'alarm' : 'primary'">
    <div class="hero" :class="`tone-${qrTone}`">
      <span class="hero__num us-mono">{{ ratio(m.queue_ratio) }}</span>
      <span class="hero__lbl">排队比</span>
    </div>

    <div class="grid">
      <div class="cell"><span class="v us-mono">{{ meters(m.queue_length_m) }}</span><span class="k">排队长度</span></div>
      <div class="cell"><span class="v us-mono">{{ meters(m.storage_length_m) }}</span><span class="k">蓄车长度</span></div>
      <div class="cell"><span class="v us-mono">{{ pct(m.saturation) }}</span><span class="k">饱和度</span></div>
      <div class="cell" :class="`tone-${guTone}`">
        <span class="v us-mono">{{ pct(m.green_utilization) }}</span><span class="k">绿灯利用率</span>
      </div>
      <div class="cell"><span class="v us-mono">{{ num(m.stop_count, 2) }}</span><span class="k">停车次数</span></div>
      <div class="cell"><span class="v us-mono">{{ num(m.avg_delay_s, 1) }}s</span><span class="k">平均延误</span></div>
    </div>

    <div v-if="ov" class="verdict" :class="`tone-${verdictTone}`" data-testid="overflow-verdict">
      <span class="verdict__badge">溢出判定 · {{ t('risk_level', ov.risk_level) }}</span>
      <p>{{ ov.message ?? '—' }}</p>
    </div>

    <p class="src">数据来源：{{ t('data_source', store.diagnosis?.data_source) }}</p>
  </BaseCard>
</template>

<style scoped>
.hero {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
}
.hero__num {
  font-size: 40px;
  font-weight: 700;
  line-height: 1;
  color: var(--primary);
}
.tone-alarm .hero__num,
.hero.tone-alarm .hero__num {
  color: var(--alarm);
}
.hero.tone-evidence .hero__num {
  color: var(--evidence);
}
.hero__lbl {
  font-size: 13px;
  color: var(--text-mute);
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.03);
}
.cell .v {
  font-size: 15px;
  color: var(--text);
}
.cell.tone-evidence .v {
  color: var(--evidence);
}
.cell .k {
  font-size: 11px;
  color: var(--text-mute);
}
.verdict {
  margin-top: 12px;
  padding: 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--primary);
  background: var(--primary-dim);
}
.verdict.tone-alarm {
  border-color: var(--alarm);
  background: var(--alarm-dim);
}
.verdict.tone-evidence {
  border-color: var(--evidence);
  background: var(--evidence-dim);
}
.verdict__badge {
  font-size: 11px;
  color: var(--text);
  font-weight: 600;
}
.verdict p {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--text);
  line-height: 1.5;
}
.src {
  margin: 10px 0 0;
  font-size: 11px;
  color: var(--text-mute);
}
</style>
