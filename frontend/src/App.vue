<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import { useVoiceNarration } from '@/composables/useVoiceNarration'
import AMapProvider from '@/map/AMapProvider.vue'
import UnderstandingPanel from '@/panels/UnderstandingPanel.vue'
import RunningDataPanel from '@/panels/RunningDataPanel.vue'
import ProcessPanel from '@/panels/ProcessPanel.vue'
import BottomDock from '@/panels/BottomDock.vue'
import DownstreamTopologyInset from '@/panels/DownstreamTopologyInset.vue'
import SkillSolidifyOverlay from '@/panels/SkillSolidifyOverlay.vue'
import SkillBuildDrawer from '@/panels/SkillBuildDrawer.vue'
import { sceneEvidencePolicy } from '@/map/sceneEvidencePolicy'
import { buildVoiceCue, resetActVoiceKeys, voiceCueForAct } from '@/services/voiceStepSync'
import { resetAbsorptionVoiceKeys } from '@/services/voiceAbsorptionSync'
import { phaseReady } from '@/composables/useTimeline'
import { useStepPauseKeyboard } from '@/composables/useStepPause'

const store = usePresentationStore()
const { status, dock, fullscreen, planMinimized, rollbackBanner, toast, currentAct, mapResetSeq, stepPaused } =
  storeToRefs(store)
const voice = useVoiceNarration()
const voiceEnabled = voice.enabled
const voicePlaying = voice.playing
const voiceError = voice.error

useStepPauseKeyboard()

store.setVoiceBarrier(voice.whenIdle)
store.setVoiceInterrupt(voice.interrupt)
store.setVoiceEnqueue((cue) => voice.enqueue(cue))

const running = computed(() => status.value !== 'idle')
/** 下游承接关系图谱卡片：暂时隐藏（保留组件与地图层逻辑）。 */
const SHOW_DOWNSTREAM_TOPOLOGY_INSET = false

const showTopologyInset = computed(() => {
  if (!SHOW_DOWNSTREAM_TOPOLOGY_INSET) return false
  const scene = store.activeAct?.scene
  return running.value && !!scene && sceneEvidencePolicy(scene).downstreamTopology
})

watch(toast, (v) => {
  if (v) window.setTimeout(() => store.clearToast(), 4200)
})

/** 进入 act 立即触发语音，与打字机并行；下一步仍等语音 barrier。 */
watch(
  () => [currentAct.value, mapResetSeq.value] as const,
  ([idx, seq]) => {
    if (idx < 0) return
    voice.enqueue(voiceCueForAct(store.acts[idx] ?? null, String(seq), store.response))
  },
  { immediate: true },
)

/** 快照就绪后预合成后续 act 语音，降低进入步骤时的等待。 */
watch(
  () => [store.response, mapResetSeq.value, currentAct.value] as const,
  ([resp, seq, cur]) => {
    if (!resp || cur < 0) return
    const runKey = String(seq)
    const from = Math.max(0, cur)
    const to = Math.min(store.acts.length - 1, cur + 3)
    for (let i = from; i <= to; i++) {
      const act = store.acts[i]
      if (!phaseReady(resp, act.phase)) continue
      voice.prefetch(buildVoiceCue(act, runKey, resp))
    }
  },
  { immediate: true, deep: true },
)

watch(mapResetSeq, () => {
  resetActVoiceKeys()
  resetAbsorptionVoiceKeys()
  voice.interrupt()
})

onBeforeUnmount(() => {
  store.setVoiceBarrier(null)
  store.setVoiceInterrupt(null)
  store.setVoiceEnqueue(null)
  voice.interrupt()
})

function toggleVoice() {
  const next = !voiceEnabled.value
  voice.setEnabled(next)
  if (!next) store.interruptVoice()
}
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
        <button
          class="ghost voice-toggle"
          :class="{ 'voice-toggle--off': !voiceEnabled, 'voice-toggle--playing': voicePlaying }"
          type="button"
          data-testid="voice-toggle"
          :aria-pressed="voiceEnabled ? 'true' : 'false'"
          :title="voiceEnabled ? '关闭语音播报' : '打开语音播报'"
          @click="toggleVoice"
        >
          <span class="speaker-shape" aria-hidden="true">
            <span class="speaker-core" />
            <span class="speaker-wave speaker-wave--one" />
            <span class="speaker-wave speaker-wave--two" />
          </span>
          <span class="voice-toggle__label">语音播报</span>
          <span v-if="voiceError" class="voice-toggle__error">{{ voiceError }}</span>
        </button>
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

    <Transition name="fade">
      <div v-if="stepPaused && running" class="pause-toast us-panel" data-testid="step-pause-toast">
        已暂停 · 空格继续
      </div>
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
.voice-toggle {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.voice-toggle__error {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: max-content;
  max-width: 260px;
  padding: 5px 8px;
  border: 1px solid rgba(255, 88, 88, 0.45);
  background: rgba(35, 10, 12, 0.92);
  color: var(--alarm);
  font-size: 11px;
  line-height: 1.35;
  pointer-events: none;
  white-space: normal;
}
.speaker-shape {
  position: relative;
  display: inline-block;
  width: 15px;
  height: 14px;
}
.speaker-core::before {
  content: '';
  position: absolute;
  left: 0;
  top: 4px;
  width: 5px;
  height: 6px;
  border-radius: 2px 0 0 2px;
  background: currentColor;
}
.speaker-core::after {
  content: '';
  position: absolute;
  left: 4px;
  top: 2px;
  width: 0;
  height: 0;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  border-right: 7px solid currentColor;
}
.speaker-wave {
  position: absolute;
  top: 2px;
  right: 0;
  width: 7px;
  height: 10px;
  border: 1px solid currentColor;
  border-left: 0;
  border-radius: 0 10px 10px 0;
  opacity: 0.8;
}
.speaker-wave--one {
  right: 2px;
  transform: scale(0.68);
}
.speaker-wave--two {
  right: -2px;
}
.voice-toggle--off .speaker-wave {
  display: none;
}
.voice-toggle--off .speaker-shape::after {
  content: '';
  position: absolute;
  left: 1px;
  top: 6px;
  width: 15px;
  height: 1px;
  background: currentColor;
  transform: rotate(-42deg);
}
.voice-toggle--playing {
  color: var(--primary);
  border-color: rgba(63, 211, 255, 0.58);
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
.pause-toast {
  position: absolute;
  top: 64px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 46;
  padding: 10px 22px;
  font-size: 14px;
  font-weight: 600;
  color: #ffc107;
  border: 1px solid rgba(255, 193, 7, 0.5);
  background: rgba(28, 22, 4, 0.92);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45);
  text-align: center;
  pointer-events: none;
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
