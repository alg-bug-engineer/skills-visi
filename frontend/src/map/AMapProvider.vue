<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { MapController } from './MapController'
import { provideAMap } from './useAMap'
import { usePresentationStore } from '@/stores/presentation'
import { buildHudMetrics } from './mapMarkers'
import { phaseReady } from '@/composables/useTimeline'

const store = usePresentationStore()
const el = ref<HTMLDivElement | null>(null)
const controller = shallowRef<MapController | null>(null)
const loadError = ref<string | null>(null)
const mapZoom = ref(11)
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

onMounted(async () => {
  const key = import.meta.env.VITE_AMAP_KEY
  const security = import.meta.env.VITE_AMAP_SECURITY
  if (!key || key === 'your_amap_key') {
    loadError.value = '未配置高德密钥（VITE_AMAP_KEY）'
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
      mapStyle: 'amap://styles/dark',
      showLabel: true,
    })
    controller.value = new MapController(AMap, mapInstance)
    syncMapZoom()
    mapInstance.on?.('zoomchange', syncMapZoom)
    mapInstance.on?.('zoomend', syncMapZoom)
  } catch (e) {
    loadError.value = '高德地图加载失败：' + String(e)
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
    const act = store.acts[idx]
    if (!act || !controller.value) return
    const showMetrics = idx >= 2 && phaseReady(store.response, 'diagnosis')
    await controller.value.applyScene(act.scene, store.response, {
      showMetrics,
      replayCamera: true,
    })
    syncMapZoom()
  },
)

