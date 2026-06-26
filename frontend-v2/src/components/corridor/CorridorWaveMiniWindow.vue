<script setup lang="ts">
import { computed } from 'vue'
import type { CorridorContext } from '../../types/evidence'
import CorridorWaveView from './CorridorWaveView.vue'

const props = defineProps<{
  corridor: CorridorContext | null | undefined
  visible: boolean
}>()

const emit = defineEmits<{ close: [] }>()

const hasCorridor = computed(
  () =>
    Boolean(props.corridor?.in_corridor) ||
    (props.corridor?.corridor_nodes?.length ?? 0) > 0,
)
</script>

<template>
  <Transition name="mini-slide">
    <div v-if="visible && hasCorridor" class="corridor-mini" role="complementary" aria-label="干线绿波小窗">
      <header class="mini-head">
        <span class="mini-title">干线绿波</span>
        <button type="button" class="mini-close" title="关闭小窗" @click="emit('close')">×</button>
      </header>
      <div class="mini-body">
        <CorridorWaveView :corridor="corridor" :compact="true" />
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.corridor-mini {
  position: absolute;
  right: 12px;
  top: 52px;
  left: auto;
  transform: none;
  z-index: 20;
  width: 300px;
  height: 152px;
  display: flex;
  flex-direction: column;
  border-radius: 4px;
  background: rgba(0, 10, 22, 0.94);
  border: 1px solid rgba(0, 230, 118, 0.28);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(10px);
  overflow: hidden;
  pointer-events: auto;
}

.mini-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border-bottom: 1px solid rgba(0, 230, 118, 0.15);
  flex-shrink: 0;
}

.mini-title {
  font-size: 10px;
  letter-spacing: 0.8px;
  color: rgba(0, 230, 118, 0.85);
  text-transform: uppercase;
}

.mini-close {
  border: none;
  background: transparent;
  color: rgba(200, 230, 255, 0.55);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  padding: 0 2px;
}

.mini-close:hover {
  color: #69f0ae;
}

.mini-body {
  flex: 1;
  min-height: 0;
  padding: 4px 6px 6px;
}

.mini-slide-enter-active,
.mini-slide-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.mini-slide-enter-from,
.mini-slide-leave-to {
  opacity: 0;
  transform: translate(-50%, 12px) scale(0.96);
}
</style>
