<script setup lang="ts">
import { computed } from 'vue'
import type { CorridorContext } from '../../types/evidence'
import { renderCorridorWaveSvg } from '../../utils/corridorWaveDraw'

const props = defineProps<{
  corridor: CorridorContext | null | undefined
  compact?: boolean
}>()

const svgHtml = computed(() => {
  if (!props.corridor) return ''
  return renderCorridorWaveSvg(props.corridor, {
    width: props.compact ? 288 : 340,
    height: props.compact ? 124 : 150,
  })
})
</script>

<template>
  <div class="corridor-wave-view" :class="{ compact }">
    <div v-if="svgHtml" class="wave-svg" v-html="svgHtml" />
    <p v-else class="empty">暂无干线拓扑</p>
  </div>
</template>

<style scoped>
.corridor-wave-view {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wave-svg {
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.wave-svg :deep(svg) {
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
