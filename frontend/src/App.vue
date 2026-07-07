<script setup lang="ts">
import { computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import AMapProvider from '@/map/AMapProvider.vue'
import UnderstandingPanel from '@/panels/UnderstandingPanel.vue'
import ProcessPanel from '@/panels/ProcessPanel.vue'
import BottomDock from '@/panels/BottomDock.vue'
import ChannelizationInset from '@/panels/ChannelizationInset.vue'

const store = usePresentationStore()
const { status, dock, fullscreen, rollbackBanner, toast } = storeToRefs(store)

const running = computed(() => status.value !== 'idle')
const showInset = computed(() => {
  const kind = store.activeAct?.scene.kind
  return running.value && (kind === 'lane' || kind === 'intersection')
})

watch(toast, (v) => {
  if (v) window.setTimeout(() => store.clearToast(), 4200)
})
</script>

<template>
  <div class="stage us-grid-bg" :class="{ 'stage--focus': fullscreen }">
    <AMapProvider />

    <header class="topbar">
      <div class="brand">
        <span class="brand__logo">◈</span>
        <span class="brand__name">TRAFFIC&nbsp;AGENT</span>
        <span class="brand__sub">排队溢出决策推演</span>
      </div>
      <div class="topbar__right">
        <button class="ghost" @click="store.toggleFullscreen()">
          {{ fullscreen ? '退出专注' : '地图专注' }}
        </button>
        <button v-if="running" class="ghost" @click="store.reset()">重置</button>
      </div>
    </header>

    <Transition name="fade">
      <aside v-show="running && !fullscreen" class="rail rail--left" :class="{ 'rail--up': dock === 'plan' }">
        <UnderstandingPanel />
      </aside>
    </Transition>

    <Transition name="fade">
      <aside v-show="running && !fullscreen" class="rail rail--right" :class="{ 'rail--up': dock === 'plan' }">
        <ProcessPanel />
      </aside>
    </Transition>

    <Transition name="fade">
      <div v-show="showInset && !fullscreen" class="inset-slot">
        <ChannelizationInset />
      </div>
    </Transition>

    <Transition name="slide-up">
      <div v-if="rollbackBanner" class="rollback">
        <span>⟲ {{ rollbackBanner }}</span>
        <button @click="store.clearRollback()">×</button>
      </div>
    </Transition>

    <Transition name="fade">
      <div v-if="toast" class="toast us-panel">{{ toast }}</div>
    </Transition>

    <footer
      class="dock-slot us-panel"
      :class="{
        'dock-slot--input': dock === 'input',
        'dock-slot--running': dock === 'running',
        'dock-slot--plan': dock === 'plan',
      }"
    >
      <BottomDock />
    </footer>
  </div>
</template>

<style scoped>
.stage {
  position: relative;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: var(--bg);
}
.topbar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 52px;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  background: linear-gradient(180deg, rgba(2, 8, 16, 0.9), transparent);
  pointer-events: none;
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 10px;
  pointer-events: auto;
}
.brand__logo {
  color: var(--primary);
  font-size: 18px;
  text-shadow: var(--glow-primary);
}
.brand__name {
  font-family: var(--font-display);
  letter-spacing: 4px;
  font-size: 16px;
  color: var(--text);
}
.brand__sub {
  font-size: 12px;
  color: var(--text-dim);
}
.topbar__right {
  display: flex;
  gap: 8px;
  pointer-events: auto;
}
.ghost {
  padding: 5px 12px;
  border-radius: 8px;
  border: 1px solid var(--panel-border);
  background: rgba(2, 8, 16, 0.6);
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
}
.ghost:hover {
  color: var(--primary);
  border-color: var(--primary);
}
.rail {
  position: absolute;
  top: 64px;
  bottom: 150px;
  z-index: 20;
  width: var(--insight-w);
  transition: bottom 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.rail--up {
  bottom: calc(46vh + 28px);
}
.rail--left {
  left: 16px;
}
.rail--right {
  right: 16px;
  width: var(--process-w);
}
.inset-slot {
  position: absolute;
  right: calc(var(--process-w) + 32px);
  bottom: 160px;
  z-index: 20;
}
.dock-slot {
  position: absolute;
  left: 16px;
  right: 16px;
  bottom: 16px;
  z-index: 25;
  padding: 14px 18px;
  border-radius: var(--radius);
  transition:
    top 0.85s cubic-bezier(0.22, 1, 0.36, 1),
    bottom 0.85s cubic-bezier(0.22, 1, 0.36, 1),
    left 0.85s cubic-bezier(0.22, 1, 0.36, 1),
    right 0.85s cubic-bezier(0.22, 1, 0.36, 1),
    width 0.85s cubic-bezier(0.22, 1, 0.36, 1),
    transform 0.85s cubic-bezier(0.22, 1, 0.36, 1);
}
.dock-slot--input {
  left: 50%;
  right: auto;
  top: 50%;
  bottom: auto;
  width: min(640px, calc(100% - 32px));
  transform: translate(-50%, -50%);
}
.dock-slot--running {
  left: 16px;
  right: 16px;
  top: auto;
  bottom: 16px;
  width: auto;
  transform: none;
  padding: 10px 16px;
}
.dock-slot--plan {
  height: 46vh;
  left: 16px;
  right: 16px;
  top: auto;
  bottom: 16px;
  width: auto;
  transform: none;
}
.rollback {
  position: absolute;
  top: 60px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 40;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 16px;
  border-radius: 10px;
  background: var(--alarm-dim);
  border: 1px solid var(--alarm);
  color: var(--alarm-2);
  font-size: 13px;
}
.rollback button {
  background: none;
  border: none;
  color: var(--alarm-2);
  cursor: pointer;
  font-size: 16px;
}
.toast {
  position: absolute;
  bottom: 170px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 45;
  padding: 12px 20px;
  font-size: 13px;
  color: var(--text);
  max-width: 60vw;
  text-align: center;
}
.stage--focus .dock-slot {
  opacity: 0.96;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.35s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
.slide-up-enter-active {
  transition: all 0.4s;
}
.slide-up-enter-from {
  opacity: 0;
  transform: translate(-50%, 12px);
}
</style>
