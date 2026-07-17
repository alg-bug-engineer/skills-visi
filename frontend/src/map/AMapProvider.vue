<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { MapController } from './MapController'
import { provideAMap } from './useAMap'
import { usePresentationStore } from '@/stores/presentation'
import { buildHudMetrics } from './mapMarkers'
import { phaseReady } from '@/composables/useTimeline'
import { mockWarningsForScene } from './mapDataQuality'

const store = usePresentationStore()
const el = ref<HTMLDivElement | null>(null)
const controller = shallowRef<MapController | null>(null)
const loadError = ref<string | null>(null)
const mapZoom = ref(11)
const hiddenLabelCount = ref(0)
const sceneError = ref<string | null>(null)
provideAMap(controller)

let mapInstance: any = null

function syncMapZoom() {
  mapZoom.value = controller.value?.getZoom() ?? mapInstance?.getZoom?.() ?? mapZoom.value
}

const showHud = computed(
  () => store.currentAct >= 2 && phaseReady(store.response, 'diagnosis'),
)
const hudTitle = computed(() => store.ticket?.intersection_name ?? '运行指标')
const hudMetrics = computed(() => buildHudMetrics(store.response))
const mockWarningPaths = computed(() => {
  const act = store.acts[store.currentAct]
  return act ? mockWarningsForScene(act.scene, store.response) : []
})
function completeMapWithoutRenderer() {
  const idx = store.currentAct
  if (idx >= 0) store.completeActBarrier('map', idx, store.actBarrierKey)
}

async function applyActiveScene(replayCamera: boolean) {
  const idx = store.currentAct
  const key = store.actBarrierKey
  const act = store.acts[idx]
  if (!act || !controller.value) return
  try {
    sceneError.value = null
    const showMetrics = idx >= 2 && phaseReady(store.response, 'diagnosis')
    await controller.value.applyScene(act.scene, store.response, { showMetrics, replayCamera })
    hiddenLabelCount.value = controller.value.getHiddenLabelCount()
  } catch (error) {
    sceneError.value = `地图场景未完成：${String(error)}`
  } finally {
    if (replayCamera) store.completeActBarrier('map', idx, key)
  }
  syncMapZoom()
}

onMounted(async () => {
  const key = import.meta.env.VITE_AMAP_KEY
  const security = import.meta.env.VITE_AMAP_SECURITY
  if (!key || key === 'your_amap_key') {
    loadError.value = '未配置高德密钥（VITE_AMAP_KEY）'
    completeMapWithoutRenderer()
    return
  }
  if (security) {
    window._AMapSecurityConfig = { securityJsCode: security }
  }
  try {
    const AMap = await AMapLoader.load({ key, version: '2.0', plugins: [] })
    if (!el.value) return
    mapInstance = new AMap.Map(el.value, {
      viewMode: '3D',
      pitch: 20,
      zoom: 11,
      center: [117.02, 36.66],
      // 用户目标图：深蓝黑城市底图承载热力道路、白色流动点与霓虹扩散环。
      mapStyle: 'amap://styles/darkblue',
      showLabel: true,
    })
    controller.value = new MapController(AMap, mapInstance)
    syncMapZoom()
    mapInstance.on?.('zoomchange', syncMapZoom)
    mapInstance.on?.('zoomend', syncMapZoom)
    await applyActiveScene(true)
  } catch (e) {
    loadError.value = '高德地图加载失败：' + String(e)
    completeMapWithoutRenderer()
  }
})

onBeforeUnmount(() => {
  controller.value?.destroy()
  mapInstance?.destroy?.()
})

// 阶段变化 → 连贯应用地图场景（重放镜头 + 覆盖物）
watch(
  () => store.currentAct,
  async (idx) => {
    if (idx < 0) return
    if (!controller.value) {
      if (loadError.value) completeMapWithoutRenderer()
      return
    }
    await applyActiveScene(true)
  },
)

// 诊断 phase 到达后仅补绘覆盖物/指标（同一阶段，不重放镜头，避免二次运镜闪烁）
watch(
  () => store.response?.phases?.diagnosis,
  async (diag) => {
    if (!diag || store.currentAct < 0 || !controller.value || !store.actBarriers.map) return
    await applyActiveScene(false)
  },
)

// 用户重置/重新开始时，地图覆盖物与溯源结果同步清空并回到城市视角。
watch(
  () => store.mapResetSeq,
  async () => {
    if (!controller.value) return
    controller.value.clear()
    await controller.value.resetToCity()
  },
)
</script>

