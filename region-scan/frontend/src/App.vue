<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import ScanMap from './components/ScanMap.vue'
import IntersectionPanel from './components/IntersectionPanel.vue'
import PilotRank from './components/PilotRank.vue'
import { fetchPilots, fetchRun, fetchRuns } from './api/scan'
import { METRIC_LABELS } from './utils/scanColors'
import type { ColorMode, RunSummary, ScanRecord } from './types/scan'

const runs = ref<RunSummary[]>([])
const runId = ref<string>('')
const periods = ref<string[]>([])
const period = ref<string>('')
const colorMode = ref<ColorMode>('band')
const records = ref<ScanRecord[]>([])
const pilots = ref<ScanRecord[]>([])
const selected = ref<ScanRecord | null>(null)
const focusTarget = ref<{ lon: number; lat: number } | null>(null)
const loading = ref(false)
const errorMsg = ref('')

const colorModes: ColorMode[] = ['band', 'saturation_max', 'unbalance_index', 'green_utilization']

const periodRecords = computed(() =>
  period.value ? records.value.filter((r) => r.period === period.value) : records.value,
)

async function loadRun() {
  if (!runId.value) return
  loading.value = true
  errorMsg.value = ''
  try {
    const detail = await fetchRun(runId.value)
    records.value = detail.records
    periods.value = detail.periods
    if (!period.value || !detail.periods.includes(period.value)) {
      period.value = detail.periods[0] ?? ''
    }
    const pr = await fetchPilots(runId.value, period.value)
    pilots.value = pr.pilots
    selected.value = null
  } catch (e: unknown) {
    errorMsg.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function refreshPilots() {
  if (!runId.value) return
  const pr = await fetchPilots(runId.value, period.value)
  pilots.value = pr.pilots
}

function onSelect(r: ScanRecord) {
  selected.value = r
}

function onLocate(r: ScanRecord) {
  selected.value = r
  if (r.lon != null && r.lat != null) focusTarget.value = { lon: r.lon, lat: r.lat }
}

watch(period, refreshPilots)

onMounted(async () => {
  try {
    runs.value = await fetchRuns()
    if (runs.value.length) {
      runId.value = runs.value[0].run_id
      await loadRun()
    } else {
      errorMsg.value = '暂无扫描快照，请先运行 python -m region_scan.cli scan'
    }
  } catch (e: unknown) {
    errorMsg.value = e instanceof Error ? e.message : '无法连接扫描 API'
  }
})
</script>

<template>
  <div class="app">
    <aside class="left">
      <PilotRank :pilots="pilots" :selected-id="selected?.inter_id" @locate="onLocate" />
    </aside>

    <main class="center">
      <div class="toolbar">
        <div class="brand">区域路口体检 · 试点选择</div>
        <select v-model="runId" @change="loadRun">
          <option v-for="r in runs" :key="r.run_id" :value="r.run_id">
            {{ r.run_id }}（{{ r.covered }}/{{ r.intersection_total }}）
          </option>
        </select>
        <select v-model="period">
          <option v-for="p in periods" :key="p" :value="p">{{ p }}</option>
        </select>
        <div class="modes">
          <button
            v-for="m in colorModes"
            :key="m"
            :class="{ on: colorMode === m }"
            @click="colorMode = m"
          >
            {{ METRIC_LABELS[m] }}
          </button>
        </div>
        <span v-if="loading" class="hint">加载中…</span>
        <span v-if="errorMsg" class="err">{{ errorMsg }}</span>
      </div>
      <div class="map-wrap">
        <ScanMap
          :records="periodRecords"
          :color-mode="colorMode"
          :selected-id="selected?.inter_id"
          :focus-target="focusTarget"
          @select="onSelect"
        />
      </div>
    </main>

    <aside class="right">
      <IntersectionPanel :record="selected" />
    </aside>
  </div>
</template>

<style scoped>
.app {
  display: grid;
  grid-template-columns: 300px 1fr 360px;
  height: 100%;
}
.left,
.right {
  background: #0a121d;
  border-left: 1px solid rgba(255, 255, 255, 0.08);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  overflow: hidden;
}
.center {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: #0a121d;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-wrap: wrap;
}
.brand {
  font-weight: 700;
  font-size: 15px;
}
.toolbar select {
  background: #111c2b;
  color: #e6edf3;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  padding: 5px 8px;
}
.modes {
  display: flex;
  gap: 4px;
}
.modes button {
  background: #111c2b;
  color: #9fb0c3;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 12px;
}
.modes button.on {
  background: #2f9bff;
  color: #fff;
  border-color: #2f9bff;
}
.hint {
  color: #8b97a7;
}
.err {
  color: #ff9b8e;
  font-size: 12px;
}
.map-wrap {
  flex: 1;
  min-height: 0;
}
</style>
