<script setup lang="ts">
import { computed } from 'vue'
import type { TimingProfile } from '../../types/evidence'
import { renderTimingRingSvg } from '../../utils/timingRingDraw'

const props = defineProps<{
  profile: TimingProfile | null | undefined
  compact?: boolean
}>()

const svgHtml = computed(() => {
  const ring = props.profile?.ring_diagram
  if (!ring?.available || !ring.record) return ''
  const deficitLabels = (props.profile?.deficit_turns ?? []).map((t) => t.label)
  return renderTimingRingSvg(ring.record, {
    width: props.compact ? 402 : 320,
    height: props.compact ? 112 : 140,
    deficitLabels,
  })
})
</script>

<template>
  <div class="timing-ring-view" :class="{ compact }">
    <div v-if="svgHtml" class="ring-svg" v-html="svgHtml" />
    <p v-else class="empty">暂无环图数据</p>
  </div>
</template>

<style scoped>
.timing-ring-view {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ring-svg {
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.ring-svg :deep(svg) {
  display: block;
  width: 100%;
  height: auto;
}

.empty {
  font-size: 10px;
  color: rgba(150, 180, 210, 0.55);
  margin: 0;
}
</style>
