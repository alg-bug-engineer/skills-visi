<script setup lang="ts">
/* eslint-disable @typescript-eslint/no-explicit-any */
import { onMounted, ref, shallowRef, watch } from 'vue'
import type { ColorMode, ScanRecord } from '../types/scan'
import { createMap, loadAmap } from '../utils/amap'
import { legendFor, recordColor } from '../utils/scanColors'

const props = defineProps<{
  records: ScanRecord[]
  colorMode: ColorMode
  selectedId?: string | null
  focusTarget?: { lon: number; lat: number } | null
}>()
const emit = defineEmits<{ (e: 'select', record: ScanRecord): void }>()

const mapEl = ref<HTMLDivElement | null>(null)
const map = shallowRef<any>(null)
const amap = shallowRef<any>(null)
let markers: any[] = []
const error = ref('')

function clearMarkers() {
  if (map.value && markers.length) map.value.remove(markers)
  markers = []
}

function render() {
  if (!map.value || !amap.value) return
  clearMarkers()
  const A = amap.value
  for (const r of props.records) {
    if (r.lon == null || r.lat == null) continue
    const color = recordColor(r, props.colorMode)
    const isSel = props.selectedId === r.inter_id
    const marker = new A.CircleMarker({
      center: [r.lon, r.lat],
      radius: isSel ? 9 : 5,
      strokeColor: isSel ? '#ffffff' : color,
      strokeWeight: isSel ? 2 : 1,
      fillColor: color,
      fillOpacity: r.has_data ? 0.85 : 0.4,
      cursor: 'pointer',
      zIndex: isSel ? 200 : 100,
    })
    marker.on('click', () => emit('select', r))
    markers.push(marker)
  }
  map.value.add(markers)
}

function focus(lon: number, lat: number) {
  if (map.value) map.value.setZoomAndCenter(16, [lon, lat], false, 800)
}

onMounted(async () => {
  try {
    const A = await loadAmap()
    amap.value = A
    if (mapEl.value) {
      map.value = createMap(mapEl.value, A)
      render()
    }
  } catch (e: any) {
    error.value = e?.message || '地图加载失败'
  }
})

watch(() => [props.records, props.colorMode, props.selectedId], render, { deep: true })
watch(
  () => props.focusTarget,
  (t) => {
    if (t) focus(t.lon, t.lat)
  },
)
</script>

<template>
  <div class="scan-map">
    <div ref="mapEl" class="map-canvas" />
    <div v-if="error" class="map-error">{{ error }}（请检查 VITE_AMAP_KEY）</div>
    <div class="legend">
      <div v-for="item in legendFor(props.colorMode)" :key="item.label" class="legend-row">
        <span class="dot" :style="{ background: item.color }" />
        <span>{{ item.label }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.scan-map {
  position: relative;
  width: 100%;
  height: 100%;
}
.map-canvas {
  width: 100%;
  height: 100%;
}
.map-error {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(192, 57, 43, 0.9);
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 13px;
}
.legend {
  position: absolute;
  left: 12px;
  bottom: 12px;
  background: rgba(2, 8, 16, 0.82);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.9;
}
.legend-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
}
</style>
