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
provideAMap(controller)

let mapInstance: any = null

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
  } catch (e) {
    loadError.value = '高德地图加载失败：' + String(e)
  }
})

onBeforeUnmount(() => {
  controller.value?.destroy()
  mapInstance?.destroy?.()
})

// 幕次变化 → 连贯应用地图场景
watch(
  () => store.currentAct,
  async (idx) => {
    const act = store.acts[idx]
    if (!act || !controller.value) return
    const metrics = idx >= 2 && phaseReady(store.response, 'diagnosis')
    await controller.value.applyScene(act.scene, store.response, metrics)
  },
)

// 诊断 phase 到达后补绘指标（流式门控）
watch(
  () => store.response?.phases?.diagnosis,
  async (diag) => {
    if (!diag || store.currentAct < 0 || !controller.value) return
    const act = store.acts[store.currentAct]
    if (act) await controller.value.applyScene(act.scene, store.response, true)
  },
)
</script>

<template>
  <div class="amap-root">
    <div ref="el" class="amap-canvas" />
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
.map-hud {
  position: absolute;
  top: 64px;
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
