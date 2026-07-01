<script setup lang="ts">
import { computed } from 'vue'
import type { TimingProfile } from '../../types/evidence'
import TimingRingView from './TimingRingView.vue'

const props = defineProps<{
  profile: TimingProfile | null | undefined
  visible: boolean
  /** 嵌入左侧叙事卡：与运行数据同宽，非地图浮层 */
  embedded?: boolean
}>()

const emit = defineEmits<{ close: [] }>()

const hasRing = computed(() => Boolean(props.profile?.ring_diagram?.available))
</script>

<template>
  <Transition :name="embedded ? 'mini-embed' : 'mini-slide'">
    <div
      v-if="visible && hasRing"
      class="timing-mini"
      :class="{ embedded: embedded }"
      role="complementary"
      aria-label="配时环图小窗"
    >
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
  bottom: 56px;
  top: auto;
  z-index: 22;
  width: min(420px, calc(100% - 24px));
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

.timing-mini.embedded {
  position: relative;
  left: auto;
  bottom: auto;
  z-index: auto;
  width: 100%;
  height: 132px;
  border-radius: 0;
  border: none;
  border-top: 1px solid rgba(0, 212, 240, 0.15);
  box-shadow: none;
  backdrop-filter: none;
  background: transparent;
}

.mini-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border-bottom: 1px solid rgba(0, 212, 240, 0.15);
  flex-shrink: 0;
}

.embedded .mini-head {
  padding: 8px 12px 6px;
  border-bottom-color: rgba(0, 212, 240, 0.12);
}

.mini-title {
  font-size: 10px;
  letter-spacing: 0.8px;
  color: rgba(0, 229, 255, 0.85);
  text-transform: uppercase;
}

.embedded .mini-title {
  font-size: 11px;
  letter-spacing: 0.4px;
  text-transform: none;
  color: rgba(0, 229, 255, 0.75);
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

.embedded .mini-body {
  padding: 2px 8px 8px;
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

.mini-embed-enter-active,
.mini-embed-leave-active {
  transition: opacity 0.25s ease, max-height 0.25s ease;
}

.mini-embed-enter-from,
.mini-embed-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
