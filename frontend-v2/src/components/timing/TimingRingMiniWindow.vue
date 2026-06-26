<script setup lang="ts">
import { computed } from 'vue'
import type { TimingProfile } from '../../types/evidence'
import TimingRingView from './TimingRingView.vue'

const props = defineProps<{
  profile: TimingProfile | null | undefined
  visible: boolean
}>()

const emit = defineEmits<{ close: [] }>()

const hasRing = computed(() => Boolean(props.profile?.ring_diagram?.available))
</script>

<template>
  <Transition name="mini-slide">
    <div v-if="visible && hasRing" class="timing-mini" role="complementary" aria-label="配时环图小窗">
      <header class="mini-head">
        <span class="mini-title">配时环图</span>
        <button type="button" class="mini-close" title="关闭小窗" @click="emit('close')">×</button>
      </header>
      <div class="mini-body">
        <TimingRingView :profile="profile" :compact="true" />
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.timing-mini {
  position: absolute;
  left: 12px;
  top: 52px;
  z-index: 20;
  width: 420px;
  height: 140px;
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
  padding: 4px 6px 6px;
}

.mini-slide-enter-active,
.mini-slide-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.mini-slide-enter-from,
.mini-slide-leave-to {
  opacity: 0;
  transform: translate(-12px, 12px) scale(0.96);
}
</style>
