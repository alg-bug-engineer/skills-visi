<script setup lang="ts">
import { computed } from 'vue'
import type { Coordination, CoordinationNode } from '@/api/types'

/**
 * 干线协调时距图。仅消费后端真实 `diagnosis.coordination.nodes`
 * （间距 dim_link_info.length_m / 绝对相位 plan_cfg.offset_sec / 真实路段速度）。
 * 缺字段即降级为文字提示，严禁在客户端合成节点/折线/相位（docs/rule.md 约束19）。
 */
const props = defineProps<{ coordination?: Coordination | null }>()

const available = computed(() => Boolean(props.coordination?.available))
const nodes = computed<CoordinationNode[]>(() => props.coordination?.nodes ?? [])
const cycle = computed(() => props.coordination?.cycle_s ?? null)

const directionLabel: Record<string, string> = {
  inbound: '来向协调（上游→目标）',
  outbound: '去向协调（目标→下游）',
  bidirectional: '双向协调',
  unknown: '方向未知',
}

// 以累计间距为纵轴（真实 spacing_m），按上游→目标→下游排布
const layout = computed(() => {
  const list = nodes.value
  if (!list.length) return { rows: [] as Array<CoordinationNode & { y: number; x: number | null }>, hasOffset: false }
  let cumulative = 0
  const distances = list.map((n) => {
    const d = cumulative
    cumulative += Math.max(n.spacing_m ?? 0, 0)
    return d
  })
  const maxDist = Math.max(cumulative, 1)
  const cyc = cycle.value && cycle.value > 0 ? cycle.value : null
  let hasOffset = false
  const rows = list.map((n, i) => {
    const y = 10 + (distances[i] / maxDist) * 80
    let x: number | null = null
    if (cyc && typeof n.offset_abs_s === 'number') {
      hasOffset = true
      x = 6 + ((((n.offset_abs_s % cyc) + cyc) % cyc) / cyc) * 88
    }
    return { ...n, y, x }
  })
  return { rows, hasOffset }
})

const offsetPolyline = computed(() =>
  layout.value.rows
    .filter((r) => r.x !== null)
    .map((r) => `${r.x},${r.y}`)
    .join(' '),
)

function roleLabel(role: string): string {
  return role === 'upstream' ? '上游' : role === 'downstream' ? '下游' : '目标'
}
</script>

<template>
  <div class="coord" data-testid="coordination-diagram">
    <template v-if="available">
      <div class="coord__meta">
        <span>{{ directionLabel[coordination?.direction ?? 'unknown'] }}</span>
        <span v-if="cycle">周期 {{ cycle }}s</span>
        <span v-if="coordination?.source" class="src">来源 {{ coordination.source }}</span>
      </div>

      <svg viewBox="0 0 100 100" preserveAspectRatio="none" class="coord__svg">
        <line v-for="r in layout.rows" :key="'g' + r.inter_id" x1="4" :y1="r.y" x2="98" :y2="r.y" class="road" />
        <polyline v-if="layout.hasOffset" :points="offsetPolyline" class="band" />
        <template v-for="r in layout.rows" :key="'p' + r.inter_id">
          <circle v-if="r.x !== null" :cx="r.x" :cy="r.y" r="1.6" class="dot" />
        </template>
      </svg>

      <ul class="coord__nodes">
        <li v-for="n in nodes" :key="'n' + n.inter_id" :class="{ target: n.role === 'target' }">
          <span class="nm">{{ roleLabel(n.role) }} · {{ n.inter_name ?? n.inter_id ?? '—' }}</span>
          <span class="fields">
            <b v-if="n.spacing_m">间距 {{ Math.round(n.spacing_m) }}m</b>
            <b v-if="n.offset_abs_s !== null">相位 {{ n.offset_abs_s }}s</b>
            <b v-if="n.phase_diff_s !== null">相位差 {{ n.phase_diff_s > 0 ? '+' : '' }}{{ n.phase_diff_s }}s</b>
            <b v-if="n.travel_time_s !== null">行程 {{ n.travel_time_s }}s</b>
            <b v-if="n.travel_speed_kmh !== null">{{ n.travel_speed_kmh }}km/h</b>
          </span>
        </li>
      </ul>
    </template>

    <p v-else class="coord__note">
      {{ coordination?.reason ? `暂不绘制协调图：${coordination.reason}` : '后端未返回协调数据，暂不绘制协调图。' }}
    </p>
  </div>
</template>

<style scoped>
.coord {
  min-height: 80px;
}
.coord__meta {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--text-mute);
  margin-bottom: 6px;
}
.coord__meta .src {
  color: var(--text-dim);
}
.coord__svg {
  width: 100%;
  height: 120px;
}
.road {
  stroke: rgba(255, 255, 255, 0.16);
  stroke-width: 0.5;
}
.band {
  fill: none;
  stroke: var(--protected);
  stroke-width: 0.8;
}
.dot {
  fill: var(--protected);
}
.coord__nodes {
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
}
.coord__nodes li {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid rgba(146, 161, 181, 0.18);
  font-size: 11.5px;
  color: var(--text-dim);
}
.coord__nodes li.target .nm {
  color: var(--text);
}
.coord__nodes .fields {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.coord__nodes .fields b {
  font-weight: 500;
  color: var(--text-mute);
}
.coord__note {
  border: 1px solid rgba(146, 161, 181, 0.35);
  background: rgba(255, 255, 255, 0.03);
  padding: 12px;
  color: var(--text-dim);
  font-size: 12.5px;
  line-height: 1.5;
  margin: 0;
}
</style>
