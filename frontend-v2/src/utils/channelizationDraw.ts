import * as d3 from 'd3'
import type { CognitionArm, ArmMetric } from '../types/map'
import type { LaneQueueSpec } from './channelizationMetrics'
import { laneQueueKey } from './channelizationMetrics'

/* ── palette (reference schematic style) ── */
const ROAD_FILL = '#4a5060'
const ROAD_EDGE = '#6b7280'
const JUNCTION_FILL = '#363c48'
const JUNCTION_STROKE = '#5a6270'
const MARK_WHITE = '#eef2f8'
const MARK_YELLOW = '#e8c547'
const CURB = '#8b92a0'
const STOP_RED = '#c62828'

const QUEUE_COLORS: Record<string, string> = {
  high: '#e53935',
  medium: '#fb8c00',
  low: '#fdd835',
  none: '#66bb6a',
}

const DIR_COLORS: Record<string, string> = {
  西: '#e53e3e',
  东: '#ed8936',
  南: '#ecc94b',
  北: '#ecc94b',
  东南: '#48bb78',
  西南: '#9f7aea',
  东北: '#38b2ac',
  西北: '#fc8181',
}

const TURN_CODE: Record<string, string> = {
  '11': '直',
  '12': '左',
  '13': '右',
  '22': '调',
  '31': '直',
  '32': '左',
  '33': '右',
}

type TurnKind = '左' | '直' | '右' | '调'

interface Pt {
  x: number
  y: number
}

function parseTurns(arm: CognitionArm): TurnKind[] {
  const laneCount = arm.lane_num || arm.lanes?.length || 3
  if (arm.lanes?.length) {
    return arm.lanes.map((l) => normalizeTurn(l.turn_move))
  }
  const raw = arm.turn_move || arm.lane_info || ''
  if (!raw) return Array.from({ length: laneCount }, () => '直')
  const parts = raw.split(/[|,，]/).map((p) => normalizeTurn(p.trim()))
  if (parts.length >= laneCount) return parts.slice(0, laneCount) as TurnKind[]
  return [...parts, ...Array.from({ length: laneCount - parts.length }, () => '直' as TurnKind)]
}

function normalizeTurn(raw: string): TurnKind {
  const t = String(raw || '').trim()
  if (TURN_CODE[t]) return TURN_CODE[t] as TurnKind
  if (t.includes('左')) return '左'
  if (t.includes('右')) return '右'
  if (t.includes('调') || t.includes('U')) return '调'
  if (t.includes('直')) return '直'
  return '直'
}

function armBearing(arm: CognitionArm): number {
  if (arm.entrance_angle != null) return arm.entrance_angle
  const map: Record<string, number> = { 北: 0, 东: 90, 南: 180, 西: 270 }
  return map[arm.dir4_label] ?? 0
}

function metricForArm(arm: CognitionArm, metrics: ArmMetric[]): ArmMetric | undefined {
  return metrics.find((m) => m.link_id === arm.link_id || m.dir4_label === arm.dir4_label)
}

function levelForSat(sat: number | null | undefined): string {
  if (sat == null) return 'unknown'
  if (sat >= 0.85) return 'high'
  if (sat >= 0.65) return 'medium'
  return 'low'
}

function vehicleColorFromSpec(spec: LaneQueueSpec | undefined, fallback: string): string {
  if (!spec || spec.colorLevel === 'none') return fallback
  return QUEUE_COLORS[spec.colorLevel] ?? fallback
}

function vehicleColor(
  arm: CognitionArm,
  sat: number | null | undefined,
  showMetrics: boolean,
): string {
  if (showMetrics && sat != null) return QUEUE_COLORS[levelForSat(sat)] ?? QUEUE_COLORS.none
  return DIR_COLORS[arm.dir4_label] ?? '#718096'
}

