<script setup lang="ts">
import { computed } from 'vue'
import type { CognitionPayload } from '../../types/map'
import ChannelizationView from '../channelization/ChannelizationView.vue'

const props = defineProps<{
  cognition: CognitionPayload | null
  highlightDirs?: string[]
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const hasArms = computed(() => (props.cognition?.arms?.length ?? 0) > 0)
</script>

<template>
  <Transition name="mini-slide">
    <div v-if="visible && hasArms" class="chan-mini" role="complementary" aria-label="渠化小窗">
      <header class="mini-head">
        <span class="mini-title">渠化示意</span>
        <button type="button" class="mini-close" title="关闭小窗" @click="emit('close')">×</button>
      </header>
      <div class="mini-body">
        <ChannelizationView
          :cognition="cognition"
          :highlight-dirs="highlightDirs"
          :compact="true"
        />
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.chan-mini {
  position: absolute;
  right: 16px;
  bottom: 100px;
  z-index: 11;
  width: 220px;
  height: 220px;
  display: flex;
  flex-direction: column;
  border-radius: 4px;
  background: rgba(0, 10, 22, 0.94);
  border: 1px solid rgba(0, 212, 240, 0.35);
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
  border-bottom: 1px solid rgba(0, 212, 240, 0.15);
  flex-shrink: 0;
}

.mini-title {
  font-size: 10px;
  letter-spacing: 0.8px;
  color: rgba(0, 229, 255, 0.85);
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
  color: #00e5ff;
}

.mini-body {
  flex: 1;
  min-height: 0;
}

.mini-body :deep(.channelization-view) {
  min-height: 0;
  border: none;
  background: transparent;
}

.mini-slide-enter-active,
.mini-slide-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.mini-slide-enter-from,
.mini-slide-leave-to {
  opacity: 0;
  transform: translate(12px, 12px) scale(0.96);
}
</style>
