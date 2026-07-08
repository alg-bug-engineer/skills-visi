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

// 时距图绘图区（带边距，为坐标轴刻度/路口标签留白）
const PLOT = { x0: 96, x1: 304, y0: 18, y1: 150 } as const

type Row = CoordinationNode & { y: number; x: number | null; dist: number }

/**
 * 标准时距图：纵轴＝沿干线累计真实间距（m），横轴＝一个公共周期内的相位时间（s）。
 * 各路口按 offset_abs_s 落点；缺 spacing 时退化为按索引等距排布（不合成距离数值，仅决定绘图位置）。
 */
const layout = computed(() => {
  const list = nodes.value
  if (!list.length) return { rows: [] as Row[], hasOffset: false }

  let cumulative = 0
  const distances = list.map((n) => {
    const d = cumulative
    cumulative += Math.max(n.spacing_m ?? 0, 0)
    return d
  })
  const maxDist = cumulative
  const cyc = cycle.value && cycle.value > 0 ? cycle.value : null
  const span = list.length > 1 ? list.length - 1 : 1

  let hasOffset = false
  const rows: Row[] = list.map((n, i) => {
    // 有真实间距按累计距离布点；否则按索引等距（仅用于绘图布局）
    const frac = maxDist > 0 ? distances[i] / maxDist : i / span
    const y = PLOT.y0 + frac * (PLOT.y1 - PLOT.y0)
    let x: number | null = null
    if (cyc && typeof n.offset_abs_s === 'number') {
      hasOffset = true
      const phase = (((n.offset_abs_s % cyc) + cyc) % cyc) / cyc
      x = PLOT.x0 + phase * (PLOT.x1 - PLOT.x0)
    }
    return { ...n, y, x, dist: distances[i] }
  })
  return { rows, hasOffset }
})

// 横轴（相位时间）刻度：0 / ¼ / ½ / ¾ / 满周期
const xTicks = computed(() => {
  const cyc = cycle.value && cycle.value > 0 ? cycle.value : null
  if (!cyc) return [] as Array<{ x: number; label: string }>
  return [0, 0.25, 0.5, 0.75, 1].map((f) => ({
    x: PLOT.x0 + f * (PLOT.x1 - PLOT.x0),
    label: `${Math.round(cyc * f)}s`,
  }))
})

const hasDistance = computed(() => layout.value.rows.some((r) => r.dist > 0))

const offsetPolyline = computed(() =>
  layout.value.rows
    .filter((r) => r.x !== null)
    .map((r) => `${r.x},${r.y}`)
    .join(' '),
)

function roleLabel(role: string): string {
  return role === 'upstream' ? '上游' : role === 'downstream' ? '下游' : '目标'
}

const SOURCE_LABELS: Record<string, string> = {
  link_geom: '路段几何(间距)',
  pg_signal: '信号配时(绝对相位)',
  link_speed: '路段车速',
  line_index: '路段车速',
}

const sourceLabel = computed(() => {
  const raw = props.coordination?.source
  if (!raw) return null
  return raw
    .split('+')
    .map((token) => SOURCE_LABELS[token.trim()] || token.trim())
    .join(' · ')
})
</script>

<template>
  <div class="coord" data-testid="coordination-diagram">
    <template v-if="available">
      <div class="coord__meta">
        <span>{{ directionLabel[coordination?.direction ?? 'unknown'] }}</span>
        <span v-if="cycle">公共信号周期 {{ cycle }}s</span>
        <span v-if="sourceLabel" class="src">数据来源：{{ sourceLabel }}</span>
      </div>

      <p class="coord__intro">
        <b>时距图</b>：纵轴为沿干线的累计间距（上游→目标→下游），横轴为一个公共信号周期内的<b>相位时间</b>。每个圆点是该路口的绿灯起始相位，<b>连线的倾斜度＝车队在相邻路口间的相位推进</b>——连线越接近车队行程时间对应的斜率，越易形成绿波、减少停车。
      </p>

      <svg viewBox="0 0 320 176" class="coord__svg" role="img" aria-label="干线协调时距图">
        <!-- 绘图区边框 -->
        <rect
          :x="96" :y="18" :width="304 - 96" :height="150 - 18"
          class="frame"
        />
        <!-- 横轴刻度：相位时间 -->
        <template v-for="tk in xTicks" :key="'x' + tk.label">
          <line :x1="tk.x" :y1="18" :x2="tk.x" :y2="150" class="grid-v" />
          <text :x="tk.x" :y="164" class="tick tick--x">{{ tk.label }}</text>
        </template>
        <!-- 每个路口一条参考横线 + 名称 + 累计间距 -->
        <template v-for="r in layout.rows" :key="'g' + r.inter_id">
          <line :x1="96" :y1="r.y" :x2="304" :y2="r.y" class="road" />
          <text :x="92" :y="r.y - 3" class="tick tick--node" text-anchor="end">
            {{ roleLabel(r.role) }}·{{ r.inter_name ?? r.inter_id ?? '—' }}
          </text>
          <text v-if="hasDistance" :x="92" :y="r.y + 8" class="tick tick--dist" text-anchor="end">
            累计 {{ Math.round(r.dist) }}m
          </text>
        </template>
        <!-- 协调折线（相位推进）+ 相位落点 -->
        <polyline v-if="layout.hasOffset" :points="offsetPolyline" class="band" />
        <template v-for="r in layout.rows" :key="'p' + r.inter_id">
          <circle v-if="r.x !== null" :cx="r.x" :cy="r.y" r="3" class="dot" :class="{ target: r.role === 'target' }" />
        </template>
        <!-- 轴标题 -->
        <text :x="200" :y="174" class="axis-title">相位时间（一个周期）</text>
      </svg>
      <p v-if="!layout.hasOffset" class="coord__hint">缺少各路口绝对相位（offset），暂不绘制相位落点，仅列出可用字段。</p>

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
.coord__intro {
  margin: 0 0 6px;
  color: var(--text-dim);
  font-size: 11px;
  line-height: 1.5;
}
.coord__intro b {
  color: var(--text);
  font-weight: 600;
}
.coord__svg {
  width: 100%;
  height: auto;
  display: block;
}
.frame {
  fill: rgba(255, 255, 255, 0.015);
  stroke: rgba(146, 161, 181, 0.28);
  stroke-width: 0.6;
}
.grid-v {
  stroke: rgba(146, 161, 181, 0.16);
  stroke-width: 0.5;
  stroke-dasharray: 2 2;
}
.road {
  stroke: rgba(255, 255, 255, 0.14);
  stroke-width: 0.6;
}
.band {
  fill: none;
  stroke: var(--protected);
  stroke-width: 1.6;
  stroke-linejoin: round;
  stroke-linecap: round;
}
.dot {
  fill: var(--protected);
  stroke: rgba(4, 13, 24, 0.9);
  stroke-width: 0.8;
}
.dot.target {
  fill: var(--primary);
  r: 3.6;
}
.tick {
  fill: var(--text-mute);
  font-size: 7px;
}
.tick--node {
  fill: var(--text-dim);
  font-size: 7.2px;
  font-weight: 600;
}
.tick--dist {
  fill: var(--text-mute);
  font-size: 6.4px;
}
.tick--x {
  text-anchor: middle;
}
.axis-title {
  fill: var(--text-mute);
  font-size: 7px;
  text-anchor: middle;
}
.coord__hint {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--text-mute);
  line-height: 1.4;
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