<template>
  <div class="amap-root">
    <div ref="el" class="amap-canvas" />
    <div class="map-atmosphere" aria-hidden="true" />
    <div
      v-if="store.currentAct < 0"
      class="map-landing-scan"
      data-testid="map-landing-scan"
      aria-hidden="true"
    />
    <div v-if="!loadError" class="zoom-debug" data-testid="zoom-indicator">
      zoom {{ mapZoom.toFixed(1) }}
    </div>
    <div v-if="mockWarningPaths.length" class="map-data-warning" role="alert" data-testid="map-mock-warning">
      ⚠ 演示模拟图层 · 生产待补数据（{{ mockWarningPaths.length }}）
    </div>
    <div v-else-if="sceneError" class="map-data-warning" role="alert">⚠ {{ sceneError }}</div>
    <div v-if="hiddenLabelCount" class="map-label-cluster" data-testid="map-label-cluster">+{{ hiddenLabelCount }} 重叠标注已收纳</div>
    <Transition name="fade">
      <div v-if="showHud && hudMetrics.length" class="map-hud us-panel" data-testid="map-hud">
        <div class="map-hud__title">{{ hudTitle }}</div>
        <div class="map-hud__grid">
          <div
            v-for="(m, i) in hudMetrics"
            :key="i"
            class="map-hud__cell"
            :class="`sev-${m.severity}`"
          >
            <span class="map-hud__label">{{ m.label }}</span>
            <span class="map-hud__value">{{ m.value }}</span>
          </div>
        </div>
      </div>
    </Transition>
    <div v-if="loadError" class="amap-fallback us-grid-bg">
      <div class="amap-fallback__msg us-panel">
        <p class="t">地图未就绪</p>
        <p class="d">{{ loadError }}</p>
        <p class="d">演出与数据面板不受影响；配置 <code>frontend/.env.local</code> 后刷新。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.amap-root,
