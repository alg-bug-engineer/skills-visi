<script setup lang="ts">
import { computed } from 'vue'
import type { PhaseStageTiming } from '@/api/types'

const props = defineProps<{ stages: PhaseStageTiming[]; cycle?: number }>()

const total = computed(() => {
  const sum = props.stages.reduce(
    (a, s) => a + (s.green_time_s || 0) + (s.yellow_time_s || 0) + (s.all_red_time_s || 0),
    0,
  )
  return props.cycle && props.cycle > 0 ? props.cycle : sum || 1
})

interface Seg {
  name: string
  green: number
  yellow: number
  red: number
  offsetPct: number
  greenPct: number
  yellowPct: number
  redPct: number
}

const segs = computed<Seg[]>(() => {
  let acc = 0
  return props.stages.map((s) => {
    const g = s.green_time_s || 0
    const y = s.yellow_time_s || 0
    const r = s.all_red_time_s || 0
    const seg = {
      name: s.phase_stage_name,
      green: g,
      yellow: y,
      red: r,
      offsetPct: (acc / total.value) * 100,
      greenPct: (g / total.value) * 100,
      yellowPct: (y / total.value) * 100,
      redPct: (r / total.value) * 100,
    }
    acc += g + y + r
    return seg
  })
})
</script>

<template>
  <div class="phase" data-testid="phase-diagram">
    <div v-if="!stages.length" class="empty">相位配时数据暂缺</div>
    <template v-else>
      <div class="phase__row" v-for="(s, i) in segs" :key="i">
        <span class="phase__name">{{ s.name }}</span>
        <div class="phase__track">
          <div class="seg green" :style="{ left: s.offsetPct + '%', width: s.greenPct + '%' }">
            <span v-if="s.greenPct > 8">{{ s.green }}s</span>
          </div>
          <div class="seg yellow" :style="{ left: s.offsetPct + s.greenPct + '%', width: s.yellowPct + '%' }" />
          <div class="seg red" :style="{ left: s.offsetPct + s.greenPct + s.yellowPct + '%', width: s.redPct + '%' }" />
        </div>
      </div>
      <div class="phase__axis"><span>0s</span><span>周期 {{ Math.round(total) }}s</span></div>
    </template>
  </div>
</template>

<style scoped>
.phase {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.phase__row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.phase__name {
  flex: 0 0 84px;
  font-size: 11px;
  color: var(--text-dim);
  text-align: right;
}
.phase__track {
  position: relative;
  flex: 1;
  height: 18px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 4px;
  overflow: hidden;
}
.seg {
  position: absolute;
  top: 0;
  height: 100%;
  display: grid;
  place-items: center;
  font-size: 10px;
  color: #04120a;
}
.seg.green {
  background: var(--protected-2);
}
.seg.yellow {
  background: var(--evidence);
}
.seg.red {
  background: var(--alarm);
}
.phase__axis {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--text-mute);
  padding-left: 92px;
}
.empty {
  font-size: 12px;
  color: var(--text-mute);
  padding: 12px;
  text-align: center;
}
</style>
