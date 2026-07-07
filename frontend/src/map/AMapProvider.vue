<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { MapController } from './MapController'
import { provideAMap } from './useAMap'
import { usePresentationStore } from '@/stores/presentation'

const store = usePresentationStore()
const el = ref<HTMLDivElement | null>(null)
const controller = shallowRef<MapController | null>(null)
const loadError = ref<string | null>(null)
provideAMap(controller)

let mapInstance: any = null

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

// 幕次变化 → 应用地图场景
watch(
  () => store.currentAct,
  (idx) => {
    const act = store.acts[idx]
    if (act && controller.value) controller.value.applyScene(act.scene, store.response)
  },
)
</script>

<template>
  <div class="amap-root">
    <div ref="el" class="amap-canvas" />
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
</style>