/** outward from center = negative Y in arm-local SVG */
function rotPt(x: number, y: number, deg: number): Pt {
  const r = (deg * Math.PI) / 180
  return {
    x: x * Math.cos(r) - y * Math.sin(r),
    y: x * Math.sin(r) + y * Math.cos(r),
  }
}

function armCorners(
  cx: number,
  cy: number,
  bearing: number,
  halfW: number,
  yInner: number,
  yOuter: number,
): Pt[] {
  const tl = rotPt(-halfW, yInner, bearing)
  const tr = rotPt(halfW, yInner, bearing)
  const br = rotPt(halfW, yOuter, bearing)
  const bl = rotPt(-halfW, yOuter, bearing)
  return [
    { x: cx + tl.x, y: cy + tl.y },
    { x: cx + tr.x, y: cy + tr.y },
    { x: cx + br.x, y: cy + br.y },
    { x: cx + bl.x, y: cy + bl.y },
  ]
}

function polyPath(pts: Pt[]): string {
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') + ' Z'
}

function drawJunctionHub(
  root: d3.Selection<SVGGElement, unknown, null, undefined>,
  cx: number,
  cy: number,
  arms: CognitionArm[],
  innerR: number,
) {
  const sorted = [...arms].sort((a, b) => armBearing(a) - armBearing(b))
  if (sorted.length < 2) {
    root
      .append('circle')
      .attr('cx', cx)
      .attr('cy', cy)
      .attr('r', innerR)
      .attr('fill', JUNCTION_FILL)
      .attr('stroke', JUNCTION_STROKE)
      .attr('stroke-width', 1.5)
    return
  }

  const hubPts: Pt[] = []
  for (let i = 0; i < sorted.length; i++) {
    const bearing = armBearing(sorted[i])
    const prev = armBearing(sorted[(i - 1 + sorted.length) % sorted.length])
    let delta = bearing - prev
    if (delta < 0) delta += 360
    const bisect = prev + delta / 2
    const p = rotPt(0, -innerR * 0.92, bisect)
    hubPts.push({ x: cx + p.x, y: cy + p.y })
  }

  root
    .append('path')
    .attr('d', polyPath(hubPts))
    .attr('fill', JUNCTION_FILL)
    .attr('stroke', JUNCTION_STROKE)
    .attr('stroke-width', 1.5)
    .attr('stroke-linejoin', 'round')
}

function drawZebra(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  halfW: number,
  yStart: number,
  depth: number,
  scale: number,
) {
  const stripes = Math.max(5, Math.floor((halfW * 2) / (5 * scale)))
  const stripeW = (halfW * 2) / stripes
  for (let i = 0; i < stripes; i += 2) {
    g.append('rect')
      .attr('x', -halfW + i * stripeW)
      .attr('y', yStart)
      .attr('width', stripeW * 0.85)
      .attr('height', depth)
      .attr('fill', MARK_WHITE)
      .attr('opacity', 0.92)
  }
}

