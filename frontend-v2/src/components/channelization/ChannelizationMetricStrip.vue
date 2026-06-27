<script setup lang="ts">
import { computed } from 'vue'
import type { ChannelQueueArm } from '../../utils/cognitionChannelAdapter'
import { formatSaturation } from '../../utils/evidencePresentation'
import { THRESHOLDS } from '../../constants'

const props = defineProps<{
  queueArms: ChannelQueueArm[]
}>()

const cards = computed(() =>
  props.queueArms.map((arm) => {
    const satRatio = arm.satRatio
    return {
      ...arm,
      queueLabel:
        arm.queueM > 0 ? `排队约 ${Math.round(arm.queueM)}m` : '暂无排队',
      satLabel:
        satRatio != null ? `饱和度 ${formatSaturation(satRatio)}` : '饱和度 —',
      satHigh: satRatio != null && satRatio >= THRESHOLDS.saturationHigh,
    }
  }),
)
</script>

<template>
  <footer class="metric-strip">
    <ul class="arm-cards">
      <li v-for="card in cards" :key="card.dir4" class="arm-card" :class="{ hot: card.satHigh }">
        <span class="dir">{{ card.label }}</span>
        <span class="metric">
          <span class="pill queue">🚗 {{ card.queueLabel }}</span>
          <span class="pill sat" :class="{ high: card.satHigh }">📊 {{ card.satLabel }}</span>
        </span>
      </li>
    </ul>
  </footer>
</template>

<style scoped>
.metric-strip {
  flex-shrink: 0;
  padding: 8px 12px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(0, 0, 0, 0.28);
}

.arm-cards {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.arm-card {
  flex: 1 1 140px;
  padding: 6px 10px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.arm-card.hot {
  border-color: rgba(239, 83, 80, 0.45);
  background: rgba(239, 83, 80, 0.08);
}

.dir {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #e8edf5;
  margin-bottom: 4px;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.pill {
  font-size: 10px;
  color: rgba(200, 215, 230, 0.85);
}

.pill.sat.high {
  color: #ff8a80;
}
</style>
