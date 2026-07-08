<script setup lang="ts">
import { computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import AMapProvider from '@/map/AMapProvider.vue'
import UnderstandingPanel from '@/panels/UnderstandingPanel.vue'
import RunningDataPanel from '@/panels/RunningDataPanel.vue'
import ProcessPanel from '@/panels/ProcessPanel.vue'
import BottomDock from '@/panels/BottomDock.vue'
import DownstreamTopologyInset from '@/panels/DownstreamTopologyInset.vue'
import SkillSolidifyOverlay from '@/panels/SkillSolidifyOverlay.vue'
import SkillBuildDrawer from '@/panels/SkillBuildDrawer.vue'
import { sceneEvidencePolicy } from '@/map/sceneEvidencePolicy'

const store = usePresentationStore()
const { status, dock, fullscreen, planMinimized, rollbackBanner, toast } = storeToRefs(store)

const running = computed(() => status.value !== 'idle')
const showTopologyInset = computed(() => {
  const scene = store.activeAct?.scene
  return running.value && !!scene && sceneEvidencePolicy(scene).downstreamTopology
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
        <span class="brand__name">济南交通决策控制台</span>
        <span class="brand__sub">交通信控处置闭环</span>
      </div>
      <div class="topbar__right">
        <button class="ghost" @click="store.toggleFullscreen()">
          {{ fullscreen ? '退出专注' : '地图专注' }}
        </button>
        <button v-if="running" class="ghost" @click="store.reset()">重置</button>
      </div>
    </header>

    <Transition name="fade">
      <aside v-show="running && !fullscreen" class="rail rail--left">
        <div class="left-stack">
          <UnderstandingPanel class="left-stack__understanding" />
          <RunningDataPanel class="left-stack__running" />
        </div>
      </aside>
    </Transition>

    <div
      v-if="!running && !fullscreen"
      class="home-drawer"
      data-testid="home-exp-drawer"
    >
      <div class="home-drawer__panel">
        <UnderstandingPanel />
      </div>
      <div class="home-drawer__tab" aria-hidden="true">
        <span class="home-drawer__tab-text">经验库 · 案例库</span>
      </div>
    </div>

    <Transition name="fade">
      <aside v-show="running && !fullscreen" class="rail rail--right">
        <ProcessPanel />
      </aside>
    </Transition>

    <Transition name="fade">
      <div v-show="showTopologyInset && !fullscreen" class="topology-slot">
        <DownstreamTopologyInset />
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
        'dock-slot--plan-min': dock === 'plan' && planMinimized,
      }"
    >
      <BottomDock />
    </footer>

    <SkillBuildDrawer v-if="!fullscreen" />

    <SkillSolidifyOverlay />
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
  bottom: 16px;
  z-index: 20;
  width: var(--insight-w);
}
.rail--left {
  left: 16px;
}
.home-drawer {
  position: absolute;
  top: 64px;
  bottom: 16px;
  left: 0;
  z-index: 25;
  display: flex;
  align-items: stretch;
  transform: translateX(calc(-1 * var(--insight-w)));
  transition: transform 0.32s cubic-bezier(0.22, 1, 0.36, 1);
}
.home-drawer:hover {
  transform: translateX(16px);
}
.home-drawer__panel {
  width: var(--insight-w);
  height: 100%;
  min-height: 0;
  display: flex;
  overflow: hidden;
}
.home-drawer__panel > * {
  flex: 1;
  min-height: 0;
}
.home-drawer__tab {
  width: 30px;
  border-radius: 0 12px 12px 0;
  background: linear-gradient(180deg, rgba(10, 22, 40, 0.95), rgba(6, 14, 26, 0.95));
  border: 1px solid var(--panel-border);
  border-left: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 2px 0 18px rgba(0, 0, 0, 0.35);
}
.home-drawer__tab-text {
  writing-mode: vertical-rl;
  letter-spacing: 3px;
  font-size: 12px;
  color: var(--text-dim);
}
.home-drawer:hover .home-drawer__tab-text {
  color: var(--primary);
}
.rail--right {
  right: 16px;
  width: var(--process-w);
}
.left-stack {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 10px;
  min-height: 0;
}
.left-stack__understanding {
  flex: 1 1 58%;
  min-height: 0;
}
.left-stack__running {
  flex: 0 1 42%;
  min-height: 160px;
}
.topology-slot {
  position: absolute;
  left: calc(var(--insight-w) + 32px);
  right: calc(var(--process-w) + 32px);
  bottom: 88px;
  z-index: 20;
  display: flex;
  justify-content: flex-start;
  pointer-events: none;
}
.topology-slot > * {
  pointer-events: auto;
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
  left: calc(var(--insight-w) + 32px);
  right: calc(var(--process-w) + 32px);
  top: auto;
  bottom: 16px;
  width: auto;
  transform: none;
  padding: 10px 16px;
}
.dock-slot--plan {
  top: 64px;
  bottom: 16px;
  left: calc(var(--insight-w) + 32px);
  right: calc(var(--process-w) + 32px);
  width: auto;
  transform: none;
  border-radius: 8px;
  border-color: rgba(142, 203, 255, 0.36);
  box-shadow:
    0 -18px 70px rgba(0, 0, 0, 0.58),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
  animation: plan-rise 0.55s cubic-bezier(0.22, 1, 0.36, 1);
}
.dock-slot--plan-min {
  top: auto;
  height: 60px;
  overflow: hidden;
  padding: 0;
  animation: none;
}
@keyframes plan-rise {
  from {
    opacity: 0;
    transform: translateY(24px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
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