function drawTurnArrow(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  turn: TurnKind,
  x: number,
  y: number,
  scale: number,
) {
  const s = scale
  const arrow = g.append('g').attr('transform', `translate(${x},${y})`)
  const stroke = MARK_WHITE
  const sw = 1.4 * s

  if (turn === '直') {
    arrow
      .append('path')
      .attr(
        'd',
        `M 0,${6 * s} L 0,${-5 * s} M ${-4 * s},${-1 * s} L 0,${-5 * s} L ${4 * s},${-1 * s}`,
      )
      .attr('fill', 'none')
      .attr('stroke', stroke)
      .attr('stroke-width', sw)
      .attr('stroke-linecap', 'round')
      .attr('stroke-linejoin', 'round')
  } else if (turn === '左') {
    arrow
      .append('path')
      .attr(
        'd',
        `M ${3 * s},${5 * s} L ${3 * s},${0} Q ${3 * s},${-6 * s} ${-4 * s},${-6 * s} M ${-7 * s},${-6 * s} L ${-4 * s},${-6 * s} L ${-4 * s},${-9 * s}`,
      )
      .attr('fill', 'none')
      .attr('stroke', stroke)
      .attr('stroke-width', sw)
      .attr('stroke-linecap', 'round')
      .attr('stroke-linejoin', 'round')
  } else if (turn === '右') {
    arrow
      .append('path')
      .attr(
        'd',
        `M ${-3 * s},${5 * s} L ${-3 * s},${0} Q ${-3 * s},${-6 * s} ${4 * s},${-6 * s} M ${7 * s},${-6 * s} L ${4 * s},${-6 * s} L ${4 * s},${-9 * s}`,
      )
      .attr('fill', 'none')
      .attr('stroke', stroke)
      .attr('stroke-width', sw)
      .attr('stroke-linecap', 'round')
      .attr('stroke-linejoin', 'round')
  } else {
    arrow
      .append('path')
      .attr(
        'd',
        `M ${-4 * s},${4 * s} Q 0,${-2 * s} ${4 * s},${4 * s} M ${-2 * s},${2 * s} L ${-4 * s},${4 * s} L ${-6 * s},${2 * s}`,
      )
      .attr('fill', 'none')
      .attr('stroke', stroke)
      .attr('stroke-width', sw)
      .attr('stroke-linecap', 'round')
  }
}

function drawVehicles(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  laneX: number,
  laneW: number,
  yStop: number,
  count: number,
  color: string,
  scale: number,
) {
  const vehW = laneW * 0.72
  const vehH = 5.5 * scale
  const gap = 1.8 * scale
  const x = laneX + (laneW - vehW) / 2

  for (let i = 0; i < count; i++) {
    const y = yStop - 8 * scale - i * (vehH + gap)
    g.append('rect')
      .attr('x', x)
      .attr('y', y)
      .attr('width', vehW)
      .attr('height', vehH)
      .attr('rx', 1.2 * scale)
      .attr('fill', color)
      .attr('opacity', 0.88 - (i / count) * 0.15)
      .attr('stroke', 'rgba(0,0,0,0.25)')
      .attr('stroke-width', 0.5)
  }
}

export interface ChannelizationDrawOptions {
  centerX: number
  centerY: number
  scale?: number
  arms: CognitionArm[]
  metricsByArm?: ArmMetric[]
  totalLanes?: number
  showMetrics?: boolean
  highlightDir?: string | null
  /** 高亮转向车道，键为「东:左」 */
  highlightTurnKeys?: string[]
  /** 真实车道排队（link_id:laneIndex → spec） */
  laneQueues?: Map<string, LaneQueueSpec>
  compact?: boolean
  fullscreen?: boolean
}

