<script setup lang="ts">
import { computed } from 'vue'

/**
 * 时距图（绿波带示意）。后端当前未透出各路口间距/绝对相位（附录 B），
 * 数据不足时明确降级为「数据暂缺」，仅用已知 cycle / offset 画示意条带（非精确）。
 */
const props = defineProps<{ cycle?: number | null; offsetSec?: number | null }>()

const ok = computed(() => typeof props.cycle === 'number' && props.cycle > 0)
const bands = computed(() => {
  if (!ok.value) return []
  const cyc = props.cycle as number
  const off = props.offsetSec ?? 0
  // 示意：3 个虚拟节点，按 offset 递推形成斜带
  return [0, 1, 2].map((n) => ({
    top: 18 + n * 30,
    x1: 8 + ((off * n) / cyc) * 60,
    x2: 40 + ((off * n) / cyc) * 60,
  }))
})
</script>

<template>
  <div class="tsd" data-testid="timespace-diagram">
    <div v-if="!ok" class="empty">
      时距图数据暂缺<br /><span>（后端未透出节点间距与绝对相位，无法绘制精确绿波带）</span>
    </div>
    <svg v-else viewBox="0 0 100 110" preserveAspectRatio="none" class="tsd__svg">
      <line v-for="g in [0, 25, 50, 75, 100]" :key="g" :x1="g" y1="8" :x2="g" y2="102" class="grid" />
      <polygon
        v-for="(b, i) in bands"
        :key="i"
        :points="`${b.x1},${b.top} ${b.x2},${b.top} ${b.x2 + 22},${b.top + 24} ${b.x1 + 22},${b.top + 24}`"
        class="band"
      />
      <line v-for="(b, i) in bands" :key="'a' + i" x1="4" :y1="b.top + 12" x2="98" :y2="b.top + 12" class="road" />
    </svg>
    <p v-if="ok" class="note">示意绿波（周期 {{ cycle }}s · 相位差 {{ offsetSec ?? 0 }}s），非精确带宽</p>
  </div>
</template>

<style scoped>
.tsd {
  min-height: 120px;
}
.tsd__svg {
  width: 100%;
  height: 130px;
}
.grid {
  stroke: var(--grid-line);
  stroke-width: 0.4;
}
.road {
  stroke: rgba(255, 255, 255, 0.15);
  stroke-width: 0.5;
}
.band {
  fill: rgba(109, 255, 181, 0.28);
  stroke: var(--protected);
  stroke-width: 0.5;
}
.empty {
  text-align: center;
  color: var(--text-mute);
  font-size: 12px;
  padding: 30px 12px;
}
.empty span {
  font-size: 11px;
  color: var(--text-mute);
}
.note {
  margin: 4px 0 0;
  font-size: 10px;
  color: var(--text-mute);
  text-align: center;
}
</style>