.amap-canvas {
  position: absolute;
  inset: 0;
}
.map-atmosphere {
  position: absolute;
  inset: 0;
  z-index: 12;
  pointer-events: none;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 45%, rgba(48, 158, 255, 0.16), transparent 34%),
    linear-gradient(180deg, rgba(4, 12, 28, 0.2), rgba(1, 4, 10, 0.72)),
    linear-gradient(90deg, rgba(18, 98, 140, 0.035) 1px, transparent 1px),
    linear-gradient(rgba(10, 41, 65, 0.03) 1px, transparent 1px);
  background-size: auto, auto, 72px 72px, 72px 72px;
}
.map-landing-scan {
  position: absolute;
  z-index: 13;
  pointer-events: none;
  left: calc(var(--insight-w) + 12px);
  right: calc(var(--process-w) + 12px);
  height: 130px;
  top: -160px;
  background: linear-gradient(180deg, transparent, rgba(33, 137, 255, 0.08), rgba(57, 223, 255, 0.12), transparent);
  filter: blur(8px);
  animation: map-scan 7.5s linear infinite;
}
@keyframes map-scan {
  to { transform: translateY(calc(100vh + 320px)); }
}
.zoom-debug {
  position: absolute;
  top: 58px;
  left: calc(var(--insight-w) + 32px);
  z-index: 19;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid rgba(142, 203, 255, 0.28);
  background: rgba(2, 10, 22, 0.84);
  color: rgba(180, 210, 240, 0.88);
  font-size: 11px;
  font-family: var(--font-mono);
  letter-spacing: 0.5px;
  pointer-events: none;
}
.map-data-warning {
  position: absolute;
  top: 102px;
  left: 50%;
  z-index: 24;
  transform: translateX(-50%);
  padding: 7px 12px;
  border: 1px solid rgba(245, 166, 35, 0.72);
  border-radius: 8px;
  background: rgba(37, 22, 4, 0.94);
  color: #ffd08a;
  font-size: 12px;
  box-shadow: 0 0 18px rgba(245, 166, 35, 0.2);
}
.map-label-cluster {
  position: absolute;
  right: calc(var(--process-w) + 24px);
  bottom: 84px;
  z-index: 22;
  padding: 5px 9px;
  border: 1px solid rgba(26, 127, 255, 0.48);
  border-radius: 12px;
  background: rgba(7, 14, 26, 0.9);
  color: #8ecbff;
  font-size: 11px;
}
.map-hud {
  position: absolute;
  top: 88px;
  left: calc(var(--insight-w) + 32px);
  z-index: 18;
  padding: 10px 14px;
  min-width: 180px;
  pointer-events: none;
}
.map-hud__title {
  font-size: 12px;
  color: var(--text-dim);
  margin-bottom: 8px;
  letter-spacing: 1px;
}
.map-hud__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.map-hud__cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.map-hud__label {
  font-size: 10px;
  color: var(--text-mute);
}
.map-hud__value {
  font-size: 14px;
  font-weight: 700;
  font-family: var(--font-mono);
}
.map-hud__cell.sev-high .map-hud__value {
  color: var(--alarm-2);
}
.map-hud__cell.sev-medium .map-hud__value {
  color: var(--evidence-2);
}
.map-hud__cell.sev-low .map-hud__value {
  color: var(--protected);
}
.amap-fallback {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: var(--bg);
}
.amap-fallback__msg {
  padding: 20px 26px;
  max-width: 420px;
  text-align: center;
}
.amap-fallback__msg .t {
  color: var(--primary);
  font-family: var(--font-display);
  letter-spacing: 2px;
  margin: 0 0 8px;
}
.amap-fallback__msg .d {
  color: var(--text-dim);
  font-size: 13px;
  margin: 4px 0;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.4s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
:global(.us-node) {
  --c: var(--primary);
  padding: 3px 8px;
  border-radius: 10px;
  background: rgba(2, 8, 16, 0.82);
  border: 1px solid var(--c);
  color: var(--c);
  font-size: 12px;
  white-space: nowrap;
  box-shadow: 0 0 10px color-mix(in srgb, var(--c) 60%, transparent);
  transform: translate(-50%, -50%);
}
:global(.us-pulse-dot) {
  position: relative;
  --c: var(--primary);
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--c);
  border: 2px solid rgba(255, 255, 255, 0.85);
  box-shadow: 0 0 12px color-mix(in srgb, var(--c) 70%, transparent);
  transform: translate(-50%, -50%);
  pointer-events: none;
}
:global(.us-pulse-dot::before),
:global(.us-pulse-dot::after) {
  content: '';
  position: absolute;
  inset: -9px;
  border-radius: 50%;
  border: 1px solid color-mix(in srgb, var(--c) 74%, transparent);
  animation: map-node-ripple 2.2s ease-out infinite;
}
:global(.us-pulse-dot::after) {
  inset: -15px;
  animation-delay: 0.72s;
  opacity: 0.7;
}
@keyframes map-node-ripple {
  0% { opacity: 0.88; transform: scale(0.38); }
  75%, 100% { opacity: 0; transform: scale(1.72); }
}
:global(.us-particle) {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  box-shadow: 0 0 8px 2px currentColor;
}
:global(.map-flow-particle) {
  position: relative;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: radial-gradient(
    circle,
    rgba(255, 255, 255, 1) 0%,
    color-mix(in srgb, var(--c, #39dfff) 82%, #64e6ff) 28%,
    transparent 100%
  );
  box-shadow: 0 0 8px 2px color-mix(in srgb, var(--c, #39dfff) 82%, transparent);
  pointer-events: none;
}
/* ── 流量溯源单链路发光层（呈现逻辑对齐 references/流量溯源，配色本项目主题） ── */
:global(.trace-target-wrap) {
  position: relative;
  width: 18px;
  height: 18px;
}
:global(.trace-target-wrap > .trace-label) {
  position: absolute;
  left: 9px;
  top: -30px;
}
:global(.trace-node) {
  position: relative;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #39dfff;
  border: 2px solid rgba(255, 255, 255, 0.85);
  box-shadow: 0 0 14px rgba(57, 223, 255, 0.78), 0 0 34px rgba(57, 223, 255, 0.26);
  transition: opacity 0.45s ease;
}
:global(.trace-node::after) {
  content: '';
  position: absolute;
  inset: -8px;
  border-radius: 50%;
  border: 1px solid currentColor;
  color: rgba(57, 223, 255, 0.72);
  animation: trace-ripple 2.2s ease-out infinite;
}
:global(.trace-node::before) {
  display: none;
}
:global(.trace-node.is-down) {
  background: #2ed573;
  box-shadow: 0 0 14px rgba(46, 213, 115, 0.78), 0 0 34px rgba(46, 213, 115, 0.26);
}
:global(.trace-node.is-down::after) {
  color: rgba(46, 213, 115, 0.7);
}
:global(.trace-node.is-gov) {
  background: #2ed573;
  box-shadow: 0 0 16px rgba(46, 213, 115, 0.78), 0 0 36px rgba(46, 213, 115, 0.22);
}
:global(.trace-node.is-gov::after) {
  color: rgba(46, 213, 115, 0.68);
}
:global(.trace-node.is-target) {
  width: 18px;
  height: 18px;
  background: #dff7ff;
  border-color: rgba(255, 255, 255, 0.98);
  box-shadow: 0 0 18px rgba(255, 60, 31, 0.9), 0 0 44px rgba(255, 60, 31, 0.32);
}
:global(.trace-node.is-target::after) {
  inset: -11px;
  color: rgba(255, 60, 31, 0.82);
}
:global(.trace-node.is-target::before) {
  display: none;
}
:global(.trace-node.is-scaled) {
  border-width: 2px;
}
:global(.trace-node.is-scaled::after) {
  inset: -6px;
}
@keyframes trace-ripple {
  0% {
    opacity: 0.88;
    transform: scale(0.45);
  }
  75%,
  100% {
    opacity: 0;
    transform: scale(2.15);
  }
}
:global(.trace-label) {
  min-width: 88px;
  max-width: 200px;
  padding: 4px 8px;
  border-radius: 8px;
  border: 1px solid rgba(57, 223, 255, 0.42);
  background: rgba(6, 12, 24, 0.94);
  white-space: nowrap;
  font-family: var(--font-body, 'Inter', system-ui, sans-serif);
  box-shadow: 0 6px 22px rgba(0, 0, 0, 0.42);
  transform: translate(-50%, -50%);
}
:global(.map-marker),
:global(.trace-label),
:global(.topology-label),
:global(.channel-label),
:global(.us-node),
:global(.us-badge) {
  overflow-wrap: anywhere;
  font-variant-numeric: tabular-nums;
  transition: translate 180ms ease, opacity 180ms ease;
}
:global(.map-cinematic-reveal) {
  animation: cinematic-label-in 520ms cubic-bezier(.2,.8,.2,1) both;
}
@keyframes cinematic-label-in {
  from { opacity: 0; filter: blur(5px) brightness(1.8); }
  to { opacity: 1; filter: blur(0) brightness(1); }
}
:global(.trace-label.is-downstream) {
  border-color: rgba(57, 223, 255, 0.55);
  color: #7cf4ff;
  font-size: 11px;
  font-weight: 600;
  white-space: normal;
  line-height: 1.35;
}
:global(.trace-label .trace-name) {
  font-size: 12px;
  font-weight: 700;
  color: #eaf4ff;
  line-height: 1.3;
}
:global(.trace-label .trace-metric) {
  font-size: 10px;
  font-weight: 700;
  margin-top: 1px;
  line-height: 1.35;
}
:global(.topology-wrap) {
  position: relative;
  transform: translate(-50%, -50%);
  pointer-events: none;
}
:global(.topology-node) {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: #1f4d7c;
  border: 2px solid rgba(240, 248, 255, 0.9);
  box-shadow: 0 0 12px rgba(31, 77, 124, 0.65);
}
:global(.topology-node.is-target) {
  width: 18px;
  height: 18px;
  background: #ff3c1f;
  border: 2px solid rgba(255, 255, 255, 0.95);
  border-radius: 50%;
  box-shadow: 0 0 18px rgba(255, 60, 31, 0.9), 0 0 44px rgba(255, 60, 31, 0.32);
}
:global(.topology-wrap.is-hot .topology-node) {
  background: #39dfff;
  box-shadow: 0 0 14px rgba(57, 223, 255, 0.9), 0 0 34px rgba(57, 223, 255, 0.34);
}
:global(.topology-label) {
  position: absolute;
  left: 50%;
  top: 22px;
  transform: translateX(-50%);
  min-width: 108px;
  max-width: 168px;
  padding: 5px 8px;
  border: 1px solid rgba(31, 77, 124, 0.45);
  border-radius: 6px;
  background: rgba(6, 12, 24, 0.94);
  color: rgba(232, 244, 255, 0.92);
  font-size: 10px;
  font-weight: 700;
  line-height: 1.3;
  text-align: center;
  white-space: normal;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.45);
}
:global(.topology-wrap.is-offset-n .topology-label) {
  top: auto;
  bottom: 22px;
}
:global(.topology-wrap.is-offset-e .topology-label) {
  left: 22px;
  top: 50%;
  transform: translateY(-50%);
}
:global(.topology-wrap.is-offset-w .topology-label) {
  left: auto;
  right: 22px;
  top: 50%;
  transform: translateY(-50%);
}
:global(.topology-wrap.is-offset-s .topology-label) {
  top: 22px;
}
:global(.topology-label strong) {
  display: block;
  color: rgba(232, 244, 255, 0.95);
}
:global(.topology-label span) {
  display: block;
  margin-top: 2px;
  color: rgba(31, 77, 124, 0.92);
  font-size: 9px;
  font-weight: 500;
}
:global(.topology-wrap.is-hot .topology-label) {
  border-color: rgba(57, 223, 255, 0.6);
  color: #7cf4ff;
}
:global(.topology-wrap.is-hot .topology-label span) {
  color: #7cf4ff;
}
:global(.topology-wrap.is-primary .topology-node),
:global(.downstream-pin) {
  position: relative;
  width: 18px;
  height: 26px;
  margin: 0 auto;
  transform: translateY(-4px);
  filter: drop-shadow(0 0 10px rgba(57, 223, 255, 0.85));
}
:global(.downstream-pin__head) {
  width: 16px;
  height: 16px;
  margin: 0 auto;
  border-radius: 50% 50% 50% 0;
  transform: rotate(-45deg);
  background: #39dfff;
  border: 2px solid rgba(255, 255, 255, 0.95);
  box-shadow: inset 0 0 0 3px rgba(57, 223, 255, 0.35);
}
:global(.downstream-pin__stem) {
  width: 2px;
  height: 8px;
  margin: -2px auto 0;
  background: rgba(57, 223, 255, 0.95);
  border-radius: 1px;
}
:global(.topology-label__tag) {
  display: block;
  margin-bottom: 2px;
  color: #5ccfff;
  font-size: 9px;
  font-style: normal;
  font-weight: 800;
  letter-spacing: 0.04em;
}
:global(.topology-wrap.is-primary .topology-label) {
  border-color: rgba(57, 223, 255, 0.85);
  box-shadow: 0 0 0 1px rgba(57, 223, 255, 0.25), 0 8px 22px rgba(0, 0, 0, 0.5);
}
:global(.channel-metric-label) {
  transform: translate(-50%, -110%);
  min-width: 112px;
  max-width: 150px;
  padding: 5px 8px;
  border: 1px solid currentColor;
  border-radius: 4px;
  background: rgba(0, 6, 14, 0.92);
  font-size: 9px;
  line-height: 1.3;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.5);
}
:global(.channel-metric-label strong),
:global(.channel-metric-label span) {
  display: block;
}
:global(.channel-metric-label span) {
  margin-top: 1px;
  color: rgba(225, 238, 252, 0.88);
}
:global(.channel-approach-badge) {
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px solid var(--c, #ff3c1f);
  background: rgba(2, 8, 16, 0.94);
  color: var(--c, #ff3c1f);
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
  box-shadow: 0 0 12px color-mix(in srgb, var(--c) 50%, transparent);
  animation: marker-pop 0.35s ease-out;
  transform: translate(-50%, -120%);
  line-height: 1.35;
  text-align: center;
}
:global(.channel-approach-badge__metric) {
  margin-top: 2px;
  color: rgba(248, 250, 252, 0.88);
  font-size: 9px;
  font-weight: 600;
}
:global(.map-marker) {
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(7, 14, 26, 0.94);
  border: 1px solid rgba(26, 127, 255, 0.44);
  min-width: 72px;
  text-align: center;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
  animation: marker-pop 0.35s ease-out;
}
:global(.map-marker.sev-high) {
  border-color: rgba(255, 60, 31, 0.66);
}
:global(.map-marker.sev-medium) {
  border-color: rgba(245, 166, 35, 0.55);
}
:global(.map-marker.sev-low) {
  border-color: rgba(46, 213, 115, 0.5);
}
:global(.map-marker__badge) {
  display: block;
  font-size: 9px;
  color: rgba(200, 220, 240, 0.7);
  letter-spacing: 0.5px;
}
:global(.map-marker__value) {
  display: block;
  font-size: 15px;
  font-weight: 700;
  color: #e7f5ff;
  font-family: var(--font-mono);
}
:global(.map-marker.sev-high .map-marker__value) {
  color: #ff7b7b;
}
:global(.map-marker.sev-medium .map-marker__value) {
  color: #ffc266;
}
:global(.map-marker__sub) {
  display: block;
  font-size: 9px;
  color: rgba(180, 200, 220, 0.55);
  margin-top: 2px;
}
@keyframes marker-pop {
  from {
    opacity: 0;
    transform: scale(0.85);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