export function drawChannelization(
  svgEl: SVGSVGElement,
  opts: ChannelizationDrawOptions,
): void {
  const {
    centerX: cx,
    centerY: cy,
    scale = 1,
    arms,
    metricsByArm = [],
    showMetrics = true,
    highlightDir = null,
    highlightTurnKeys = [],
    laneQueues,
    compact = false,
    fullscreen = false,
  } = opts

  const svg = d3.select(svgEl)
  svg.selectAll('*').remove()

  if (fullscreen) {
    svg
      .append('rect')
      .attr('width', '100%')
      .attr('height', '100%')
      .attr('fill', '#1e2430')
    const grid = svg.append('g').attr('opacity', 0.12)
    const step = 28 * scale
    for (let x = 0; x < cx * 2; x += step) {
      grid.append('line').attr('x1', x).attr('y1', 0).attr('x2', x).attr('y2', cy * 2).attr('stroke', '#8899aa')
    }
    for (let y = 0; y < cy * 2; y += step) {
      grid.append('line').attr('x1', 0).attr('y1', y).attr('x2', cx * 2).attr('y2', y).attr('stroke', '#8899aa')
    }
  }

  const laneW = (compact ? 11 : fullscreen ? 20 : 16) * scale
  const laneGap = (compact ? 0.8 : 1.2) * scale
  const shoulder = (compact ? 3 : fullscreen ? 8 : 6) * scale
  const innerR = (compact ? 18 : fullscreen ? 32 : 26) * scale
  const armLen = (compact ? 100 : fullscreen ? 190 : 155) * scale
  const crossDepth = (compact ? 5 : 8) * scale
  const stopW = 2.4 * scale

  const root = svg.append('g').attr('class', 'channel-root')

  /* ── layer 1: road surfaces ── */
  const roadLayer = root.append('g').attr('class', 'road-layer')
  arms.forEach((arm) => {
    const bearing = armBearing(arm)
    const turns = parseTurns(arm)
    const totalW = turns.length * laneW + (turns.length - 1) * laneGap
    const halfW = totalW / 2 + shoulder
    const yInner = -innerR * 0.55
    const yOuter = -(innerR + armLen)
    const corners = armCorners(cx, cy, bearing, halfW, yInner, yOuter)
    const isDim = highlightDir && highlightDir !== arm.dir4_label

    roadLayer
      .append('path')
      .attr('d', polyPath(corners))
      .attr('fill', ROAD_FILL)
      .attr('stroke', ROAD_EDGE)
      .attr('stroke-width', 1)
      .attr('opacity', isDim ? 0.4 : 1)
  })

  drawJunctionHub(root, cx, cy, arms, innerR)

  /* ── layer 2: per-arm markings & traffic ── */
  arms.forEach((arm) => {
    const bearing = armBearing(arm)
    const turns = parseTurns(arm)
    const laneCount = turns.length
    const totalW = laneCount * laneW + (laneCount - 1) * laneGap
    const halfW = totalW / 2
    const metric = metricForArm(arm, metricsByArm)
    const sat = showMetrics ? metric?.saturation : null
    const baseVehColor = vehicleColor(arm, sat ?? null, showMetrics)
    const isHighlight = highlightDir === arm.dir4_label
    const isDim = highlightDir && !isHighlight

    const armG = root
      .append('g')
      .attr('class', `arm-${arm.dir4_label}`)
      .attr('transform', `translate(${cx},${cy}) rotate(${bearing})`)
      .attr('opacity', isDim ? 0.38 : 1)

    const yJunction = -innerR * 0.55
    const yCrossFar = yJunction - crossDepth
    const yStop = yCrossFar - 2 * scale
    const yArrow = yStop - 14 * scale

    /* curb lines */
    armG
      .append('line')
      .attr('x1', -halfW - shoulder * 0.6)
      .attr('y1', yJunction)
      .attr('x2', -halfW - shoulder * 0.6)
      .attr('y2', -(innerR + armLen))
      .attr('stroke', CURB)
      .attr('stroke-width', 1.2 * scale)
    armG
      .append('line')
      .attr('x1', halfW + shoulder * 0.6)
      .attr('y1', yJunction)
      .attr('x2', halfW + shoulder * 0.6)
      .attr('y2', -(innerR + armLen))
      .attr('stroke', CURB)
      .attr('stroke-width', 1.2 * scale)

    /* center double yellow */
    const cyLine = 0
    armG
      .append('line')
      .attr('x1', cyLine - 0.8 * scale)
      .attr('y1', yJunction)
      .attr('x2', cyLine - 0.8 * scale)
      .attr('y2', -(innerR + armLen))
      .attr('stroke', MARK_YELLOW)
      .attr('stroke-width', 1 * scale)
      .attr('opacity', 0.7)
    armG
      .append('line')
      .attr('x1', cyLine + 0.8 * scale)
      .attr('y1', yJunction)
      .attr('x2', cyLine + 0.8 * scale)
      .attr('y2', -(innerR + armLen))
      .attr('stroke', MARK_YELLOW)
      .attr('stroke-width', 1 * scale)
      .attr('opacity', 0.7)

    /* lane dashed dividers */
    for (let i = 1; i < laneCount; i++) {
      const lx = -halfW + i * laneW + (i - 0.5) * laneGap
      armG
        .append('line')
        .attr('x1', lx)
        .attr('y1', yJunction)
        .attr('x2', lx)
        .attr('y2', -(innerR + armLen))
        .attr('stroke', MARK_WHITE)
        .attr('stroke-width', 0.8 * scale)
        .attr('stroke-dasharray', `${5 * scale},${4 * scale}`)
        .attr('opacity', 0.55)
    }

    /* zebra crosswalk */
    drawZebra(armG, halfW + shoulder * 0.3, yCrossFar, crossDepth, scale)

    /* stop line */
    armG
      .append('line')
      .attr('x1', -halfW - shoulder * 0.3)
      .attr('y1', yStop)
      .attr('x2', halfW + shoulder * 0.3)
      .attr('y2', yStop)
      .attr('stroke', STOP_RED)
      .attr('stroke-width', stopW * 1.1)
      .attr('stroke-linecap', 'square')
      .attr('opacity', 0.92)

    turns.forEach((turn, i) => {
      const laneX = -halfW + i * (laneW + laneGap)
      const turnKey = `${arm.dir4_label}:${turn}`
      const turnHit = highlightTurnKeys.includes(turnKey)
      const queueSpec = laneQueues?.get(laneQueueKey(arm.link_id, i))
      const vehColor = vehicleColorFromSpec(queueSpec, baseVehColor)

      if (turnHit) {
        armG
          .append('rect')
          .attr('x', laneX - 1 * scale)
          .attr('y', yArrow - 10 * scale)
          .attr('width', laneW + 2 * scale)
          .attr('height', yStop - yArrow + 18 * scale)
          .attr('rx', 2 * scale)
          .attr('fill', 'rgba(0, 229, 255, 0.14)')
          .attr('stroke', '#00e5ff')
          .attr('stroke-width', 1.8 * scale)
          .attr('stroke-dasharray', `${4 * scale},${3 * scale}`)
      }

      drawTurnArrow(armG, turn, laneX + laneW / 2, yArrow, scale * (compact ? 0.85 : 1))
      const count =
        queueSpec?.vehicleCount ??
        (sat != null ? Math.min(12, Math.max(0, Math.round(sat * 8))) : 0)
      if (count > 0) {
        drawVehicles(armG, laneX, laneW, yStop, count, vehColor, scale)
      }
    })

    if (!compact) {
      armG
        .append('text')
        .attr('x', 0)
        .attr('y', -(innerR + armLen + 20 * scale))
        .attr('text-anchor', 'middle')
        .attr('fill', isHighlight ? '#90cdf4' : '#c5cdd8')
        .attr('font-size', (fullscreen ? 11 : 10) * scale)
        .attr('font-weight', isHighlight ? 700 : 500)
        .text(
          `${arm.dir_label || `${arm.dir4_label}进口`} · ${laneCount}车道`,
        )
    }

    const displaySat = queueSpecForArm(laneQueues, arm, turns.length)?.saturation ?? sat
    if (showMetrics && displaySat != null && !compact) {
      armG
        .append('text')
        .attr('x', halfW + 14 * scale)
        .attr('y', -(innerR + armLen * 0.45))
        .attr('fill', QUEUE_COLORS[levelForSat(displaySat)] ?? '#a0aec0')
        .attr('font-size', 9 * scale)
        .attr('font-family', 'ui-monospace, monospace')
        .text(displaySat.toFixed(2))
    }
  })
}

function queueSpecForArm(
  laneQueues: Map<string, LaneQueueSpec> | undefined,
  arm: CognitionArm,
  laneCount: number,
): LaneQueueSpec | undefined {
  if (!laneQueues) return undefined
  let best: LaneQueueSpec | undefined
  for (let i = 0; i < laneCount; i++) {
    const spec = laneQueues.get(laneQueueKey(arm.link_id, i))
    if (spec && (!best || (spec.saturation ?? 0) > (best.saturation ?? 0))) {
      best = spec
    }
  }
  return best
}