// 诊断 phase 到达后仅补绘覆盖物/指标（同一阶段，不重放镜头，避免二次运镜闪烁）
watch(
  () => store.response?.phases?.diagnosis,
  async (diag) => {
    if (!diag || store.currentAct < 0 || !controller.value) return
    const act = store.acts[store.currentAct]
    if (act)
      await controller.value.applyScene(act.scene, store.response, {
        showMetrics: true,
        replayCamera: false,
      })
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
    <div v-if="!loadError" class="zoom-debug" data-testid="zoom-indicator">
      zoom {{ mapZoom.toFixed(1) }}
    </div>
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
.zoom-debug {
  position: absolute;
  top: 58px;
  left: calc(var(--insight-w) + 32px);
  z-index: 19;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid rgba(142, 203, 255, 0.28);
  background: rgba(2, 8, 16, 0.72);
  color: rgba(180, 210, 240, 0.88);
  font-size: 11px;
  font-family: var(--font-mono);
  letter-spacing: 0.5px;
  pointer-events: none;
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
:global(.us-particle) {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  box-shadow: 0 0 8px 2px currentColor;
}

/* ── 流量溯源单链路发光层（呈现逻辑对齐 references/流量溯源，配色本项目主题） ── */
:global(.trace-node) {
  position: relative;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #f5a623;
  border: 2px solid rgba(255, 255, 255, 0.85);
  box-shadow: 0 0 14px rgba(245, 166, 35, 0.78), 0 0 34px rgba(245, 166, 35, 0.26);
  transition: opacity 0.45s ease;
}
:global(.trace-node)::after {
  content: '';
  position: absolute;
  inset: -8px;
  border-radius: 50%;
  border: 1px solid currentColor;
  color: rgba(245, 166, 35, 0.72);
  animation: trace-ripple 2.2s ease-out infinite;
}
:global(.trace-node.is-down) {
  background: #0ea5e9;
  box-shadow: 0 0 14px rgba(14, 165, 233, 0.78), 0 0 34px rgba(14, 165, 233, 0.26);
}
:global(.trace-node.is-down)::after {
  color: rgba(56, 189, 248, 0.7);
}
:global(.trace-node.is-gov) {
  background: #2ed573;
  box-shadow: 0 0 16px rgba(46, 213, 115, 0.78), 0 0 36px rgba(46, 213, 115, 0.22);
}
:global(.trace-node.is-gov)::after {
  color: rgba(46, 213, 115, 0.68);
}
:global(.trace-node.is-target) {
  width: 18px;
  height: 18px;
  background: #ff5050;
  box-shadow: 0 0 18px rgba(255, 80, 80, 0.9), 0 0 44px rgba(255, 80, 80, 0.32);
}
:global(.trace-node.is-target)::after {
  inset: -11px;
  color: rgba(255, 80, 80, 0.82);
}
:global(.trace-node.is-scaled) {
  border-width: 2px;
}
:global(.trace-node.is-scaled)::after {
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
  border: 1px solid rgba(245, 166, 35, 0.42);
  background: rgba(6, 12, 24, 0.94);
  white-space: nowrap;
  font-family: var(--font-body, 'Inter', system-ui, sans-serif);
  box-shadow: 0 6px 22px rgba(0, 0, 0, 0.42);
  transform: translate(-50%, -50%);
}
:global(.trace-label.is-downstream) {
  border-color: rgba(56, 189, 248, 0.55);
  color: #bae6fd;
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
  background: #8aa0b8;
  border: 2px solid rgba(240, 248, 255, 0.9);
  box-shadow: 0 0 12px rgba(138, 160, 184, 0.65);
}
:global(.topology-node.is-target) {
  width: 18px;
  height: 18px;
  background: #ff5050;
  border: 2px solid rgba(255, 255, 255, 0.95);
  border-radius: 50%;
  box-shadow: 0 0 18px rgba(255, 80, 80, 0.9), 0 0 44px rgba(255, 80, 80, 0.32);
}
:global(.topology-wrap.is-hot .topology-node) {
  background: #38bdf8;
  box-shadow: 0 0 14px rgba(56, 189, 248, 0.9), 0 0 34px rgba(14, 165, 233, 0.34);
}
:global(.topology-label) {
  position: absolute;
  left: 50%;
  top: 18px;
  transform: translateX(-50%);
  min-width: 96px;
  max-width: 160px;
  padding: 4px 7px;
  border: 1px solid rgba(138, 160, 184, 0.45);
  border-radius: 6px;
  background: rgba(6, 12, 24, 0.9);
  color: rgba(232, 244, 255, 0.92);
  font-size: 10px;
  font-weight: 700;
  line-height: 1.25;
  text-align: center;
  white-space: normal;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.38);
}
:global(.topology-label strong) {
  display: block;
  color: rgba(232, 244, 255, 0.95);
}
:global(.topology-label span) {
  display: block;
  margin-top: 2px;
  color: rgba(138, 160, 184, 0.92);
  font-size: 9px;
  font-weight: 500;
}
:global(.topology-wrap.is-hot .topology-label) {
  border-color: rgba(56, 189, 248, 0.6);
  color: #bae6fd;
}
:global(.topology-wrap.is-hot .topology-label span) {
  color: #bae6fd;
}
:global(.channel-metric-label) {
  transform: translate(-50%, -50%);
  min-width: 112px;
  padding: 4px 7px;
  border: 1px solid currentColor;
  border-radius: 4px;
  background: rgba(0, 6, 14, 0.9);
  font-size: 9px;
  line-height: 1.25;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.42);
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
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid var(--c, #ff5050);
  background: rgba(2, 8, 16, 0.92);
  color: var(--c, #ff5050);
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
  box-shadow: 0 0 12px color-mix(in srgb, var(--c) 50%, transparent);
  animation: marker-pop 0.35s ease-out;
}
:global(.map-marker) {
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(2, 8, 16, 0.9);
  border: 1px solid rgba(0, 229, 255, 0.35);
  min-width: 72px;
  text-align: center;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
  animation: marker-pop 0.35s ease-out;
}
:global(.map-marker.sev-high) {
  border-color: rgba(255, 80, 80, 0.6);
}
:global(.map-marker.sev-medium) {
  border-color: rgba(245, 166, 35, 0.55);
}
:global(.map-marker.sev-low) {
  border-color: rgba(109, 255, 181, 0.45);
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
